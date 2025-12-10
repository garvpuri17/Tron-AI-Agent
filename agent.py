# agent.py
"""
Championship Agent - Optimized for 1st Place
DO NOT RENAME THIS FILE - Must be named agent.py for submission
"""
from flask import Flask, request, jsonify
import threading
import numpy as np

from tron_engine import TronEngine
from case_closed_game import Direction

# REQUIRED: Update these with your details
PARTICIPANT = "Tilak Varma FC"
AGENT_NAME = "Tilak Supreme"

app = Flask(__name__)

# shared state
game_state = {}
state_lock = threading.Lock()

# Initialize the engine
ENGINE = TronEngine()


def infer_direction(trail, default_dir: Direction) -> Direction:
    """
    Infer current direction from last 2 trail points.
    Board is 20x18 torus (wraparound).
    """
    if not trail or len(trail) < 2:
        return default_dir

    (x1, y1), (x2, y2) = trail[-2], trail[-1]
    dx = x2 - x1
    dy = y2 - y1

    # Handle torus wraparound
    W, H = 20, 18
    if dx > 1:
        dx = -1
    elif dx < -1:
        dx = 1
    if dy > 1:
        dy = -1
    elif dy < -1:
        dy = 1

    if dx == 1:
        return Direction.RIGHT
    if dx == -1:
        return Direction.LEFT
    if dy == 1:
        return Direction.DOWN
    if dy == -1:
        return Direction.UP
    return default_dir


@app.route("/", methods=["GET"])
def info():
    """
    REQUIRED ENDPOINT: Basic health/info check used by judge.
    Returns participant and agent_name.
    """
    return jsonify({"participant": PARTICIPANT, "agent_name": AGENT_NAME}), 200


@app.route("/send-state", methods=["POST"])
def receive_state():
    """
    REQUIRED ENDPOINT: Judge sends current game state via POST.
    We store it for use in send_move.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "no json"}), 400

    with state_lock:
        game_state.clear()
        game_state.update(data)

    return jsonify({"status": "state received"}), 200


@app.route("/send-move", methods=["GET"])
def send_move():
    """
    REQUIRED ENDPOINT: Judge requests our move via GET.
    
    Query params from judge (optional):
    - player_number: 1 or 2
    - attempt_number: which attempt this is
    - random_moves_left: how many random moves we have left
    - turn_count: current turn number
    
    MUST return: {"move": "DIRECTION"} or {"move": "DIRECTION:BOOST"}
    Valid directions: UP, DOWN, LEFT, RIGHT
    """
    with state_lock:
        # Safety fallback if no state received yet
        if not game_state:
            return jsonify({"move": "RIGHT"}), 200

        board_list = game_state["board"]
        turn_count = game_state.get("turn_count", 0)
        player_number = request.args.get("player_number", default=1, type=int)

        # Extract our state based on player number
        if player_number == 1:
            my_trail = [tuple(p) for p in game_state.get("agent1_trail", [])]
            opp_trail = [tuple(p) for p in game_state.get("agent2_trail", [])]
            my_boosts = game_state.get("agent1_boosts", 0)
            opp_boosts = game_state.get("agent2_boosts", 0)
            current_dir = infer_direction(my_trail, Direction.RIGHT)
        else:
            my_trail = [tuple(p) for p in game_state.get("agent2_trail", [])]
            opp_trail = [tuple(p) for p in game_state.get("agent1_trail", [])]
            my_boosts = game_state.get("agent2_boosts", 0)
            opp_boosts = game_state.get("agent1_boosts", 0)
            current_dir = infer_direction(my_trail, Direction.LEFT)

    # Convert to numpy array for engine
    board_np = np.array(board_list, dtype=np.int8)

    # Get current positions
    if my_trail:
        my_pos = my_trail[-1]
    else:
        my_pos = (1, 2) if player_number == 1 else (17, 15)

    if opp_trail:
        opp_pos = opp_trail[-1]
    else:
        opp_pos = (17, 15) if player_number == 1 else (1, 2)

    # ADAPTIVE TIME LIMITS - Critical for avoiding timeouts!
    # Judge timeout is 4 seconds, we need buffer for network/Flask overhead
    if turn_count < 5:
        time_limit = 2.5  # Very fast for first moves to avoid timeout
    elif turn_count < 15:
        time_limit = 2.8  # Opening book handles this
    elif turn_count > 140:
        time_limit = 3.5  # Critical endgame - use maximum safe time
    elif turn_count > 100:
        time_limit = 3.3  # Late game complexity
    elif turn_count > 60:
        time_limit = 3.1  # Mid-late game
    else:
        time_limit = 2.9  # Early-mid game

    # Get move from our engine
    move_dir, use_boost = ENGINE.decide_move(
        board=board_np,
        my_pos=my_pos,
        opp_pos=opp_pos,
        my_trail=my_trail,
        opp_trail=opp_trail,
        current_direction=current_dir,
        my_boosts=my_boosts,
        opp_boosts=opp_boosts,
        turn_count=turn_count,
        time_limit=time_limit,
    )

    # Format move string
    move_str = move_dir.name
    if use_boost:
        move_str += ":BOOST"

    return jsonify({"move": move_str}), 200


@app.route("/end", methods=["POST"])
def end_game():
    """
    REQUIRED ENDPOINT: Judge notifies us that game ended.
    We acknowledge and return 200.
    """
    return jsonify({"status": "acknowledged"}), 200


if __name__ == "__main__":
    # Port can be overridden with PORT environment variable
    import os
    port = int(os.environ.get("PORT", "5008"))
    
    # IMPORTANT: Set debug=False for production/submission
    # Debug mode can cause issues in containerized environments
    app.run(host="0.0.0.0", port=port, debug=False)