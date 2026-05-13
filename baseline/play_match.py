from reconchess import play_local_game
from reconchess.bots.random_bot import RandomBot
from reconchess.bots.trout_bot import TroutBot

from goat import MyGoat 

if __name__ == "__main__":
    print("Starting match: MyAgent vs RandomBot...")
    
    # Run the game locally
    winner, win_reason, history = play_local_game(MyGoat(), RandomBot())
    
    print(f"\nGame Over!")
    print(f"Winner: {winner}")
    print(f"Reason: {win_reason}")
    
    #
    history.save("test_match_history.json")
    print("Saved replay to test_match_history.json")