  # Tron AI Agent (TAMU Datathon 2025)

  This project implements a competitive autonomous agent for a Tron style grid game used in the TAMU Datathon 2025 environment.  
  The agent evaluates the game board, predicts opponent movement, and chooses actions using deep search and territory control heuristics under strict time limits.

  The repository includes:
  - A complete game engine for a two player Tron variant
  - A Flask based HTTP agent service used by the competition judge
  - A search engine with iterative deepening alpha beta, transposition tables, a Voronoi style territory heuristic, and an opening book
  - Local tools for testing, benchmarking, and tournament style evaluation

  ---

  ## Game Overview

  The game is a head to head variant of Tron or light cycle style snakes.

  - The board is a toroidal grid
    - Height: 18 cells
    - Width: 20 cells
    - Toroidal means that moving off the left edge wraps to the right edge, and moving off the top wraps to the bottom, and vice versa.
    - This is implemented in `GameBoard` using modular arithmetic on coordinates.
  - There are two agents on the same board
    - `agent1` starts at position `(1, 2)` facing right.
    - `agent2` starts at position `(17, 15)` facing left.
    - These defaults come from the `Game` class in `case_closed_game.py`.
  - Movement and trails
    - On each turn, both agents choose a direction (up, down, left, or right).
    - Agents move into the next cell, and their previous positions become part of a permanent trail.
    - The trail is stored as a deque of positions and every trail cell is marked on the board as occupied.
    - Trails never disappear. Every step makes the board tighter and space more valuable.
  - Collisions
    - If an agent moves into a cell that already contains any trail or an occupied cell, that agent dies.
    - If both agents die on the same turn, the game is a draw.
    - If one agent dies and the other survives, the surviving agent wins.
  - Boosts
    - Each agent starts with three boosts.
    - A boost allows an agent to move two steps in a single turn.
    - Boosts are optional per move and are consumed when used.
    - Boost logic and safety checks are implemented in the `Agent.move` method in `case_closed_game.py`.
  - Turn limit and scoring
    - The game has a maximum of 200 turns.
    - If both agents are still alive after 200 turns, the winner is decided by trail length.
      - Longer trail wins.
      - Equal trail length results in a draw.

  In short, the agents are competing to control space on an 18 by 20 wraparound grid while avoiding collisions with walls and each other. The optimal strategy is not simply to survive the next move, but to maximize future reachable territory while restricting the opponent.

  ---

  ## System Architecture

  The project is split into three core layers:

  1. Game engine and rules  
  2. HTTP based agent interface used by the judge  
  3. Search and evaluation engine that decides moves

  ### 1. Game Engine (`case_closed_game.py`)

  This module defines the rules and mechanics of the Tron style game.

  - `GameBoard`
    - Manages the 2D grid.
    - Tracks which cells are empty or occupied by agent trails.
    - Provides toroidal movement using wraparound logic in `wrap_position`.
    - Supports spawning agents, setting cell state, and printing the board.
  - `Direction`
    - Enum of four directions: up, down, left, right.
    - Used both by the game engine and the AI engine.
  - `Agent`
    - Keeps track of an individual agent’s trail, direction, alive status, length, and remaining boosts.
    - `move` method:
      - Validates boosts and decrements the boost counter if used.
      - Prevents 180 degree turns directly into the opposite of the current direction.
      - Applies movement one or two times depending on boost usage.
      - Applies toroidal wrapping.
      - Detects collisions with walls, own trail, or the other agent’s trail.
      - Updates the board with the new trail cells.
  - `Game`
    - Holds one shared `GameBoard` and two `Agent` instances.
    - Handles turn stepping with `step(dir1, dir2, boost1, boost2)`.
    - Enforces the 200 turn limit and decides the winner on trail length if needed.
    - Reports game results using a `GameResult` enum (agent 1 win, agent 2 win, draw).

  The AI does not directly modify `Game`. Instead, it is given board state derived from this engine by the judge side logic.

  ### 2. HTTP Agent Interface (`agent.py`)

  The competition environment runs agents as HTTP services.  

  `agent.py` exposes a Flask API that the judge calls during a game.

  - Metadata
    - `PARTICIPANT` and `AGENT_NAME` identify the participant and agent.
  - State handling
    - A global `game_state` dict stores the most recent state pushed by the judge.
    - A threading lock protects concurrent reads and writes.
  - Endpoints
    - `/` or `/health`
      - Used by the judge to verify the agent is up and to read metadata.
    - `/update-state`
      - Called by the judge each turn.
      - Receives JSON containing:
        - The board grid as a list of lists.
        - The full trails for both agents.
        - Current boosts remaining.
        - Current turn count.
      - This state is stored and becomes the input to the decision engine.
    - `/move`
      - Called by the judge when a move is required.
      - Accepts a `player_number` query parameter to indicate whether the agent should consider itself player 1 or player 2.
      - Extracts:
        - `my_trail` and `opp_trail`
        - `my_boosts` and `opp_boosts`
        - `current_direction` inferred from the last two positions in the trail
        - The underlying board as a NumPy array
      - Calls `TronEngine.decide_move` with all of this information.
      - Returns a move string in the format:
        - `"UP"`, `"DOWN"`, `"LEFT"`, `"RIGHT"`
        - Or `"UP:BOOST"` if a boost is used.
    - `/game-over`
      - Called by the judge at the end of a game.
      - Used to reset or log information if desired.

  This HTTP layer isolates the game environment from the decision logic and makes it easy to run the same AI locally and in the competition.

  ### 3. Search and Evaluation Engine (`tron_engine.py`)

  `TronEngine` is the core of the AI decision making.

  High level responsibilities:

  - Convert board state and trails into a search friendly representation.
  - Decide whether the two agents share the same reachable region or are separated.
  - Use iterative deepening alpha beta search to evaluate moves.
  - Use a Voronoi style flood fill when both players share space.
  - Use chamber size differences when agents have been separated into distinct regions.
  - Decide intelligently when to use boosts.

  Key components and techniques:

  - Board representation
    - The board is a binary NumPy array with 1 indicating a blocked or occupied cell and 0 indicating free space.
    - Agent positions are stored as tuples `(x, y)`.
  - Opening book
    - `_build_opening_book` defines hard coded opening move sequences for specific starting positions, such as `(1, 2)` versus `(17, 15)` or `(18, 15)`.
    - In the early turns, if the positions match an entry in the book, the engine will follow the precomputed line as long as it remains valid.
    - This gives fast and strong early play before search takes over.
  - Iterative deepening and time management
    - `decide_move` receives a `time_limit` and computes a per turn time budget with a safety margin.
    - The engine starts with depth 1 and repeatedly increases the search depth.
    - At each depth, if time remains, it computes a best move using alpha beta.
    - At any point if the deadline is reached, the engine returns the best move found at the highest completed depth.
    - Time utilization is adaptive based on the turn count and game phase. For example:
      - Early moves use a small fraction of the budget.
      - Endgame when the board is tight can use up to roughly 85 percent of the time limit.
  - Alpha beta search
    - `_alpha_beta` implements a standard minimizing and maximizing recursive search with alpha and beta bounds.
    - The root call loops over ordered candidate moves for the current player, applies the move, and evaluates the reply space for the opponent.
    - At each node, the engine:
      - Computes legal moves using `_get_valid_moves_raw`.
      - Checks for forced wins or losses when move sets are empty.
      - Uses transposition table lookups before recursing.
      - Uses move ordering to search promising moves first.
  - Transposition table and killer moves
    - The transposition table uses a hashed key based on:
      - The board bytes
      - Player positions
      - Search depth
      - Whether this is a maximizing or minimizing node.
    - The table stores `(score, depth)` and is implemented as an `OrderedDict` with a maximum size.
    - Recently used entries are kept while old ones are evicted.
    - `_order_moves_killer` and related logic prioritize moves that previously caused strong cutoffs. This increases pruning efficiency.
  - Separation detection and heuristics
    - `_same_region` and `_flood_fill` are used to determine whether both players are still in a single connected region of free space or separated by walls and trails.
    - If separated:
      - The engine computes the size of each player’s free region by counting reachable cells.
      - The evaluation returns a very large positive or negative score depending on which player has more space.
      - This simulates the idea that once separated, the game is determined mostly by who has the larger chamber.
    - If not separated:
      - The engine uses a Voronoi style heuristic:
        - It performs simultaneous breadth first search from both agents.
        - Each empty cell is assigned to the agent that can reach it in fewer steps.
        - The difference between cells closer to the agent and cells closer to the opponent becomes part of the score.
      - Additional terms can include mobility, distance weighting, and centrality to avoid getting trapped on the extreme edges.
  - Boost logic
    - The engine decides whether to use boosts through helper functions that consider:
      - Remaining boosts for both players.
      - Turn count.
      - Local board density and escape options.
    - Early and mid game tends to be conservative with boosts.
    - In tight late game windows a boost can be used aggressively to reach key territory or to escape a near trap.

  Overall, `TronEngine` combines hard coded opening lines, region based heuristics, Voronoi territory estimation, and a search engine tuned to the time constraints and grid size.

  ---

  ## Local Judge and Testing

  Several scripts support local experimentation.

  ### `judge_engine.py`

  - Connects to two HTTP agents using their base URLs.
  - Pings each agent to retrieve its metadata and confirm it is live.
  - For each turn:
    - Builds a game state from a `Game` instance in `case_closed_game.py`.
    - Sends state updates to both agents.
    - Requests a move from each agent’s `/move` endpoint.
    - Applies the moves on the underlying game.
    - Detects termination conditions and prints the result.
  - Enforces a per move timeout and treats unresponsive agents as failures.

  This is effectively the same role the online judge plays in the Datathon environment.

  ### `sample_agent.py`

  - Provides a baseline opponent with much simpler decision logic.
  - Useful for testing that the main agent does not crash and can consistently beat naive strategies.

  ### `local-tester.py`

  - Allows running agents locally without the full remote tournament setup.
  - Can be used to run multiple games, collect win rates, and smoke test changes to the search engine.

  ### `test_engine.py`

  - Contains targeted tests and sanity checks for the decision engine.
  - Examples include:
    - Calling `TronEngine.decide_move` with handcrafted board states.
    - Measuring runtime and verifying the result is returned within constraints.
    - Ensuring that moves returned are legal and do not immediately self collide.

  ### `batch_process.py`

  - Used for batch simulations or tournaments.
  - Can be wired to run many matches between different versions of the agent and aggregate statistics.

  ---

  ## How to Run

  Basic setup on Windows (PowerShell):

  ```powershell
  git clone https://github.com/garvpuri17/Tron-AI-Agent.git
  cd Tron-AI-Agent
  python -m venv .venv
  .\.venv\Scripts\activate
  pip install -r requirements.txt
