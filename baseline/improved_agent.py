import random
import time
import chess
import chess.engine
from collections import Counter
from reconchess import Player, Color, WinReason, GameHistory, utilities

DEBUG = True
STOCKFISH_PATH = "./stockfish.exe"
MAX_STATES = 1500

# Debugger
def _dbg(msg: str) -> None: 
    if DEBUG:
        print(f"[DBG]: {msg}", flush=True)


class MyGoat(Player):
    """
    Agent class routing logic to logic specific classes
    """
    
    def __init__(self, observer =None):
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH, setpgrp=True)
        except FileNotFoundError:
            # Fallback for automarker if local test path fails
            self.engine = chess.engine.SimpleEngine.popen_uci('/opt/stockfish/stockfish', setpgrp=True)
            
        self.tracker = StateTracker()
        self.sensing = SensingStrategy()
        self.movement = MoveStrategy(self.engine)
        self.observer = observer

    def handle_game_start(self, color: Color, board: chess.Board, opponent_name: str):
        _dbg(f"Game started! Playing as {'WHITE' if color == chess.WHITE else 'BLACK'} against {opponent_name}.")
        self.tracker.initialize(color, board)

        if self.observer:
            self.observer.on_game_start(color, opponent_name, board.fen())


    def handle_opponent_move_result(self, captured_my_piece: bool, capture_square: chess.Square):
        before = len(self.tracker.possible_states)

        self.tracker.update_after_opponent(captured_my_piece, capture_square)

        after = len(self.tracker.possible_states)
        _dbg(f"Opponent moved. States: {before} -> {after} | Captured our piece: {captured_my_piece}")
        
        if self.observer:
            rep_fen = next(iter(self.tracker.possible_states), chess.STARTING_FEN)
            self.observer.on_opponent_move(before, after, captured_my_piece, rep_fen)

    def choose_sense(self, sense_actions: list[chess.Square], move_actions: list[chess.Move], seconds_left: float) -> chess.Square:
        start_time = time.time()
        best_square = self.sensing.get_best_square(self.tracker, sense_actions)
        elapsed = time.time() - start_time
        _dbg(f"Sensing choice '{chess.square_name(best_square)}' took {elapsed:.3f}s. States tracked: {len(self.tracker.possible_states)}")
        
        if self.observer:
            self.observer.on_sense_chosen(best_square, 0, len(self.tracker.possible_states))
            
        return best_square

    def handle_sense_result(self, sense_result: list[tuple[chess.Square, chess.Piece]]):
        before = len(self.tracker.possible_states)
        self.tracker.update_after_sense(sense_result)
        after = len(self.tracker.possible_states)
        _dbg(f"Sense result processed. States: {before} -> {after}")
        
        if self.observer:
            rep_fen = next(iter(self.tracker.possible_states), chess.STARTING_FEN)
            self.observer.on_sense_result(before, after, rep_fen)

    def choose_move(self, move_actions: list[chess.Move], seconds_left: float) -> chess.Move:
        start_time = time.time()
        best_move = self.movement.get_best_move(self.tracker, move_actions)
        elapsed = time.time() - start_time
        _dbg(f"Move choice '{best_move.uci()}' took {elapsed:.3f}s. Seconds left on clock: {seconds_left:.1f}s")
        
        if self.observer:
            rep_fen = next(iter(self.tracker.possible_states), chess.STARTING_FEN)
            self.observer.on_move_chosen(best_move.uci(), 0, len(self.tracker.possible_states), rep_fen)
            
        return best_move

    def handle_move_result(self, requested_move: chess.Move, taken_move: chess.Move, captured_opponent_piece: bool, capture_square: chess.Square):
        self.tracker.update_after_move(requested_move, taken_move, captured_opponent_piece, capture_square)
        _dbg(f"Move executed: {taken_move.uci() if taken_move else 'None'}. Captured opponent: {captured_opponent_piece}")

    def handle_game_end(self, winner_color: Color, win_reason: WinReason, game_history: GameHistory):
        _dbg(f"Game ended! Winner: {winner_color} | Reason: {win_reason}")
        if self.observer:
            self.observer.on_game_end(winner_color)

        try:
            self.engine.quit()
        except Exception:
            pass



