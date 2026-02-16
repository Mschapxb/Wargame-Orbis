import random
import heapq


class Battlefield:
    def __init__(self, width=40, height=30, obstacle_count=8, map_name="Prairie", grid=None, map_data=None):
        self.width = width
        self.height = height
        self.map_name = map_name
        self.units = {}
        
        # Données de siège
        self.siege_data = map_data or {}
        self.gate_hp = dict(self.siege_data.get('gates', {}))  # {(x,y): hp}
        self.gate_save = self.siege_data.get('gate_save', 7)   # Sauvegarde des portes
        self.walls = set(tuple(w) for w in self.siege_data.get('walls', []))
        self.ramparts = set(tuple(r) for r in self.siege_data.get('ramparts', []))
        self.stairs = set(tuple(s) for s in self.siege_data.get('stairs', []))
        
        if grid is not None:
            self.grid = grid
        else:
            self.grid = [[0] * height for _ in range(width)]
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
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        cell = self.grid[x][y]
        if cell == 0:
            return True
        if cell == 4:  # Rempart: marchable
            return True
        if cell == 5:  # Escalier: marchable
            return True
        if cell == 3:  # Porte: traversable si détruite (hp <= 0)
            return self.gate_hp.get((x, y), 0) <= 0
        return False  # 1=obstacle, 2=mur
    
    def is_wall(self, x, y):
        """Retourne True si la case est un mur."""
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[x][y] == 2
    
    def is_rampart(self, x, y):
        """Retourne True si la case est un rempart marchable."""
        return (x, y) in self.ramparts
    
    def is_gate(self, x, y):
        """Retourne True si la case est une porte (intacte)."""
        return (0 <= x < self.width and 0 <= y < self.height 
                and self.grid[x][y] == 3 and self.gate_hp.get((x, y), 0) > 0)
    
    def damage_gate(self, x, y, dmg):
        """Inflige des dégâts à une porte. Retourne True si détruite."""
        pos = (x, y)
        if pos in self.gate_hp:
            self.gate_hp[pos] -= dmg
            if self.gate_hp[pos] <= 0:
                self.gate_hp[pos] = 0
                return True
        return False

    def is_occupied(self, x, y):
        return (x, y) in self.units

    def is_free(self, x, y, ignore_unit=None):
        if not self.is_valid(x, y):
            return False
        occupant = self.units.get((x, y))
        return occupant is None or (ignore_unit and occupant == ignore_unit)

    def get_unit_dims(self, unit):
        """Retourne (largeur, hauteur) en cases selon la taille.
        size 1 = 1×1 (1 case), size 2 = 2×2 (4 cases), size 3 = 2×4 (8 cases)."""
        if unit.size <= 1:
            return (1, 1)
        elif unit.size == 2:
            return (2, 2)
        else:  # size 3+
            return (2, 4)

    def get_unit_cells(self, unit):
        """Retourne toutes les cases occupées par une unité. Ancré en haut-gauche."""
        x, y = unit.position
        w, h = self.get_unit_dims(unit)
        cells = []
        for dx in range(w):
            for dy in range(h):
                cells.append((x + dx, y + dy))
        return cells

    def can_place_unit(self, x, y, unit, ignore_unit=None):
        """Vérifie si une unité peut être placée en (x, y) selon sa taille."""
        w, h = self.get_unit_dims(unit)
        for dx in range(w):
            for dy in range(h):
                if not self.is_free(x + dx, y + dy, ignore_unit):
                    return False
        return True

    def place_unit(self, unit):
        """Place une unité sur la grille (toutes ses cases)."""
        for cell in self.get_unit_cells(unit):
            self.units[cell] = unit

    def remove_unit(self, unit):
        """Retire une unité de la grille."""
        to_del = [cell for cell, u in self.units.items() if u is unit]
        for cell in to_del:
            del self.units[cell]

    def move_unit(self, unit, new_pos):
        """Déplace une unité vers une nouvelle position."""
        self.remove_unit(unit)
        unit.position = new_pos
        self.place_unit(unit)

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
        
        # Siège: si l'unité est côté attaquant, ne pas viser derrière le mur
        wall_x = self.siege_data.get('wall_x') if self.siege_data else None
        unit_is_attacker = wall_x is not None and unit_pos[0] < wall_x
        # Portes toutes détruites? Alors on peut passer
        all_gates_open = wall_x is not None and all(hp <= 0 for hp in self.gate_hp.values()) if self.gate_hp else True
        
        # Collecter les cases à portée de la cible
        candidates = []
        for dx in range(-max_range, max_range + 1):
            for dy in range(-max_range, max_range + 1):
                if abs(dx) + abs(dy) > max_range or (dx == 0 and dy == 0):
                    continue
                pos = (target_pos[0] + dx, target_pos[1] + dy)
                if not self.is_valid(*pos) or pos in reserved_positions:
                    continue
                # Siège: ne pas viser derrière le mur si les portes sont intactes
                if unit_is_attacker and not all_gates_open and pos[0] >= wall_x:
                    continue
                dist = self.chebyshev_distance(unit_pos, pos)
                is_empty = not self.is_occupied(*pos)
                priority = (0 if is_empty else 1, dist)
                candidates.append((priority, pos))
        
        if not candidates:
            return None  # Pas de position valide (sera géré par le fallback siège)
        
        candidates.sort()
        return candidates[0][1]

    def compute_move(self, unit, battle, reserved_positions):
        if unit.fleeing:
            # Unités en fuite: vitesse minimum 1 pour pouvoir fuir
            flee_speed = max(1, unit.vitesse)
            flee_x = 0 if unit in battle.army1 else self.width - 1
            goal = (flee_x, unit.position[1])
            path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions)
            if path:
                steps = min(flee_speed, len(path))
                if steps > 0:
                    new_pos = path[steps - 1]
                    if self._can_move_to(unit, new_pos, reserved_positions):
                        return new_pos, None
            return None, None
        
        # Unités immobiles (artillerie) ne bougent pas
        if unit.vitesse <= 0:
            enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
            if not enemies:
                return None, None
            target = min(enemies, key=lambda e: self.manhattan_distance(unit.position, e.position))
            if self.manhattan_distance(unit.position, target.position) <= unit._max_range:
                return None, target
            return None, None
        
        enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
        if not enemies:
            return None, None
        
        target = min(enemies, key=lambda e: self.manhattan_distance(unit.position, e.position))
        current_dist = self.manhattan_distance(unit.position, target.position)
        
        if current_dist <= unit._max_range:
            # Siège: vérifier qu'un mur ne bloque pas le CaC
            wall_x_s = self.siege_data.get('wall_x') if self.siege_data else None
            if wall_x_s and unit._max_range < 4 and unit.position[0] < wall_x_s and target.position[0] >= wall_x_s:
                # CaC côté attaquant, cible derrière le mur → pas vraiment à portée
                pass  # Continue vers le pathfinding porte
            else:
                return None, target
        
        # Siège: défenseurs sur rempart restent en place tant qu'il reste des portes intactes
        if self.is_rampart(*unit.position) and self.gate_hp:
            intact_gates = any(hp > 0 for hp in self.gate_hp.values())
            if intact_gates:
                return None, target  # Rester sur le rempart, tirer depuis la position
        
        goal = self.find_best_attack_position(unit, target, battle, reserved_positions)
        
        # Siège: si pas de position d'attaque valide côté attaquant, aller vers la porte
        wall_x_siege = self.siege_data.get('wall_x') if self.siege_data else None
        if goal is None and wall_x_siege and unit.position[0] < wall_x_siege:
            # Aller directement vers la porte
            pass  # Tombe dans le block siège ci-dessous
        elif goal is None:
            return None, target
        else:
            path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions)
            if path:
                steps = min(unit.vitesse, len(path))
                for i in range(steps, 0, -1):
                    candidate = path[i - 1]
                    if self._can_move_to(unit, candidate, reserved_positions):
                        return candidate, target
        
        # Siège: pas de chemin direct → passer par une porte
        if self.gate_hp:
            wall_x = self.siege_data.get('wall_x', 0)
            ux = unit.position[0]
            
            # Unité côté attaquant (à gauche du mur)?
            if ux < wall_x:
                # Chercher une porte détruite pour passer à travers
                destroyed_gates = [pos for pos, hp in self.gate_hp.items() if hp <= 0]
                if destroyed_gates:
                    # Aller vers la porte détruite la plus proche (traversable)
                    nearest = min(destroyed_gates, key=lambda g: self.manhattan_distance(unit.position, g))
                    gpath = self.a_star_path(unit.position, nearest, unit, battle, reserved_positions)
                    if gpath:
                        steps = min(unit.vitesse, len(gpath))
                        for i in range(steps, 0, -1):
                            candidate = gpath[i - 1]
                            if self._can_move_to(unit, candidate, reserved_positions):
                                return candidate, target
                
                # Sinon aller adjacent à la porte intacte la plus proche (pour la détruire au CaC)
                intact_gates = [pos for pos, hp in self.gate_hp.items() if hp > 0]
                if intact_gates:
                    nearest_gate = min(intact_gates, key=lambda g: self.manhattan_distance(unit.position, g))
                    gate_goal = self._find_adjacent_free(nearest_gate, unit, reserved_positions, side="left", wall_x=wall_x)
                    if gate_goal:
                        gpath = self.a_star_path(unit.position, gate_goal, unit, battle, reserved_positions)
                        if gpath:
                            steps = min(unit.vitesse, len(gpath))
                            for i in range(steps, 0, -1):
                                candidate = gpath[i - 1]
                                if self._can_move_to(unit, candidate, reserved_positions):
                                    return candidate, target
            
            # Ne PAS utiliser fallback_move classique (ça colle au mur)
            # Longer le mur vers la porte la plus proche
            if ux < wall_x:
                all_gates = list(self.gate_hp.keys())
                if all_gates:
                    nearest = min(all_gates, key=lambda g: abs(unit.position[1] - g[1]))
                    uy = unit.position[1]
                    gy = nearest[1]
                    dy = 0 if uy == gy else (1 if gy > uy else -1)
                    # Essayer dans l'ordre: latéral, diagonales, reculer
                    candidates = []
                    if dy != 0:
                        candidates.append((ux, uy + dy))       # Latéral pur
                        candidates.append((ux - 1, uy + dy))   # Diagonal en reculant
                    candidates.append((ux - 1, uy))            # Reculer
                    if dy != 0:
                        candidates.append((ux - 2, uy + dy))   # Reculer + latéral
                        candidates.append((ux - 1, uy + dy*2)) # Recul + grand latéral
                    
                    for cand in candidates:
                        if self._can_move_to(unit, cand, reserved_positions):
                            return cand, target
                return None, target
        
        return self.fallback_move(unit, target, reserved_positions), target
    
    def _find_adjacent_free(self, pos, unit, reserved, side=None, wall_x=None):
        """Trouve une case libre adjacente à pos. side='left' = côté attaquant seulement."""
        px, py = pos
        best = None
        best_d = 999
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = px + dx, py + dy
                # Restreindre au côté attaquant si demandé
                if side == "left" and wall_x is not None and nx >= wall_x:
                    continue
                if self._can_move_to(unit, (nx, ny), reserved):
                    d = self.manhattan_distance(unit.position, (nx, ny))
                    if d < best_d:
                        best = (nx, ny)
                        best_d = d
        return best

    def _can_move_to(self, unit, pos, reserved_positions):
        """Vérifie si une unité peut se déplacer vers pos (multi-cases)."""
        if unit.size <= 1:
            return self.is_free(*pos, unit) and pos not in reserved_positions
        # Multi-case : vérifier toutes les cases de destination
        w, h = self.get_unit_dims(unit)
        for dx in range(w):
            for dy in range(h):
                cell = (pos[0] + dx, pos[1] + dy)
                if cell in reserved_positions:
                    return False
                if not self.is_free(*cell, unit):
                    return False
        return True

    def _get_reserved_cells(self, unit, pos):
        """Retourne toutes les cases qu'une unité occuperait à pos."""
        if unit.size <= 1:
            return {pos}
        w, h = self.get_unit_dims(unit)
        return {(pos[0] + dx, pos[1] + dy) for dx in range(w) for dy in range(h)}

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
                if self._can_move_to(unit, (nx, ny), reserved_positions):
                    dist = self.manhattan_distance((nx, ny), (tx, ty))
                    neighbors.append((dist, (nx, ny)))
        
        if neighbors:
            neighbors.sort()
            return neighbors[0][1]
        return None