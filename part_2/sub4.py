from chess import Board, Piece, Square, parse_square
from reconchess import utilities

def get_moves(board: Board) -> list[str]:
    moves: list[str] = list()

    for move in board.generate_pseudo_legal_moves():
        moves.append(move.uci())

    for move in utilities.without_opponent_pieces(board).generate_castling_moves():
        if not utilities.is_illegal_castle(board, move):
            moves.append(move.uci())

    moves.append("0000")

    return list(dict.fromkeys(sorted(moves)))

num_states = int(input())

states: list[Board] = list()

for i in range(num_states):
    states.append(Board(input()))

window = input()

def get_valid_boards(states: list[Board], window: str) -> list[str]:
    slices = window.split(";")

    valid_states: list[str] = list()

    for state in states:
        all_succeeded = True
        for slice in slices:
            square, piece = slice.split(":")
            
            if piece == "?":
                if state.piece_at(Square(parse_square(square))) is not None:
                    all_succeeded = False
                    break
            else:
                if Piece.from_symbol(piece) != state.piece_at(Square(parse_square(square))):
                    all_succeeded = False
                    break
        
        if all_succeeded: 
            valid_states.append(state.fen())

    return list(dict.fromkeys(sorted(valid_states)))

for state in get_valid_boards(states, window):
    print(state)
    