"""Système de cartes — génère différents terrains pour le champ de bataille.

Types de cellules dans la grille:
    0 = vide (traversable)
    1 = obstacle (infranchissable, bloque vision)
    2 = mur (infranchissable, unités dessus = +2 svg, CaC ne passe pas)
    3 = porte (destructible, a des PV)
"""

import random


# ═══════════════════════════════════════════════════════════════
#                    DÉFINITIONS DES MAPS
# ═══════════════════════════════════════════════════════════════

MAP_TYPES = {
    "Prairie": {
        "description": "Terrain ouvert — 3 couloirs naturels séparés par des crêtes rocheuses",
        "bg_color": (45, 65, 35),
        "obstacle_color": (70, 90, 55),
        "grid_color": (55, 75, 45),
    },
    "Forêt": {
        "description": "Forêt dense — route centrale et deux chemins latéraux",
        "bg_color": (30, 55, 25),
        "obstacle_color": (20, 70, 15),
        "grid_color": (35, 60, 30),
    },
    "Village": {
        "description": "Village — deux rangées de bâtiments avec rues et place centrale",
        "bg_color": (55, 50, 40),
        "obstacle_color": (90, 70, 50),
        "grid_color": (60, 55, 45),
    },
    "Siège": {
        "description": "Forteresse avec murs et portes défensives",
        "bg_color": (40, 45, 50),
        "obstacle_color": (80, 80, 80),
        "grid_color": (50, 55, 60),
        "wall_color": (100, 100, 110),
        "gate_color": (140, 100, 50),
    },
    "Défilé": {
        "description": "Goulet montagneux — chokepoint central, flancs impraticables",
        "bg_color": (55, 50, 45),
        "obstacle_color": (90, 85, 75),
        "grid_color": (65, 60, 55),
    },
}


def get_map_names():
    return list(MAP_TYPES.keys())


def get_map_info(name):
    return MAP_TYPES.get(name, MAP_TYPES["Prairie"])


# ═══════════════════════════════════════════════════════════════
#                      GÉNÉRATEURS
# ═══════════════════════════════════════════════════════════════

