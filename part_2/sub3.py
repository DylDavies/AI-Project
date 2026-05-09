from chess import Board, Move
from reconchess import utilities

FEN = input()
capture_square = input()

def get_moves(board: Board) -> list[str]:
    moves: list[str] = list()

    for move in board.generate_pseudo_legal_moves():
        moves.append(move.uci())

    for move in utilities.without_opponent_pieces(board).generate_castling_moves():
        if not utilities.is_illegal_castle(board, move):
            moves.append(move.uci())

    moves.append("0000")

    return list(dict.fromkeys(sorted(moves)))

def make_move(board: Board, move: Move) -> str:
    board.push(move)

    return board.fen()

def get_prediction_with_captures(initial_board: Board) -> list[str]:
    boards: list[str] = list()

    for move in get_moves(initial_board):
        if move[2:4] == capture_square:
            board = Board(FEN)

            boards.append(make_move(board, Move.from_uci(move)))

    return list(dict.fromkeys(sorted(boards)))

for board in get_prediction_with_captures(Board(FEN)):
    print(board)