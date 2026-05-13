import random
import chess
import chess.engine
from reconchess import Player, Color, WinReason, GameHistory, utilities

class MyGoat(Player):
    def __init__(self):
        self.engine = chess.engine.SimpleEngine.popen_uci('./stockfish.exe', setpgrp=True)
        self.possible_states = set()
        self.color = None


    def handle_game_start(self, color: Color, board: chess.Board, opponent_name: str):
        self.color = color
        self.possible_states = {board.fen()} 


    def handle_opponent_move_result(self, captured_my_piece: bool, capture_square: chess.Square):
        new_possible_states = set()
        
        for fen in self.possible_states:
            board = chess.Board(fen)
            board.turn = not self.color
            
            for move in self.get_legal_moves(board):

                if captured_my_piece:
                    if move.to_square != capture_square: continue 

                    # Check there is piece at square
                    if board.piece_at(move.to_square) is None or board.piece_at(move.to_square).color != self.color: continue

                else:
                    # no piece captured so nothing happens
                    if move != chess.Move.null() and board.piece_at(move.to_square) is not None and board.piece_at(move.to_square).color == self.color: continue
                
                
                # Add new move and update states
                new_board = board.copy()
                new_board.push(move)
                new_possible_states.add(new_board.fen())
                
        self.possible_states = new_possible_states

    def handle_sense_result(self, sense_result: list[tuple[chess.Square, chess.Piece]]):
        new_possible_states = set()
        
        for fen in self.possible_states:
            board = chess.Board(fen)
            is_consistent = True
            
            # Check every square we sensed
            for square, piece in sense_result:
                # simulated board does not align with whats real, so exit
                if board.piece_at(square) != piece:
                    is_consistent = False
                    break
                    
            if is_consistent:
                new_possible_states.add(fen)
                
        self.possible_states = new_possible_states


    def handle_move_result(self, requested_move: chess.Move, taken_move: chess.Move, captured_opponent_piece: bool, capture_square: chess.Square):
        new_possible_states = set()
        
        for fen in self.possible_states:
            board = chess.Board(fen)
            board.turn = self.color
            
            if taken_move is not None: 
                board.push(taken_move)
            else:
                board.push(chess.Move.null())
                
            new_possible_states.add(board.fen())
            
        self.possible_states = new_possible_states

    def choose_sense(self, sense_actions: list[chess.Square], move_actions: list[chess.Move], seconds_left: float) -> chess.Square:
        valid_squares = []

        for square in sense_actions:
            file = chess.square_file(square)
            rank = chess.square_file(square)

            if 1 <= file <= 6 and 1 <= rank <= 6: 
                valid_squares.append(square)

        if not valid_squares: valid_squares = sense_actions()

        return random.choice(valid_squares)

    def choose_move(self, move_actions: list[chess.Move], seconds_left: float) -> chess.Move:
        # Hard limit on explorable states
        if len(self.possible_states) > 10000:
            self.possible_states = set(random.sample(list(self.possible_states), 10000))
            
        N = len(self.possible_states)
        if N == 0: return random.choice(move_actions)
            
        time_limit = float(10.0 / N)
        move_votes = {}
        
        for fen in self.possible_states:
            board = chess.Board(fen)
            board.turn = self.color
            
            enemy_king_square = board.king(not self.color)
            chosen_move = None
            
            # Attack
            if enemy_king_square is not None:
                attackers = board.attackers(self.color, enemy_king_square)

                if attackers:
                    attacker_square = attackers.pop()
                    chosen_move = chess.Move(attacker_square, enemy_king_square)
                    
            # Ask Stockfish for move
            if chosen_move is None:
                try:
                    board.clear_stack()
                    result = self.engine.play(board, chess.engine.Limit(time=time_limit))

                    if result.move is not None: chosen_move = result.move

                except Exception:
                    pass
                    
            if chosen_move is not None:
                move_uci = chosen_move.uci()
                move_votes[move_uci] = move_votes.get(move_uci, 0) + 1
                
        if not move_votes:
            return random.choice(move_actions)
            
        # Majority votes - tie broken with alphabetical ordering
        max_votes = max(move_votes.values())
        tied_moves = [move for move, votes in move_votes.items() if votes == max_votes]
        best_move_uci = sorted(tied_moves)[0]
        
        return chess.Move.from_uci(best_move_uci)


    def handle_game_end(self, winner_color: Color, win_reason: WinReason, game_history: GameHistory):
        self.engine.quit()


    def get_legal_moves(self, board: chess.Board) -> list[chess.Move]:
        moves = list(board.generate_pseudo_legal_moves())

        for move in utilities.without_opponent_pieces(board).generate_castling_moves():

            if not utilities.is_illegal_castle(board, move): moves.append(move)
        
        moves.append(chess.Move.null())

        return moves
    
