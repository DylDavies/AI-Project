import chess.engine
from chess import Board, Color, Move
from collections import Counter
engine = chess.engine.SimpleEngine.popen_uci("/opt/stockfish/stockfish", setpgrp=True)
# engine = chess.engine.SimpleEngine.popen_uci("./stockfish/stockfish-windows-x86-64-avx2.exe", setpgrp=True)

def choose_move(board: Board, color: Color) -> str:
    enemy_king_square = board.king(not color)

    if enemy_king_square:
        enemy_king_attackers = board.attackers(color, enemy_king_square)

        if enemy_king_attackers:
            attacker_square = enemy_king_attackers.pop()
            move = Move(attacker_square, enemy_king_square)
            return move.uci()
        
    board.clear_stack()
    result = engine.play(board, chess.engine.Limit(time=0.05))
    move = result.move

    return move.uci() # type: ignore

num_boards = int(input())
board_strings: list[str] = list()

for i in range(num_boards):
    board_strings.append(input())

def get_best_move(boards: list[str]) -> str:
    plays: list[str] = list()

    for i in range(len(boards)):
        board = Board(boards[i])
        plays.append(choose_move(board, board.turn))

    counts = Counter(plays)

    max_plays: list[str] = list()
    max_val = max(dict.values(counts))

    for key in dict.keys(counts):
        if counts[key] == max_val:
            max_plays.append(key)

    max_plays = list(dict.fromkeys(sorted(max_plays)))

    return max_plays[0]

print(get_best_move(board_strings))

engine.quit()