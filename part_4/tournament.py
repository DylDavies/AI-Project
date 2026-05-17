import sys
import os
import json
import csv
import argparse
import traceback
import time
import datetime
import chess
import itertools

sys.path.insert(0, os.path.dirname(__file__))

from reconchess import play_local_game, WinReason
from reconchess.bots.random_bot import RandomBot
from reconchess.bots.trout_bot import TroutBot
import baseline
from baseline import RandomSensing
import improved
from improved import ImprovedAgent

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

RandomSensing.__init__ = _make_patched_init(baseline)
ImprovedAgent.__init__ = _make_patched_init(improved)


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

        if history is not None:
            replay_name = f"{matchup_idx:02d}_{label_safe}_{i+1:03d}.json"
            try:
                history.save(os.path.join(replay_dir, replay_name))
            except Exception as e:
                print(f"  [WARN] Could not save replay: {e}", flush=True)

        _append_csv(csv_path, [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            matchup_idx, label, i + 1,
            white_cls.__name__, black_cls.__name__,
            outcome, duration,
        ])

    return results


def _write_summary(run_dir, all_matchups, all_results, total_duration):
    # Build per-agent totals across all matchups
    agent_stats: dict[str, dict] = {}

    for (label, white_cls, black_cls), results in zip(all_matchups, all_results):
        for cls, color in [(white_cls, "white"), (black_cls, "black")]:
            name = cls.__name__
            if name not in agent_stats:
                agent_stats[name] = {
                    "wins": 0, "losses": 0, "draws": 0, "errors": 0,
                    "white_wins": 0, "white_played": 0,
                    "black_wins": 0, "black_played": 0,
                }
            s = agent_stats[name]
            for r in results:
                if r == "error":
                    s["errors"] += 1
                elif r == "draw":
                    s["draws"] += 1
                    s[f"{color}_played"] += 1
                elif r == color:
                    s["wins"] += 1
                    s[f"{color}_wins"] += 1
                    s[f"{color}_played"] += 1
                else:
                    s["losses"] += 1
                    s[f"{color}_played"] += 1

    lines = []
    lines.append(f"Tournament summary — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total runtime: {total_duration:.0f}s ({total_duration/60:.1f} min)")
    lines.append("")

    # Per-matchup breakdown
    hdr = f"{'Matchup':<42} {'W':>4} {'L':>4} {'D':>4} {'E':>4} {'WhiteWin%':>9}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for (label, white_cls, black_cls), results in zip(all_matchups, all_results):
        w = sum(1 for r in results if r == "white")
        b = sum(1 for r in results if r == "black")
        d = sum(1 for r in results if r == "draw")
        e = sum(1 for r in results if r == "error")
        played = w + b + d
        rate = w / played if played > 0 else 0.0
        lines.append(f"{label:<42} {w:>4} {b:>4} {d:>4} {e:>4} {rate*100:>8.1f}%")

    # Per-agent leaderboard
    lines.append("")
    lines.append("=== Agent leaderboard ===")
    hdr2 = f"{'Agent':<20} {'W':>5} {'L':>5} {'D':>5} {'E':>5} {'Win%':>7} {'AsWhite%':>9} {'AsBlack%':>9}"
    lines.append(hdr2)
    lines.append("-" * len(hdr2))
    ranked = sorted(agent_stats.items(),
                    key=lambda kv: kv[1]["wins"] / max(kv[1]["wins"] + kv[1]["losses"] + kv[1]["draws"], 1),
                    reverse=True)
    for name, s in ranked:
        played = s["wins"] + s["losses"] + s["draws"]
        rate = s["wins"] / played if played > 0 else 0.0
        white_rate = s["white_wins"] / s["white_played"] if s["white_played"] > 0 else 0.0
        black_rate = s["black_wins"] / s["black_played"] if s["black_played"] > 0 else 0.0
        lines.append(
            f"{name:<20} {s['wins']:>5} {s['losses']:>5} {s['draws']:>5} {s['errors']:>5}"
            f" {rate*100:>6.1f}% {white_rate*100:>8.1f}% {black_rate*100:>8.1f}%"
        )

    text = "\n".join(lines)
    print("\n\n=== RESULTS SUMMARY ===")
    print(text)

    with open(os.path.join(run_dir, "summary.txt"), "w") as f:
        f.write(text + "\n")

    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=1,
                        help="Games per matchup (default 1)")
    args = parser.parse_args()
    n = args.games

    run_dir, ts = _setup_run_dir()
    csv_path = _init_csv(run_dir)
    print(f"Run directory: {run_dir}", flush=True)
    print(f"Games per matchup: {n}", flush=True)

    agents = [
        ("Improved", ImprovedAgent),
        ("RandomSensing", RandomSensing),
        ("RandomBot", RandomBot),
        ("TroutBot", TroutBot),
    ]

    # Round-robin: every ordered pair plays once (white, black swapped covers both directions)
    matchups = []
    for (wname, wcls), (bname, bcls) in itertools.permutations(agents, 2):
        label = f"{wname}(W) vs {bname}(B)"
        matchups.append((label, wcls, bcls))

    t_start = time.time()
    all_results = []
    for idx, (label, white_cls, black_cls) in enumerate(matchups):
        print(f"\n=== [{idx+1}/{len(matchups)}] {label} ({n} games) ===", flush=True)
        results = play_match(white_cls, black_cls, n, idx, label, run_dir, csv_path)
        all_results.append(results)

        out_path = os.path.join(run_dir, "tournament_results.json")
        with open(out_path, "w") as f:
            json.dump([
                {"matchup": m[0], "white": m[1].__name__, "black": m[2].__name__, "results": r}
                for m, r in zip(matchups[:idx+1], all_results)
            ], f, indent=2)

    total_duration = time.time() - t_start
    _write_summary(run_dir, matchups, all_results, total_duration)

    legacy_path = os.path.join(os.path.dirname(__file__), "tournament_results.json")
    with open(legacy_path, "w") as f:
        json.dump([
            {"matchup": m[0], "white": m[1].__name__, "black": m[2].__name__, "results": r}
            for m, r in zip(matchups, all_results)
        ], f, indent=2)

    print(f"\nRun directory: {run_dir}")
    print(f"Replay JSONs:  {os.path.join(run_dir, 'replays')}")
    print(f"Game log CSV:  {csv_path}")


if __name__ == "__main__":
    main()
