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
        """Retire une unité de la grille (utilise get_unit_cells au lieu de scanner tout le dict)."""
        if unit.position is None:
            return
        x, y = unit.position
        w, h = self.get_unit_dims(unit)
        for dx in range(w):
            for dy in range(h):
                cell = (x + dx, y + dy)
                if self.units.get(cell) is unit:
                    del self.units[cell]

    def move_unit(self, unit, new_pos):
        """Déplace une unité vers une nouvelle position."""
        unit._prev_position = unit.position  # Sauvegarder pour animation
        self.remove_unit(unit)
        unit.position = new_pos
        self.place_unit(unit)

    def manhattan_distance(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def chebyshev_distance(self, a, b):
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    def a_star_path(self, start, goal, unit, battle, reserved_positions=None, max_nodes=1200):
        """A* optimisé — opérations inlinées pour la performance."""
        if reserved_positions is None:
            reserved_positions = set()
        
        if start == goal:
            return [goal]
        
        allies = battle.get_allies(unit)
        ally_positions = {u.position for u in allies if u.is_alive and u is not unit}
        
        # Pénalité réduite quand loin de la cible
        sx, sy = start
        gx, gy = goal
        dist_to_goal = max(abs(gx - sx), abs(gy - sy))
        ALLY_PENALTY = 1.5 if dist_to_goal > 8 else 2.5
        
        # Cache local pour éviter les lookups d'attributs répétés
        grid = self.grid
        width = self.width
        height = self.height
        gate_hp = self.gate_hp
        reserved = reserved_positions
        
        open_set = []
        h0 = max(abs(gx - sx), abs(gy - sy))
        heapq.heappush(open_set, (h0, 0.0, sx, sy))
        g_score = {start: 0.0}
        came_from = {}
        
        _DIRS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
        _DIAG_COST = 1.414
        nodes_explored = 0
        _heappush = heapq.heappush
        _heappop = heapq.heappop
        _abs = abs
        _INF = 1e9
        
        while open_set:
            _, g, cx, cy = _heappop(open_set)
            nodes_explored += 1
            
            if nodes_explored > max_nodes:
                break
            
            if cx == gx and cy == gy:
                # Reconstruire le chemin
                path = []
                current = (gx, gy)
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                return path
            
            current = (cx, cy)
            if g > g_score.get(current, _INF):
                continue
            
            for dx, dy in _DIRS:
                nx, ny = cx + dx, cy + dy
                
                # is_valid inliné
                if nx < 0 or nx >= width or ny < 0 or ny >= height:
                    continue
                cell = grid[nx][ny]
                if cell == 1 or cell == 2:
                    continue
                if cell == 3 and gate_hp.get((nx, ny), 0) > 0:
                    continue
                
                neighbor = (nx, ny)
                if neighbor in reserved:
                    continue
                
                base_cost = _DIAG_COST if (dx and dy) else 1.0
                
                if neighbor in ally_positions and neighbor != goal:
                    new_g = g + base_cost + ALLY_PENALTY
                else:
                    new_g = g + base_cost
                
                if new_g < g_score.get(neighbor, _INF):
                    came_from[neighbor] = current
                    g_score[neighbor] = new_g
                    # chebyshev inliné
                    h = _abs(gx - nx)
                    hdy = _abs(gy - ny)
                    if hdy > h:
                        h = hdy
                    _heappush(open_set, (new_g + h, new_g, nx, ny))
        
        return []
        
        return []

    def find_best_attack_position(self, unit, target, battle, reserved_positions=None):
        """Trouve la meilleure case libre à portée de la cible.
        
        Prend en compte la lane assignée à l'unité pour étaler les troupes
        et éviter que tout le monde converge sur le même point.
        """
        if reserved_positions is None:
            reserved_positions = set()
        
        max_range = unit._max_range
        target_pos = target.position
        unit_pos = unit.position
        
        if self.manhattan_distance(unit_pos, target_pos) <= max_range:
            return None
        
        # Siège: ne pas viser derrière le mur si portes intactes
        wall_x = self.siege_data.get('wall_x') if self.siege_data else None
        unit_is_attacker = wall_x is not None and unit_pos[0] < wall_x
        all_gates_open = wall_x is not None and all(hp <= 0 for hp in self.gate_hp.values()) if self.gate_hp else True
        
        # Lane de l'unité pour l'étalement
        from ai_commander import get_lane_offset
        lane_y = get_lane_offset(unit, self)
        
        tx, ty = target_pos
        ux, uy = unit_pos
        grid = self.grid
        width = self.width
        height = self.height
        units_dict = self.units
        gate_hp_dict = self.gate_hp
        
        best_priority = None
        best_pos = None
        
        for dx in range(-max_range, max_range + 1):
            px = tx + dx
            if px < 0 or px >= width:
                continue
            if unit_is_attacker and not all_gates_open and px >= wall_x:
                continue
            adx = abs(dx)
            max_dy = max_range - adx
            for dy in range(-max_dy, max_dy + 1):
                if dx == 0 and dy == 0:
                    continue
                py = ty + dy
                if py < 0 or py >= height:
                    continue
                # is_valid inliné
                cell = grid[px][py]
                if cell == 1 or cell == 2:
                    continue
                if cell == 3 and gate_hp_dict.get((px, py), 0) > 0:
                    continue
                pos = (px, py)
                if pos in reserved_positions:
                    continue
                
                occupied = 0 if pos not in units_dict else 1
                dist = max(abs(ux - px), abs(uy - py))
                lane_dist = abs(py - lane_y) // 3
                priority = (occupied, lane_dist, dist)
                
                if best_priority is None or priority < best_priority:
                    best_priority = priority
                    best_pos = pos
        
        return best_pos

    def compute_move(self, unit, battle, reserved_positions):
        if unit.fleeing:
            # Unités en fuite: courir vers le bord le plus proche
            flee_speed = max(2, unit.vitesse)  # Minimum 2 cases/round en fuite
            ux, uy = unit.position
            
            # Trouver le bord le plus proche
            dist_left = ux
            dist_right = self.width - 1 - ux
            dist_top = uy
            dist_bottom = self.height - 1 - uy
            
            min_dist = min(dist_left, dist_right, dist_top, dist_bottom)
            
            if min_dist == dist_top:
                goal = (ux, 0)
            elif min_dist == dist_bottom:
                goal = (ux, self.height - 1)
            elif min_dist == dist_left:
                goal = (0, uy)
            else:
                goal = (self.width - 1, uy)
            
            # Essayer le A* en premier
            path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions)
            if path:
                steps = min(flee_speed, len(path))
                # Essayer le step le plus loin possible, puis réduire
                for i in range(steps, 0, -1):
                    new_pos = path[i - 1]
                    if self._can_move_to(unit, new_pos, reserved_positions):
                        return new_pos, None
            
            # Fallback: mouvement direct vers le bord, en essayant plusieurs directions
            gx, gy = goal
            dx_main = 0 if gx == ux else (1 if gx > ux else -1)
            dy_main = 0 if gy == uy else (1 if gy > uy else -1)
            
            # Essayer toutes les directions, triées par efficacité vers le bord
            candidates = []
            for step in range(flee_speed, 0, -1):
                for ddx in [-1, 0, 1]:
                    for ddy in [-1, 0, 1]:
                        if ddx == 0 and ddy == 0:
                            continue
                        nx, ny = ux + ddx * step, uy + ddy * step
                        pos = (nx, ny)
                        if not (0 <= nx < self.width and 0 <= ny < self.height):
                            # Case hors map = on s'y dirige quand même (pour atteindre le bord)
                            # Clipper au bord
                            nx = max(0, min(self.width - 1, nx))
                            ny = max(0, min(self.height - 1, ny))
                            pos = (nx, ny)
                        if self._can_move_to(unit, pos, reserved_positions):
                            # Score: distance au bord le plus proche (plus petit = mieux)
                            border_dist = min(nx, self.width - 1 - nx, ny, self.height - 1 - ny)
                            candidates.append((border_dist, pos))
            
            if candidates:
                candidates.sort()
                return candidates[0][1], None
            
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
        
        # === Siège: tireurs/mages sur rempart ne bougent JAMAIS ===
        if self.gate_hp and self.is_rampart(*unit.position):
            if unit._max_range >= 4 or bool(unit.spells):
                ux, uy = unit.position
                mr = unit._max_range
                in_range = [e for e in enemies if abs(ux - e.position[0]) + abs(uy - e.position[1]) <= mr]
                if in_range:
                    return None, min(in_range, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
                return None, min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
        
        # === COMBAT COLLANT: si un ennemi est au contact (dist ≤ portée), ===
        # === l'unité reste et le combat, elle ne se déplace PAS ===
        ux, uy = unit.position
        closest_dist = 999
        closest_enemy = None
        for e in enemies:
            d = abs(ux - e.position[0]) + abs(uy - e.position[1])
            if d < closest_dist:
                closest_dist = d
                closest_enemy = e
        
        if closest_dist <= unit._max_range and not unit.fleeing:
            # En mêlée: ne pas bouger, combattre le plus proche (ou le plus blessé à portée)
            in_range = [e for e in enemies if abs(ux - e.position[0]) + abs(uy - e.position[1]) <= unit._max_range]
            # Priorité: le plus blessé en proportion, puis le plus proche
            best_target = min(in_range, key=lambda e: (e.hp / max(1, e.max_hp), abs(ux - e.position[0]) + abs(uy - e.position[1])))
            
            # Exception siège: CaC côté attaquant vs cible derrière le mur
            wall_x_s = self.siege_data.get('wall_x') if self.siege_data else None
            if wall_x_s and unit._max_range < 4 and ux < wall_x_s and best_target.position[0] >= wall_x_s:
                pass  # Continue vers le pathfinding normal
            else:
                return None, best_target
        
        # Utiliser le ciblage tactique de l'IA si disponible
        from ai_commander import select_tactical_target, select_tactical_move_target
        
        target_unit, move_pos = select_tactical_move_target(unit, battle, self)
        
        # Flanquement/protection: se déplacer vers une position, pas une unité
        if move_pos and target_unit is None:
            goal = move_pos
            # Trouver une cible pour le combat (le plus proche)
            target = min(enemies, key=lambda e: self.manhattan_distance(unit.position, e.position))
            path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions)
            if path:
                steps = min(unit.vitesse, len(path))
                for i in range(steps, 0, -1):
                    candidate = path[i - 1]
                    if self._can_move_to(unit, candidate, reserved_positions):
                        return candidate, target
            return self.fallback_move(unit, target, reserved_positions), target
        
        # Ciblage tactique: attaquer l'unité assignée par l'IA
        if target_unit and target_unit.is_alive:
            target = target_unit
        else:
            target = select_tactical_target(unit, battle, self)
            if target is None:
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
        
        # Siège: défenseurs TIREURS sur rempart restent TOUJOURS en place
        # Le rempart donne un avantage défensif trop précieux pour l'abandonner
        if self.is_rampart(*unit.position) and self.gate_hp:
            if unit._max_range >= 4 or bool(unit.spells):
                # Tireur/mage sur rempart: ne jamais bouger
                return None, target
            # CaC sur rempart: rester tant que portes intactes
            intact_gates = any(hp > 0 for hp in self.gate_hp.values())
            if intact_gates:
                return None, target
        
        # IA hold: rester en position si l'ordre est "hold" et pas d'ennemi au contact
        order = getattr(unit, '_tactical_order', None)
        if order and order.order_type == "hold" and current_dist > unit._max_range + 1:
            # Rester mais garder la cible pour tirer si possible
            return None, target
        
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
            
            # Longer le mur vers la porte la plus proche (ou lane)
            if ux < wall_x:
                all_gates = list(self.gate_hp.keys())
                if all_gates:
                    from ai_commander import get_lane_offset
                    lane_y = get_lane_offset(unit, self)
                    nearest = min(all_gates, key=lambda g: abs(unit.position[1] - g[1]))
                    uy = unit.position[1]
                    gy = nearest[1]
                    dy = 0 if uy == gy else (1 if gy > uy else -1)
                    
                    # Essayer: vers la porte, vers la lane, latéral pur, reculer
                    candidates = []
                    if dy != 0:
                        candidates.append((ux, uy + dy))
                        candidates.append((ux - 1, uy + dy))
                    # Vers la lane si on est pas aligné
                    dy_lane = 0 if lane_y == uy else (1 if lane_y > uy else -1)
                    if dy_lane != 0 and dy_lane != dy:
                        candidates.append((ux, uy + dy_lane))
                        candidates.append((ux - 1, uy + dy_lane))
                    candidates.append((ux - 1, uy))
                    if dy != 0:
                        candidates.append((ux - 2, uy + dy))
                    
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
        """Mouvement de secours: avance vers la cible avec étalement latéral.
        
        1) Avancer vers la cible si possible
        2) Sinon contourner latéralement (vers la lane assignée)
        3) Si totalement bloqué, reculer pour laisser passer
        """
        tx, ty = target.position
        ux, uy = unit.position
        
        from ai_commander import get_lane_offset
        lane_y = get_lane_offset(unit, self)
        
        best_dist = self.manhattan_distance((ux, uy), (tx, ty))
        
        # Direction principale vers la cible
        dx_main = 0 if tx == ux else (1 if tx > ux else -1)
        dy_main = 0 if ty == uy else (1 if ty > uy else -1)
        
        # Direction latérale vers la lane
        dy_lane = 0 if lane_y == uy else (1 if lane_y > uy else -1)
        
        # Candidats triés: avancer vers cible, contourner vers lane, latéral, reculer
        moves = []
        for ddx in [-1, 0, 1]:
            for ddy in [-1, 0, 1]:
                if ddx == 0 and ddy == 0:
                    continue
                nx, ny = ux + ddx, uy + ddy
                pos = (nx, ny)
                if not self._can_move_to(unit, pos, reserved_positions):
                    continue
                
                new_dist = self.manhattan_distance(pos, (tx, ty))
                # Score composite: rapprochement de la cible + alignement lane
                approach = best_dist - new_dist  # Positif = on se rapproche
                lane_align = -abs(ny - lane_y)   # Plus haut = mieux aligné
                
                # Prioriser: rapprochement > alignement lane > distance latérale
                score = (approach * 3 + lane_align, -new_dist)
                moves.append((score, pos))
        
        if moves:
            moves.sort(reverse=True)
            return moves[0][1]
        
        # Totalement bloqué: essayer de se décaler vers la lane même sans se rapprocher
        for ddy in [dy_lane, -dy_lane]:
            if ddy == 0:
                continue
            pos = (ux, uy + ddy)
            if self._can_move_to(unit, pos, reserved_positions):
                return pos
        
        # Reculer pour désencombrer
        pos = (ux - dx_main, uy + dy_lane) if dy_lane else (ux - dx_main, uy)
        if self._can_move_to(unit, pos, reserved_positions):
            return pos
        
        return None

    def find_lateral_advance(self, unit, battle, reserved_positions):
        """Mouvement latéral pour les unités bloquées durant l'approche.
        
        Quand une unité ne peut pas avancer tout droit (bloquée par des alliés),
        elle se décale latéralement vers sa lane pour créer un front plus large
        et permettre à plusieurs unités d'avancer simultanément.
        """
        ux, uy = unit.position
        enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
        if not enemies:
            return None
        
        from ai_commander import get_lane_offset
        lane_y = get_lane_offset(unit, self)
        
        # Centre ennemi pour déterminer la direction d'avance
        ec_x = sum(e.position[0] for e in enemies) / len(enemies)
        dx_toward = 0 if ec_x == ux else (1 if ec_x > ux else -1)
        
        # Direction latérale vers la lane
        dy_lane = 0 if lane_y == uy else (1 if lane_y > uy else -1)
        
        # Essayer dans l'ordre:
        # 1) Avancer en diagonale vers la lane (avance + étalement)
        # 2) Se décaler purement vers la lane (étalement pur)
        # 3) Avancer en diagonale opposée à la lane
        # 4) Se décaler dans la direction opposée à la lane
        candidates = []
        
        if dy_lane != 0:
            # Diagonale vers lane + avance
            candidates.append((ux + dx_toward, uy + dy_lane))
            # Pur latéral vers lane
            candidates.append((ux, uy + dy_lane))
            # Diagonale vers lane + recul (pour se dégager)
            candidates.append((ux - dx_toward, uy + dy_lane))
        
        # Diagonale opposée à la lane + avance (contournement par l'autre côté)
        if dy_lane != 0:
            candidates.append((ux + dx_toward, uy - dy_lane))
            candidates.append((ux, uy - dy_lane))
        else:
            # Pas de lane assignée → essayer les deux côtés
            candidates.append((ux + dx_toward, uy + 1))
            candidates.append((ux + dx_toward, uy - 1))
            candidates.append((ux, uy + 1))
            candidates.append((ux, uy - 1))
        
        for pos in candidates:
            if self._can_move_to(unit, pos, reserved_positions):
                return pos
        
        return None