from chess import Board
from reconchess import utilities

board = Board(input())

def get_moves(board: Board) -> list[str]:
    moves: list[str] = list()

    for move in board.generate_pseudo_legal_moves():
        moves.append(move.uci())

    for move in utilities.without_opponent_pieces(board).generate_castling_moves():
        if not utilities.is_illegal_castle(board, move):
            moves.append(move.uci())

    moves.append("0000")

    return sorted(moves)

for move in list(dict.fromkeys(get_moves(board))):
    print(move)