class BoardUtils:
    """
    Helper Functions
    """
    
    @staticmethod
    def fast_copy_board(board: chess.Board) -> chess.Board:
        new_board = object.__new__(chess.Board)
        new_board.pawns = board.pawns
        new_board.knights = board.knights
        new_board.bishops = board.bishops
        new_board.rooks = board.rooks
        new_board.queens = board.queens
        new_board.kings = board.kings
        new_board.occupied_co = [*board.occupied_co]
        new_board.occupied = board.occupied
        new_board.promoted = board.promoted
        new_board.chess960 = board.chess960
        new_board.ep_square = board.ep_square
        new_board.castling_rights = board.castling_rights
        new_board.turn = board.turn
        new_board.fullmove_number = board.fullmove_number
        new_board.halfmove_clock = board.halfmove_clock
        new_board.move_stack = []
        new_board._stack = []
        return new_board

    @staticmethod
    def move_heuristic_value(board: chess.Board, move: chess.Move) -> float:
        """
        Heuristic scoring to weight Stockfish votes based on urgency.
        """
        if move == chess.Move.null(): return -2.0
        
        score = 1.0
        piece = board.piece_at(move.from_square)

        # Reward for giving a move that would result in a check
        if board.gives_check(move): score += .5 
        
        # Scaling reward for bishop possible move distance
        if piece and piece.piece_type == chess.BISHOP: score += 0.1 * chess.square_distance(move.from_square, move.to_square) 

        return score

    @staticmethod
    def get_legal_moves(board: chess.Board) -> list[chess.Move]:

        moves = list(board.generate_pseudo_legal_moves())
        for move in utilities.without_opponent_pieces(board).generate_castling_moves():
            if not utilities.is_illegal_castle(board, move):
                moves.append(move)

        moves.append(chess.Move.null())

        return moves
    


class StateTracker:
    """
    Handles State Tracking and management of the "Totality Board"
    """
    
    def __init__(self):
        self.possible_states: set[str] = set()
        self.totality_board: chess.Board = chess.Board() # Representation of what we think the board should look like - serves as the fallback and some ground truth
        self.color = None
        self.last_capture_square = None # Rememer if we got attacked

    def initialize(self, color: Color, board: chess.Board):
        self.color = color
        self.possible_states = { board.fen() }
        self.totality_board = board.copy()

    def update_after_opponent(self, captured_my_piece: bool, capture_square: chess.Square):

        # Update totality board
        if captured_my_piece and capture_square is not None:
            self.totality_board.remove_piece_at(capture_square)

        self.last_capture_square = capture_square if captured_my_piece else None

        # Generate next states based on opponent's possible moves
        new_states = set()
        for fen in self.possible_states:
            board = chess.Board(fen)
            board.turn = not self.color

            for move in BoardUtils.get_legal_moves(board):
                if captured_my_piece:

                    if move.to_square != capture_square: continue

                    if board.piece_at(move.to_square) is None or board.piece_at(move.to_square).color != self.color: continue
                else:
                    if move != chess.Move.null() and board.piece_at(move.to_square) is not None and board.piece_at(move.to_square).color == self.color: continue
                
                new_board = BoardUtils.fast_copy_board(board)
                new_board.push(move)
                new_states.add(new_board.fen())

        self._apply_state_cap(new_states) # we need to minimize the total number of potential states we are taking into account


    def update_after_sense(self, sense_result: list[tuple[chess.Square, chess.Piece]]):
        # Update totality board with absolute truth from sensing
        for square, piece in sense_result:
            self.totality_board.set_piece_at(square, piece)

        # Filter impossible states
        new_states = set()
        for fen in self.possible_states:
            board = chess.Board(fen)

            if all(board.piece_at(sq) == piece for sq, piece in sense_result):
                new_states.add(fen)

        self._apply_state_cap(new_states)


    def update_after_move(self, requested: chess.Move, taken: chess.Move, captured_opp: bool, capture_sq: chess.Square):
        # Update totality board
        taken_move = taken if taken is not None else chess.Move.null()
        self.totality_board.clear_stack()
        try:
            self.totality_board.push(taken_move)
        except Exception:
            pass

        requested_move = requested if requested is not None else chess.Move.null()
        
        # Apply Loopyfish's aggressive Cases I-IV pruning logic
        new_states = set()
        for fen in self.possible_states:
            board = chess.Board(fen)
            board.turn = self.color
            
            # CASE I: Move blocked/illegal
            if requested_move != chess.Move.null() and taken_move == chess.Move.null() and board.is_legal(requested_move):
                continue
            # CASE II: Reality says move is legal, board says it isn't
            if taken_move != chess.Move.null() and not board.is_legal(taken_move):
                continue
            # CASE III: Capture occurred, but board says no capture
            if captured_opp and not board.is_capture(taken_move):
                continue
            # CASE IV: No capture occurred, but board says capture
            if not captured_opp and board.is_capture(taken_move):
                continue
                
            try:
                new_board = BoardUtils.fast_copy_board(board)
                new_board.push(taken_move)
                
                # Check for impossible game states (opponent king missing but game not over)
                if len(list(new_board.pieces(chess.KING, not self.color))) != 1:
                    continue
                    
                new_states.add(new_board.fen())
            except Exception:
                pass
                
        self._apply_state_cap(new_states)

    def _apply_state_cap(self, new_states: set):
        if len(new_states) == 0:
            _dbg("CRITICAL: States dropped to 0. Falling back to Totality Board.")
            self.possible_states = {self.totality_board.fen()}
        elif len(new_states) > MAX_STATES:
            self.possible_states = set(random.sample(list(new_states), MAX_STATES))
        else:
            self.possible_states = new_states


