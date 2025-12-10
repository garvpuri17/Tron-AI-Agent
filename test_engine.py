import numpy as np
import time

from tron_engine import TronEngine
from case_closed_game import Direction

def main():
    eng = TronEngine()

    # empty 18x20 board
    H, W = 18, 20
    board = np.zeros((H, W), dtype=int)

    # fake trails
    my_trail = [(1, 2), (2, 2)]
    opp_trail = [(17, 15), (16, 15)]

    my_pos = my_trail[-1]
    opp_pos = opp_trail[-1]

    start = time.time()
    move, boost = eng.decide_move(
        board=board,
        my_pos=my_pos,
        opp_pos=opp_pos,
        my_trail=my_trail,
        opp_trail=opp_trail,
        current_direction=Direction.RIGHT,
        my_boosts=3,
        opp_boosts=3,
        turn_count=5,
        time_limit=1.0,  # short just for test
    )
    dur = time.time() - start

    print("Move:", move, "Boost:", boost, f"Time: {dur:.3f}s")


if __name__ == "__main__":
    main()
