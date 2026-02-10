import random
import heapq


class Battlefield:
    def __init__(self, width=40, height=30, obstacle_count=8):
        self.width = width
        self.height = height
        self.grid = [[0] * height for _ in range(width)]
        self.units = {}
        self.add_obstacles(obstacle_count)

    def add_obstacles(self, count):
        placed = 0
        min_distance = 7
        obstacles = []
        
        margin_x = self.width // 4
        min_x = max(10, margin_x)
        max_x = min(self.width - 11, self.width - margin_x)
        min_y = 3
        max_y = self.height - 4
        
        if max_x <= min_x or max_y <= min_y:
            return
        
        max_attempts = count * 50
        attempts = 0
        while placed < count and attempts < max_attempts:
            attempts += 1
            x = random.randint(min_x, max_x)
            y = random.randint(min_y, max_y)
            if not any(abs(x - ox) + abs(y - oy) < min_distance for ox, oy in obstacles) and self.grid[x][y] == 0:
                self.grid[x][y] = 1
                obstacles.append((x, y))
                placed += 1

    def is_valid(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[x][y] == 0

    def is_occupied(self, x, y):
        return (x, y) in self.units

    def is_free(self, x, y, ignore_unit=None):
        if not self.is_valid(x, y):
            return False
        occupant = self.units.get((x, y))
        return occupant is None or (ignore_unit and occupant == ignore_unit)

    def manhattan_distance(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def chebyshev_distance(self, a, b):
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    def a_star_path(self, start, goal, unit, battle, reserved_positions=None, max_nodes=600):
        """A* avec alliés traversables (coût élevé) au lieu de bloquants.
        
        Ça évite que les unités restent coincées derrière leurs alliés
        quand il reste peu de monde en fin de bataille.
        """
        if reserved_positions is None:
            reserved_positions = set()
        
        allies = battle.get_allies(unit)
        ally_positions = {u.position for u in allies if u.is_alive and u != unit}
        
        ALLY_PENALTY = 3.0  # Traverser un allié coûte cher mais est possible
        
        open_set = []
        heapq.heappush(open_set, (self.chebyshev_distance(start, goal), 0.0, start))
        came_from = {}
        g_score = {start: 0.0}
        directions = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        nodes_explored = 0
        
        while open_set:
            _, g, current = heapq.heappop(open_set)
            nodes_explored += 1
            
            if nodes_explored > max_nodes:
                break
            
            if current == goal:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                return path
            
            # Skip si on a déjà trouvé un meilleur chemin
            if g > g_score.get(current, float('inf')):
                continue
            
            for dx, dy in directions:
                neighbor = (current[0] + dx, current[1] + dy)
                
                if not self.is_valid(*neighbor):
                    continue
                if neighbor in reserved_positions:
                    continue
                
                base_cost = 1.414 if dx != 0 and dy != 0 else 1.0
                
                # Les alliés sont traversables mais avec une pénalité
                if neighbor in ally_positions and neighbor != goal:
                    cost = base_cost + ALLY_PENALTY
                else:
                    cost = base_cost
                
                new_g = g + cost
                if new_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = new_g
                    h = self.chebyshev_distance(neighbor, goal)
                    heapq.heappush(open_set, (new_g + h, new_g, neighbor))
        
        return []

    def find_best_attack_position(self, unit, target, battle, reserved_positions=None):
        """Trouve la meilleure case libre à portée de la cible."""
        if reserved_positions is None:
            reserved_positions = set()
        
        max_range = unit._max_range
        target_pos = target.position
        unit_pos = unit.position
        
        if self.manhattan_distance(unit_pos, target_pos) <= max_range:
            return None  # Déjà à portée
        
        # Collecter les cases à portée de la cible
        candidates = []
        for dx in range(-max_range, max_range + 1):
            for dy in range(-max_range, max_range + 1):
                if abs(dx) + abs(dy) > max_range or (dx == 0 and dy == 0):
                    continue
                pos = (target_pos[0] + dx, target_pos[1] + dy)
                if not self.is_valid(*pos) or pos in reserved_positions:
                    continue
                dist = self.chebyshev_distance(unit_pos, pos)
                is_empty = not self.is_occupied(*pos)
                # Cases vides en priorité, puis par distance
                priority = (0 if is_empty else 1, dist)
                candidates.append((priority, pos))
        
        if not candidates:
            return target_pos  # Fallback: aller vers la cible
        
        candidates.sort()
        return candidates[0][1]

    def compute_move(self, unit, battle, reserved_positions):
        if unit.fleeing:
            flee_x = 0 if unit in battle.army1 else self.width - 1
            goal = (flee_x, unit.position[1])
            path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions)
            if path:
                steps = min(unit.vitesse, len(path))
                new_pos = path[steps - 1]
                if self.is_free(*new_pos, unit) and new_pos not in reserved_positions:
                    return new_pos, None
            return None, None
        
        enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
        if not enemies:
            return None, None
        
        target = min(enemies, key=lambda e: self.manhattan_distance(unit.position, e.position))
        current_dist = self.manhattan_distance(unit.position, target.position)
        
        if current_dist <= unit._max_range:
            return None, target
        
        goal = self.find_best_attack_position(unit, target, battle, reserved_positions)
        if goal is None:
            return None, target
        
        path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions)
        if path:
            # Avancer le long du chemin en s'arrêtant sur une case réellement libre
            steps = min(unit.vitesse, len(path))
            for i in range(steps, 0, -1):
                candidate = path[i - 1]
                if self.is_free(*candidate, unit) and candidate not in reserved_positions:
                    return candidate, target
        
        # Fallback: mouvement direct vers la cible
        return self.fallback_move(unit, target, reserved_positions), target

    def fallback_move(self, unit, target, reserved_positions):
        """Mouvement simple: 8 directions triées par proximité avec la cible."""
        tx, ty = target.position
        ux, uy = unit.position
        
        neighbors = []
        for ddx in [-1, 0, 1]:
            for ddy in [-1, 0, 1]:
                if ddx == 0 and ddy == 0:
                    continue
                nx, ny = ux + ddx, uy + ddy
                if self.is_free(nx, ny, unit) and (nx, ny) not in reserved_positions:
                    dist = self.manhattan_distance((nx, ny), (tx, ty))
                    neighbors.append((dist, (nx, ny)))
        
        if neighbors:
            neighbors.sort()
            return neighbors[0][1]
        return None