class SensingStrategy:
    """
    Decides where to look based on game phase and threats
    """
    
    def __init__(self):
        self.turn_number = 0

    def get_best_square(self, tracker: StateTracker, sense_actions: list[chess.Square]) -> chess.Square:
        self.turn_number += 1
        
       # Scripting opening Radar
        if self.turn_number <= 3:
            return self._get_opening_sense(tracker.color)
            
        # Threat detection and 2 step lookahead
        interior = [s for s in sense_actions if 1 <= chess.square_file(s) <= 6 and 1 <= chess.square_rank(s) <= 6]
        if not interior:
            interior = sense_actions
            
        return self._get_entropy_sense_with_mask(tracker, interior)

    def _get_opening_sense(self, color: Color) -> chess.Square:
        # Scan the middle of the board - offset by 1 to see if a knight has moved
        if color == chess.WHITE:
            if self.turn_number == 1: return chess.D5 # Center pawns
            if self.turn_number == 2: return chess.C5 # Queenside
            if self.turn_number == 3: return chess.F5 # Kingside
        else:
            if self.turn_number == 1: return chess.D4
            if self.turn_number == 2: return chess.C4
            if self.turn_number == 3: return chess.F4
        return chess.D4 # Fallback

    # Mask our backrank to avoid sensing there
    def _get_entropy_sense_with_mask(self, tracker: StateTracker, interior: list[chess.Square]) -> chess.Square:
        states = list(tracker.possible_states)
        total = len(states)
        
        if total <= 1:
            return random.choice(interior)

        windows = {
            center: [
                chess.square(chess.square_file(center) + df, chess.square_rank(center) + dr)
                for dr in (-1, 0, 1) for df in (-1, 0, 1)
            ]
            for center in interior
        }

        # Only penalize if we are staring at our OWN back two ranks.
        back_ranks = [0, 1] if tracker.color == chess.WHITE else [6, 7]
        own_piece_counts = {}
        for center in interior:
            penalty = 0
            for sq in windows[center]:

                # If the square is in our back rank AND contains our piece, add penalty
                if chess.square_rank(sq) in back_ranks:
                    piece = tracker.totality_board.piece_at(sq)
                    if piece and piece.color == tracker.color:
                        penalty += 10
            own_piece_counts[center] = penalty

        fingerprints = {c: [] for c in interior}
        for fen in states:
            board = chess.Board(fen)
            for center in interior:
                fingerprints[center].append(tuple(
                    p.symbol() if (p := board.piece_at(sq)) else None
                    for sq in windows[center]
                ))

        best_square = interior[0]
        best_key = (float('inf'), float('inf'), float('inf'))

        for s1 in interior:
            groups = {}
            for i, fp in enumerate(fingerprints[s1]):
                groups.setdefault(fp, []).append(i)

            score_s1 = 0.0
            for group_indices in groups.values():
                best_sumsq = float('inf')
                for s2 in interior:
                    sub_counts = {}
                    for i in group_indices:
                        fp2 = fingerprints[s2][i]
                        sub_counts[fp2] = sub_counts.get(fp2, 0) + 1
                    sumsq = sum(c * c for c in sub_counts.values())
                    if sumsq < best_sumsq:
                        best_sumsq = sumsq
                score_s1 += best_sumsq

            score_s1 /= total
            
            # Apply the targeted backrank penalty
            score_s1 += own_piece_counts[s1] 

            # REVENGE SENSOR: If we were just attacked, heavily reward looking at the attacker - WE SEEK BLOOD
            if tracker.last_capture_square and tracker.last_capture_square in windows[s1]:
                score_s1 -= 100  # Massive negative score to guarantee we look here

            cf, cr = chess.square_file(s1), chess.square_rank(s1)
            centrality = (cf - 3.5) ** 2 + (cr - 3.5) ** 2
            
            key = (score_s1, centrality, s1)
            if key < best_key:
                best_key = key
                best_square = s1

        return best_square


