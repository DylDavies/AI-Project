import time
import chess
from typing import Optional, Protocol


class AgentObserver(Protocol):
    def on_game_start(self, color: chess.Color, opponent: str, board_fen: str) -> None: ...
    def on_opponent_move(self, n_before: int, n_after: int, captured: bool, board_fen: str) -> None: ...
    def on_sense_chosen(self, square: chess.Square, expected_remaining: float, n_states: int) -> None: ...
    def on_sense_result(self, n_before: int, n_after: int, board_fen: str) -> None: ...
    def on_move_chosen(self, move_uci: str, votes: int, total_boards: int, board_fen: str) -> None: ...
    def on_game_end(self, winner: Optional[chess.Color]) -> None: ...


class NullObserver:
    def on_game_start(self, color, opponent, board_fen): pass
    def on_opponent_move(self, n_before, n_after, captured, board_fen): pass
    def on_sense_chosen(self, square, expected_remaining, n_states): pass
    def on_sense_result(self, n_before, n_after, board_fen): pass
    def on_move_chosen(self, move_uci, votes, total_boards, board_fen): pass
    def on_game_end(self, winner): pass


class PrintObserver:
    def _ts(self) -> str:
        return time.strftime('%H:%M:%S')

    def on_game_start(self, color, opponent, board_fen):
        side = 'WHITE' if color else 'BLACK'
        print(f"[{self._ts()}] game start: {side} vs {opponent}", flush=True)

    def on_opponent_move(self, n_before, n_after, captured, board_fen):
        print(f"[{self._ts()}] opp move: states {n_before} -> {n_after} (capture={captured})", flush=True)

    def on_sense_chosen(self, square, expected_remaining, n_states):
        name = chess.square_name(square)
        print(f"[{self._ts()}] sense: {name} | states={n_states} expected_after={expected_remaining:.1f}", flush=True)

    def on_sense_result(self, n_before, n_after, board_fen):
        print(f"[{self._ts()}] sense result: states {n_before} -> {n_after}", flush=True)

    def on_move_chosen(self, move_uci, votes, total_boards, board_fen):
        print(f"[{self._ts()}] move: {move_uci} ({votes}/{total_boards} votes)", flush=True)

    def on_game_end(self, winner):
        if winner is None:
            label = 'draw'
        elif winner == chess.WHITE:
            label = 'WHITE wins'
        else:
            label = 'BLACK wins'
        print(f"[{self._ts()}] game end: {label}", flush=True)


class LiveObserver:
    """Pushes structured state to the live_viewer HTTP dashboard only.
    Compose with PrintObserver via CompositeObserver to get both."""

    def __init__(self, agent_name: str = "MyGoat", port: int = 5000):
        import live_viewer as lv
        lv.start_server(port)
        self._lv = lv
        self._agent_name = agent_name
        self._our_color = None
        self._turn_number = 0

    def on_game_start(self, color, opponent, board_fen):
        self._our_color = color
        self._turn_number = 0
        white = self._agent_name if color == chess.WHITE else opponent
        black = opponent if color == chess.WHITE else self._agent_name
        our_turn = "White" if color == chess.WHITE else "Black"
        self._lv.update(
            fen=board_fen,
            white=white,
            black=black,
            matchup_label=f"{white} vs {black}",
            turn=our_turn,
            turn_number=self._turn_number,
            last_action=f"Game start — {our_turn} to move",
            winner=None,
        )

    def on_opponent_move(self, n_before, n_after, captured, board_fen):
        self._turn_number += 1
        our_turn = "White" if self._our_color == chess.WHITE else "Black"
        self._lv.update(
            fen=board_fen,
            turn=our_turn,
            turn_number=self._turn_number,
            last_action=f"Opp moved: states {n_before} -> {n_after}",
        )

    def on_sense_chosen(self, square, expected_remaining, n_states):
        name = chess.square_name(square)
        self._lv.update(last_action=f"Sensing {name} | states={n_states} exp_after={expected_remaining:.1f}")

    def on_sense_result(self, n_before, n_after, board_fen):
        self._lv.update(fen=board_fen, last_action=f"Sense result: {n_before} -> {n_after} states")

    def on_move_chosen(self, move_uci, votes, total_boards, board_fen):
        opp_turn = "Black" if self._our_color == chess.WHITE else "White"
        self._lv.update(
            fen=board_fen,
            turn=opp_turn,
            last_action=f"Move: {move_uci} ({votes}/{total_boards} votes)",
        )

    def on_game_end(self, winner):
        if winner is None:
            label = 'Draw'
        elif winner == chess.WHITE:
            label = 'White wins'
        else:
            label = 'Black wins'
        self._lv.update(winner=label)


class CompositeObserver:
    """Fans out every event to a list of observers."""

    def __init__(self, *observers):
        self._observers = observers

    def on_game_start(self, color, opponent, board_fen):
        for o in self._observers: o.on_game_start(color, opponent, board_fen)

    def on_opponent_move(self, n_before, n_after, captured, board_fen):
        for o in self._observers: o.on_opponent_move(n_before, n_after, captured, board_fen)

    def on_sense_chosen(self, square, expected_remaining, n_states):
        for o in self._observers: o.on_sense_chosen(square, expected_remaining, n_states)

    def on_sense_result(self, n_before, n_after, board_fen):
        for o in self._observers: o.on_sense_result(n_before, n_after, board_fen)

    def on_move_chosen(self, move_uci, votes, total_boards, board_fen):
        for o in self._observers: o.on_move_chosen(move_uci, votes, total_boards, board_fen)

    def on_game_end(self, winner):
        for o in self._observers: o.on_game_end(winner)