def generate_prairie(width, height):
    """Prairie: deux crêtes rocheuses créent 3 couloirs horizontaux naturels.

    Structure:
      • Flanc haut  (y < height//4)      — couloir ouvert, cavalry route
      • Zone centre (y ≈ height//2)      — couloir principal avec couverts
      • Flanc bas   (y > 3*height//4)    — couloir ouvert, cavalry route

    Les crêtes à height//4 et 3*height//4 sont interrompues à leurs extrémités
    pour laisser les flancs totalement libres au déploiement.
    """
    grid = [[0] * height for _ in range(width)]

    ridge_ys = [height // 4, 3 * height // 4]
    # Les crêtes ne commencent qu'après la zone de déploiement (x > width//6)
    # et s'arrêtent avant l'autre zone de déploiement (x < 5*width//6)
    ridge_start_x = width // 5
    ridge_end_x = 4 * width // 5

    for ry in ridge_ys:
        # Placer 4–6 groupes de roches le long de la crête
        num_groups = random.randint(4, 6)
        spacing = (ridge_end_x - ridge_start_x) // num_groups
        for g in range(num_groups):
            cx = ridge_start_x + g * spacing + random.randint(0, spacing - 1)
            cy = ry + random.randint(-1, 1)
            group_size = random.randint(2, 4)
            for _ in range(group_size):
                ox = cx + random.randint(-1, 1)
                oy = cy + random.randint(-1, 1)
                if ridge_start_x <= ox <= ridge_end_x and 1 < oy < height - 1:
                    grid[ox][oy] = 1

    # Quelques couverts isolés au centre (abris pour tireurs)
    center_x = width // 2
    center_y = height // 2
    cover_attempts = 0
    covers_placed = 0
    while covers_placed < 4 and cover_attempts < 80:
        cover_attempts += 1
        cx = center_x + random.randint(-width // 6, width // 6)
        cy = center_y + random.randint(-3, 3)
        if grid[cx][cy] == 0:
            grid[cx][cy] = 1
            covers_placed += 1

    return grid, {}


def generate_forest(width, height):
    """Forêt: 3 routes garanties traversant toute la carte, forêt dense entre elles.

    Routes (garanties libres sur toute la largeur):
      • Centre      (y ≈ height//2)         — 5 cases de large
      • Nord        (y ≈ height//4)         — 3 cases de large
      • Sud         (y ≈ 3*height//4)       — 3 cases de large

    Zones boisées: remplissage case par case avec probabilité décroissante
    au bord des routes (lisière progressive, pas un mur vertical brutal).
    Quelques clairières aléatoires dans les zones boisées.
    """
    grid = [[0] * height for _ in range(width)]

    center_y = height // 2
    road_north_y = height // 4
    road_south_y = 3 * height // 4

    # Demi-largeurs des routes (cases libres de chaque côté de l'axe)
    ROAD_HALF_C = 2   # Route centrale: 5 cases (±2)
    ROAD_HALF_S = 1   # Routes latérales: 3 cases (±1)

    def road_clearance(y):
        """Distance au bord de la route la plus proche (0 = sur la route)."""
        d_c = max(0, abs(y - center_y) - ROAD_HALF_C)
        d_n = max(0, abs(y - road_north_y) - ROAD_HALF_S)
        d_s = max(0, abs(y - road_south_y) - ROAD_HALF_S)
        return min(d_c, d_n, d_s)

    # Remplir la forêt case par case
    # p(arbre) augmente avec la distance à la route (lisière progressive)
    for x in range(width):
        for y in range(height):
            if y == 0 or y == height - 1:
                continue
            dist = road_clearance(y)
            if dist == 0:
                continue   # Sur la route: toujours libre
            # Lisière (dist=1): 40%, dist=2: 65%, dist>=3: 80%
            if dist == 1:
                p = 0.40
            elif dist == 2:
                p = 0.65
            else:
                p = 0.80
            if random.random() < p:
                grid[x][y] = 1

    # Creuser des clairières (zones ouvertes dans la forêt)
    num_clearings = random.randint(6, 10)
    for _ in range(num_clearings):
        cx = random.randint(width // 6, 5 * width // 6)
        # Clairière uniquement dans les zones boisées (loin des routes)
        zone = random.choice([
            (road_north_y + ROAD_HALF_S + 3, center_y - ROAD_HALF_C - 3),
            (center_y + ROAD_HALF_C + 3, road_south_y - ROAD_HALF_S - 3),
        ])
        if zone[0] >= zone[1]:
            continue
        cy = random.randint(zone[0], zone[1])
        r = random.randint(2, 4)
        for ox in range(cx - r, cx + r + 1):
            for oy in range(cy - r, cy + r + 1):
                if 1 <= ox < width - 1 and 1 <= oy < height - 1:
                    if abs(ox - cx) + abs(oy - cy) <= r:
                        grid[ox][oy] = 0

    # Garantir que les routes sont 100% libres (passe finale)
    for x in range(width):
        for y in range(height):
            if road_clearance(y) == 0:
                grid[x][y] = 0

    # Quelques couverts légers dans les routes (arbres isolés)
    for route_y in [center_y, road_north_y, road_south_y]:
        count = 0
        for _ in range(50):
            if count >= 4:
                break
            tx = random.randint(width // 5, 4 * width // 5)
            ty = route_y + random.randint(-1, 1)
            if 0 <= ty < height and grid[tx][ty] == 0 and road_clearance(ty) == 0:
                # Ne pas placer deux arbres adjacents (garder le passage)
                if not any(grid[tx + dx][ty] == 1 for dx in [-1, 1] if 0 <= tx + dx < width):
                    if random.random() < 0.4:
                        grid[tx][ty] = 1
                        count += 1

    return grid, {}


def generate_village(width, height):
    """Village: réseau de rues avec bâtiments individuels.

    Structure garantie:
      • 1 rue centrale horizontale (y ≈ height//2), large de 4 cases
      • Rues transversales verticales régulières (tous les ~12-14 cases en x)
      • Bâtiments individuels (2-5 wide × 2-4 tall) dans les blocs entre rues
      • Flancs nord/sud libres (y < height//4 et y > 3*height//4) pour la cavalerie
      • Place centrale autour de (center_x, center_y) laissée ouverte

    Les rues forment un quadrillage lisible que l'IA peut exploiter
    (avancer rue par rue, se mettre à couvert derrière un bâtiment).
    """
    grid = [[0] * height for _ in range(width)]

    center_y = height // 2
    center_x = width // 2

    # ── Définir les rues ──────────────────────────────────────────
    # Rue centrale horizontale
    street_c_half = 2   # 4 cases de large (±2)

    # Rues transversales: espacées de 12-14 cases à partir de bld_start
    bld_start_x = width // 6
    bld_end_x = 5 * width // 6
    street_spacing = random.randint(12, 15)
    transversal_xs = set()
    sx = bld_start_x + random.randint(4, 8)
    while sx < bld_end_x - 4:
        transversal_xs.add(sx)
        sx += street_spacing + random.randint(-2, 2)

    # Limite verticale des bâtiments (flancs libres)
    flank_top = height // 4      # y < flank_top → flank libre
    flank_bot = 3 * height // 4  # y > flank_bot → flank libre

    def is_street(x, y):
        """Vrai si la case appartient à une rue."""
        # Rue centrale horizontale
        if abs(y - center_y) <= street_c_half:
            return True
        # Rues transversales (1 case de large)
        if any(abs(x - sx) <= 1 for sx in transversal_xs):
            return True
        # Flancs libres
        if y <= flank_top or y >= flank_bot:
            return True
        return False

    # ── Place centrale (rayon 5 autour du centre) ─────────────────
    plaza_r = 5

    # ── Placer les bâtiments ──────────────────────────────────────
    # Itérer sur les blocs définis par les rues transversales
    block_starts = sorted(transversal_xs)
    # Ajouter les limites de la zone de bâtiments
    xs_bounds = [bld_start_x] + block_starts + [bld_end_x]

    for bi in range(len(xs_bounds) - 1):
        block_left = xs_bounds[bi] + 2    # +2 pour laisser la rue
        block_right = xs_bounds[bi + 1] - 2

        if block_right - block_left < 2:
            continue

        # Dans ce bloc x, remplir les deux moitiés (nord de la rue centrale, sud)
        for band_top, band_bot in [
            (flank_top + 1, center_y - street_c_half - 1),
            (center_y + street_c_half + 1, flank_bot - 1),
        ]:
            if band_bot - band_top < 2:
                continue

            # Placer des bâtiments dans ce bloc×bande
            y = band_top
            while y <= band_bot:
                if band_bot - y < 1:
                    break
                bh = random.randint(2, max(2, min(4, band_bot - y + 1)))
                x = block_left
                while x <= block_right:
                    bw = random.randint(2, max(2, min(5, block_right - x + 1)))

                    # Skip si on est sur la place centrale
                    bx_c = x + bw // 2
                    by_c = y + bh // 2
                    if abs(bx_c - center_x) <= plaza_r and abs(by_c - center_y) <= plaza_r:
                        x += bw + 1
                        continue

                    # Placer le bâtiment (en s'assurant de ne pas déborder)
                    for bx in range(x, min(x + bw, block_right + 1)):
                        for by in range(y, min(y + bh, band_bot + 1)):
                            if 0 <= bx < width and 0 <= by < height:
                                grid[bx][by] = 1

                    x += bw + 1   # +1 = allée entre bâtiments
                y += bh + 1       # +1 = allée entre bâtiments

    # ── Passe finale: effacer toutes les rues garanties ──────────
    for x in range(width):
        for y in range(height):
            if is_street(x, y):
                grid[x][y] = 0
            # Place centrale
            if abs(x - center_x) <= plaza_r and abs(y - center_y) <= plaza_r:
                grid[x][y] = 0

    return grid, {}


def generate_siege(width, height):
    """Siège: mur vertical avec porte unique, remparts, et lignes de couverture attaquant.

    Améliorations:
      • 2 lignes de couverts côté attaquant (x ≈ wall_x//3 et 2*wall_x//3)
      • Bunkers/redoutes aux angles du mur
      • Répartition des couverts sur tout le front (haut/centre/bas)
    """
    grid = [[0] * height for _ in range(width)]

    wall_x = width * 2 // 3

    gate_center = height // 2
    gate_half = 3
    gate_positions = [gate_center]

    walls = []
    gates = []
    ramparts = []
    stairs = []

    # Construire le mur
    for y in range(1, height - 1):
        is_gate = (gate_center - gate_half <= y < gate_center + gate_half)
        if is_gate:
            grid[wall_x][y] = 3
            gates.append((wall_x, y))
        else:
            grid[wall_x][y] = 2
            walls.append((wall_x, y))
            for dx in [1, 2]:
                rx = wall_x + dx
                if 0 <= rx < width and grid[rx][y] == 0:
                    grid[rx][y] = 4
                    ramparts.append((rx, y))
            sx = wall_x + 3
            if 0 <= sx < width and grid[sx][y] == 0:
                grid[sx][y] = 5
                stairs.append((sx, y))

    # Tours aux coins du mur
    for dy in [-1, 0, 1]:
        for y_anchor in [1, height - 2]:
            tx, ty = wall_x - 1, y_anchor + dy
            if 0 <= ty < height:
                grid[tx][ty] = 2
                walls.append((tx, ty))
            tx2 = wall_x + 1
            if 0 <= tx2 < width and 0 <= ty < height and grid[tx2][ty] != 4:
                grid[tx2][ty] = 2
                walls.append((tx2, ty))

    # ── Ligne 1 de couverture (proche des attaquants, x ≈ wall_x // 3) ──
    line1_x = wall_x // 3
    # 3 groupes de couverts répartis haut/centre/bas
    for zone_y in [height // 5, height // 2, 4 * height // 5]:
        for _ in range(random.randint(2, 4)):
            ox = line1_x + random.randint(-3, 3)
            oy = zone_y + random.randint(-2, 2)
            if 1 < ox < wall_x - 5 and 1 < oy < height - 1 and grid[ox][oy] == 0:
                grid[ox][oy] = 1

    # ── Ligne 2 de couverture (avancée, x ≈ 2*wall_x // 3) ──
    line2_x = 2 * wall_x // 3
    for zone_y in [height // 4, height // 2, 3 * height // 4]:
        for _ in range(random.randint(2, 3)):
            ox = line2_x + random.randint(-3, 3)
            oy = zone_y + random.randint(-2, 2)
            if 1 < ox < wall_x - 5 and 1 < oy < height - 1 and grid[ox][oy] == 0:
                grid[ox][oy] = 1

    siege_data = {
        'walls': walls,
        'ramparts': ramparts,
        'stairs': stairs,
        'gates': {pos: 10 for pos in gates},
        'gate_save': 3,
        'gate_positions': gate_positions,
        'wall_x': wall_x,
    }

    return grid, siege_data


def generate_defile(width, height):
    """Défilé montagneux: goulet central avec flancs impraticables.

    Structure:
      • Terrain rocheux dense sur y < pass_top et y > pass_bot
      • Goulet central libre (pass_top à pass_bot, environ height//3 à 2*height//3)
      • Étranglement au milieu (x ≈ width//2): le goulet se rétrécit de 4 cases de part et d'autre
      • Gros rochers à l'intérieur du goulet comme couverts
      • Couloir légèrement sinueux (quelques roches éparpillées dans les parois)

    Tactique possible pour l'IA:
      • Tenir les rochers du centre = position défensive forte
      • Flanquement impossible → combat de front ou contournement par l'étranglement
      • Les tireurs sur les bords du goulet dominent le couloir
    """
    grid = [[0] * height for _ in range(width)]

    pass_top = height // 3
    pass_bot = 2 * height // 3
    pass_center_y = height // 2

    # ── Parois rocheuses Nord et Sud ──
    for x in range(width):
        for y in range(height):
            # Zone Nord: entièrement obstruée
            if y < pass_top:
                grid[x][y] = 1
            # Zone Sud: entièrement obstruée
            elif y > pass_bot:
                grid[x][y] = 1

    # ── Étranglement central (x ≈ width//2 ± width//8) ──
    # Le goulet se rétrécit de "throat" cases sur chaque paroi
    throat_start = width // 2 - width // 8
    throat_end = width // 2 + width // 8
    throat_squeeze = random.randint(3, 5)  # Cases ajoutées à chaque paroi

    for x in range(throat_start, throat_end):
        for squeeze_y in range(throat_squeeze):
            # Rétrécir la paroi nord
            ny = pass_top + squeeze_y
            if 0 <= ny < height:
                grid[x][ny] = 1
            # Rétrécir la paroi sud
            sy = pass_bot - squeeze_y
            if 0 <= sy < height:
                grid[x][sy] = 1

    # ── Dégazer les bords du goulet (quelques irrégularités) ──
    for x in range(width // 6, 5 * width // 6):
        # Saillies rocheuses dans le goulet depuis la paroi nord
        if random.random() < 0.07:
            jut = random.randint(1, 2)
            for j in range(jut):
                ny = pass_top + j
                if 0 <= ny < height and grid[x][ny] == 0:
                    grid[x][ny] = 1
        # Saillies depuis la paroi sud
        if random.random() < 0.07:
            jut = random.randint(1, 2)
            for j in range(jut):
                sy = pass_bot - j
                if 0 <= sy < height and grid[x][sy] == 0:
                    grid[x][sy] = 1

    # ── Rochers/couverts dans le goulet (abris tactiques) ──
    # 3 zones de couverts: 1/4, 1/2 et 3/4 de la largeur
    for zone_x in [width // 4, width // 2, 3 * width // 4]:
        num_rocks = random.randint(2, 4)
        placed = 0
        attempts = 0
        while placed < num_rocks and attempts < 40:
            attempts += 1
            rx = zone_x + random.randint(-4, 4)
            ry = pass_center_y + random.randint(-4, 4)
            # Ne pas placer dans l'étranglement (trop difficile à traverser)
            if throat_start - 2 < rx < throat_end + 2:
                continue
            if 0 <= rx < width and grid[rx][ry] == 0:
                grid[rx][ry] = 1
                placed += 1

    # ── Dégager les zones de spawn (x < width//6 et x > 5*width//6) ──
    # Enlever les obstacles dans les zones de déploiement des armées
    for x in range(0, width // 6):
        for y in range(pass_top, pass_bot + 1):
            grid[x][y] = 0
    for x in range(5 * width // 6, width):
        for y in range(pass_top, pass_bot + 1):
            grid[x][y] = 0

    return grid, {}


# ═══════════════════════════════════════════════════════════════
#                    FONCTION PRINCIPALE
# ═══════════════════════════════════════════════════════════════

def generate_map(map_name, width, height):
    """Génère la grille et les données spéciales pour un type de map.

    Retourne (grid, map_data) où:
        grid: [[int]] — grille 2D (0=vide, 1=obstacle, 2=mur, 3=porte)
        map_data: dict — données spéciales (siege_data, etc.)
    """
    generators = {
        "Prairie": generate_prairie,
        "Forêt": generate_forest,
        "Village": generate_village,
        "Siège": generate_siege,
        "Défilé": generate_defile,
    }

    gen = generators.get(map_name, generate_prairie)
    return gen(width, height)
