import random
import heapq

import terrain as tr


class Battlefield:
    def __init__(self, width=40, height=30, obstacle_count=8, map_name="Prairie", grid=None, map_data=None):
        self.width = width
        self.height = height
        self.map_name = map_name
        self.units = {}
        
        # Décor purement visuel: extrait AVANT tout le reste. Il ne doit
        # surtout pas rester dans siege_data — `bool(siege_data)` sert à
        # détecter une carte de siège, et un simple buisson suffirait à
        # faire croire à l'IA qu'elle défend une forteresse.
        _raw = dict(map_data or {})
        self.decor = list(_raw.pop('decor', []))
        self.ground_patches = list(_raw.pop('ground_patches', []))
        # Demi-écart entre les fronts au déploiement, imposé par la carte
        # (forêt, village: juste à l'extérieur du terrain central)
        self.deploy_gap = _raw.pop('deploy_gap', None)

        # Terrain à effets (colline, bois, rivière…): grille parallèle à
        # `grid`. Extrait AVANT siege_data pour la même raison que le décor.
        self.terrain = _raw.pop('terrain', None)

        # Données de siège
        self.siege_data = _raw
        self.gate_hp = dict(self.siege_data.get('gates', {}))  # {(x,y): hp}
        self.gate_save = self.siege_data.get('gate_save', 7)   # Sauvegarde des portes
        self.walls = set(tuple(w) for w in self.siege_data.get('walls', []))
        self.ramparts = set(tuple(r) for r in self.siege_data.get('ramparts', []))
        self.stairs = set(tuple(s) for s in self.siege_data.get('stairs', []))
        # Portes ouvertes volontairement par les défenseurs (sortie).
        # Une porte ouverte est traversable par TOUT le monde (risque assumé).
        self.gates_open = False
        
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
        if self.terrain is not None and tr.MOVE[self.terrain[x][y]] is None:
            return False  # Rivière: infranchissable
        cell = self.grid[x][y]
        if cell == 0:
            return True
        if cell == 4:  # Rempart: marchable
            return True
        if cell == 5:  # Escalier: marchable
            return True
        if cell == 3:  # Porte: traversable si détruite (hp <= 0) ou ouverte
            return self.gates_open or self.gate_hp.get((x, y), 0) <= 0
        return False  # 1=obstacle, 2=mur

    def open_gates(self):
        """Les défenseurs ouvrent les portes (sortie). Tout le monde passe."""
        self.gates_open = True

    def close_gates(self):
        """Referme les portes — seulement si aucune unité ne se trouve
        sur une case porte (on ne broie personne dans les battants)."""
        for pos in self.gate_hp:
            if pos in self.units:
                return False
        self.gates_open = False
        return True

    def has_line_of_fire(self, shooter, target):
        """Ligne de vue pour les tirs (armes portée >= 4).

        Les murs et les portes fermées intactes BLOQUENT les tirs.
        Exception: une unité sur un rempart est surélevée — elle peut tirer
        par-dessus le mur, et peut être visée par-dessus le mur (c'est tout
        l'intérêt et le risque d'être sur le rempart).
        Le terrain (bois, collines) peut aussi masquer la cible, cf. terrain.blocks_line.
        """
        sx, sy = shooter.position
        tx, ty = target.position
        if not self.walls and not self.gate_hp:
            if self.terrain is None:
                return True  # Ni fortifications ni terrain sur cette carte
            return not tr.blocks_line(self, sx, sy, tx, ty)
        if self.is_rampart(sx, sy) or self.is_rampart(tx, ty):
            return True
        if not self._los_clear(sx, sy, tx, ty):
            return False
        return self.terrain is None or not tr.blocks_line(self, sx, sy, tx, ty)

    def _los_clear(self, x0, y0, x1, y1):
        """Trace de Bresenham: False si un mur (2) ou une porte fermée
        intacte (3) se trouve entre les deux points (exclus)."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        step_x = 1 if x1 > x0 else -1
        step_y = 1 if y1 > y0 else -1
        err = dx - dy
        x, y = x0, y0
        grid = self.grid
        gate_hp = self.gate_hp
        gates_open = self.gates_open
        while True:
            if (x != x0 or y != y0) and (x != x1 or y != y1):
                c = grid[x][y]
                if c == 2:
                    return False
                if c == 3 and not gates_open and gate_hp.get((x, y), 0) > 0:
                    return False
            if x == x1 and y == y1:
                return True
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += step_x
            if e2 < dx:
                err += dx
                y += step_y
    
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
        self.remove_unit(unit)
        unit.position = new_pos
        self.place_unit(unit)

    def manhattan_distance(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def chebyshev_distance(self, a, b):
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    def a_star_path(self, start, goal, unit, battle, reserved_positions=None, max_nodes=1200,
                    partial=False):
        """A* optimisé — opérations inlinées pour la performance.

        partial=True: si l'objectif est inaccessible (case d'arbre visée par
        un ordre, poche fermée, budget épuisé), renvoie le chemin vers la
        case atteinte la plus PROCHE de l'objectif plutôt qu'une liste vide.
        Sans cela, l'unité retombait sur un déplacement glouton et venait
        buter contre les bosquets. Réservé au mouvement: une charge, elle,
        doit réellement atteindre sa case.
        """
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
        gates_open = self.gates_open
        reserved = reserved_positions
        # Lu une seule fois ici, valable pour tout cet appel (le terrain ne
        # change jamais en cours de bataille). Pas de cache d'instance: si
        # bf.terrain est réassigné entre deux appels d'a_star_path, le
        # prochain appel relit la valeur à jour dès cette ligne.
        terr = self.terrain
        _move_elev = tr.MOVE_ELEV
        _uphill = tr.UPHILL_FACTOR
        
        open_set = []
        h0 = max(abs(gx - sx), abs(gy - sy))
        heapq.heappush(open_set, (h0, 0.0, sx, sy))
        g_score = {start: 0.0}
        came_from = {}
        best_node, best_h = start, h0
        
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
            if partial:
                hc = _abs(gx - cx)
                hcy = _abs(gy - cy)
                if hcy > hc:
                    hc = hcy
                if hc < best_h:
                    best_h, best_node = hc, current

            # Élévation de la case courante: invariante pour les 8 voisins.
            # Calculée une fois par nœud (pas huit fois, une par voisin),
            # depuis `terr` local ci-dessus — donc toujours cohérente avec
            # les valeurs lues pour chaque voisin dans la même boucle.
            if terr is not None:
                cur_elevated = _move_elev[terr[cx][cy]][1]

            for dx, dy in _DIRS:
                nx, ny = cx + dx, cy + dy

                # is_valid inliné
                if nx < 0 or nx >= width or ny < 0 or ny >= height:
                    continue
                cell = grid[nx][ny]
                if cell == 1 or cell == 2:
                    continue
                if cell == 3 and not gates_open and gate_hp.get((nx, ny), 0) > 0:
                    continue

                neighbor = (nx, ny)
                if neighbor in reserved:
                    continue

                base_cost = _DIAG_COST if (dx and dy) else 1.0
                if terr is not None:
                    mc, n_elevated = _move_elev[terr[nx][ny]]
                    if mc is None:
                        continue  # rivière
                    if n_elevated and not cur_elevated:
                        mc *= _uphill
                    base_cost *= mc

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

        if partial and best_node != start:
            path = []
            current = best_node
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path
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
        all_gates_open = (self.gates_open or
                          (wall_x is not None and all(hp <= 0 for hp in self.gate_hp.values()))) if self.gate_hp else True
        
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
        terr = self.terrain

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
                if cell == 3 and not self.gates_open and gate_hp_dict.get((px, py), 0) > 0:
                    continue
                if terr is not None and tr.MOVE[terr[px][py]] is None:
                    continue
                pos = (px, py)
                if pos in reserved_positions:
                    continue
                
                occupied = 0 if pos not in units_dict else 1
                dist = abs(ux - px) + abs(uy - py)
                lane_dist = abs(py - lane_y) // 3
                priority = (occupied, lane_dist, dist)
                
                if best_priority is None or priority < best_priority:
                    best_priority = priority
                    best_pos = pos
        
        return best_pos

    def compute_move(self, unit, battle, reserved_positions):
        # Coût terrain réel du prochain déplacement, calculé ci-dessous quand
        # le candidat retourné vient d'un chemin A* (path[i-1]/gpath[i-1]).
        # Réinitialisé à chaque appel pour qu'une valeur d'un appel précédent
        # ne puisse jamais être réutilisée pour une destination différente.
        unit._planned_move_cost = None
        unit._planned_move_dest = None
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
            path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions, partial=True)
            if path:
                steps = tr.steps_within(self, unit.position, path, flee_speed)
                # Essayer le step le plus loin possible, puis réduire
                for i in range(steps, 0, -1):
                    new_pos = path[i - 1]
                    if self._can_move_to(unit, new_pos, reserved_positions):
                        unit._planned_move_cost = tr.path_cost(self, unit.position, path[:i])
                        unit._planned_move_dest = new_pos
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
        
        # Artillerie: ancrée tant qu'elle a une cible atteignable, sinon
        # repositionnement lent (les machines de guerre ont vitesse 1-2).
        # Unités vraiment immobiles (vitesse 0): ne bougent jamais.
        if unit.vitesse <= 0 or getattr(unit, 'is_artillery', False):
            enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
            if not enemies:
                return None, None
            # L'artillerie ne vise QUE ce qu'elle peut atteindre ET voir
            # (sinon elle "tirait" inutilement sur des cibles hors d'atteinte)
            ux_a, uy_a = unit.position
            reachable = [e for e in enemies
                         if abs(ux_a - e.position[0]) + abs(uy_a - e.position[1]) <= tr.effective_range(self, unit, e)
                         and self.has_line_of_fire(unit, e)]
            if reachable:
                # Priorité: achever les blessés, sinon le plus proche
                t = min(reachable, key=lambda e: (e.hp / max(1, e.max_hp),
                                                  abs(ux_a - e.position[0]) + abs(uy_a - e.position[1])))
                return None, t
            if unit.vitesse <= 0:
                return None, None  # Immobile et rien d'atteignable: tenir, sans visée
            # Artillerie mobile sans cible visible: si elle est sur un rempart
            # en défense, elle y reste (descendre seule = suicide); sinon elle
            # se repositionne lentement via la logique normale ci-dessous.
            if self.gate_hp and self.is_rampart(ux_a, uy_a):
                return None, None
        
        enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
        if not enemies:
            return None, None
        
        # === Siège: tireurs/mages sur rempart ne bougent JAMAIS ===
        if self.gate_hp and self.is_rampart(*unit.position):
            if unit._max_range >= 4 or bool(unit.spells):
                ux, uy = unit.position
                in_range = [e for e in enemies
                            if abs(ux - e.position[0]) + abs(uy - e.position[1]) <= tr.effective_range(self, unit, e)
                            and self.has_line_of_fire(unit, e)]
                if in_range:
                    return None, min(in_range, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
                return None, None  # Rien à portée: pas de visée futile
        
        # === COMBAT COLLANT: si un ennemi est au contact (dist ≤ portée), ===
        # === l'unité reste et le combat, elle ne se déplace PAS ===
        # Exception: ordre "kite" (tireur qui recule en tirant)
        _order = getattr(unit, '_tactical_order', None)
        # "kite" (tireur qui recule en tirant) et "withdraw" (unité à
        # l'agonie qui décroche) rompent volontairement le contact.
        _is_kiting = (_order is not None
                      and _order.order_type in ("kite", "withdraw"))
        # Repli urgent: tireur en ordre "support" loin de son poste (très
        # exposé devant la ligne) → ne pas rester collé, rejoindre l'arrière
        _is_repositioning = (
            _order is not None and _order.order_type == "support"
            and _order.target_pos is not None and unit._max_range >= 4
            and abs(unit.position[0] - _order.target_pos[0])
            + abs(unit.position[1] - _order.target_pos[1]) > 3)
        ux, uy = unit.position
        closest_dist = 999
        closest_enemy = None
        for e in enemies:
            d = abs(ux - e.position[0]) + abs(uy - e.position[1])
            if d < closest_dist:
                closest_dist = d
                closest_enemy = e
        
        if (closest_enemy is not None
                and closest_dist <= tr.effective_range(self, unit, closest_enemy)
                and not unit.fleeing and not _is_kiting and not _is_repositioning):
            # En mêlée: ne pas bouger, combattre le plus proche (ou le plus blessé à portée)
            in_range = [e for e in enemies
                        if abs(ux - e.position[0]) + abs(uy - e.position[1])
                        <= tr.effective_range(self, unit, e)]
            # Tireurs: seules les cibles VISIBLES comptent (un ennemi caché
            # derrière la porte ne doit pas figer un arbalétrier sur place)
            if unit._max_range >= 4:
                in_range = [e for e in in_range if self.has_line_of_fire(unit, e)]
            if in_range:
                # Priorité: le plus blessé en proportion, puis le plus proche
                best_target = min(in_range, key=lambda e: (e.hp / max(1, e.max_hp), abs(ux - e.position[0]) + abs(uy - e.position[1])))
                
                # Exception siège: CaC séparé de sa cible par le mur (dans un sens
                # comme dans l'autre) → la distance Manhattan ment, continuer le pathfinding
                wall_x_s = self.siege_data.get('wall_x') if self.siege_data else None
                if (wall_x_s and unit._max_range < 4
                        and ((ux < wall_x_s) != (best_target.position[0] < wall_x_s))
                        and not self.gates_open):
                    pass  # Continue vers le pathfinding normal
                else:
                    return None, best_target
        
        # Utiliser le ciblage tactique de l'IA si disponible
        from ai_commander import select_tactical_target, select_tactical_move_target
        
        # === Ordres SUPPORT/GUARD au poste: tenir la position ===
        # (sans ce bloc, A* vers sa propre case + fallback_move feraient
        # dériver l'unité vers l'ennemi)
        if (_order is not None and _order.order_type in ("support", "guard")
                and _order.target_pos is not None):
            _post = _order.target_pos
            _d_post = abs(ux - _post[0]) + abs(uy - _post[1])
            if _d_post <= 1:
                _guard_busy = False
                if _order.order_type == "guard":
                    _guard_busy = any(
                        abs(e.position[0] - _post[0]) + abs(e.position[1] - _post[1]) <= 6
                        for e in enemies)
                if not _guard_busy:
                    # Au poste: ne pas bouger; tirer si quelque chose est
                    # atteignable ET visible, sinon pas de visée
                    mr = unit._max_range
                    in_r = [e for e in enemies
                            if abs(ux - e.position[0]) + abs(uy - e.position[1]) <= tr.effective_range(self, unit, e)
                            and (mr < 4 or self.has_line_of_fire(unit, e))]
                    if in_r:
                        return None, min(in_r, key=lambda e: (e.hp / max(1, e.max_hp),
                                                              abs(ux - e.position[0]) + abs(uy - e.position[1])))
                    return None, None
        
        target_unit, move_pos = select_tactical_move_target(unit, battle, self)
        
        # Flanquement/protection: se déplacer vers une position, pas une unité
        if move_pos and target_unit is None:
            goal = move_pos
            # Trouver une cible pour le combat (le plus proche)
            target = min(enemies, key=lambda e: self.manhattan_distance(unit.position, e.position))
            path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions, partial=True)
            if path:
                steps = tr.steps_within(self, unit.position, path, unit.vitesse)
                for i in range(steps, 0, -1):
                    candidate = path[i - 1]
                    if self._can_move_to(unit, candidate, reserved_positions):
                        unit._planned_move_cost = tr.path_cost(self, unit.position, path[:i])
                        unit._planned_move_dest = candidate
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
        
        if current_dist <= tr.effective_range(self, unit, target):
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
            # CaC sur rempart: rester tant que portes intactes ET fermées
            intact_gates = any(hp > 0 for hp in self.gate_hp.values()) and not self.gates_open
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
            path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions, partial=True)
            if path:
                steps = tr.steps_within(self, unit.position, path, unit.vitesse)
                for i in range(steps, 0, -1):
                    candidate = path[i - 1]
                    if self._can_move_to(unit, candidate, reserved_positions):
                        unit._planned_move_cost = tr.path_cost(self, unit.position, path[:i])
                        unit._planned_move_dest = candidate
                        return candidate, target

        # Siège: pas de chemin direct → passer par une porte
        if self.gate_hp:
            wall_x = self.siege_data.get('wall_x', 0)
            ux = unit.position[0]
            
            # Unité côté attaquant (à gauche du mur)?
            if ux < wall_x:
                # Chercher une porte franchissable (détruite OU ouverte)
                if self.gates_open:
                    destroyed_gates = list(self.gate_hp.keys())
                else:
                    destroyed_gates = [pos for pos, hp in self.gate_hp.items() if hp <= 0]
                if destroyed_gates:
                    # Aller vers la porte désignée par le commandant (axe
                    # d'assaut choisi), à défaut la plus proche
                    nearest = self._preferred_gate(unit, destroyed_gates)
                    gpath = self.a_star_path(unit.position, nearest, unit, battle, reserved_positions)
                    if gpath:
                        steps = tr.steps_within(self, unit.position, gpath, unit.vitesse)
                        for i in range(steps, 0, -1):
                            candidate = gpath[i - 1]
                            if self._can_move_to(unit, candidate, reserved_positions):
                                unit._planned_move_cost = tr.path_cost(self, unit.position, gpath[:i])
                                unit._planned_move_dest = candidate
                                return candidate, target
                
                # Sinon aller adjacent à la porte intacte la plus proche (pour la détruire au CaC)
                intact_gates = [pos for pos, hp in self.gate_hp.items() if hp > 0]
                if intact_gates:
                    nearest_gate = self._preferred_gate(unit, intact_gates)
                    gate_goal = self._find_adjacent_free(nearest_gate, unit, reserved_positions, side="left", wall_x=wall_x)
                    if gate_goal:
                        gpath = self.a_star_path(unit.position, gate_goal, unit, battle, reserved_positions)
                        if gpath:
                            steps = tr.steps_within(self, unit.position, gpath, unit.vitesse)
                            for i in range(steps, 0, -1):
                                candidate = gpath[i - 1]
                                if self._can_move_to(unit, candidate, reserved_positions):
                                    unit._planned_move_cost = tr.path_cost(self, unit.position, gpath[:i])
                                    unit._planned_move_dest = candidate
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
    
    def _preferred_gate(self, unit, gates):
        """Porte visée: celle que le commandant a désignée pour l'assaut si
        elle est encore utilisable, sinon la plus proche."""
        wanted = getattr(unit, '_assault_gate', None)
        if wanted is not None and wanted in gates:
            return wanted
        return min(gates, key=lambda g: self.manhattan_distance(unit.position, g))

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