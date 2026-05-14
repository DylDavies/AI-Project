import random
import chess
import chess.engine
from reconchess import Player, Color, WinReason, GameHistory, utilities
from observer import NullObserver


class MyGoat(Player):
    def __init__(self, observer=None):
        self.engine = chess.engine.SimpleEngine.popen_uci('./stockfish.exe', setpgrp=True)
        self.possible_states: set[str] = set()
        self.color: Color | None = None
        self._obs = observer if observer is not None else NullObserver()

    def handle_game_start(self, color: Color, board: chess.Board, opponent_name: str):
        self.color = color
        self.possible_states = {board.fen()}
        self._obs.on_game_start(color, opponent_name, board.fen())

    def handle_opponent_move_result(self, captured_my_piece: bool, capture_square: chess.Square):
        before = len(self.possible_states)
        new_states: set[str] = set()

        for fen in self.possible_states:
            board = chess.Board(fen)
            board.turn = not self.color

            for move in self._get_legal_moves(board):
                if captured_my_piece:
                    if move.to_square != capture_square:
                        continue
                    if board.piece_at(move.to_square) is None or board.piece_at(move.to_square).color != self.color:
                        continue
                else:
                    if (move != chess.Move.null()
                            and board.piece_at(move.to_square) is not None
                            and board.piece_at(move.to_square).color == self.color):
                        continue

                new_board = board.copy()
                new_board.push(move)
                new_states.add(new_board.fen())

        if len(new_states) > 1500:
            new_states = set(random.sample(list(new_states), 1500))
        self.possible_states = new_states
        rep_fen = next(iter(self.possible_states), chess.STARTING_FEN)
        self._obs.on_opponent_move(before, len(self.possible_states), captured_my_piece, rep_fen)

    def choose_sense(self, sense_actions: list[chess.Square], move_actions: list[chess.Move], seconds_left: float) -> chess.Square:
        interior = [s for s in sense_actions
                    if 1 <= chess.square_file(s) <= 6 and 1 <= chess.square_rank(s) <= 6]
        if not interior:
            interior = sense_actions

        states = list(self.possible_states)
        total = len(states)

        if total <= 1:
            choice = random.choice(interior)
            self._obs.on_sense_chosen(choice, float(total), total)
            return choice

        # Pre-compute 3x3 windows for each candidate center.
        windows = {
            center: [
                chess.square(chess.square_file(center) + df, chess.square_rank(center) + dr)
                for dr in (-1, 0, 1) for df in (-1, 0, 1)
            ]
            for center in interior
        }

        # Parse each board once and build fingerprints for every candidate center.
        # fingerprints[center][i] = piece-pattern tuple for board i at that center's window.
        fingerprints: dict[chess.Square, list[tuple]] = {c: [] for c in interior}
        for fen in states:
            board = chess.Board(fen)
            for center in interior:
                fingerprints[center].append(tuple(
                    p.symbol() if (p := board.piece_at(sq)) else None
                    for sq in windows[center]
                ))

        # 2-step lookahead:
        # score(s1) = (1/total) * sum over s1-partitions of  min_s2( sum(c^2) over s2-sub-partitions )
        #
        # This equals the expected states remaining after sensing s1, then optimally choosing s2
        # on the next turn — without any further information about the opponent's move.
        # It is provably tighter than the 1-step greedy and only costs O(36^2 * N) after pre-computation.
        best_square = interior[0]
        best_score = float('inf')

        for s1 in interior:
            # Group board indices by their fingerprint at s1.
            groups: dict[tuple, list[int]] = {}
            for i, fp in enumerate(fingerprints[s1]):
                groups.setdefault(fp, []).append(i)

            score_s1 = 0.0
            for group_indices in groups.values():
                # For this observation sub-group, find the s2 that minimises sum(c^2).
                best_sumsq = float('inf')
                for s2 in interior:
                    sub_counts: dict[tuple, int] = {}
                    for i in group_indices:
                        fp2 = fingerprints[s2][i]
                        sub_counts[fp2] = sub_counts.get(fp2, 0) + 1
                    sumsq = sum(c * c for c in sub_counts.values())
                    if sumsq < best_sumsq:
                        best_sumsq = sumsq
                score_s1 += best_sumsq

            score_s1 /= total

            if score_s1 < best_score:
                best_score = score_s1
                best_square = s1

        self._obs.on_sense_chosen(best_square, best_score, total)
        return best_square

    def handle_sense_result(self, sense_result: list[tuple[chess.Square, chess.Piece]]):
        before = len(self.possible_states)
        new_states: set[str] = set()

        for fen in self.possible_states:
            board = chess.Board(fen)
            if all(board.piece_at(sq) == piece for sq, piece in sense_result):
                new_states.add(fen)

        self.possible_states = new_states
        rep_fen = next(iter(self.possible_states), chess.STARTING_FEN)
        self._obs.on_sense_result(before, len(self.possible_states), rep_fen)

    def choose_move(self, move_actions: list[chess.Move], seconds_left: float) -> chess.Move:
        if len(self.possible_states) > 1500:
            self.possible_states = set(random.sample(list(self.possible_states), 1500))

        N = len(self.possible_states)
        if N == 0:
            return random.choice(move_actions)

        time_limit = 10.0 / N
        move_votes: dict[str, int] = {}

        for fen in self.possible_states:
            board = chess.Board(fen)
            board.turn = self.color
            chosen_move = None

            enemy_king_sq = board.king(not self.color)
            if enemy_king_sq is not None:
                attackers = board.attackers(self.color, enemy_king_sq)
                if attackers:
                    chosen_move = chess.Move(attackers.pop(), enemy_king_sq)

            if chosen_move is None:
                try:
                    board.clear_stack()
                    result = self.engine.play(board, chess.engine.Limit(time=time_limit))
                    if result.move is not None:
                        chosen_move = result.move
                except Exception:
                    pass

            if chosen_move is not None:
                uci = chosen_move.uci()
                move_votes[uci] = move_votes.get(uci, 0) + 1

        if not move_votes:
            return random.choice(move_actions)

        max_votes = max(move_votes.values())
        best_uci = sorted(m for m, v in move_votes.items() if v == max_votes)[0]

        rep_fen = next(iter(self.possible_states), chess.STARTING_FEN)
        self._obs.on_move_chosen(best_uci, max_votes, N, rep_fen)
        return chess.Move.from_uci(best_uci)

    def handle_move_result(self, requested_move: chess.Move, taken_move: chess.Move, captured_opponent_piece: bool, capture_square: chess.Square):
        new_states: set[str] = set()
        move = taken_move if taken_move is not None else chess.Move.null()

        for fen in self.possible_states:
            board = chess.Board(fen)
            board.turn = self.color
            try:
                board.push(move)
                new_states.add(board.fen())
            except Exception:
                pass

        self.possible_states = new_states

    def handle_game_end(self, winner_color: Color, win_reason: WinReason, game_history: GameHistory):
        self._obs.on_game_end(winner_color)
        try:
            self.engine.quit()
        except Exception:
            pass

    def _get_legal_moves(self, board: chess.Board) -> list[chess.Move]:
        moves = list(board.generate_pseudo_legal_moves())
        for move in utilities.without_opponent_pieces(board).generate_castling_moves():
            if not utilities.is_illegal_castle(board, move):
                moves.append(move)
        moves.append(chess.Move.null())
        return moves
