"""Système de cartes WW1 — terrains de la Grande Guerre.

Types de cellules dans la grille:
    0 = vide (traversable)
    1 = obstacle (infranchissable — cratère, barbelés denses, ruine)
    2 = mur (infranchissable — mur béton, casemate)
    3 = porte (destructible — barrage de barbelés franchissable)
    4 = rempart (marchable — tranchée / position surélevée)
    5 = escalier (marchable — boyau de communication vers la tranchée)
"""

import random


# ═══════════════════════════════════════════════════════════════
#                    DÉFINITIONS DES MAPS
# ═══════════════════════════════════════════════════════════════

MAP_TYPES = {
    "No Man's Land": {
        "description": "Terrain dévasté — cratères, barbelés, boue et ruines entre deux lignes de tranchées",
        "bg_color": (55, 48, 35),
        "obstacle_color": (40, 35, 25),
        "grid_color": (62, 55, 42),
    },
    "Tranchées": {
        "description": "Système de tranchées — lignes défensives avec boyaux et positions de tir",
        "bg_color": (50, 44, 32),
        "obstacle_color": (70, 60, 40),
        "grid_color": (58, 52, 38),
        "wall_color": (80, 70, 50),
        "gate_color": (60, 50, 35),
    },
    "Village détruit": {
        "description": "Village en ruines — rues effondrées, bâtiments éventrés, positions de combat urbain",
        "bg_color": (58, 52, 44),
        "obstacle_color": (90, 78, 60),
        "grid_color": (66, 60, 50),
    },
    "Forêt d'Argonne": {
        "description": "Forêt dense — sous-bois épais, sentiers étroits, combat rapproché inévitable",
        "bg_color": (32, 50, 28),
        "obstacle_color": (22, 65, 18),
        "grid_color": (38, 56, 34),
    },
    "Champs de Flandre": {
        "description": "Plaine ouverte — terrain plat, quelques fermes fortifiées, idéal pour l'artillerie",
        "bg_color": (60, 70, 40),
        "obstacle_color": (75, 85, 50),
        "grid_color": (68, 78, 46),
    },
}


def get_map_names():
    return list(MAP_TYPES.keys())


def get_map_info(name):
    return MAP_TYPES.get(name, MAP_TYPES["No Man's Land"])


# ═══════════════════════════════════════════════════════════════
#                      GÉNÉRATEURS
# ═══════════════════════════════════════════════════════════════

def generate_no_mans_land(width, height):
    """No Man's Land : terrain dévasté entre deux lignes de tranchées.

    Structure:
      • Ligne de tranchée alliée (x ≈ width//6) — remparts + boyaux
      • Ligne de tranchée ennemie (x ≈ 5*width//6) — remparts + boyaux
      • Zone centrale parsemée de cratères (obstacles), barbelés et ruines
      • Quelques barbelés franchissables (type 3) en lignes irrégulières
    """
    grid = [[0] * height for _ in range(width)]

    # ── Zones de déploiement (dégagées) ──
    deploy_w = width // 7

    # ── Cratères dans le No Man's Land ──
    nml_start = deploy_w + 2
    nml_end = width - deploy_w - 2
    crater_count = random.randint(18, 28)
    craters = []
    for _ in range(crater_count * 10):
        if len(craters) >= crater_count:
            break
        cx = random.randint(nml_start, nml_end)
        cy = random.randint(2, height - 3)
        # Pas trop proches entre eux
        if any(abs(cx - ox) + abs(cy - oy) < 4 for ox, oy in craters):
            continue
        r = random.randint(1, 2)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < width and 0 <= ny < height:
                    if abs(dx) + abs(dy) <= r:
                        grid[nx][ny] = 1
        craters.append((cx, cy))

    # ── Lignes de barbelés irrégulières (franchissables type 3) ──
    # 2 à 3 lignes entre les tranchées
    wire_xs = sorted(random.sample(range(nml_start + 4, nml_end - 4), 3))
    for wx in wire_xs:
        y = random.randint(1, 3)
        while y < height - 1:
            length = random.randint(3, 7)
            gap = random.randint(1, 4)
            for dy in range(length):
                ny = y + dy
                if 0 < ny < height - 1 and grid[wx][ny] == 0:
                    grid[wx][ny] = 3  # Barbelé franchissable
            y += length + gap

    # ── Tranchée côté gauche (alliés) ──
    tx_left = deploy_w + 1
    ramparts_left = []
    stairs_left = []
    for y in range(1, height - 1):
        grid[tx_left][y] = 4  # Rempart (tranchée)
        ramparts_left.append((tx_left, y))
        if y % 5 == 0 and tx_left + 1 < width:
            grid[tx_left + 1][y] = 5  # Boyau de sortie
            stairs_left.append((tx_left + 1, y))

    # ── Tranchée côté droit (ennemis) ──
    tx_right = width - deploy_w - 2
    ramparts_right = []
    stairs_right = []
    for y in range(1, height - 1):
        grid[tx_right][y] = 4
        ramparts_right.append((tx_right, y))
        if y % 5 == 0 and tx_right - 1 >= 0:
            grid[tx_right - 1][y] = 5
            stairs_right.append((tx_right - 1, y))

    # Pas de siege_data, les tranchées sont juste des remparts sans portes
    return grid, {
        'walls': [],
        'ramparts': ramparts_left + ramparts_right,
        'stairs': stairs_left + stairs_right,
        'gates': {},
        'gate_save': 7,
        'gate_positions': [],
    }


