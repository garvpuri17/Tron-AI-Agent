**Tron AI Agent (TAMU Datathon 2025)
**
A competitive autonomous Tron agent built to evaluate game state, predict opponent paths, and choose optimal movement using deep search and territory control logic. Designed for stable decision making under strict time constraints and adversarial board conditions.

TLDR for Reviewers

This project implements a full decision-making engine for the Tron game. The agent reads the current board, simulates future moves for both itself and the opponent, evaluates reachable space using a Voronoi-style territory heuristic, and selects the move associated with the strongest long-term survival outlook.

The core system uses iterative deepening alpha-beta search with transposition table caching and move ordering to ensure speed and depth. The project is structured for testing, benchmarking, and tournament-style evaluation.

Technical Summary

Key capabilities:

Iterative deepening search for predictable time-bounded move selection
Alpha-beta pruning to reduce unnecessary search exploration
Transposition table caching to re-use previously evaluated board states
Move ordering and prioritization heuristics for faster branch resolution
Voronoi-inspired territory evaluation for long-term space control
Local judge engine for head-to-head agent competition and evaluation
Modular structure suitable for future optimization or ML integration
Designed for clarity, reproducibility, extensibility, and competitive play.

File Structure Overview
File	Purpose
tron_engine.py	Core decision logic including search, heuristics, and evaluation
agent.py	Primary executable agent used for gameplay
judge_engine.py	Match referee used to run two agents against each other
sample_agent.py	Baseline opponent for benchmarking
local-tester.py	Local simulation and testing harness
test_engine.py	Quick internal validation for move output correctness
batch_process.py	Batch game execution and result collection
requirements.txt	Python dependency list
Dockerfile	Container configuration for agent execution

Each component is documented internally for maintainability.

How to Run

Clone and set up environment:

git clone https://github.com/garvpuri17/Tron-AI-Agent.git
cd Tron-AI-Agent
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt


Start the main agent:
python agent.py


Start a baseline opponent:
python sample_agent.py


Run the judge to observe matches:
setx PLAYER1_URL "http://localhost:5008"
setx PLAYER2_URL "http://localhost:5009"
python judge_engine.py


This will print the match result, move sequence, and termination state to the console.

Potential Extensions

Monte-Carlo rollouts for tie-break scenarios

Reinforcement learning self-play model for adaptive strategy

Visualization framework for replay and analysis

Opening book generation through large-scale simulation
