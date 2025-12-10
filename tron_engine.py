# tron_engine.py
"""
Tron Decision Engine - CHAMPIONSHIP VERSION
Optimized for 1st place finish - 350+ competitors
"""

import time
from collections import deque, OrderedDict
from typing import Tuple, List, Dict, Optional
import numpy as np
from case_closed_game import Direction

Pos = Tuple[int, int]


class TronEngine:
    def __init__(self):
        self.directions = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]

        # LRU transposition table
        self.tt: "OrderedDict[int, Tuple[float, int]]" = OrderedDict()
        self.max_tt = 75000

        # Killer moves
        self.killer_moves: Dict[int, List[Direction]] = {}

        # 12-move book
        self.opening_book = self._build_opening_book()

    def _build_opening_book(self) -> Dict:
        book = {}

        book[((1, 2), (17, 15))] = [
            Direction.RIGHT, Direction.RIGHT, Direction.DOWN,
            Direction.RIGHT, Direction.RIGHT, Direction.DOWN,
            Direction.RIGHT, Direction.DOWN, Direction.RIGHT,
            Direction.DOWN, Direction.RIGHT, Direction.RIGHT
        ]

        book[((1, 2), (18, 15))] = [
            Direction.RIGHT, Direction.RIGHT, Direction.RIGHT,
            Direction.DOWN, Direction.RIGHT, Direction.DOWN,
            Direction.RIGHT, Direction.RIGHT, Direction.DOWN,
            Direction.RIGHT, Direction.DOWN, Direction.RIGHT
        ]

        book[((17, 15), (1, 2))] = [
            Direction.LEFT, Direction.LEFT, Direction.UP,
            Direction.LEFT, Direction.LEFT, Direction.UP,
            Direction.LEFT, Direction.UP, Direction.LEFT,
            Direction.UP, Direction.LEFT, Direction.LEFT
        ]

        book[((18, 15), (1, 2))] = [
            Direction.LEFT, Direction.LEFT, Direction.LEFT,
            Direction.UP, Direction.LEFT, Direction.UP,
            Direction.LEFT, Direction.LEFT, Direction.UP,
            Direction.LEFT, Direction.UP, Direction.LEFT
        ]

        return book

    # ================= PUBLIC ENTRY =================
    def decide_move(
        self,
        board: np.ndarray,
        my_pos: Pos,
        opp_pos: Pos,
        my_trail: List,
        opp_trail: List,
        current_direction: Direction,
        my_boosts: int,
        opp_boosts: int,
        turn_count: int,
        time_limit: float = 3.5,
    ) -> Tuple[Direction, bool]:
        start = time.time()

        # SMART adaptive time utilization - but with safety buffer for network
        # Key insight: use more time when it matters, but ALWAYS leave buffer
        if turn_count < 3:
            # Critical early moves - be FAST to avoid timeout
            time_utilization = 0.50
        elif turn_count < 12:
            # Opening book handles this, but just in case
            time_utilization = 0.55
        elif turn_count < 20:
            # CRITICAL: First real searches after opening book - be CONSERVATIVE
            time_utilization = 0.60
        elif turn_count < 40:
            # Early-mid game - still conservative
            time_utilization = 0.68
        elif turn_count > 140:
            # Critical endgame - use maximum safe time
            time_utilization = 0.85
        elif turn_count > 120:
            # Late game advantage seeking
            time_utilization = 0.82
        elif turn_count > 100:
            # Late game - complex positions
            time_utilization = 0.78
        elif turn_count > 60:
            # Mid game - balanced
            time_utilization = 0.72
        else:
            # Mid game
            time_utilization = 0.70

        # CRITICAL: Network overhead means we MUST have buffer
        # Judge timeout is 4 seconds, but Flask + JSON + network takes time
        deadline = start + time_limit * time_utilization

        H, W = board.shape

        # FIXED: Opening book from turn 0 (not turn 1!)
        if 0 <= turn_count <= 11 and my_trail and opp_trail:
            key = (tuple(my_trail[0]), tuple(opp_trail[0]))
            seq = self.opening_book.get(key)
            idx = turn_count
            if seq and idx < len(seq):
                book_move = seq[idx]
                if self._is_valid_move(board, my_pos, book_move, current_direction):
                    return book_move, False

        # legal moves
        moves = self._get_valid_moves(board, my_pos, current_direction)
        if not moves:
            return current_direction, False
        if len(moves) == 1:
            return moves[0], self._should_boost_aggressive(
                board, my_pos, opp_pos, my_boosts, opp_boosts, turn_count
            )

        # separated?
        separated = not self._same_region(board, my_pos, opp_pos, H, W)

        best_move = moves[0]
        best_score = -1e9

        ordered_moves = self._order_moves_killer(board, my_pos, opp_pos, moves, turn_count)

        # Adaptive depth based on game phase and separation
        if turn_count < 5:
            max_depth_cap = 8  # Shallow for speed in early game
        elif turn_count < 15:
            max_depth_cap = 10
        elif separated and turn_count > 120:
            max_depth_cap = 16  # Deep when separated and late game
        elif separated:
            max_depth_cap = 10
        elif turn_count > 120:
            max_depth_cap = 13  # Deep search in critical endgame
        elif turn_count > 100:
            max_depth_cap = 12
        else:
            max_depth_cap = 11

        for depth in range(3, max_depth_cap + 1):
            if time.time() > deadline:
                break

            depth_best_move = None
            depth_best_score = -1e9

            for mv in ordered_moves:
                if time.time() > deadline:
                    break

                nx, ny = self._apply_direction(my_pos, mv, H, W)
                child_board = board.copy()
                child_board[my_pos[1], my_pos[0]] = 1

                if separated:
                    val = self._single_player_solve(child_board, (nx, ny), depth - 1, deadline)
                else:
                    val = self._alpha_beta(
                        child_board,
                        (nx, ny),
                        opp_pos,
                        depth - 1,
                        -1e9,
                        1e9,
                        False,
                        deadline,
                        turn_count,
                    )

                if val > depth_best_score:
                    depth_best_score = val
                    depth_best_move = mv

            if depth_best_move is not None:
                best_move = depth_best_move
                best_score = depth_best_score

                km = self.killer_moves.setdefault(turn_count, [])
                if best_move in km:
                    km.remove(best_move)
                km.insert(0, best_move)
                if len(km) > 2:
                    km.pop()

            # Early exit if we found a winning move
            if best_score > 5000:
                break

        use_boost = self._should_boost_aggressive(
            board, my_pos, opp_pos, my_boosts, opp_boosts, turn_count
        )

        return best_move, use_boost

    # ================= SEARCH =================
    def _alpha_beta(
        self,
        board: np.ndarray,
        my_pos: Pos,
        opp_pos: Pos,
        depth: int,
        alpha: float,
        beta: float,
        maximizing: bool,
        deadline: float,
        turn_count: int,
    ) -> float:
        if time.time() > deadline:
            return 0.0

        H, W = board.shape

        my_moves = self._get_valid_moves_raw(board, my_pos, H, W)
        opp_moves = self._get_valid_moves_raw(board, opp_pos, H, W)

        if not my_moves and not opp_moves:
            return 0.0
        if not my_moves:
            return -100000.0
        if not opp_moves:
            return 100000.0

        tt_key = self._tt_key(board, my_pos, opp_pos, depth, maximizing)
        if tt_key in self.tt:
            stored_score, stored_depth = self.tt[tt_key]
            if stored_depth >= depth:
                self.tt.move_to_end(tt_key)
                return stored_score

        if depth == 0:
            val = self._evaluate_position(board, my_pos, opp_pos, turn_count)
            self._tt_store(tt_key, val, depth)
            return val

        if maximizing:
            value = -1e9
            ordered = self._order_moves_killer(board, my_pos, opp_pos, my_moves, turn_count)
            for mv in ordered:
                nx, ny = self._apply_direction(my_pos, mv, H, W)
                cb = board.copy()
                cb[my_pos[1], my_pos[0]] = 1
                val = self._alpha_beta(cb, (nx, ny), opp_pos,
                                       depth - 1, alpha, beta, False, deadline, turn_count)
                value = max(value, val)
                alpha = max(alpha, val)
                if beta <= alpha:
                    break
            self._tt_store(tt_key, value, depth)
            return value
        else:
            value = 1e9
            ordered = self._order_moves_killer(board, opp_pos, my_pos, opp_moves, turn_count)
            for mv in ordered:
                nx, ny = self._apply_direction(opp_pos, mv, H, W)
                cb = board.copy()
                cb[opp_pos[1], opp_pos[0]] = 1
                val = self._alpha_beta(cb, my_pos, (nx, ny),
                                       depth - 1, alpha, beta, True, deadline, turn_count)
                value = min(value, val)
                beta = min(beta, val)
                if beta <= alpha:
                    break
            self._tt_store(tt_key, value, depth)
            return value

    def _single_player_solve(self, board: np.ndarray, pos: Pos, depth: int, deadline: float) -> float:
        if time.time() > deadline or depth == 0:
            return float(self._flood_fill(board, pos, full=True))

        H, W = board.shape
        moves = self._get_valid_moves_raw(board, pos, H, W)
        if not moves:
            return float(self._flood_fill(board, pos, full=True))

        best = -1e9
        for mv in moves:
            nx, ny = self._apply_direction(pos, mv, H, W)
            cb = board.copy()
            cb[pos[1], pos[0]] = 1
            val = self._single_player_solve(cb, (nx, ny), depth - 1, deadline)
            best = max(best, val)
        return best

    # ================= EVAL / HELPERS =================
    def _evaluate_position(self, board: np.ndarray, my_pos: Pos, opp_pos: Pos, turn_count: int) -> float:
        H, W = board.shape
        separated = not self._same_region(board, my_pos, opp_pos, H, W)

        if separated:
            my_chamber = self._flood_fill(board, my_pos, full=True)
            opp_chamber = self._flood_fill(board, opp_pos, full=True)
            diff = my_chamber - opp_chamber
            if diff > 0:
                return 50000.0 + diff * 1000.0
            elif diff < 0:
                return -50000.0 + diff * 1000.0
            else:
                return 0.0

        # Dynamic weights based on game phase
        if turn_count < 40:
            vor_weight, mob_weight, space_weight = 20.0, 8.0, 12.0
        elif turn_count < 120:
            vor_weight, mob_weight, space_weight = 25.0, 10.0, 5.0
        else:
            vor_weight, mob_weight, space_weight = 35.0, 15.0, 8.0

        score = 0.0
        vor = self._voronoi_advantage(board, my_pos, opp_pos)
        score += vor * vor_weight

        my_mob = len(self._get_valid_moves_raw(board, my_pos, H, W))
        opp_mob = len(self._get_valid_moves_raw(board, opp_pos, H, W))
        score += (my_mob - opp_mob) * mob_weight

        my_space = self._flood_fill(board, my_pos, limit=70)
        opp_space = self._flood_fill(board, opp_pos, limit=70)
        score += (my_space - opp_space) * space_weight

        score += self._articulation_pressure(board, my_pos, opp_pos)

        if turn_count < 40:
            cx, cy = W // 2, H // 2
            my_dist = self._torus_dist(my_pos, (cx, cy), W, H)
            opp_dist = self._torus_dist(opp_pos, (cx, cy), W, H)
            score += (opp_dist - my_dist) * 3.0

        return score

    def _voronoi_advantage(self, board: np.ndarray, my_pos: Pos, opp_pos: Pos) -> int:
        H, W = board.shape
        my_dist = {my_pos: 0}
        opp_dist = {opp_pos: 0}
        mq = deque([my_pos])
        oq = deque([opp_pos])
        MAX_D = 20

        while mq:
            x, y = mq.popleft()
            d = my_dist[(x, y)]
            if d >= MAX_D:
                continue
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = (x + dx) % W, (y + dy) % H
                if board[ny, nx] == 0 and (nx, ny) not in my_dist:
                    my_dist[(nx, ny)] = d + 1
                    mq.append((nx, ny))

        while oq:
            x, y = oq.popleft()
            d = opp_dist[(x, y)]
            if d >= MAX_D:
                continue
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = (x + dx) % W, (y + dy) % H
                if board[ny, nx] == 0 and (nx, ny) not in opp_dist:
                    opp_dist[(nx, ny)] = d + 1
                    oq.append((nx, ny))

        my_t = 0
        opp_t = 0
        for cell, d in my_dist.items():
            od = opp_dist.get(cell)
            if od is None or d < od:
                my_t += 1
            elif od < d:
                opp_t += 1
        return my_t - opp_t

    def _articulation_pressure(self, board: np.ndarray, my_pos: Pos, opp_pos: Pos) -> float:
        H, W = board.shape
        if not self._same_region(board, my_pos, opp_pos, H, W):
            return 0.0

        my_front = self._frontier(board, my_pos, steps=3)
        opp_front = self._frontier(board, opp_pos, steps=3)
        boundary = my_front & opp_front
        if not boundary:
            return 0.0

        best = 0.0
        for bx, by in list(boundary)[:6]:
            my_d = self._torus_dist(my_pos, (bx, by), W, H)
            opp_d = self._torus_dist(opp_pos, (bx, by), W, H)
            best = max(best, (opp_d - my_d) * 8.0)
        return best

    def _frontier(self, board: np.ndarray, start: Pos, steps: int = 3) -> set:
        H, W = board.shape
        cur = {start}
        visited = {start}
        for _ in range(steps):
            nxt = set()
            for x, y in cur:
                for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nx, ny = (x + dx) % W, (y + dy) % H
                    if board[ny, nx] == 0 and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        nxt.add((nx, ny))
            cur = nxt
            if not cur:
                break
        return visited

    def _should_boost_aggressive(
        self,
        board: np.ndarray,
        my_pos: Pos,
        opp_pos: Pos,
        my_boosts: int,
        opp_boosts: int,
        turn_count: int,
    ) -> bool:
        if my_boosts <= 0:
            return False

        H, W = board.shape
        my_mob = len(self._get_valid_moves_raw(board, my_pos, H, W))

        # Emergency boost when trapped
        if my_mob <= 2 and turn_count > 5:
            return True

        my_space = self._flood_fill(board, my_pos, limit=80)
        opp_space = self._flood_fill(board, opp_pos, limit=80)

        # Aggressive early boost if we have advantage
        if 15 <= turn_count <= 35 and my_boosts >= 2:
            if my_space >= opp_space * 0.9:
                return True

        # Mid-game strategic boosts
        if 40 < turn_count < 110:
            if my_space > 1.25 * opp_space and my_boosts > 0:
                return True
            if opp_space > 1.3 * my_space and my_boosts > 1:
                return True

        # Late game boost advantage
        if turn_count > 100 and my_boosts > opp_boosts:
            return True

        # Critical endgame - use remaining boosts
        if turn_count > 140 and my_boosts > 0:
            if turn_count > 160 or my_space > opp_space * 0.95:
                return True

        # Close quarters combat
        if 40 < turn_count < 100:
            dist = self._torus_dist(my_pos, opp_pos, W, H)
            if dist < 8 and my_boosts >= 2:
                return True

        return False

    def _order_moves_killer(
        self,
        board: np.ndarray,
        my_pos: Pos,
        opp_pos: Pos,
        moves: List[Direction],
        turn_count: Optional[int],
    ) -> List[Direction]:
        H, W = board.shape
        killers = self.killer_moves.get(turn_count, []) if turn_count is not None else []

        scored = []
        for mv in moves:
            nx, ny = self._apply_direction(my_pos, mv, H, W)
            cb = board.copy()
            cb[my_pos[1], my_pos[0]] = 1
            mob = len(self._get_valid_moves_raw(cb, (nx, ny), H, W))
            dist = self._torus_dist((nx, ny), opp_pos, W, H)
            score = mob * 10 + dist * 0.5
            if mv in killers:
                score += 1000.0
            scored.append((score, mv))

        scored.sort(reverse=True)
        return [m for _, m in scored]

    def _get_valid_moves(self, board: np.ndarray, pos: Pos, current_dir: Direction) -> List[Direction]:
        H, W = board.shape
        opposite = {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT,
        }
        res = []
        for d in self.directions:
            if d == opposite.get(current_dir):
                continue
            nx, ny = self._apply_direction(pos, d, H, W)
            if board[ny, nx] == 0:
                res.append(d)
        return res

    def _get_valid_moves_raw(self, board: np.ndarray, pos: Pos, H: int, W: int) -> List[Direction]:
        res = []
        for d in self.directions:
            nx, ny = self._apply_direction(pos, d, H, W)
            if board[ny, nx] == 0:
                res.append(d)
        return res

    def _apply_direction(self, pos: Pos, direction: Direction, H: int, W: int) -> Pos:
        dx, dy = direction.value
        return ((pos[0] + dx) % W, (pos[1] + dy) % H)

    def _is_valid_move(self, board: np.ndarray, pos: Pos, direction: Direction, current_dir: Direction) -> bool:
        H, W = board.shape
        opposite = {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT,
        }
        if direction == opposite.get(current_dir):
            return False
        nx, ny = self._apply_direction(pos, direction, H, W)
        return board[ny, nx] == 0

    def _flood_fill(self, board: np.ndarray, start: Pos, limit: Optional[int] = None, full: bool = False) -> int:
        H, W = board.shape
        if board[start[1], start[0]] != 0:
            return 0

        q = deque([start])
        seen = {start}
        count = 0

        while q:
            x, y = q.popleft()
            count += 1
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = (x + dx) % W, (y + dy) % H
                if (nx, ny) not in seen and board[ny, nx] == 0:
                    seen.add((nx, ny))
                    q.append((nx, ny))
            if not full and limit is not None and count >= limit:
                break

        return count

    def _same_region(self, board: np.ndarray, a: Pos, b: Pos, H: int, W: int) -> bool:
        if board[a[1], a[0]] != 0:
            return False
        q = deque([a])
        seen = {a}
        while q:
            x, y = q.popleft()
            if (x, y) == b:
                return True
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = (x + dx) % W, (y + dy) % H
                if (nx, ny) not in seen and board[ny, nx] == 0:
                    seen.add((nx, ny))
                    q.append((nx, ny))
            if len(seen) > 120:
                break
        return b in seen

    def _tt_key(self, board: np.ndarray, my_pos: Pos, opp_pos: Pos, depth: int, maximizing: bool) -> int:
        return hash((board.tobytes(), my_pos, opp_pos, depth, maximizing))

    def _tt_store(self, key: int, score: float, depth: int) -> None:
        self.tt[key] = (score, depth)
        self.tt.move_to_end(key)
        if len(self.tt) > self.max_tt:
            self.tt.popitem(last=False)

    def _torus_dist(self, a: Pos, b: Pos, W: int, H: int) -> int:
        dx = min(abs(a[0] - b[0]), W - abs(a[0] - b[0]))
        dy = min(abs(a[1] - b[1]), H - abs(a[1] - b[1]))
        return dx + dy