class MoveStrategy:
    """
    Decides what piece to move using voting, heuristics, and panic states
    """
    
    def __init__(self, engine):
        self.engine = engine

    def get_best_move(self, tracker: StateTracker, move_actions: list[chess.Move]) -> chess.Move:
        states = list(tracker.possible_states)
        N = len(states)
        if N == 0:
            return random.choice(move_actions)

        valid_moves = set(move_actions)
        move_votes = Counter()
        king_captures = Counter()
        
        # King Panic Check - Be anxious about being in check
        boards_in_check = sum(1 for fen in states if chess.Board(fen).is_check())
        check_probability = boards_in_check / N
        
        # If >20% chance of being in check, restrict Stockfish voting ONLY to boards where we are in check
        # This prevents it from pushing a pawn while a sniper bishop threatens the king.
        if check_probability > 0.20:
            _dbg(f"PANIC MODE! King is in danger in {check_probability*100:.1f}% of universes.")
            states_to_evaluate = [fen for fen in states if chess.Board(fen).is_check()]
        else:
            states_to_evaluate = states

        time_per_board = max(10.0 / len(states_to_evaluate), 0.001) if states_to_evaluate else 0.001

        for fen in states_to_evaluate:
            board = chess.Board(fen)
            board.turn = tracker.color
            
            # Aggression Mode: King Capture
            enemy_king_sq = board.king(not tracker.color)
            if enemy_king_sq is not None:
                attackers = board.attackers(tracker.color, enemy_king_sq)
                if attackers:
                    capture_move = chess.Move(attackers.pop(), enemy_king_sq)
                    if capture_move in valid_moves:
                        king_captures[capture_move] += 1
                        continue

            # Standard Engine Evaluation
            try:
                board.clear_stack()
                result = self.engine.play(board, chess.engine.Limit(time=time_per_board))
                move = result.move
                if move and move in valid_moves:
                    move_votes[move] += BoardUtils.move_heuristic_value(board, move)
            except Exception:
                pass

        # Execution Logic 1: King Capture Threshold
        if king_captures:
            top_capture, votes = king_captures.most_common(1)[0]
            if (votes / N) > 0.35:  # If 35% of all tracking boards agree we can capture the king, swing for it!
                _dbg(f"Executing King Capture: {top_capture.uci()}")
                return top_capture

        # Execution Logic 2: Standard Voting
        if not move_votes:
            return random.choice(move_actions)

        # Return move with highest weighted score
        best_move = move_votes.most_common(1)[0][0]
        return best_move