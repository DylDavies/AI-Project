import os
import json
import argparse
import traceback
import chess
from reconchess import play_local_game
from reconchess.bots.random_bot import RandomBot
from reconchess.bots.trout_bot import TroutBot

from improved_agent import MyGoat
from random_sensing import RandomSensingAgent
from observer import PrintObserver, LiveObserver, CompositeObserver
import live_viewer

STOCKFISH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stockfish.exe")

# Sentinel so the matchup table can refer to MyGoat without importing it twice.
GOAT = "goat"

# Each entry: (label, white, black, goat_color)
# goat_color is "white" or "black" — which side MyGoat is on, used for win/loss accounting.
MATCHUPS = [
    ("MyGoat(W) vs Random(B)",         GOAT,               RandomBot,           "white"),
    ("Random(W) vs MyGoat(B)",          RandomBot,          GOAT,                "black"),
    ("MyGoat(W) vs Trout(B)",           GOAT,               TroutBot,            "white"),
    ("Trout(W) vs MyGoat(B)",           TroutBot,           GOAT,                "black"),
    ("MyGoat(W) vs Baseline(B)",        GOAT,               RandomSensingAgent,  "white"),
    ("Baseline(W) vs MyGoat(B)",        RandomSensingAgent, GOAT,                "black"),
]


def _make_players(white_cls, black_cls, use_live: bool):
    obs = CompositeObserver(PrintObserver(), LiveObserver()) if use_live else PrintObserver()
    white = MyGoat(observer=obs) if white_cls is GOAT else white_cls()
    black = MyGoat(observer=obs) if black_cls is GOAT else black_cls()
    return white, black


def play_match(label: str, white_cls, black_cls, goat_color: str, n_games: int, use_live: bool) -> list:
    results = []

    for i in range(n_games):
        print(f"  [{label}] Game {i + 1}/{n_games}", flush=True)

        white, black = _make_players(white_cls, black_cls, use_live)
        white_name = "MyGoat" if white_cls is GOAT else white.__class__.__name__
        black_name = "MyGoat" if black_cls is GOAT else black.__class__.__name__

        if use_live:
            live_viewer.update(
                matchup_label=label,
                game_index=i + 1,
                n_games=n_games,
                white=white_name,
                black=black_name,
                winner=None,
                turn_number=0,
                last_action=f"Starting game {i + 1}",
            )

        try:
            winner_color, win_reason, _ = play_local_game(white, black)
            if winner_color is None:
                outcome = "draw"
            elif winner_color == chess.WHITE:
                outcome = "white"
            else:
                outcome = "black"
        except Exception:
            outcome = "error"
            traceback.print_exc()

        if use_live:
            live_viewer.update(winner=outcome)
            live_viewer.record_result(label, outcome)

        results.append(outcome)
        print(f"  [{label}] Game {i + 1}/{n_games}: {outcome}", flush=True)

    return results


def summarise(label: str, goat_color: str, results: list) -> dict:
    wins = losses = draws = errors = 0
    for r in results:
        if r == "error":
            errors += 1
        elif r == "draw":
            draws += 1
        elif r == goat_color:
            wins += 1
        else:
            losses += 1
    played = len(results) - errors
    return {
        "matchup": label,
        "goat_color": goat_color,
        "wins": wins, "losses": losses, "draws": draws, "errors": errors,
        "total": len(results),
        "win_rate": round(wins / played, 3) if played > 0 else 0.0,
    }


def print_summary(all_stats: list):
    print("\n\n=== RESULTS SUMMARY ===")
    print(f"{'Matchup':<40} {'W':>4} {'L':>4} {'D':>4} {'E':>4} {'Win%':>7}")
    print("-" * 68)
    for s in all_stats:
        print(f"{s['matchup']:<40} {s['wins']:>4} {s['losses']:>4} "
              f"{s['draws']:>4} {s['errors']:>4} {s['win_rate'] * 100:>6.1f}%")

    def agg(group):
        w = sum(s["wins"] for s in group)
        played = sum(s["wins"] + s["losses"] + s["draws"] for s in group)
        return w / played if played else 0.0

    vs_random = [s for s in all_stats if "Random"   in s["matchup"]]
    vs_trout  = [s for s in all_stats if "Trout"    in s["matchup"]]
    vs_base   = [s for s in all_stats if "Baseline" in s["matchup"]]

    print(f"\nMyGoat vs RandomBot  combined win rate: {agg(vs_random) * 100:.1f}%")
    print(f"MyGoat vs TroutBot   combined win rate: {agg(vs_trout)  * 100:.1f}%")
    print(f"MyGoat vs Baseline   combined win rate: {agg(vs_base)   * 100:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Run a baseline tournament for MyGoat.")
    parser.add_argument("--games",     type=int,  default=10,    help="Games per matchup (default 10)")
    parser.add_argument("--port",      type=int,  default=5000,  help="Live viewer port (default 5000)")
    parser.add_argument("--no-viewer", action="store_true",      help="Disable the live viewer")
    parser.add_argument("--matchups",  nargs="*", default=None,
                        help="Space-separated matchup indices to run (0-based). Runs all if omitted.")
    args = parser.parse_args()

    os.environ["STOCKFISH_EXECUTABLE"] = STOCKFISH_PATH

    use_live = not args.no_viewer
    if use_live:
        live_viewer.start_server(args.port)

    selected = MATCHUPS
    if args.matchups is not None:
        indices = [int(i) for i in args.matchups]
        selected = [MATCHUPS[i] for i in indices]

    print("Matchups to run:")
    for i, (label, *_) in enumerate(selected):
        print(f"  [{i}] {label}")

    all_stats = []
    for label, white_cls, black_cls, goat_color in selected:
        print(f"\n=== {label} ({args.games} games) ===", flush=True)
        results = play_match(label, white_cls, black_cls, goat_color, args.games, use_live)
        stats = summarise(label, goat_color, results)
        all_stats.append(stats)

    print_summary(all_stats)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tournament_results.json")
    with open(out, "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"\nFull results saved to {out}")


if __name__ == "__main__":
    main()
