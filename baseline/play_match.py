import os
from reconchess import play_local_game
from reconchess.bots.trout_bot import TroutBot
from improved_agent import MyGoat
from observer import PrintObserver, LiveObserver, CompositeObserver
STOCKFISH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stockfish.exe")

if __name__ == "__main__":
    os.environ["STOCKFISH_EXECUTABLE"] = STOCKFISH

    agent = MyGoat(LiveObserver()) # remove live observer is you dont wish to see the board

    print("Starting match: MyGoat vs TroutBot...")
    winner, win_reason, history = play_local_game(TroutBot, agent)

    print(f"\nGame Over!")
    print(f"Winner: {winner}")
    print(f"Reason: {win_reason}")

    history.save("test_match_history.json")
    print("Saved replay to test_match_history.json")
