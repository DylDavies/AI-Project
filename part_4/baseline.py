import random
import time
from reconchess import Optional, List, Tuple, GameHistory, WinReason, Player, utilities
import chess.engine
from chess import Board, Color, Square, Move, square_name, parse_square, Piece
from collections import Counter

DEBUG = True

def _dbg(msg: str) -> None:
    if DEBUG:
        print(f"[DBG {time.strftime('%H:%M:%S')}] {msg}", flush=True)

# STOCKFISH_PATH = "/opt/stockfish/stockfish"
STOCKFISH_PATH = "./stockfish/stockfish-windows-x86-64-avx2.exe"
MAX_RESTARTS_PER_GAME = 3

# Status flags that make a board structurally impossible for Stockfish to parse.
# STATUS_OPPOSITE_CHECK / TOO_MANY_CHECKERS / IMPOSSIBLE_CHECK are intentionally
# excluded: they occur legitimately in RBC when the opponent moves into our attack.
_ENGINE_UNSAFE_MASK = (
    chess.STATUS_NO_WHITE_KING
    | chess.STATUS_NO_BLACK_KING
    | chess.STATUS_TOO_MANY_KINGS
    | chess.STATUS_TOO_MANY_WHITE_PAWNS
    | chess.STATUS_TOO_MANY_BLACK_PAWNS
    | chess.STATUS_PAWNS_ON_BACKRANK
    | chess.STATUS_TOO_MANY_WHITE_PIECES
    | chess.STATUS_TOO_MANY_BLACK_PIECES
    | chess.STATUS_BAD_CASTLING_RIGHTS
    | chess.STATUS_INVALID_EP_SQUARE
    | chess.STATUS_EMPTY
)

_NULL_MOVE = Move.null()

def get_moves(board: Board) -> list[str]:
    moves: list[str] = list()

    for move in board.generate_pseudo_legal_moves():
        moves.append(move.uci())

    for move in utilities.without_opponent_pieces(board).generate_castling_moves():
        if not utilities.is_illegal_castle(board, move):
            moves.append(move.uci())

    moves.append("0000")

    return list(dict.fromkeys(sorted(moves)))

def fast_copy_board(board: Board) -> Board:
    b = object.__new__(Board)
    b.pawns = board.pawns
    b.knights = board.knights
    b.bishops = board.bishops
    b.rooks = board.rooks
    b.queens = board.queens
    b.kings = board.kings
    b.occupied_co = [*board.occupied_co]
    b.occupied = board.occupied
    b.promoted = board.promoted
    b.chess960 = board.chess960
    b.ep_square = board.ep_square
    b.castling_rights = board.castling_rights
    b.turn = board.turn
    b.fullmove_number = board.fullmove_number
    b.halfmove_clock = board.halfmove_clock
    b.move_stack = []
    b._stack = []
    return b

def get_possible_next_boards(initial_board: Board, capture_square: Square) -> list[Board]:
    sq_name = square_name(capture_square)
    seen: dict[str, Board] = {}
    for move in get_moves(initial_board):
        if move[2:4] == sq_name:
            b = fast_copy_board(initial_board)
            b.push(Move.from_uci(move))
            fen = b.fen()
            if fen not in seen:
                seen[fen] = b
    return list(seen.values())

def get_possible_next_boards_no_capture(initial_board: Board) -> list[Board]:
    seen: dict[str, Board] = {}
    for move in get_moves(initial_board):
        m = Move.from_uci(move)
        if move != "0000" and initial_board.is_capture(m):
            continue
        b = fast_copy_board(initial_board)
        b.push(m)
        fen = b.fen()
        if fen not in seen:
            seen[fen] = b
    return list(seen.values())

def get_valid_boards(states: list[Board], window: str) -> list[Board]:
    slices = window.split(";")

    valid_states: list[Board] = list()

    for state in states:
        all_succeeded = True
        for slice in slices:
            square, piece = slice.split(":")
            
            if piece == "?":
                if state.piece_at(Square(parse_square(square))) is not None:
                    all_succeeded = False
                    break
            else:
                if Piece.from_symbol(piece) != state.piece_at(Square(parse_square(square))):
                    all_succeeded = False
                    break
        
        if all_succeeded: 
            valid_states.append(state)

    return valid_states

def build_sense_string(sense_results: List[Tuple[Square, Optional[chess.Piece]]]) -> str:
    sense_string = ""
    for i in range(len(sense_results)):
        sense_string += square_name(sense_results[i][0]) + ":"

        piece = sense_results[i][1]

        if piece:
            sense_string += piece.symbol()
        else:
            sense_string += "?"

        if i + 1 != len(sense_results):
            sense_string += ";"

    return sense_string

