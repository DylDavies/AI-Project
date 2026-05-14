import sys
import os
import json
import argparse
import traceback
import chess

sys.path.insert(0, os.path.dirname(__file__))

import reconchess
from reconchess import WinReason
from reconchess.bots.random_bot import RandomBot
from reconchess.bots.trout_bot import TroutBot
from reconchess.play import play_turn
import baseline
from baseline import BaselineBot
import improved
from improved import ImprovedBot
import live_viewer

# STOCKFISH_PATH = "/opt/stockfish/stockfish"
STOCKFISH_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../stockfish/stockfish-windows-x86-64-avx2.exe"))

baseline.STOCKFISH_PATH = STOCKFISH_PATH
improved.STOCKFISH_PATH = STOCKFISH_PATH
os.environ["STOCKFISH_EXECUTABLE"] = STOCKFISH_PATH

def _make_patched_init(module):
    def _patched_init(self):
        import chess.engine
        self.board = None
        self.color = None
        self.engine = chess.engine.SimpleEngine.popen_uci(module.STOCKFISH_PATH, setpgrp=True)
        self._engine_restarts = 0
        self.possible_previous_states = []
        self.possible_states = []
        from reconchess import Player
        Player.__init__(self)
    return _patched_init

BaselineBot.__init__ = _make_patched_init(baseline)
ImprovedBot.__init__ = _make_patched_init(improved)


def play_match(matchup_label: str, white_cls, black_cls, n_games: int):
    results = []
    for i in range(n_games):
        white = white_cls()
        black = black_cls()
        white_name = white.__class__.__name__
        black_name = black.__class__.__name__

        print(f"  Playing Game {i+1}/{n_games}", flush=True)
        live_viewer.update(
            matchup_label=matchup_label,
            game_index=i + 1,
            n_games=n_games,
            white=white_name,
            black=black_name,
            winner=None,
            turn_number=0,
            last_action=f"Starting {white_name} vs {black_name}",
        )

        try:
            outcome, history = _play_game_live(white, black, white_name, black_name)
        except Exception:
            outcome = "error"
            history = None
            traceback.print_exc()

        live_viewer.update(winner=outcome)
        live_viewer.record_result(matchup_label, outcome)
        results.append(outcome)
        print(f"  Game {i+1}/{n_games}: {outcome}", flush=True)

    return results


def _play_game_live(white_player, black_player, white_name: str, black_name: str):
    """Inlined play_local_game with live_viewer hooks between turns."""
    players = {chess.BLACK: black_player, chess.WHITE: white_player}

    game = reconchess.LocalGame(seconds_per_player=900)
    game.store_players(white_name, black_name)

    white_player.handle_game_start(chess.WHITE, game.board.copy(), black_name)
    black_player.handle_game_start(chess.BLACK, game.board.copy(), white_name)
    game.start()

    live_viewer.update(fen=game.board.fen(), turn_number=0,
                       last_action=f"Game started")

    while not game.is_over():
        color = game.turn
        color_name = "white" if color == chess.WHITE else "black"
        play_turn(game, players[color], end_turn_last=True)
        live_viewer.update(
            fen=game.board.fen(),
            turn="white" if game.turn == chess.WHITE else "black",
            turn_number=game.board.fullmove_number,
            last_action=f"{color_name} moved (turn {game.board.fullmove_number})",
        )

    game.end()
    winner_color = game.get_winner_color()
    win_reason = game.get_win_reason()
    history = game.get_game_history()

    white_player.handle_game_end(winner_color, win_reason, history)
    black_player.handle_game_end(winner_color, win_reason, history)

    if winner_color is None:
        outcome = "draw"
    elif winner_color == chess.WHITE:
        outcome = "white"
    else:
        outcome = "black"
    return outcome, history


def summarise(matchup_label, baseline_color, results):
    wins = losses = draws = errors = 0
    for r in results:
        if r == "error":
            errors += 1
        elif r == "draw":
            draws += 1
        elif r == baseline_color:
            wins += 1
        else:
            losses += 1
    total = len(results)
    rate = wins / (total - errors) if (total - errors) > 0 else 0.0
    return {
        "matchup": matchup_label,
        "baseline_color": baseline_color,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "errors": errors,
        "total": total,
        "win_rate": round(rate, 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=25,
                        help="Games per color per opponent (default 25)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port for the live viewer (default 5000)")
    args = parser.parse_args()
    n = args.games

    live_viewer.start_server(port=args.port)

    matchups = [
        # ("Baseline(W) vs Random(B)",   BaselineBot, RandomBot,   "white"),
        # ("Random(W) vs Baseline(B)",   RandomBot,   BaselineBot, "black"),
        # ("Baseline(W) vs Trout(B)",    BaselineBot, TroutBot,    "white"),
        # ("Trout(W) vs Baseline(B)",    TroutBot,    BaselineBot, "black"),
        # ("Improved(W) vs Random(B)",   ImprovedBot, RandomBot,   "white"),
        # ("Random(W) vs Improved(B)",   RandomBot,   ImprovedBot, "black"),
        # ("Improved(W) vs Trout(B)",    ImprovedBot, TroutBot,    "white"),
        ("Trout(W) vs Improved(B)",    TroutBot,    ImprovedBot, "black")
        # ("Baseline(W) vs Improved(B)", BaselineBot, ImprovedBot, "white"),
        # ("Improved(W) vs Baseline(B)", ImprovedBot, BaselineBot, "white"),
    ]

    all_stats = []
    for label, white_cls, black_cls, baseline_color in matchups:
        print(f"\n=== {label} ({n} games) ===", flush=True)
        results = play_match(label, white_cls, black_cls, n)
        stats = summarise(label, baseline_color, results)
        all_stats.append(stats)

    print("\n\n=== RESULTS SUMMARY ===")
    print(f"{'Matchup':<35} {'W':>4} {'L':>4} {'D':>4} {'E':>4} {'Win%':>7}")
    print("-" * 62)
    for s in all_stats:
        print(f"{s['matchup']:<35} {s['wins']:>4} {s['losses']:>4} "
              f"{s['draws']:>4} {s['errors']:>4} {s['win_rate']*100:>6.1f}%")

    def agg_rate(group):
        wins   = sum(s["wins"]   for s in group)
        losses = sum(s["losses"] for s in group)
        draws  = sum(s["draws"]  for s in group)
        played = wins + losses + draws
        return wins / played if played > 0 else 0.0

    base_vs_random = [s for s in all_stats if "Baseline" in s["matchup"] and "Random"  in s["matchup"]]
    base_vs_trout  = [s for s in all_stats if "Baseline" in s["matchup"] and "Trout"   in s["matchup"]]
    impr_vs_random = [s for s in all_stats if "Improved" in s["matchup"] and "Random"  in s["matchup"]]
    impr_vs_trout  = [s for s in all_stats if "Improved" in s["matchup"] and "Trout"   in s["matchup"]]

    print(f"\nBaseline vs RandomBot overall win rate: {agg_rate(base_vs_random)*100:.1f}%")
    print(f"Baseline vs TroutBot  overall win rate: {agg_rate(base_vs_trout)*100:.1f}%")
    print(f"Improved vs RandomBot overall win rate: {agg_rate(impr_vs_random)*100:.1f}%")
    print(f"Improved vs TroutBot  overall win rate: {agg_rate(impr_vs_trout)*100:.1f}%")
    print("\n(Target: >80% vs Random to confirm correctness; Improved should beat Baseline head-to-head)")

    out_path = os.path.join(os.path.dirname(__file__), "tournament_results.json")
    with open(out_path, "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    main()
