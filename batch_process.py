import subprocess

GAMES = 30
p1_wins = 0
p2_wins = 0
draws = 0

for i in range(GAMES):
    print(f"=== GAME {i+1} ===")
    # run judge_engine.py and capture output
    result = subprocess.run(
        ["python", "judge_engine.py"],
        capture_output=True,
        text=True
    )
    out = result.stdout

    if "Player 1 wins" in out:
        p1_wins += 1
    elif "Player 2 wins" in out:
        p2_wins += 1
    else:
        draws += 1

print("\nRESULTS")
print("P1 (us):", p1_wins)
print("P2 (sample):", p2_wins)
print("Draws:", draws)
print("Total games:", GAMES)