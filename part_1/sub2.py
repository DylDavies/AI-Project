from chess import Move, Board
from reconchess import Player
from reconchess.types import List, Square

board = Board(input())
move = Move.from_uci(input())

board.push(move)

print(board.fen())