from reconchess import play_local_game
from reconchess.bots.random_bot import RandomBot
from reconchess.bots.trout_bot import TroutBot
import random_sensing

def run_match(white_name, white_class, black_name, black_class):

    winner, win_reason, history = play_local_game(white_class(), black_class())

    print(f"--> Winner: {winner.name} | Reason: {win_reason.name}\n")
    return winner

if __name__ == "__main__":
    print("--- STARTING BASELINE TOURNAMENT ---\n")
    
    results = []
    
    # Against Random
    results.append(run_match("RandomSensing", random_sensing.RandomSensingAgent, "RandomBot", RandomBot))
    results.append(run_match("RandomBot", RandomBot, "RandomSensing", random_sensing.RandomSensingAgent))
    
    # Agaisnt Trout
    results.append(run_match("RandomSensing", random_sensing.RandomSensingAgent, "TroutBot", TroutBot))
    results.append(run_match("TroutBot", TroutBot, "RandomSensing", random_sensing.RandomSensingAgent))
    
    print("--- TOURNAMENT COMPLETE ---")