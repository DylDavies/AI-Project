import os
import re
import sys
import json
import datetime
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

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
STOCKFISH_PATH = os.path.join(BASE_DIR, "stockfish.exe")
LOGS_DIR      = os.path.join(BASE_DIR, "logs")
HISTORY_DIR   = os.path.join(BASE_DIR, "game_history")

# Import BaselineBot from part_4, redirecting its Stockfish path to ours
sys.path.insert(0, os.path.join(BASE_DIR, "..", "part_4"))
import baseline as _part4_baseline
sys.path.pop(0)
_part4_baseline.STOCKFISH_PATH = STOCKFISH_PATH
_part4_baseline.DEBUG = False
BaselineBot = _part4_baseline.BaselineBot

GOAT = "goat"

MATCHUPS = [
    ("MyGoat(W) vs Random(B)",         GOAT,               RandomBot,           "white"),
    ("Random(W) vs MyGoat(B)",          RandomBot,          GOAT,                "black"),
    ("MyGoat(W) vs Trout(B)",           GOAT,               TroutBot,            "white"),
    ("Trout(W) vs MyGoat(B)",           TroutBot,           GOAT,                "black"),
    ("MyGoat(W) vs Baseline(B)",        GOAT,               RandomSensingAgent,  "white"),
    ("Baseline(W) vs MyGoat(B)",        RandomSensingAgent, GOAT,                "black"),
    ("MyGoat(W) vs Part4Base(B)",       GOAT,               BaselineBot,         "white"),
    ("Part4Base(W) vs MyGoat(B)",       BaselineBot,        GOAT,                "black"),
]

_SUMMARY_SENTINEL = "=== CUMULATIVE SUMMARY ==="


def _sanitize_label(label: str) -> str:
    s = label.replace("(", "_").replace(")", "").replace(" ", "_")
    return re.sub(r"_+", "_", s).strip("_")


def _make_players(white_cls, black_cls, use_live: bool):
    obs = CompositeObserver(PrintObserver(), LiveObserver()) if use_live else PrintObserver()
    white = MyGoat(observer=obs) if white_cls is GOAT else white_cls()
    black = MyGoat(observer=obs) if black_cls is GOAT else black_cls()
    return white, black


def _update_matchup_log(log_path: str, new_entries: list, goat_color: str) -> None:
    """Append new game entries then rewrite the cumulative summary at the end of the file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    all_game_lines = []
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            for line in f:
                stripped = line.rstrip()
                if stripped == _SUMMARY_SENTINEL:
                    break
                all_game_lines.append(stripped)

    # Remove trailing blank lines before appending
    while all_game_lines and all_game_lines[-1] == "":
        all_game_lines.pop()

    for outcome, json_filename in new_entries:
        if outcome == goat_color:
            tag = "WIN"
        elif outcome == "draw":
            tag = "DRAW"
        elif outcome == "error":
            tag = "ERROR"
        else:
            tag = "LOSS"
        all_game_lines.append(f"{timestamp} | {tag:<5} | {json_filename}")

    wins   = sum(1 for l in all_game_lines if " | WIN   | " in l)
    losses = sum(1 for l in all_game_lines if " | LOSS  | " in l)
    draws  = sum(1 for l in all_game_lines if " | DRAW  | " in l)
    errors = sum(1 for l in all_game_lines if " | ERROR | " in l)
    played = wins + losses + draws
    win_rate = wins / played if played > 0 else 0.0

    with open(log_path, "w") as f:
        for line in all_game_lines:
            f.write(line + "\n")
        f.write("\n")
        f.write(f"{_SUMMARY_SENTINEL}\n")
        f.write(f"Total Games Played : {played}  (+{errors} errors)\n")
        f.write(f"Wins               : {wins}\n")
        f.write(f"Losses             : {losses}\n")
        f.write(f"Draws              : {draws}\n")
        f.write(f"Win Rate           : {win_rate * 100:.1f}%\n")
        f.write(f"Last updated       : {timestamp}\n")


def play_match(label: str, white_cls, black_cls, goat_color: str,
               n_games: int, use_live: bool, run_ts: str) -> list:
    results = []
    file_prefix = _sanitize_label(label)
    log_path = os.path.join(LOGS_DIR, f"{file_prefix}.txt")
    new_entries = []

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

        game_filename = f"{file_prefix}_{run_ts}_game{i + 1:02d}.json"
        game_path = os.path.join(HISTORY_DIR, game_filename)
        outcome = "error"

        try:
            winner_color, win_reason, history = play_local_game(white, black)
            history.save(game_path)
            if winner_color is None:
                outcome = "draw"
            elif winner_color == chess.WHITE:
                outcome = "white"
            else:
                outcome = "black"
        except Exception:
            game_filename = game_filename.replace(".json", "_ERROR.json")
            traceback.print_exc()

        if use_live:
            live_viewer.update(winner=outcome)
            live_viewer.record_result(label, outcome, goat_color)

        results.append(outcome)
        new_entries.append((outcome, game_filename))
        print(f"  [{label}] Game {i + 1}/{n_games}: {outcome}", flush=True)

    _update_matchup_log(log_path, new_entries, goat_color)
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

    vs_random = [s for s in all_stats if "Random"    in s["matchup"]]
    vs_trout  = [s for s in all_stats if "Trout"     in s["matchup"]]
    vs_base   = [s for s in all_stats if "Baseline"  in s["matchup"] and "Part4" not in s["matchup"]]
    vs_p4base = [s for s in all_stats if "Part4Base" in s["matchup"]]

    print(f"\nMyGoat vs RandomBot  combined win rate: {agg(vs_random) * 100:.1f}%")
    print(f"MyGoat vs TroutBot   combined win rate: {agg(vs_trout)  * 100:.1f}%")
    print(f"MyGoat vs Baseline   combined win rate: {agg(vs_base)   * 100:.1f}%")
    print(f"MyGoat vs Part4Base  combined win rate: {agg(vs_p4base) * 100:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Run a baseline tournament for MyGoat.")
    parser.add_argument("--games",     type=int,  default=5,    help="Games per matchup (default 5)")
    parser.add_argument("--port",      type=int,  default=5000,  help="Live viewer port (default 5000)")
    parser.add_argument("--no-viewer", action="store_true",      help="Disable the live viewer")
    parser.add_argument("--matchups",  nargs="*", default=None,
                        help="Space-separated matchup indices to run (0-based). Runs all if omitted.")
    args = parser.parse_args()

    os.environ["STOCKFISH_EXECUTABLE"] = STOCKFISH_PATH
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)

    run_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

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
        results = play_match(label, white_cls, black_cls, goat_color, args.games, use_live, run_ts)
        stats = summarise(label, goat_color, results)
        all_stats.append(stats)

    print_summary(all_stats)

    out = os.path.join(BASE_DIR, "tournament_results.json")
    with open(out, "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"\nFull results saved to {out}")
    print(f"Game logs  -> {LOGS_DIR}")
    print(f"Game JSON  -> {HISTORY_DIR}")


if __name__ == "__main__":
    main()
