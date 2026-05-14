import sys
import os
import json
import argparse
import traceback
import chess

sys.path.insert(0, os.path.dirname(__file__))

from reconchess import play_local_game, WinReason
from reconchess.bots.random_bot import RandomBot
from reconchess.bots.trout_bot import TroutBot
import baseline
from baseline import BaselineBot

# STOCKFISH_PATH = "/opt/stockfish/stockfish"
STOCKFISH_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../stockfish/stockfish-windows-x86-64-avx2.exe"))

baseline.STOCKFISH_PATH = STOCKFISH_PATH
os.environ["STOCKFISH_EXECUTABLE"] = STOCKFISH_PATH

_original_init = BaselineBot.__init__
def _patched_init(self):
    import chess.engine
    self.board = None
    self.color = None
    self.engine = chess.engine.SimpleEngine.popen_uci(baseline.STOCKFISH_PATH, setpgrp=True)
    self._engine_restarts = 0
    self.possible_previous_states = []
    self.possible_states = []
    from reconchess import Player
    Player.__init__(self)
BaselineBot.__init__ = _patched_init


def play_match(white_cls, black_cls, n_games: int):
    results = []
    for i in range(n_games):
        white = white_cls()
        black = black_cls()

        print(f"  Playing Game {i+1}/{n_games}", flush=True)

        try:
            winner_color, win_reason, _ = play_local_game(white, black)
            if winner_color is None:
                outcome = "draw"
            elif winner_color == chess.WHITE:
                outcome = "white"
            else:
                outcome = "black"
        except Exception as e:
            outcome = "error"
            traceback.print_exc()
        results.append(outcome)
        print(f"  Game {i+1}/{n_games}: {outcome}", flush=True)
    return results


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
    args = parser.parse_args()
    n = args.games
    print(n)

    matchups = [
        ("Baseline(W) vs Random(B)", BaselineBot, RandomBot, "white"),
        ("Random(W) vs Baseline(B)", RandomBot, BaselineBot, "black"),
        ("Baseline(W) vs Trout(B)",  BaselineBot, TroutBot,  "white"),
        ("Trout(W) vs Baseline(B)",  TroutBot,  BaselineBot, "black"),
    ]

    all_stats = []
    for label, white_cls, black_cls, baseline_color in matchups:
        print(f"\n=== {label} ({n} games) ===", flush=True)
        results = play_match(white_cls, black_cls, n)
        stats = summarise(label, baseline_color, results)
        all_stats.append(stats)

    print("\n\n=== RESULTS SUMMARY ===")
    print(f"{'Matchup':<35} {'W':>4} {'L':>4} {'D':>4} {'E':>4} {'Win%':>7}")
    print("-" * 62)
    for s in all_stats:
        print(f"{s['matchup']:<35} {s['wins']:>4} {s['losses']:>4} "
              f"{s['draws']:>4} {s['errors']:>4} {s['win_rate']*100:>6.1f}%")

    vs_random = [s for s in all_stats if "Random" in s["matchup"]]
    vs_trout  = [s for s in all_stats if "Trout"  in s["matchup"]]

    def agg_rate(group):
        wins   = sum(s["wins"]   for s in group)
        losses = sum(s["losses"] for s in group)
        draws  = sum(s["draws"]  for s in group)
        played = wins + losses + draws
        return wins / played if played > 0 else 0.0

    print(f"\nBaseline vs RandomBot overall win rate: {agg_rate(vs_random)*100:.1f}%")
    print(f"Baseline vs TroutBot  overall win rate: {agg_rate(vs_trout)*100:.1f}%")
    print("\n(Target: >80% vs Random to confirm correctness; competitive vs Trout for on-par baseline)")

    out_path = os.path.join(os.path.dirname(__file__), "tournament_results.json")
    with open(out_path, "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    main()
