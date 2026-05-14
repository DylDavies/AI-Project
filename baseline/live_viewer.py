import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import chess
import chess.svg

_lock = threading.Lock()
_state = {
    "fen": chess.STARTING_FEN,
    "white": "White",
    "black": "Black",
    "matchup_label": "Waiting...",
    "game_index": 0,
    "n_games": 0,
    "turn": "white",
    "turn_number": 0,
    "last_action": "Tournament not started",
    "winner": None,
    "results_so_far": [],
}

_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>RBC Live Viewer</title>
  <style>
    body { font-family: monospace; background: #1a1a1a; color: #e0e0e0; margin: 20px; }
    h1 { color: #f0c040; margin-bottom: 4px; }
    .sub { color: #aaa; margin-bottom: 16px; }
    .board { display: inline-block; border: 2px solid #555; }
    .info { display: inline-block; vertical-align: top; margin-left: 24px; max-width: 340px; }
    .label { color: #f0c040; font-size: 1.1em; margin-bottom: 6px; }
    .row { margin: 4px 0; }
    .key { color: #aaa; }
    .white-badge { background: #f0f0f0; color: #111; padding: 1px 6px; border-radius: 3px; }
    .black-badge { background: #222; color: #eee; border: 1px solid #555; padding: 1px 6px; border-radius: 3px; }
    .timer { color: #f0c040; font-weight: bold; }
    .win { color: #6dff6d; }
    .loss { color: #ff6d6d; }
    table { border-collapse: collapse; margin-top: 16px; width: 100%; }
    th { border-bottom: 1px solid #555; padding: 4px 8px; text-align: left; color: #aaa; }
    td { padding: 3px 8px; }
    tr:nth-child(even) { background: #222; }
  </style>
</head>
<body>
<h1>RBC Live Viewer</h1>
<div class="sub">Auto-refreshes every second.</div>
<div>
  <div class="board"><img id="board-img" src="/board.svg" width="480" height="480" alt="board"></div>
  <div class="info">
    <div class="label" id="matchup">-</div>
    <div class="row">
      <span class="key">White: </span><span id="white-player" class="white-badge">-</span>
    </div>
    <div class="row">
      <span class="key">Black: </span><span id="black-player" class="black-badge">-</span>
    </div>
    <div class="row"><span class="key">Game: </span><span id="game-index">-</span></div>
    <div class="row"><span class="key">Turn #: </span><span id="turn-number">-</span></div>
    <div class="row"><span class="key">To move: </span><span id="turn">-</span></div>
    <div class="row"><span class="key">Turn time: </span><span id="timer" class="timer">0s</span></div>
    <div class="row"><span class="key">Last: </span><span id="last-action">-</span></div>
    <div class="row"><span class="key">Result: </span><span id="winner">-</span></div>
    <table>
      <thead><tr><th>Matchup</th><th>W</th><th>L</th><th>D</th><th>E</th></tr></thead>
      <tbody id="results-body"></tbody>
    </table>
  </div>
</div>
<script>
var _lastTurnKey = null;
var _turnStart = Date.now();

function refresh() {
  fetch('/state.json').then(function(r) { return r.json(); }).then(function(s) {
    document.getElementById('board-img').src = '/board.svg?t=' + Date.now();
    document.getElementById('matchup').textContent = s.matchup_label;
    document.getElementById('white-player').textContent = s.white;
    document.getElementById('black-player').textContent = s.black;
    document.getElementById('game-index').textContent = s.game_index + ' / ' + s.n_games;
    document.getElementById('turn-number').textContent = s.turn_number;
    document.getElementById('turn').textContent = s.turn;
    document.getElementById('last-action').textContent = s.last_action;
    document.getElementById('winner').textContent = s.winner || '(in progress)';

    var turnKey = s.turn_number + ':' + s.turn;
    if (turnKey !== _lastTurnKey) {
      _lastTurnKey = turnKey;
      _turnStart = Date.now();
    }
    var elapsed = Math.floor((Date.now() - _turnStart) / 1000);
    document.getElementById('timer').textContent = elapsed + 's';

    var tbody = document.getElementById('results-body');
    tbody.innerHTML = '';
    s.results_so_far.forEach(function(r) {
      var tr = document.createElement('tr');
      tr.innerHTML = '<td>' + r.matchup + '</td><td>' + r.w + '</td><td>' + r.l + '</td><td>' + r.d + '</td><td>' + r.e + '</td>';
      tbody.appendChild(tr);
    });
  });
}
refresh();
setInterval(refresh, 250);
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, "text/html", _HTML.encode())
        elif path == "/state.json":
            with _lock:
                data = json.dumps(_state).encode()
            self._send(200, "application/json", data)
        elif path == "/board.svg":
            with _lock:
                fen = _state["fen"]
            try:
                board = chess.Board(fen)
            except Exception:
                board = chess.Board()
            svg_data = chess.svg.board(board, size=480).encode()
            self._send(200, "image/svg+xml", svg_data)
        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError):
            pass


def start_server(port: int = 5000) -> None:
    server = ThreadingHTTPServer(("", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"Live viewer: http://localhost:{port}", flush=True)


def update(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def record_result(matchup: str, outcome: str) -> None:
    with _lock:
        for row in _state["results_so_far"]:
            if row["matchup"] == matchup:
                if outcome == "error":
                    row["e"] += 1
                elif outcome == "draw":
                    row["d"] += 1
                elif outcome == "win":
                    row["w"] += 1
                else:
                    row["l"] += 1
                return
        row = {"matchup": matchup, "w": 0, "l": 0, "d": 0, "e": 0}
        if outcome == "error":
            row["e"] = 1
        elif outcome == "draw":
            row["d"] = 1
        elif outcome == "win":
            row["w"] = 1
        else:
            row["l"] = 1
        _state["results_so_far"].append(row)
