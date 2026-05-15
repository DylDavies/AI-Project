import sys
import os
import json
import csv
import argparse
import traceback
import time
import datetime
import chess

sys.path.insert(0, os.path.dirname(__file__))

from reconchess import play_local_game, WinReason
from reconchess.bots.random_bot import RandomBot
from reconchess.bots.trout_bot import TroutBot
import baseline
from baseline import BaselineBot
import improved
from improved import ImprovedBot

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


def _setup_run_dir():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(os.path.dirname(__file__), "logs", ts)
    os.makedirs(os.path.join(run_dir, "replays"), exist_ok=True)
    return run_dir, ts


def _init_csv(run_dir):
    path = os.path.join(run_dir, "games.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "matchup_idx", "matchup", "game_num",
            "white", "black", "outcome", "duration_s"
        ])
    return path


def _append_csv(csv_path, row: list):
    with open(csv_path, "a", newline="") as f:
        csv.writer(f).writerow(row)


def play_match(white_cls, black_cls, n_games: int, matchup_idx: int,
               label: str, run_dir: str, csv_path: str):
    results = []
    replay_dir = os.path.join(run_dir, "replays")
    label_safe = label.replace("(", "").replace(")", "").replace(" ", "_").replace("/", "-")

    for i in range(n_games):
        white = white_cls()
        black = black_cls()
        print(f"  Game {i+1}/{n_games}", flush=True)

        t0 = time.time()
        outcome = "error"
        history = None
        try:
            winner_color, win_reason, history = play_local_game(white, black)
            if winner_color is None:
                outcome = "draw"
            elif winner_color == chess.WHITE:
                outcome = "white"
            else:
                outcome = "black"
        except Exception:
            traceback.print_exc()

        duration = round(time.time() - t0, 1)
        results.append(outcome)
        print(f"  Game {i+1}/{n_games}: {outcome} ({duration}s)", flush=True)

        # Save replay JSON
        if history is not None:
            replay_name = f"{matchup_idx:02d}_{label_safe}_{i+1:03d}.json"
            try:
                history.save(os.path.join(replay_dir, replay_name))
            except Exception as e:
                print(f"  [WARN] Could not save replay: {e}", flush=True)

        # Append to CSV immediately so progress is not lost if run is interrupted
        _append_csv(csv_path, [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            matchup_idx, label, i + 1,
            white_cls.__name__, black_cls.__name__,
            outcome, duration,
        ])

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


def _write_summary(run_dir, all_stats, total_duration):
    lines = []
    lines.append(f"Tournament summary — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total runtime: {total_duration:.0f}s ({total_duration/60:.1f} min)")
    lines.append("")
    header = f"{'Matchup':<38} {'W':>4} {'L':>4} {'D':>4} {'E':>4} {'Win%':>7}"
    lines.append(header)
    lines.append("-" * len(header))
    for s in all_stats:
        lines.append(
            f"{s['matchup']:<38} {s['wins']:>4} {s['losses']:>4} "
            f"{s['draws']:>4} {s['errors']:>4} {s['win_rate']*100:>6.1f}%"
        )

    def agg_rate(group):
        wins   = sum(s["wins"]   for s in group)
        losses = sum(s["losses"] for s in group)
        draws  = sum(s["draws"]  for s in group)
        played = wins + losses + draws
        return wins / played if played > 0 else 0.0

    groups = {
        "Baseline vs RandomBot": [s for s in all_stats if "Baseline" in s["matchup"] and "Random"   in s["matchup"]],
        "Baseline vs TroutBot":  [s for s in all_stats if "Baseline" in s["matchup"] and "Trout"    in s["matchup"]],
        "Improved vs RandomBot": [s for s in all_stats if "Improved" in s["matchup"] and "Random"   in s["matchup"]],
        "Improved vs TroutBot":  [s for s in all_stats if "Improved" in s["matchup"] and "Trout"    in s["matchup"]],
        "Improved vs Baseline":  [s for s in all_stats if "Improved" in s["matchup"] and "Baseline" in s["matchup"]],
    }
    lines.append("")
    for label, group in groups.items():
        if group:
            lines.append(f"{label} overall win rate: {agg_rate(group)*100:.1f}%")

    text = "\n".join(lines)
    print("\n\n=== RESULTS SUMMARY ===")
    print(text)

    with open(os.path.join(run_dir, "summary.txt"), "w") as f:
        f.write(text + "\n")

    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=25,
                        help="Games per color per opponent (default 25)")
    args = parser.parse_args()
    n = args.games

    run_dir, ts = _setup_run_dir()
    csv_path = _init_csv(run_dir)
    print(f"Run directory: {run_dir}", flush=True)
    print(f"Games per matchup: {n}", flush=True)

    matchups = [
        ("Baseline(W) vs Random(B)",   BaselineBot, RandomBot,   "white"),
        ("Random(W) vs Baseline(B)",   RandomBot,   BaselineBot, "black"),
        ("Baseline(W) vs Trout(B)",    BaselineBot, TroutBot,    "white"),
        ("Trout(W) vs Baseline(B)",    TroutBot,    BaselineBot, "black"),
        ("Improved(W) vs Random(B)",   ImprovedBot, RandomBot,   "white"),
        ("Random(W) vs Improved(B)",   RandomBot,   ImprovedBot, "black"),
        ("Improved(W) vs Trout(B)",    ImprovedBot, TroutBot,    "white"),
        ("Trout(W) vs Improved(B)",    TroutBot,    ImprovedBot, "black"),
        ("Baseline(W) vs Improved(B)", BaselineBot, ImprovedBot, "white"),
        ("Improved(W) vs Baseline(B)", ImprovedBot, BaselineBot, "white"),
    ]

    t_start = time.time()
    all_stats = []
    for idx, (label, white_cls, black_cls, baseline_color) in enumerate(matchups):
        print(f"\n=== {label} ({n} games) ===", flush=True)
        results = play_match(white_cls, black_cls, n, idx, label, run_dir, csv_path)
        stats = summarise(label, baseline_color, results)
        all_stats.append(stats)

        # Rolling JSON after each matchup so results survive an interrupted run
        out_path = os.path.join(run_dir, "tournament_results.json")
        with open(out_path, "w") as f:
            json.dump(all_stats, f, indent=2)

    total_duration = time.time() - t_start
    _write_summary(run_dir, all_stats, total_duration)

    # Also write to the legacy path for backwards compatibility
    legacy_path = os.path.join(os.path.dirname(__file__), "tournament_results.json")
    with open(legacy_path, "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"\nRun directory: {run_dir}")
    print(f"Replay JSONs:  {os.path.join(run_dir, 'replays')}")
    print(f"Game log CSV:  {csv_path}")


if __name__ == "__main__":
    main()