class BaselineBot(Player):
    def __init__(self) -> None:
        self.board = None
        self.color = None
        self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH, setpgrp=True)
        self._engine_restarts = 0
        self.possible_previous_states: list[Board] = list()
        self.possible_states: list[Board] = list()

        super().__init__()

    def _is_safe_for_engine(self, board: Board, color: Color) -> bool:
        if board.king(color) is None or board.king(not color) is None:
            return False
        return (board.status() & _ENGINE_UNSAFE_MASK) == 0

    def _restart_engine(self) -> None:
        _dbg(f"engine crashed — restart #{self._engine_restarts + 1}")
        try:
            self.engine.close()
        except Exception:
            pass
        if self._engine_restarts >= MAX_RESTARTS_PER_GAME:
            _dbg("restart limit reached — engine disabled for this game")
            self.engine = None
            return
        self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH, setpgrp=True)
        self._engine_restarts += 1

    def choose_move_internal(self, board: Board, color: Color, time_limit: float = 1.0) -> Optional[str]:
        if self.engine is None:
            return None

        enemy_king_square = board.king(not color)

        if enemy_king_square:
            enemy_king_attackers = board.attackers(color, enemy_king_square)

            if enemy_king_attackers:
                attacker_square = enemy_king_attackers.pop()
                move = Move(attacker_square, enemy_king_square)
                return move.uci()

        b = fast_copy_board(board)
        b.turn = color
        b.ep_square = None

        try:
            result = self.engine.play(b, chess.engine.Limit(time=time_limit), ponder=False)
        except chess.engine.EngineTerminatedError:
            self._restart_engine()
            return None
        except chess.engine.EngineError:
            return None

        return result.move.uci() if result.move else None  # type: ignore

    def handle_game_start(self, color: Color, board: chess.Board, opponent_name: str):
        self.board = board
        self.color = color
        # possible_states must have turn = opponent's color so that
        # handle_opponent_move_result generates the opponent's moves, not ours.
        # The starting board has turn=WHITE; for white we must flip to BLACK.
        b = board.copy()
        b.turn = not color
        b.clear_stack()
        self.possible_states.append(b)
        _dbg(f"game start: playing as {'WHITE' if color else 'BLACK'} vs {opponent_name}")

    def handle_opponent_move_result(self, captured_my_piece: bool, capture_square: Optional[Square]):
        before = len(self.possible_states)
        new_states = []
        for board in self.possible_states:
            # Pre-expansion filter: if the opponent captured our piece, that piece must
            # actually exist on this board at capture_square. Boards that disagree are
            # already inconsistent with what we know about our own piece positions.
            if captured_my_piece and capture_square is not None:
                piece = board.piece_at(capture_square)
                if piece is None or piece.color != self.color:
                    continue

            if capture_square:
                new_states.extend(get_possible_next_boards(board, capture_square))
            else:
                new_states.extend(get_possible_next_boards_no_capture(board))

        seen = {}
        for b in new_states:
            seen[b.fen()] = b
        unique = list(seen.values())

        valid_unique = [b for b in unique if self._is_safe_for_engine(b, self.color)]

        if len(valid_unique) > 10000:
            self.possible_states = random.sample(valid_unique, 10000)
        else:
            self.possible_states = valid_unique
        _dbg(f"opponent move result: states {before} -> {len(self.possible_states)} (capture={capture_square is not None})")

    def choose_sense(self, sense_actions: List[Square], move_actions: List[chess.Move], seconds_left: float) -> \
            Optional[Square]:
        
        interior_actions = [
            s for s in sense_actions
            if 0 < chess.square_rank(s) < 7 and 0 < chess.square_file(s) < 7
        ]

        return random.choice(interior_actions)

    def handle_sense_result(self, sense_result: List[Tuple[Square, Optional[chess.Piece]]]):
        before = len(self.possible_states)
        sense_string = build_sense_string(sense_result)
        self.possible_states = get_valid_boards(self.possible_states, sense_string)
        _dbg(f"sense result: states {before} -> {len(self.possible_states)}")

    def choose_move(self, move_actions: List[chess.Move], seconds_left: float) -> Optional[chess.Move]:
        plays: list[str] = list()
        boards = self.possible_states
        legal = {m.uci() for m in move_actions}

        if len(boards) > 10000:
            boards = random.sample(boards, 10000)

        N = len(boards)
        time_per_call = max(10 / N, 0.001) if N > 0 else 0.001
        _dbg(f"choose_move: total={N} time_per_call={time_per_call:.4f}s  total_budget~{N * time_per_call:.1f}s  seconds_left={seconds_left:.0f}")

        t0 = time.time()
        for board in boards:
            move_uci = self.choose_move_internal(board, self.color, time_limit=time_per_call)
            if move_uci is not None:
                plays.append(move_uci)
        _dbg(f"choose_move: stockfish loop took {time.time()-t0:.2f}s, got {len(plays)} votes")

        counts = Counter(p for p in plays if p in legal)

        if not counts:
            return random.choice(move_actions)

        max_plays: list[str] = list()
        max_val = max(dict.values(counts))

        for key in dict.keys(counts):
            if counts[key] == max_val:
                max_plays.append(key)

        max_plays = list(dict.fromkeys(sorted(max_plays)))

        return Move.from_uci(max_plays[0])

    def handle_move_result(self, requested_move: Optional[chess.Move], taken_move: Optional[chess.Move],
                           captured_opponent_piece: bool, capture_square: Optional[Square]):
        requested = requested_move if requested_move is not None else _NULL_MOVE
        taken = taken_move if taken_move is not None else _NULL_MOVE
        new_states = []
        for board in self.possible_states:
            # Case I: requested a real move but it was blocked (taken=null) → drop boards where it was legal
            if requested != _NULL_MOVE and taken == _NULL_MOVE:
                if board.is_legal(requested):
                    continue

            if taken != _NULL_MOVE:
                # Case II: taken move wasn't legal on this board → drop it
                if not board.is_legal(taken):
                    continue
                # Case III: capture happened but this board wouldn't have captured
                if captured_opponent_piece:
                    if not board.is_capture(taken):
                        continue
                    piece_at = board.piece_at(capture_square)
                    if piece_at and piece_at.piece_type == chess.KING:
                        continue
                # Case IV: no capture happened but this board would have captured
                elif board.is_capture(taken):
                    continue

            b = fast_copy_board(board)
            try:
                b.push(taken)
                new_states.append(b)
            except Exception:
                pass

        if new_states:
            self.possible_states = new_states

    def handle_game_end(self, winner_color: Optional[Color], win_reason: Optional[WinReason],
                        game_history: GameHistory):
        if self.engine is not None:
            try:
                self.engine.quit()
            except chess.engine.EngineTerminatedError:
                pass