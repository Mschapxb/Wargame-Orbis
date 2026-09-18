from rng_scope import RNG
import heapq

import facing
import terrain as tr
import structures as st

# Obstacles qui masquent même un tireur posté sur un rempart
TALL_OBSTACLES = frozenset((st.HOUSE, st.GROVE))


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
        # Thème résolu (biome, rivière, collines): sert au rendu.
        self.theme = _raw.pop('theme', None)
        # Structures destructibles (maisons, haies, bosquets, rochers):
        # extraites AVANT siege_data, installées une fois la grille connue.
        _structures = _raw.pop('structures', None)

        # Données de siège
        self.siege_data = _raw
        self.gate_hp = dict(self.siege_data.get('gates', {}))  # {(x,y): hp}
        self.gate_max_hp = dict(self.gate_hp)
        self.gate_save = self.siege_data.get('gate_save', 7)   # Sauvegarde des portes
        self.walls = set(tuple(w) for w in self.siege_data.get('walls', []))
        self.ramparts = set(tuple(r) for r in self.siege_data.get('ramparts', []))
        self.stairs = set(tuple(s) for s in self.siege_data.get('stairs', []))
        # Enceintes, de l'extérieur vers l'intérieur. Le Siège n'en a qu'une
        # (construite depuis les clés historiques), la Citadelle deux. Seule
        # l'enceinte ACTIVE se défend et s'assaille; `gate_hp`, `walls`,
        # `ramparts` décrivent la géométrie physique de toutes.
        rings = self.siege_data.get('rings')
        if rings is None and self.siege_data.get('wall_x') is not None:
            rings = [{'wall_x': self.siege_data['wall_x'], 'gates': list(self.gate_hp.keys())}]
        self.rings = [{'wall_x': r['wall_x'], 'gates': [tuple(g) for g in r['gates']]}
                      for r in (rings or [])]
        self.active_ring = 0
        # Portes ouvertes volontairement par les défenseurs (sortie, repli).
        # Ouvertes PAR CASE: ouvrir le donjon n'ouvre pas l'enceinte
        # extérieure. Une porte ouverte est traversable par TOUT le monde.
        self.open_gate_cells = set()
        
        if grid is not None:
            self.grid = grid
        else:
            self.grid = [[0] * height for _ in range(width)]
            self.add_obstacles(obstacle_count)
        st.attach(self, _structures)

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
            x = RNG.randint(min_x, max_x)
            y = RNG.randint(min_y, max_y)
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
            return (x, y) in self.open_gate_cells or self.gate_hp.get((x, y), 0) <= 0
        return False  # 1=obstacle, 2=mur

    # ─── Enceintes ───

    @property
    def is_siege(self):
        return bool(self.rings)

    @property
    def wall_x(self):
        """Colonne du mur de l'enceinte active (None hors siège)."""
        return self.rings[self.active_ring]['wall_x'] if self.rings else None

    @property
    def has_next_ring(self):
        return self.active_ring + 1 < len(self.rings)

    @property
    def active_gates(self):
        """{position: PV} des portes de l'enceinte active."""
        if not self.rings:
            return {}
        return {g: self.gate_hp.get(g, 0) for g in self.rings[self.active_ring]['gates']}

    @property
    def active_breaches(self):
        """Brèches ouvertes dans le mur de l'enceinte active."""
        wx = self.wall_x
        return {b for b in getattr(self, 'breaches', ()) if b[0] == wx}

    @property
    def gates_open(self):
        """Les portes de l'enceinte active sont-elles ouvertes ?"""
        return bool(self.rings) and any(
            g in self.open_gate_cells for g in self.rings[self.active_ring]['gates'])

    @gates_open.setter
    def gates_open(self, value):
        if value:
            self.open_gates()
        elif self.rings:
            self.open_gate_cells.difference_update(self.rings[self.active_ring]['gates'])

    def open_gates(self):
        """Les défenseurs ouvrent les portes de l'enceinte active (sortie).
        Tout le monde passe."""
        if self.rings:
            self.open_ring_gates(self.active_ring)

    def open_ring_gates(self, index):
        """Ouvre les portes d'une enceinte donnée (repli vers le donjon)."""
        if 0 <= index < len(self.rings):
            self.open_gate_cells.update(self.rings[index]['gates'])

    def close_gates(self):
        """Referme les portes de l'enceinte active — seulement si aucune unité
        ne se trouve sur une case porte (on ne broie personne dans les
        battants)."""
        if not self.rings:
            return True
        gates = self.rings[self.active_ring]['gates']
        for pos in gates:
            if pos in self.units:
                return False
        self.open_gate_cells.difference_update(gates)
        return True

    def advance_ring(self):
        """L'enceinte active est tombée: ses portes encore debout sont
        forcées, l'enceinte suivante devient la ligne de défense."""
        if not self.has_next_ring:
            return False
        for g in self.rings[self.active_ring]['gates']:
            if self.gate_hp.get(g, 0) > 0:
                self.gate_hp[g] = 0
        self.active_ring += 1
        return True

    def has_line_of_fire(self, shooter, target):
        """Ligne de vue pour les tirs (armes portée >= 4).

        Les obstacles (rochers, maisons, haies, cœurs de bosquet), les murs
        et les portes fermées intactes BLOQUENT les tirs.
        Exception: une unité sur un rempart est surélevée — elle peut tirer
        par-dessus le mur, et peut être visée par-dessus le mur (c'est tout
        l'intérêt et le risque d'être sur le rempart). Elle voit aussi
        par-dessus les obstacles bas (haies, palissades, rochers) et le
        terrain, mais une maison ou un bosquet reste un écran.
        Le terrain (bois, collines) peut aussi masquer la cible, cf. terrain.blocks_line.
        """
        sx, sy = shooter.position
        tx, ty = target.position
        if (self.walls or self.gate_hp) and (self.is_rampart(sx, sy)
                                             or self.is_rampart(tx, ty)):
            return self._los_clear(sx, sy, tx, ty, elevated=True)
        if not self._los_clear(sx, sy, tx, ty):
            return False
        return self.terrain is None or not tr.blocks_line(self, sx, sy, tx, ty)

    def _los_clear(self, x0, y0, x1, y1, elevated=False):
        """Trace de Bresenham: False si un obstacle (1), un mur (2) ou une
        porte fermée intacte (3) se trouve entre les deux points (exclus).

        elevated: tir depuis/vers un rempart — murs, portes et obstacles bas
        ne comptent plus, seuls les obstacles hauts (TALL_OBSTACLES) coupent."""
        if elevated:
            structs = getattr(self, 'structures', None) or {}
            for (x, y) in self._line_cells(x0, y0, x1, y1):
                if self.grid[x][y] == 1:
                    entry = structs.get((x, y))
                    # Obstacle sans structure (générique): considéré haut
                    if entry is None or entry[0] in TALL_OBSTACLES:
                        return False
            return True
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        step_x = 1 if x1 > x0 else -1
        step_y = 1 if y1 > y0 else -1
        err = dx - dy
        x, y = x0, y0
        grid = self.grid
        gate_hp = self.gate_hp
        open_cells = self.open_gate_cells
        while True:
            if (x != x0 or y != y0) and (x != x1 or y != y1):
                c = grid[x][y]
                if c == 1 or c == 2:
                    return False
                if c == 3 and (x, y) not in open_cells and gate_hp.get((x, y), 0) > 0:
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
    
    @staticmethod
    def _line_cells(x0, y0, x1, y1):
        """Cases strictement entre deux points (tracé de Bresenham)."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        step_x = 1 if x1 > x0 else -1
        step_y = 1 if y1 > y0 else -1
        err = dx - dy
        x, y = x0, y0
        out = []
        while not (x == x1 and y == y1):
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += step_x
            if e2 < dx:
                err += dx
                y += step_y
            if not (x == x1 and y == y1):
                out.append((x, y))
        return out

    def is_wall(self, x, y):
        """Retourne True si la case est un mur."""
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[x][y] == 2
    
    def is_rampart(self, x, y):
        """Retourne True si la case est un rempart marchable."""
        return (x, y) in self.ramparts
    
    def on_active_rampart(self, x, y, unit=None, battle=None):
        """Rempart de l'enceinte ACTIVE tenu par un DÉFENSEUR. Les anciens
        remparts d'une enceinte tombée ne sont plus qu'un sol surélevé, et un
        assaillant monté sur le chemin de ronde n'a aucune raison de s'y
        figer: dans les deux cas, on ne s'y cramponne pas."""
        wx = self.wall_x
        if not ((x, y) in self.ramparts and wx is not None and wx < x <= wx + 2):
            return False
        if unit is not None and battle is not None:
            attackers = getattr(battle, '_army1_ids', None)
            if attackers is not None and id(unit) in attackers:
                return False
        return True

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

    def unit_distance(self, a, b, a_pos=None, b_pos=None):
        """Distance de combat entre deux unités: Manhattan entre leurs cases
        les plus proches (empreintes 1×1, 2×2, 2×4). Pour deux unités d'une
        case, c'est la distance entre positions.

        Mesurer d'ancre à ancre (coin haut-gauche) avantageait un camp: un
        cavalier 2×2 collé à l'OUEST d'un fantassin avait son ancre à 2 cases
        (« hors de portée »), collé à l'EST à 1 case. Les grosses unités de
        l'armée de gauche devaient contourner leur cible pour frapper, par
        derrière — camp gauche 57-63 % à armées égales avec cavalerie."""
        ax, ay = a.position if a_pos is None else a_pos
        bx, by = b.position if b_pos is None else b_pos
        aw, ah = self.get_unit_dims(a)
        bw, bh = self.get_unit_dims(b)
        dx = max(0, bx - (ax + aw - 1), ax - (bx + bw - 1))
        dy = max(0, by - (ay + ah - 1), ay - (by + bh - 1))
        return dx + dy

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
        open_cells = self.open_gate_cells
        reserved = reserved_positions
        # Lu une seule fois ici, valable pour tout cet appel (le terrain ne
        # change jamais en cours de bataille). Pas de cache d'instance: si
        # bf.terrain est réassigné entre deux appels d'a_star_path, le
        # prochain appel relit la valeur à jour dès cette ligne.
        terr = self.terrain
        _move_elev = tr.MOVE_ELEV
        _uphill = tr.UPHILL_FACTOR
        # Cases en feu: franchissables mais évitées (cf. terrain.step_cost)
        fires = getattr(self, 'fires', None)
        _fire_factor = tr.FIRE_MOVE_FACTOR
        
        open_set = []
        h0 = max(abs(gx - sx), abs(gy - sy))
        # Départage des égalités de coût: par x ORIENTÉ selon le sens de
        # marche, pour que deux armées en miroir suivent des chemins en
        # miroir. Un départage par x brut favorisait toujours l'ouest: les
        # deux camps n'abordaient pas l'ennemi sous les mêmes angles (biais
        # de côté révélé par l'orientation, cf. facing.py).
        xs = -1 if gx >= sx else 1
        heapq.heappush(open_set, (h0, 0.0, xs * sx, sy, sx))
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
            _, g, _xk, cy, cx = _heappop(open_set)
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
                if cell == 3 and (nx, ny) not in open_cells and gate_hp.get((nx, ny), 0) > 0:
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
                if fires and neighbor in fires:
                    base_cost *= _fire_factor

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
                    _heappush(open_set, (new_g + h, new_g, xs * nx, ny, nx))

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
        
        if self.unit_distance(unit, target) <= max_range:
            return None
        if unit.size > 1 or target.size > 1:
            return self._best_attack_anchor(unit, target, reserved_positions)
        
        # Siège: ne pas viser derrière le mur si portes intactes
        wall_x = self.wall_x
        unit_is_attacker = wall_x is not None and unit_pos[0] < wall_x
        all_gates_open = (self.gates_open or bool(self.active_breaches) or
                          (wall_x is not None and all(hp <= 0 for hp in self.active_gates.values()))) if self.gate_hp else True
        
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
        melee = max_range < 4
        close = self.manhattan_distance(unit_pos, target_pos) <= unit.vitesse * 2 + max_range

        # Parcours orienté: à priorité égale, la première case trouvée
        # l'emporte — du côté de l'unité, quel que soit son camp (miroir)
        dxs = range(-max_range, max_range + 1)
        if ux > tx:
            dxs = reversed(dxs)
        for dx in dxs:
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
                if cell == 3 and (px, py) not in self.open_gate_cells and gate_hp_dict.get((px, py), 0) > 0:
                    continue
                if terr is not None and tr.MOVE[terr[px][py]] is None:
                    continue
                pos = (px, py)
                if pos in reserved_positions:
                    continue
                
                occupied = 0 if pos not in units_dict else 1
                dist = abs(ux - px) + abs(uy - py)
                # L'étalement par couloirs sert l'approche; au contact, il
                # faisait glisser les unités de côté au lieu de frapper.
                lane_dist = abs(py - lane_y) // 3 if not close else 0
                # Mêlée: le flanc ou le dos de la cible valent au plus un pas
                # de détour (au-delà, on tournait autour au lieu de frapper)
                cost = float(dist)
                if melee:
                    cost += facing.ARC_COST[facing.arc_from(pos, target)]
                priority = (occupied, lane_dist, cost)
                
                if best_priority is None or priority < best_priority:
                    best_priority = priority
                    best_pos = pos
        
        return best_pos

    def _best_attack_anchor(self, unit, target, reserved_positions):
        """Case d'attaque (ancre) pour les grosses unités ou les grosses
        cibles: toute ancre dont l'EMPREINTE est à portée de celle de la
        cible, sans chevauchement. Même critère que la version 1×1 (la plus
        proche, flanc/dos à coût réduit), mais en miroir: aucun côté n'est
        interdit par la géométrie de l'ancre."""
        mr = unit._max_range
        uw, uh = self.get_unit_dims(unit)
        tw, th = self.get_unit_dims(target)
        tx, ty = target.position
        ux, uy = unit.position
        melee = mr < 4
        best, best_key = None, None
        for px in range(tx - mr - uw + 1, tx + tw + mr):
            for py in range(ty - mr - uh + 1, ty + th + mr):
                if not (0 <= px <= self.width - uw and 0 <= py <= self.height - uh):
                    continue
                g = self.unit_distance(unit, target, a_pos=(px, py))
                if g < 1 or g > mr:
                    continue
                if not self._can_move_to(unit, (px, py), reserved_positions):
                    continue
                if self.terrain is not None and any(
                        tr.MOVE[self.terrain[px + i][py + j]] is None
                        for i in range(uw) for j in range(uh)):
                    continue
                cost = abs(ux - px) + abs(uy - py)
                if melee:
                    cx, cy = px + (uw - 1) / 2.0, py + (uh - 1) / 2.0
                    cost += facing.ARC_COST[facing.arc_from((cx, cy), target)]
                key = (cost, abs(py - uy), abs(px - ux))
                if best_key is None or key < best_key:
                    best, best_key = (px, py), key
        return best

    # ─── Déplacement d'une unité pour le round ───
    # compute_move enchaîne des phases; chacune renvoie sa décision
    # (case, cible) — (None, cible) = rester sur place — ou None pour
    # laisser la main à la suivante.

    def compute_move(self, unit, battle, reserved_positions):
        """(case où aller ou None, cible ou None) pour ce round."""
        # Coût terrain réel du prochain déplacement, renseigné par
        # _advance_along quand la case vient d'un chemin A*. Réinitialisé à
        # chaque appel pour qu'une valeur d'un appel précédent ne puisse
        # jamais servir pour une destination différente.
        unit._planned_move_cost = None
        unit._planned_move_dest = None
        if unit.fleeing:
            return self._flee_move(unit, battle, reserved_positions)
        decision = self._artillery_decision(unit, battle)
        if decision is not None:
            return decision
        enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
        if not enemies:
            return None, None
        for phase in (self._rampart_shooter_decision, self._contact_decision,
                      self._post_decision):
            decision = phase(unit, battle, enemies)
            if decision is not None:
                return decision
        return self._approach_move(unit, battle, enemies, reserved_positions)

    def _advance_along(self, unit, path, speed, reserved_positions):
        """Case la plus avancée de `path` atteignable ce round (≤ speed en
        coût de terrain) et libre; None sinon. Mémorise son coût réel."""
        steps = tr.steps_within(self, unit.position, path, speed)
        for i in range(steps, 0, -1):
            candidate = path[i - 1]
            if self._can_move_to(unit, candidate, reserved_positions):
                unit._planned_move_cost = tr.path_cost(self, unit.position, path[:i])
                unit._planned_move_dest = candidate
                return candidate
        return None

    @staticmethod
    def _weakest_then_closest(unit, candidates):
        """Le plus blessé en proportion, puis le plus proche."""
        ux, uy = unit.position
        return min(candidates, key=lambda e: (e.hp / max(1, e.max_hp),
                                              abs(ux - e.position[0]) + abs(uy - e.position[1])))

    def _in_range(self, unit, enemies, need_sight=True):
        """Ennemis à portée effective (et visibles si need_sight)."""
        return [e for e in enemies
                if self.unit_distance(unit, e) <= tr.effective_range(self, unit, e)
                and (not need_sight or self.has_line_of_fire(unit, e))]

    def _flee_move(self, unit, battle, reserved_positions):
        """Unité en fuite: courir vers le bord le plus proche (≥ 2 cases)."""
        flee_speed = max(2, unit.vitesse)
        ux, uy = unit.position
        dist_left, dist_right = ux, self.width - 1 - ux
        dist_top, dist_bottom = uy, self.height - 1 - uy
        min_dist = min(dist_left, dist_right, dist_top, dist_bottom)
        if min_dist == dist_top:
            goal = (ux, 0)
        elif min_dist == dist_bottom:
            goal = (ux, self.height - 1)
        elif min_dist == dist_left:
            goal = (0, uy)
        else:
            goal = (self.width - 1, uy)

        path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions, partial=True)
        if path:
            step = self._advance_along(unit, path, flee_speed, reserved_positions)
            if step is not None:
                return step, None

        # Repli: pas direct dans les 8 directions (hors carte = case du bord),
        # celui qui rapproche le plus d'un bord
        candidates = []
        for step in range(flee_speed, 0, -1):
            for ddx in (-1, 0, 1):
                for ddy in (-1, 0, 1):
                    if ddx == 0 and ddy == 0:
                        continue
                    nx = max(0, min(self.width - 1, ux + ddx * step))
                    ny = max(0, min(self.height - 1, uy + ddy * step))
                    if self._can_move_to(unit, (nx, ny), reserved_positions):
                        border_dist = min(nx, self.width - 1 - nx, ny, self.height - 1 - ny)
                        candidates.append((border_dist, (nx, ny)))
        if candidates:
            candidates.sort()
            return candidates[0][1], None
        return None, None

    def _artillery_decision(self, unit, battle):
        """Artillerie: ancrée tant qu'elle a une cible atteignable et
        visible (sinon elle « tirait » sur des cibles hors d'atteinte),
        sinon repositionnement lent par la logique normale. Unités de
        vitesse 0: ne bougent jamais."""
        if not (unit.vitesse <= 0 or getattr(unit, 'is_artillery', False)):
            return None
        enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
        if not enemies:
            return None, None
        reachable = self._in_range(unit, enemies)
        if reachable:
            return None, self._weakest_then_closest(unit, reachable)
        if unit.vitesse <= 0:
            return None, None   # immobile et rien d'atteignable: tenir, sans visée
        order = getattr(unit, '_tactical_order', None)
        if order is not None and order.order_type == "demolish":
            return None, None   # elle abat ce qui masque sa cible: en place
        # Sur un rempart en défense, elle y reste (descendre seule = suicide)
        if (self.gate_hp and self.on_active_rampart(*unit.position, unit, battle)
                and not (order is not None and order.order_type == "withdraw")):
            return None, None
        return None

    def _rampart_shooter_decision(self, unit, battle, enemies):
        """Siège: tireurs et mages sur rempart ne bougent JAMAIS (sauf ordre
        de repli vers l'enceinte suivante)."""
        order = getattr(unit, '_tactical_order', None)
        if not (self.gate_hp and self.on_active_rampart(*unit.position, unit, battle)
                and not (order is not None and order.order_type == "withdraw")):
            return None
        if not (unit._max_range >= 4 or bool(unit.spells)):
            return None
        in_range = self._in_range(unit, enemies)
        if in_range:
            ux, uy = unit.position
            return None, min(in_range, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
        return None, None   # rien à portée: pas de visée futile

    def _separated_by_wall(self, unit, target):
        """Siège: mêlée et cible de part et d'autre du mur, portes fermées —
        la distance ment, il faut passer par une porte."""
        wall_x = self.wall_x
        return bool(wall_x and unit._max_range < 4
                    and (unit.position[0] < wall_x) != (target.position[0] < wall_x)
                    and not self.gates_open)

    def _contact_decision(self, unit, battle, enemies):
        """COMBAT COLLANT: un ennemi à portée → rester et combattre, sauf
        ordre de rompre le contact (kite: tireur qui recule en tirant;
        withdraw: unité à l'agonie qui décroche) ou tireur en « support »
        très exposé loin de son poste (> 3 cases), qui rejoint l'arrière."""
        order = getattr(unit, '_tactical_order', None)
        if order is not None and order.order_type in ("kite", "withdraw"):
            return None
        if (order is not None and order.order_type == "support"
                and order.target_pos is not None and unit._max_range >= 4
                and abs(unit.position[0] - order.target_pos[0])
                + abs(unit.position[1] - order.target_pos[1]) > 3):
            return None
        closest = min(enemies, key=lambda e: self.unit_distance(unit, e))
        if self.unit_distance(unit, closest) > tr.effective_range(self, unit, closest):
            return None
        # Tireurs: seules les cibles VISIBLES comptent (un ennemi caché
        # derrière la porte ne doit pas figer un arbalétrier sur place)
        in_range = self._in_range(unit, enemies, need_sight=unit._max_range >= 4)
        if not in_range:
            return None
        best = self._weakest_then_closest(unit, in_range)
        if self._separated_by_wall(unit, best):
            return None   # continuer vers le pathfinding normal
        return None, best

    def _post_decision(self, unit, battle, enemies):
        """Ordres support/guard/form au poste (≤ 1 case): tenir la position
        (sinon A* vers sa propre case + fallback_move faisaient dériver
        l'unité vers l'ennemi). Un garde quitte son poste si un ennemi
        approche à ≤ 6 cases."""
        order = getattr(unit, '_tactical_order', None)
        if not (order is not None and order.order_type in ("support", "guard", "form")
                and order.target_pos is not None):
            return None
        px, py = order.target_pos
        if abs(unit.position[0] - px) + abs(unit.position[1] - py) > 1:
            return None
        if order.order_type == "guard" and any(
                abs(e.position[0] - px) + abs(e.position[1] - py) <= 6 for e in enemies):
            return None
        # Au poste: tirer si quelque chose est atteignable ET visible
        in_range = self._in_range(unit, enemies, need_sight=unit._max_range >= 4)
        if in_range:
            return None, self._weakest_then_closest(unit, in_range)
        return None, None

    def _approach_move(self, unit, battle, enemies, reserved_positions):
        """Marcher vers la position ou la cible choisie par l'IA tactique."""
        from ai_commander import select_tactical_target, select_tactical_move_target
        target_unit, move_pos = select_tactical_move_target(unit, battle, self)

        # Flanquement/protection: se déplacer vers une position, pas une unité
        if move_pos and target_unit is None:
            target = min(enemies, key=lambda e: self.manhattan_distance(unit.position, e.position))
            path = self.a_star_path(unit.position, move_pos, unit, battle, reserved_positions,
                                    partial=True)
            if path:
                step = self._advance_along(unit, path, unit.vitesse, reserved_positions)
                if step is not None:
                    return step, target
            return self.fallback_move(unit, target, reserved_positions), target

        # Ciblage tactique: attaquer l'unité assignée par l'IA
        if target_unit and target_unit.is_alive:
            target = target_unit
        else:
            target = select_tactical_target(unit, battle, self)
            if target is None:
                target = min(enemies, key=lambda e: self.manhattan_distance(unit.position, e.position))

        current_dist = self.unit_distance(unit, target)
        if current_dist <= tr.effective_range(self, unit, target):
            # Tireur à portée mais aveuglé (rocher, maison, bois): rester
            # planté figeait les duels de tir jusqu'au plafond de rounds. On
            # se décale vers une case d'où la cible est visible.
            if unit._max_range >= 4 and not self.has_line_of_fire(unit, target):
                step = self._clear_line_step(unit, target, reserved_positions)
                if step is not None:
                    return step, target
            # Siège: mêlée côté assaillant, cible derrière le mur → pas
            # vraiment à portée, continuer vers la porte
            wall_x = self.wall_x
            if not (wall_x and unit._max_range < 4 and unit.position[0] < wall_x
                    and target.position[0] >= wall_x):
                return None, target

        # Siège: sur un rempart, tireurs et mages ne bougent jamais (l'avantage
        # défensif est trop précieux); la mêlée y reste tant que les portes
        # sont intactes ET fermées
        if self.on_active_rampart(*unit.position, unit, battle) and self.gate_hp:
            if unit._max_range >= 4 or bool(unit.spells):
                return None, target
            if any(hp > 0 for hp in self.active_gates.values()) and not self.gates_open:
                return None, target

        # Ordre "hold": rester (en gardant la cible pour tirer) tant
        # qu'aucun ennemi n'est au contact
        order = getattr(unit, '_tactical_order', None)
        if order and order.order_type == "hold" and current_dist > unit._max_range + 1:
            return None, target

        goal = self.find_best_attack_position(unit, target, battle, reserved_positions)
        if goal is None:
            # Siège, côté assaillant: passer par une porte (plus bas)
            if not (self.wall_x and unit.position[0] < self.wall_x):
                return None, target
        else:
            path = self.a_star_path(unit.position, goal, unit, battle, reserved_positions,
                                    partial=True)
            if path:
                step = self._advance_along(unit, path, unit.vitesse, reserved_positions)
                if step is not None:
                    return step, target

        if self.gate_hp:
            return self._gate_move(unit, battle, target, reserved_positions)
        return self.fallback_move(unit, target, reserved_positions), target

    def _gate_move(self, unit, battle, target, reserved_positions):
        """Siège, pas de chemin direct: passer par une porte. Côté
        assaillant: vers une porte franchissable (détruite, ouverte, ou
        brèche), sinon au contact de la porte intacte pour l'enfoncer,
        sinon longer le mur vers la porte (ou le couloir d'assaut)."""
        wall_x = self.wall_x
        gates_now = self.active_gates
        if unit.position[0] >= wall_x:
            return self.fallback_move(unit, target, reserved_positions), target

        if self.gates_open:
            passable = list(gates_now.keys())
        else:
            passable = [pos for pos, hp in gates_now.items() if hp <= 0]
        # Une brèche est une porte qui ne se referme pas
        passable += sorted(self.active_breaches)
        if passable:
            # Vers la porte désignée par le commandant (axe d'assaut choisi),
            # à défaut la plus proche
            gpath = self.a_star_path(unit.position, self._preferred_gate(unit, passable),
                                     unit, battle, reserved_positions)
            if gpath:
                step = self._advance_along(unit, gpath, unit.vitesse, reserved_positions)
                if step is not None:
                    return step, target

        intact = [pos for pos, hp in gates_now.items() if hp > 0]
        if intact:
            gate_goal = self._find_adjacent_free(self._preferred_gate(unit, intact), unit,
                                                 reserved_positions, side="left", wall_x=wall_x)
            if gate_goal:
                gpath = self.a_star_path(unit.position, gate_goal, unit, battle, reserved_positions)
                if gpath:
                    step = self._advance_along(unit, gpath, unit.vitesse, reserved_positions)
                    if step is not None:
                        return step, target

        all_gates = list(gates_now.keys())
        if all_gates:
            return self._skirt_wall_step(unit, all_gates, reserved_positions), target
        return None, target

    def _skirt_wall_step(self, unit, gates, reserved_positions):
        """Un pas le long du mur: vers la porte la plus proche, vers le
        couloir d'assaut, sinon en recul. None si tout est bloqué."""
        from ai_commander import get_lane_offset
        lane_y = get_lane_offset(unit, self)
        ux, uy = unit.position
        gy = min(gates, key=lambda g: abs(uy - g[1]))[1]
        dy = 0 if uy == gy else (1 if gy > uy else -1)
        candidates = []
        if dy != 0:
            candidates += [(ux, uy + dy), (ux - 1, uy + dy)]
        dy_lane = 0 if lane_y == uy else (1 if lane_y > uy else -1)
        if dy_lane != 0 and dy_lane != dy:
            candidates += [(ux, uy + dy_lane), (ux - 1, uy + dy_lane)]
        candidates.append((ux - 1, uy))
        if dy != 0:
            candidates.append((ux - 2, uy + dy))
        return next((c for c in candidates if self._can_move_to(unit, c, reserved_positions)),
                    None)

    def _clear_line_step(self, unit, target, reserved_positions):
        """Case atteignable ce round (≤ vitesse pas) d'où `target` est à portée
        ET visible; la plus proche. None s'il n'y en a pas."""
        ux, uy = unit.position
        tx, ty = target.position
        reach = tr.effective_range(self, unit, target)
        r = max(1, min(3, unit.vitesse))
        terr = self.terrain
        best, best_key = None, None
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if not (dx or dy):
                    continue
                pos = (ux + dx, uy + dy)
                if abs(pos[0] - tx) + abs(pos[1] - ty) > reach:
                    continue
                if not self._can_move_to(unit, pos, reserved_positions):
                    continue
                if not self._los_clear(pos[0], pos[1], tx, ty):
                    continue
                if terr is not None and tr.blocks_line(self, pos[0], pos[1], tx, ty):
                    continue
                key = (max(abs(dx), abs(dy)), abs(dx) + abs(dy), pos)
                if best_key is None or key < best_key:
                    best, best_key = pos, key
        return best

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