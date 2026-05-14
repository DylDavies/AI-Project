import os
from reconchess import play_local_game
from reconchess.bots.trout_bot import TroutBot
from improved_agent import MyGoat
from observer import PrintObserver, LiveObserver, CompositeObserver

if __name__ == "__main__":
    os.environ["STOCKFISH_EXECUTABLE"] = os.path.join(os.path.dirname(__file__), "stockfish.exe")

    agent = MyGoat(observer=CompositeObserver(PrintObserver(), LiveObserver()))

    print("Starting match: MyGoat vs TroutBot...")
    winner, win_reason, history = play_local_game(agent, TroutBot())

    print(f"\nGame Over!")
    print(f"Winner: {winner}")
    print(f"Reason: {win_reason}")

    history.save("test_match_history.json")
    print("Saved replay to test_match_history.json")