def generate_tranchees(width, height):
    """Tranchées : assaut sur une position défensive fortifiée.

    Structure:
      • Mur de tranchée principal (x ≈ 2*width//3) avec accès par boyaux
      • Barbelés devant (type 3, destructibles)
      • Remparts derrière le mur pour les défenseurs
      • Couverts pour les assaillants (sacs de sable, ruines)
    """
    grid = [[0] * height for _ in range(width)]

    wall_x = width * 2 // 3

    # ── Mur de tranchée ──
    walls = []
    ramparts = []
    stairs = []
    gates = {}

    # Trouées régulières dans le mur (boyaux de communication = "portes")
    gap_positions = [height // 4, height // 2, 3 * height // 4]

    for y in range(1, height - 1):
        is_gap = any(abs(y - gy) < 2 for gy in gap_positions)
        if is_gap:
            grid[wall_x][y] = 3
            gates[(wall_x, y)] = 8  # Barricade avec 8 PV
        else:
            grid[wall_x][y] = 2
            walls.append((wall_x, y))
            # Remparts derrière
            for dx in [1, 2]:
                rx = wall_x + dx
                if 0 <= rx < width:
                    grid[rx][y] = 4
                    ramparts.append((rx, y))
            sx = wall_x + 3
            if 0 <= sx < width:
                grid[sx][y] = 5
                stairs.append((sx, y))

    # ── Ligne de barbelés devant la tranchée ──
    wire_x = wall_x - 5
    for y in range(2, height - 2):
        if random.random() < 0.6:
            grid[wire_x][y] = 3  # Barbelé franchissable
            gates[(wire_x, y)] = 4

    # ── Couverts pour les assaillants ──
    # Ligne 1 (proche)
    for zone_y in [height // 5, height // 2, 4 * height // 5]:
        for _ in range(random.randint(2, 4)):
            ox = random.randint(width // 4, wire_x - 6)
            oy = zone_y + random.randint(-2, 2)
            if 1 < ox < wire_x - 1 and 1 < oy < height - 1 and grid[ox][oy] == 0:
                grid[ox][oy] = 1

    # Ligne 2 (avancée)
    for zone_y in [height // 4, height // 2, 3 * height // 4]:
        for _ in range(random.randint(2, 3)):
            ox = random.randint(wire_x - 5, wire_x - 2)
            oy = zone_y + random.randint(-2, 2)
            if 1 < ox < wire_x - 1 and 1 < oy < height - 1 and grid[ox][oy] == 0:
                grid[ox][oy] = 1

    siege_data = {
        'walls': walls,
        'ramparts': ramparts,
        'stairs': stairs,
        'gates': gates,
        'gate_save': 3,
        'gate_positions': gap_positions,
        'wall_x': wall_x,
    }

    return grid, siege_data


def generate_village_detruit(width, height):
    """Village détruit : ruines de bâtiments, rues encombrées, combat urbain.

    Structure:
      • Rues principales conservées (dégagées mais exposées)
      • Bâtiments éventrés (clusters d'obstacles irréguliers)
      • Quelques murs épais restants (type 2) = positions défensives
      • Cratères d'obus dans les rues
    """
    grid = [[0] * height for _ in range(width)]

    center_y = height // 2
    center_x = width // 2

    # Rues principales (garanties libres)
    street_half = 2
    road_north_y = height // 4
    road_south_y = 3 * height // 4

    def is_main_street(x, y):
        if abs(y - center_y) <= street_half:
            return True
        if abs(y - road_north_y) <= 1:
            return True
        if abs(y - road_south_y) <= 1:
            return True
        # Rues transversales
        for tx in [width // 4, width // 2, 3 * width // 4]:
            if abs(x - tx) <= 1:
                return True
        return False

    # ── Bâtiments en ruines ──
    bld_zones_x = [width // 6, width // 3, width // 2, 2 * width // 3, 5 * width // 6]
    for bx in bld_zones_x:
        for _ in range(random.randint(3, 6)):
            ox = bx + random.randint(-5, 5)
            oy = random.randint(3, height - 4)
            w = random.randint(2, 5)
            h_b = random.randint(2, 4)
            for dx in range(w):
                for dy in range(h_b):
                    nx, ny = ox + dx, oy + dy
                    if 0 < nx < width - 1 and 0 < ny < height - 1:
                        if not is_main_street(nx, ny):
                            # Mélange ruines légères (1) et murs épais (2)
                            grid[nx][ny] = 2 if random.random() < 0.25 else 1

    # ── Cratères dans les rues ──
    for _ in range(random.randint(8, 14)):
        cx = random.randint(width // 8, 7 * width // 8)
        cy = random.randint(2, height - 3)
        if is_main_street(cx, cy) and grid[cx][cy] == 0:
            grid[cx][cy] = 1

    # ── Passe finale : dégager les rues ──
    for x in range(width):
        for y in range(height):
            if is_main_street(x, y):
                grid[x][y] = 0

    return grid, {}


def generate_foret_argonne(width, height):
    """Forêt d'Argonne : sous-bois dense avec sentiers étroits.

    Structure:
      • Forêt très dense (80% d'obstacles hors des sentiers)
      • 1 sentier central (3 cases) + 2 sentiers latéraux (2 cases)
      • Clairières rares et petites
      • Quelques positions de tireurs embusqués (couverts isolés dans les sentiers)
    """
    grid = [[0] * height for _ in range(width)]

    center_y = height // 2
    trail_north_y = height // 3
    trail_south_y = 2 * height // 3

    TRAIL_C = 1   # Sentier central : 3 cases (±1)
    TRAIL_S = 1   # Sentiers latéraux : 3 cases (±1)

    def trail_clearance(y):
        d_c = max(0, abs(y - center_y) - TRAIL_C)
        d_n = max(0, abs(y - trail_north_y) - TRAIL_S)
        d_s = max(0, abs(y - trail_south_y) - TRAIL_S)
        return min(d_c, d_n, d_s)

    for x in range(width):
        for y in range(height):
            if y == 0 or y == height - 1:
                continue
            dist = trail_clearance(y)
            if dist == 0:
                continue
            p = 0.55 if dist == 1 else 0.80 if dist == 2 else 0.92
            if random.random() < p:
                grid[x][y] = 1

    # Clairières petites
    for _ in range(random.randint(4, 7)):
        cx = random.randint(width // 5, 4 * width // 5)
        zone = random.choice([
            (trail_north_y + TRAIL_S + 2, center_y - TRAIL_C - 2),
            (center_y + TRAIL_C + 2, trail_south_y - TRAIL_S - 2),
        ])
        if zone[0] >= zone[1]:
            continue
        cy = random.randint(zone[0], zone[1])
        r = random.randint(1, 3)
        for ox in range(cx - r, cx + r + 1):
            for oy in range(cy - r, cy + r + 1):
                if 1 <= ox < width - 1 and 1 <= oy < height - 1:
                    if abs(ox - cx) + abs(oy - cy) <= r:
                        grid[ox][oy] = 0

    # Garantie sentiers libres
    for x in range(width):
        for y in range(height):
            if trail_clearance(y) == 0:
                grid[x][y] = 0

    # Embuscades (couverts isolés dans les sentiers)
    for trail_y in [center_y, trail_north_y, trail_south_y]:
        for _ in range(random.randint(3, 5)):
            tx = random.randint(width // 6, 5 * width // 6)
            ty = trail_y + random.randint(-1, 1)
            if 0 <= ty < height and grid[tx][ty] == 0:
                if not any(grid[tx + ddx][ty] == 1 for ddx in [-1, 1] if 0 <= tx + ddx < width):
                    if random.random() < 0.5:
                        grid[tx][ty] = 1

    return grid, {}


def generate_champs_flandre(width, height):
    """Champs de Flandre : plaine ouverte avec fermes fortifiées et fossés.

    Structure:
      • Terrain majoritairement dégagé (idéal artillerie et cavalerie)
      • 3–4 fermes fortifiées (clusters de murs type 2) = positions défensives clés
      • Fossés/haies irrégulières (lignes d'obstacles type 1)
      • Très peu de couverts naturels — avance risquée
    """
    grid = [[0] * height for _ in range(width)]

    # ── Fermes fortifiées ──
    farm_positions = []
    attempts = 0
    while len(farm_positions) < 3 and attempts < 100:
        attempts += 1
        fx = random.randint(width // 5, 4 * width // 5)
        fy = random.randint(height // 6, 5 * height // 6)
        if any(abs(fx - ox) + abs(fy - oy) < 12 for ox, oy in farm_positions):
            continue
        farm_positions.append((fx, fy))
        fw = random.randint(4, 7)
        fh = random.randint(3, 5)
        # Murs extérieurs (type 2), intérieur libre
        for dx in range(fw):
            for dy in range(fh):
                nx, ny = fx + dx - fw // 2, fy + dy - fh // 2
                if 0 < nx < width - 1 and 0 < ny < height - 1:
                    on_edge = (dx == 0 or dx == fw - 1 or dy == 0 or dy == fh - 1)
                    grid[nx][ny] = 2 if on_edge else 0

    # ── Fossés / haies horizontaux ──
    num_hedges = random.randint(4, 6)
    for _ in range(num_hedges):
        hy = random.randint(3, height - 4)
        hx_start = random.randint(0, width // 4)
        hx_end = random.randint(3 * width // 4, width - 1)
        # Trouées aléatoires dans la haie
        x = hx_start
        while x < hx_end:
            seg_len = random.randint(4, 10)
            gap = random.randint(2, 5)
            for dx in range(seg_len):
                nx = x + dx
                if 0 < nx < width - 1 and 0 < hy < height - 1 and grid[nx][hy] == 0:
                    grid[nx][hy] = 1
            x += seg_len + gap

    # ── Quelques couverts isolés (sacs de sable, épaves) ──
    for _ in range(random.randint(6, 10)):
        ox = random.randint(width // 8, 7 * width // 8)
        oy = random.randint(2, height - 3)
        if grid[ox][oy] == 0:
            grid[ox][oy] = 1

    return grid, {}


# ═══════════════════════════════════════════════════════════════
#                    FONCTION PRINCIPALE
# ═══════════════════════════════════════════════════════════════

def generate_map(map_name, width, height):
    """Génère la grille et les données spéciales pour un type de map WW1.

    Retourne (grid, map_data) où:
        grid: [[int]] — grille 2D
        map_data: dict — données spéciales (siege_data pour Tranchées)
    """
    generators = {
        "No Man's Land":   generate_no_mans_land,
        "Tranchées":       generate_tranchees,
        "Village détruit": generate_village_detruit,
        "Forêt d'Argonne": generate_foret_argonne,
        "Champs de Flandre": generate_champs_flandre,
    }

    gen = generators.get(map_name, generate_no_mans_land)
    return gen(width, height)
