import chess.engine
from chess import Board, Color, Move
engine = chess.engine.SimpleEngine.popen_uci("/opt/stockfish/stockfish", setpgrp=True)

FEN = input()

def choose_move(board: Board, color: Color) -> str:
    enemy_king_square = board.king(not color)

    if enemy_king_square:
        enemy_king_attackers = board.attackers(color, enemy_king_square)

        if enemy_king_attackers:
            attacker_square = enemy_king_attackers.pop()
            move = Move(attacker_square, enemy_king_square)
            return move.uci()
        
    board.clear_stack()
    result = engine.play(board, chess.engine.Limit(time=0.5))
    move = result.move

    return move.uci() # type: ignore

initial_board = Board(FEN)

print(choose_move(initial_board, initial_board.turn))

engine.quit()