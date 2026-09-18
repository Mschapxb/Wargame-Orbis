"""Système de cartes — génère différents terrains pour le champ de bataille.

Types de cellules dans la grille:
    0 = vide (traversable)
    1 = obstacle (infranchissable; rocher, maison, haie ou cœur de bosquet:
        coupe la ligne de tir, comme les murs, les portes fermées intactes
        et le terrain à effets — bois, collines, cf. terrain.blocks_line)
    2 = mur (infranchissable, unités dessus = +2 svg, CaC ne passe pas)
    3 = porte (destructible, a des PV)

Les cartes de bataille rangée (Prairie, Forêt, Désert, Village, Défilé)
sont symétriques: grille et terrain de la moitié ouest sont recopiés à
l'est. Les obstacles `1` de Prairie, Forêt, Désert et Village sont des
structures destructibles (cf. generate_structures et structures.py).

Thèmes: chaque carte (sauf le Défilé) accepte un biome et un relief
(rivière, collines) posés en couches procédurales — cf. « THÈMES ET
RELIEF » et procgen.py.
"""

import math
import random

import procgen
import structures as st
import terrain as tr


# ═══════════════════════════════════════════════════════════════
#                    DÉFINITIONS DES MAPS
# ═══════════════════════════════════════════════════════════════

MAP_TYPES = {
    "Prairie": {
        "description": "Campagne vallonnée — collines éparses, bosquets, couloir central ouvert",
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
        "bg_color": (64, 62, 50),
        "obstacle_color": (92, 88, 80),
        "grid_color": (70, 68, 56),
        "wall_color": (100, 100, 110),
        "gate_color": (140, 100, 50),
    },
    "Citadelle": {
        "description": "Double enceinte — mur extérieur à deux portes, basse-cour, donjon",
        "bg_color": (60, 60, 50),
        "obstacle_color": (92, 88, 80),
        "grid_color": (68, 68, 56),
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
# Le Désert est inséré après la Forêt: les trois cartes de rase campagne
# se suivent dans le menu.
MAP_TYPES = dict(list(MAP_TYPES.items())[:2] + [("Désert", {
    "description": "Désert — reg ouvert, dunes, affleurements rocheux et oasis centrale",
    "bg_color": (122, 104, 70),
    "obstacle_color": (150, 128, 92),
    "grid_color": (130, 112, 78),
})] + list(MAP_TYPES.items())[2:])


# ═══════════════════════════════════════════════════════════════
#                    THÈMES ET RELIEF
# ═══════════════════════════════════════════════════════════════
# Une carte = une DISPOSITION (Prairie, Village, Siège…) + des OPTIONS:
#   biome  — "Prairie", "Forêt" ou "Désert": couleurs, décor, végétation
#   river  — une rivière à franchir (gués, ponts)
#   hills  — des collines / dunes
# Chaque disposition a un thème NATUREL: le choisir rend exactement la carte
# historique (mêmes tirages, même équilibrage mesuré). Les autres choix
# ajoutent ou retirent des couches procédurales (cf. procgen.py).

BIOMES = ("Prairie", "Forêt", "Désert")
# Cartes de rase campagne: leur nom EST leur biome
OPEN_MAPS = ("Prairie", "Forêt", "Désert")
# Cartes dont on peut choisir le thème et le relief
THEMED_MAPS = OPEN_MAPS + ("Village", "Siège", "Citadelle")
SIEGE_MAPS = ("Siège", "Citadelle")

RELIEFS = {
    "Plat": (False, False),
    "Rivière": (True, False),
    "Collines": (False, True),
    "Rivière + collines": (True, True),
}
RANDOM_RELIEF = "Aléatoire"

# (rivière, collines) de la carte historique
NATURAL_RELIEF = {
    "Prairie": (False, True),
    "Forêt": (True, False),
    "Désert": (False, True),
    "Village": (False, True),
    "Siège": (False, False),
    "Citadelle": (False, False),
    "Défilé": (True, True),
}

# Teinte appliquée aux couleurs d'une disposition bâtie hors de son biome
_BIOME_TINT = {
    "Forêt": (-16, 2, -12),
    "Désert": (56, 40, 16),
}


def get_map_names():
    return list(MAP_TYPES.keys())


def natural_biome(map_name):
    return map_name if map_name in OPEN_MAPS else "Prairie"


def natural_relief_name(map_name):
    pair = NATURAL_RELIEF.get(map_name, (False, False))
    return next(name for name, v in RELIEFS.items() if v == pair)


def resolve_options(map_name, options=None):
    """Options complètes {biome, river, hills} d'une carte.

    `options` peut donner `relief` (clé de RELIEFS ou "Aléatoire") au lieu
    de `river`/`hills`. Sans options: le thème naturel. Le Défilé n'a pas
    d'options (sa géométrie est son relief). "Aléatoire" ne tire un dé que
    s'il est demandé."""
    river, hills = NATURAL_RELIEF.get(map_name, (False, False))
    biome = natural_biome(map_name)
    if options and map_name in THEMED_MAPS:
        if map_name not in OPEN_MAPS and options.get('biome') in BIOMES:
            biome = options['biome']
        relief = options.get('relief')
        if relief == RANDOM_RELIEF:
            relief = random.choice(list(RELIEFS))
        if relief in RELIEFS:
            river, hills = RELIEFS[relief]
        river = bool(options.get('river', river))
        hills = bool(options.get('hills', hills))
    return {'biome': biome, 'river': river, 'hills': hills}


def get_map_info(name, biome=None):
    """Couleurs et description d'une carte, dans le biome demandé.
    `grassy`: le sol porte des brins d'herbe (sinon des gravillons)."""
    base = MAP_TYPES.get(name, MAP_TYPES["Prairie"])
    info = dict(base)
    if biome in _BIOME_TINT and biome != natural_biome(name):
        tint = _BIOME_TINT[biome]
        for key in ("bg_color", "obstacle_color", "grid_color"):
            info[key] = tuple(max(0, min(255, c + d)) for c, d in zip(base[key], tint))
    info['grassy'] = name in ("Prairie", "Forêt") or biome == "Forêt"
    return info


def theme_info(bf):
    """Couleurs du champ de bataille `bf` (disposition + biome choisi)."""
    theme = getattr(bf, 'theme', None) or {}
    return get_map_info(bf.map_name, theme.get('biome'))


def describe_options(map_name, opts):
    """Libellé court pour la console et le menu: « Village, désert, rivière »."""
    if map_name not in THEMED_MAPS or not opts:
        return map_name
    parts = [map_name]
    if map_name not in OPEN_MAPS:
        parts.append(opts['biome'].lower())
    parts.append(next(n for n, v in RELIEFS.items()
                      if v == (opts['river'], opts['hills'])).lower())
    return ", ".join(parts)


# ═══════════════════════════════════════════════════════════════
#                      GÉNÉRATEURS
# ═══════════════════════════════════════════════════════════════

def generate_prairie(width, height):
    """Prairie: une campagne vallonnée, ouverte, sans règle ni équerre.

    Structure:
      • Des collines éparses au nord et au sud, de tailles et d'orientations
        variées, parfois coiffées de rochers: le centre reste un couloir
        ouvert, les flancs sont vallonnés
      • Une butte irrégulière au centre, objectif naturel du couloir principal
      • Bosquets et broussailles de formes libres dans l'entre-deux (jamais
        sur les lignes de déploiement), qui masquent une cavalerie
      • Quelques rochers isolés près du centre, couverts pour les tireurs

    La moitié ouest est tirée au hasard puis recopiée à l'est (équitable).
    """
    grid = [[0] * height for _ in range(width)]
    terr = tr.make_grid(width, height)
    half = width // 2
    mx, cy = (width - 1) / 2, (height - 1) / 2
    lo = deploy_front(width) + 3
    small = height < 40
    west = (1, half - 1)

    # ── Collines: des buttes éparses au nord et au sud, de tailles et
    # d'orientations variées — pas de crête tirée d'un bord à l'autre. Le
    # centre reste dégagé: trois couloirs subsistent, mais irréguliers. ──
    hill_x0 = max(2, int(width * 0.16))
    n_hills = 3 + (width * height) // 3000
    for k in range(n_hills):
        side = -1 if k % 2 == 0 else 1
        hy = cy + side * height * random.uniform(0.14, 0.38)
        hx = random.uniform(hill_x0, half - 2)
        r = random.uniform(1.3, 2.2 if small else 3.6)
        stretch = random.uniform(1.0, 2.2)
        procgen.paint_blob(terr, grid, width, height, hx, hy, r * stretch, r,
                           random.uniform(-1.0, 1.0), tr.HILL, x_range=west, rough=0.3)
        # Quelques rochers sur les plus grandes, hors des lignes de départ
        if r > 1.8 and hx >= lo and random.random() < 0.6:
            for _ in range(random.randint(1, 3)):
                rx = int(round(hx + random.uniform(-r, r)))
                ry = int(round(hy + random.uniform(-r * 0.6, r * 0.6)))
                if lo <= rx < half and 1 < ry < height - 2 and terr[rx][ry] == tr.HILL:
                    grid[rx][ry] = 1

    # ── Butte centrale ──
    r = max(2.2, min(width, height) * 0.055)
    procgen.paint_blob(terr, grid, width, height, mx, cy + random.uniform(-1.5, 1.5),
                       r * random.uniform(1.0, 1.35), r, random.uniform(0, math.pi),
                       tr.HILL, x_range=west, rough=0.3)

    # ── Bosquets et broussailles, sur les flancs ──
    # Le couloir central reste ouvert: une Prairie boisée entre les armées
    # se jouerait comme une forêt (l'IA y renonce aux manœuvres et aux rangs).
    n_woods = 2 + (width * height) // 2600
    for k in range(n_woods):
        r = random.uniform(1.0, 1.8 if small else 2.6)
        x_min = lo + r * 1.4 + 1
        if x_min > half - 2:
            break
        wx = random.uniform(x_min, half - 2)
        side = -1 if k % 2 == 0 else 1
        wy = cy + side * random.uniform(height * 0.3, height * 0.44)
        procgen.paint_blob(terr, grid, width, height, wx, wy, r * random.uniform(1.0, 1.6), r,
                           random.uniform(0, math.pi), tr.WOOD, x_range=west, rough=0.35)

    # ── Rochers isolés près du centre (abris pour tireurs) ──
    for _ in range(random.randint(2, 4)):
        rx = random.randint(max(lo, half - max(3, width // 6)), max(lo, half - 2))
        ry = int(round(cy + random.randint(-4, 4)))
        if 1 < ry < height - 2 and grid[rx][ry] == 0:
            grid[rx][ry] = 1

    _mirror_grid(grid, width, height)
    _mirror_terrain(terr, width, height)
    return grid, {'terrain': terr}


def _carve(grid, x, y, r, width, height):
    """Dégage un disque de rayon r (sentiers, clairières)."""
    ri = int(math.ceil(r))
    for dx in range(-ri, ri + 1):
        for dy in range(-ri, ri + 1):
            if dx * dx + dy * dy <= r * r:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    grid[nx][ny] = 0


def _connected(grid, width, height, start, goal, terrain=None, avoid=()):
    """Vrai si goal est atteignable depuis start (8-voisinage, cases libres).
    Avec `terrain`: la rivière bloque, et les terrains de `avoid` aussi."""
    return _bfs_path(grid, width, height, [start], [goal], terrain, avoid) is not None


def _bfs_path(grid, width, height, starts, goals, terrain=None, avoid=(), blocked=()):
    """Plus court chemin (en cases, 8-voisinage) d'une case de `starts` à une
    case de `goals`, ou None. `blocked`: cases interdites en plus."""
    goals = set(goals)
    blocked = set(blocked)

    def ok(x, y):
        if grid[x][y] != 0 or (x, y) in blocked:
            return False
        if terrain is not None:
            name = terrain[x][y]
            if tr.MOVE[name] is None or name in avoid:
                return False
        return True

    from collections import deque
    came = {}
    queue = deque()
    for s in starts:
        if ok(*s) and s not in came:
            came[s] = None
            queue.append(s)
    while queue:
        cur = queue.popleft()
        if cur in goals:
            path = []
            while cur is not None:
                path.append(cur)
                cur = came[cur]
            return path[::-1]
        cx, cy = cur
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = cx + dx, cy + dy
                if (0 <= nx < width and 0 <= ny < height and (nx, ny) not in came
                        and ok(nx, ny)):
                    came[(nx, ny)] = cur
                    queue.append((nx, ny))
    return None


def _mirror_grid(grid, width, height):
    """Recopie la moitié ouest de la grille bâtie sur l'est (x → width-1-x).
    Sans cela, les tirages aléatoires (rochers, maisons, saillies) donnent
    à un camp plus de couverts qu'à l'autre."""
    for x in range(width // 2):
        for y in range(height):
            grid[width - 1 - x][y] = grid[x][y]


def _mirror_terrain(terr, width, height):
    """Recopie la moitié ouest sur l'est (x → width-1-x): aucun camp n'est
    avantagé par le terrain."""
    for x in range(width // 2):
        for y in range(height):
            terr[width - 1 - x][y] = terr[x][y]


def _paint_disc(terr, cx, cy, r, name, width, height):
    """Peint un disque de terrain (centre réel autorisé)."""
    ri = int(math.ceil(r)) + 1
    for x in range(int(cx) - ri, int(cx) + ri + 2):
        for y in range(int(cy) - ri, int(cy) + ri + 2):
            if 0 <= x < width and 0 <= y < height and (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                terr[x][y] = name


def generate_forest(width, height):
    """Forêt: un MASSIF BOISÉ au centre du champ de bataille.

    Les deux armées se déploient en terrain découvert, de part et d'autre,
    puis doivent entrer dans le bois pour se rencontrer.

    Structure:
      • Massif elliptique au centre, contour irrégulier (pas un ovale net)
      • Fait de BOSQUETS serrés séparés par des passages sinueux: on s'y
        faufile au lieu d'y buter sur un mur d'arbres
      • Clairières intérieures (points d'affrontement naturels)
      • 3 à 4 sentiers ouest → est garantis, légèrement sinueux
      • Lisière clairsemée, puis champ ouvert où l'on se déploie
    """
    grid = [[0] * height for _ in range(width)]
    cx, cy = width // 2, height // 2
    rx = max(5, int(width * 0.10))
    ry = max(4, int(height * 0.40))

    phases = [random.uniform(0, math.tau) for _ in range(3)]
    amps, freqs = (0.10, 0.07, 0.05), (3, 5, 8)

    def edge(theta):
        return 1.0 + sum(a * math.sin(f * theta + p) for a, f, p in zip(amps, freqs, phases))

    def inside(x, y, scale=1.0):
        dx, dy = (x - cx) / rx, (y - cy) / ry
        return math.hypot(dx, dy) < edge(math.atan2(dy, dx)) * scale

    # ── Bosquets ──
    area = math.pi * rx * ry
    for _ in range(int(area / 11)):
        for _try in range(20):
            gx = random.randint(cx - rx, cx + rx)
            gy = random.randint(cy - ry, cy + ry)
            if inside(gx, gy, 0.95):
                break
        else:
            continue
        gr = random.uniform(1.0, 2.6)
        ri = int(math.ceil(gr))
        for dx in range(-ri, ri + 1):
            for dy in range(-ri, ri + 1):
                nx, ny = gx + dx, gy + dy
                if not (0 <= nx < width and 1 <= ny < height - 1):
                    continue
                if dx * dx + dy * dy <= gr * gr and random.random() < 0.85 and inside(nx, ny, 1.02):
                    grid[nx][ny] = 1

    # ── Lisière: arbres isolés autour du massif ──
    for x in range(max(0, cx - int(rx * 1.6)), min(width, cx + int(rx * 1.6) + 1)):
        for y in range(1, height - 1):
            if grid[x][y] == 0 and inside(x, y, 1.4) and not inside(x, y, 1.0):
                if random.random() < 0.07:
                    grid[x][y] = 1

    # ── Clairières ──
    for _ in range(random.randint(3, 5)):
        for _try in range(20):
            kx = random.randint(cx - rx // 2, cx + rx // 2)
            ky = random.randint(cy - int(ry * 0.7), cy + int(ry * 0.7))
            if inside(kx, ky, 0.7):
                _carve(grid, kx, ky, random.uniform(1.8, 3.2), width, height)
                break

    # ── Sentiers ouest → est ──
    n_trails = 3 if height < 40 else 4
    x_start = max(0, cx - int(rx * 1.6))
    x_end = min(width - 1, cx + int(rx * 1.6))
    trail_ys = []
    for i in range(n_trails):
        y0 = int(cy + (i - (n_trails - 1) / 2) * (ry * 1.5 / max(1, n_trails - 1)))
        y = y0
        half = 1.2 if abs(y0 - cy) <= 2 else 0.8
        for x in range(x_start, x_end + 1):
            if random.random() < 0.35:
                y += random.choice((-1, 1))
                y = max(y0 - 3, min(y0 + 3, y))
            _carve(grid, x, max(1, min(height - 2, y)), half, width, height)
            if x == cx - 1:
                trail_ys.append(max(1, min(height - 2, y)))

    # ── Symétrie: l'ouest est recopié à l'est (terrain équitable) ──
    _mirror_grid(grid, width, height)

    # ── Bosquets: le cœur reste impénétrable, le pourtour devient un
    # sous-bois traversable (lent, à couvert). On coupe à travers bois. ──
    terr = tr.make_grid(width, height)
    core = [[grid[x][y] == 1 and all(
                not (0 <= x + dx < width and 0 <= y + dy < height)
                or grid[x + dx][y + dy] == 1
                for dx in (-1, 0, 1) for dy in (-1, 0, 1))
             for y in range(height)] for x in range(width)]
    for x in range(width):
        for y in range(height):
            if grid[x][y] == 1:
                if not core[x][y]:
                    grid[x][y] = 0
                terr[x][y] = tr.WOOD
    # Lisière clairsemée
    for x in range(width // 2):
        for y in range(1, height - 1):
            if (grid[x][y] == 0 and inside(x, y, 1.4) and not inside(x, y, 1.0)
                    and random.random() < 0.25):
                terr[x][y] = tr.WOOD
    _mirror_terrain(terr, width, height)

    # ── Ruisseau nord-sud au cœur du massif, franchissable à deux gués ──
    # Tracé naturel (bras, îlots, largeur qui respire), en miroir.
    spans = procgen.river_spans_symmetric(width, height, 0 if width < 90 else 1)
    for y in range(1, height - 1):
        if inside(cx, y, 0.9):
            for x0, x1 in spans[y]:
                for x in range(x0, x1 + 1):
                    grid[x][y] = 0
                    terr[x][y] = tr.RIVER
    for ty in sorted(set(trail_ys), key=lambda t: abs(t - cy))[:2]:
        for y in (ty - 1, ty, ty + 1):
            if 0 < y < height - 1:
                x0, x1 = procgen.span_bounds(spans[y])
                for x in range(x0, x1 + 1):
                    if terr[x][y] == tr.RIVER:
                        terr[x][y] = tr.FORD

    # ── Champs de déploiement dégagés: on se range hors du bois ──
    deploy_gap = rx + 5
    for x in range(cx - deploy_gap - 5, cx - deploy_gap + 6):
        for xx in (x, width - 1 - x):
            if 0 <= xx < width:
                for y in range(height):
                    grid[xx][y] = 0
                    terr[xx][y] = tr.PLAIN

    # ── Garantie de passage d'un camp à l'autre ──
    left, right = (max(0, cx - int(rx * 2)), cy), (min(width - 1, cx + int(rx * 2)), cy)
    if not _connected(grid, width, height, left, right, terr):
        for x in range(left[0], right[0] + 1):
            _carve(grid, x, cy, 1.2, width, height)
            for y in (cy - 1, cy, cy + 1):
                if terr[x][y] == tr.RIVER:
                    terr[x][y] = tr.FORD

    return grid, {'deploy_gap': deploy_gap, 'terrain': terr}


def generate_village(width, height):
    """Village: un bourg CIRCULAIRE au centre du champ de bataille.

    Les armées se déploient dans les champs, de part et d'autre, puis
    s'engagent dans les rues pour se rencontrer au cœur du bourg.

    Structure:
      • Place centrale ronde (point de rencontre naturel)
      • Maisons disposées en anneaux concentriques autour de la place,
        chacune séparée de ses voisines par une ruelle
      • Rues rayonnantes: la grand-rue est-ouest (large) relie directement
        les deux zones de déploiement; d'autres rues partent en étoile
      • Quelques fermes isolées dans les champs alentour
    """
    grid = [[0] * height for _ in range(width)]
    cx, cy = width // 2, height // 2
    R = max(7, int(min(height * 0.40, width * 0.12)))
    plaza = max(2.5, R * 0.22)

    # Rues rayonnantes: la grand-rue est-ouest, plus 5 à 6 rues en étoile
    n_side = random.randint(5, 6)
    streets = [(0.0, 1.6), (math.pi, 1.6)]
    base = random.uniform(0, math.pi / n_side)
    for i in range(n_side):
        a = base + i * math.tau / n_side
        # pas de doublon trop proche de la grand-rue
        if min(abs(math.sin(a)), 1.0) < 0.35:
            continue
        streets.append((a, 1.0))

    def in_street(x, y):
        vx, vy = x - cx, y - cy
        for a, half in streets:
            ux, uy = math.cos(a), math.sin(a)
            along = vx * ux + vy * uy
            if along < 0:
                continue
            if abs(vx * uy - vy * ux) <= half:
                return True
        return False

    occupied = set()

    def try_house(hx, hy, w, h, keep_out_r):
        cells = [(hx + i, hy + j) for i in range(w) for j in range(h)]
        for (x, y) in cells:
            if not (1 <= x < width - 1 and 1 <= y < height - 1):
                return False
            if math.hypot(x - cx, y - cy) < keep_out_r:
                return False
            if in_street(x, y):
                return False
        # Ruelle d'au moins une case avec les maisons voisines
        for (x, y) in cells:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if (x + dx, y + dy) in occupied:
                        return False
        for (x, y) in cells:
            grid[x][y] = 1
            occupied.add((x, y))
        return True

    # ── Anneaux de maisons ──
    # Pour chaque emplacement on essaie plusieurs gabarits, du plus grand au
    # plus petit: le bourg reste dense tout en gardant ses ruelles.
    r = plaza + 2.8
    while r <= R - 1.2:
        n_slots = max(6, int(math.tau * r / 3.6))
        offset = random.uniform(0, math.tau / n_slots)
        for k in range(n_slots):
            a = offset + k * math.tau / n_slots
            sizes = [(random.randint(3, 4), random.randint(2, 3)), (3, 2), (2, 3), (2, 2)]
            for w, h in sizes:
                hx = int(round(cx + math.cos(a) * r - w / 2))
                hy = int(round(cy + math.sin(a) * r - h / 2))
                if try_house(hx, hy, w, h, plaza + 1.2):
                    break
        r += 3.8

    # ── Haie circulaire: la ceinture du bourg, percée à chaque rue ──
    ring_r = R + 0.8
    for x in range(max(1, cx - R - 3), min(width - 1, cx + R + 4)):
        for y in range(1, height - 1):
            d = math.hypot(x - cx, y - cy)
            if abs(d - ring_r) > 0.55:
                continue
            # ouverture un peu plus large que la rue elle-même
            vx, vy = x - cx, y - cy
            opening = False
            for a, half in streets:
                ux, uy = math.cos(a), math.sin(a)
                if vx * ux + vy * uy > 0 and abs(vx * uy - vy * ux) <= half + 1.2:
                    opening = True
                    break
            if opening:
                continue
            if any((x + dx, y + dy) in occupied for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                continue
            grid[x][y] = 1

    # ── Fermes isolées dans les champs (jamais sur l'axe des armées) ──
    for _ in range(random.randint(2, 4)):
        for _try in range(30):
            a = random.uniform(0, math.tau)
            if abs(math.sin(a)) < 0.6:
                continue
            d = random.uniform(R + 4, R + 8)
            w, h = random.randint(2, 3), random.randint(2, 3)
            if try_house(int(cx + math.cos(a) * d), int(cy + math.sin(a) * d), w, h, R + 3):
                break

    # ── Symétrie: maisons, haie et fermes de l'ouest recopiées à l'est ──
    # (le terrain l'était déjà: des rues d'un côté face à des jardins de
    # l'autre donnaient l'avantage à un camp)
    _mirror_grid(grid, width, height)

    # ── Terrain ──
    terr = tr.make_grid(width, height)
    mx = (width - 1) / 2
    # Le bourg est sur une butte aux contours irréguliers: ses rues dominent
    # les champs. Peinte à l'ouest, recopiée à l'est avec le reste.
    procgen.paint_blob(terr, grid, width, height, mx, cy, R + 1.2,
                       (R + 1.2) * random.uniform(0.92, 1.0), random.uniform(0, math.pi),
                       tr.HILL, x_range=(0, width // 2 - 1), rough=0.08)
    # Bosquets dans les champs, au nord et au sud du bourg
    lo_v = deploy_front(width, R + 5) + 3
    for _ in range(random.randint(2, 4)):
        r = random.uniform(1.2, 2.6)
        wx = random.uniform(lo_v + r * 1.4 + 1, max(lo_v + r * 1.4 + 1, mx - 2))
        wy = random.choice((random.uniform(2, cy - R * 0.7), random.uniform(cy + R * 0.7, height - 3)))
        if math.hypot(wx - mx, wy - cy) < R + 3 + r or abs(wy - cy) < 3:
            continue
        procgen.paint_blob(terr, grid, width, height, wx, wy, r * random.uniform(1.0, 1.5), r,
                           random.uniform(0, math.pi), tr.WOOD, x_range=(0, width // 2 - 1),
                           rough=0.35)
    # Jardins et vergers entre les maisons (jamais dans une rue, ni la
    # nôtre ni celle d'en face une fois le terrain mis en miroir)
    for x in range(width // 2):
        for y in range(1, height - 1):
            d = math.hypot(x - mx, y - cy)
            if not (R * 0.55 <= d <= R - 0.5) or grid[x][y] != 0:
                continue
            if in_street(x, y) or in_street(width - 1 - x, y):
                continue
            if random.random() < 0.30:
                terr[x][y] = tr.WOOD
    # Mare boueuse au bord de la place, hors de la grand-rue
    _paint_disc(terr, mx - (plaza + 2.5), cy + plaza + 1.5, 1.6, tr.MARSH, width, height)
    _mirror_terrain(terr, width, height)

    return grid, {'deploy_gap': R + 5, 'terrain': terr}


def _build_wall(grid, wall_x, gate_rows, width, height, walls, gates, ramparts, stairs):
    """Une enceinte: mur vertical percé de portes sur `gate_rows`, chemin de
    ronde sur deux rangs, escalier, tours aux deux extrémités."""
    for y in range(1, height - 1):
        if y in gate_rows:
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


def _siege_copses(grid, terr, width, height, wall_x, gate_rows):
    """Quelques bosquets dans les champs de l'assaillant, loin des axes des
    portes et du fossé: un paysage, pas un terrain vague."""
    x_lo = deploy_front(width, siege=True) + 3
    x_hi = wall_x - 9
    if x_hi - x_lo < 3:
        return
    for _ in range(random.randint(2, 4)):
        r = random.uniform(1.0, 2.2 if height >= 40 else 1.5)
        wx = random.uniform(x_lo + r, x_hi - r)
        wy = random.uniform(2, height - 3)
        if any(abs(wy - g) < 6 + r for g in gate_rows):
            continue
        procgen.paint_blob(terr, grid, width, height, wx, wy, r * random.uniform(1.0, 1.6), r,
                           random.uniform(0, math.pi), tr.WOOD, x_range=(x_lo, x_hi), rough=0.35)


def generate_citadel(width, height):
    """Citadelle: deux enceintes successives.

    Structure:
      • Mur extérieur (x ≈ 0,55 × largeur) percé de DEUX portes (1/3 et 2/3
        de la hauteur), fossé boueux à son pied, palissades de l'assaillant
      • Basse-cour: maisons, jardins, glacis derrière le mur extérieur et
        butte devant le donjon; des chemins restent libres des portes
        extérieures jusqu'à la porte du donjon
      • Donjon (x ≈ 0,80 × largeur): une porte centrale, remparts, escalier

    Quand l'enceinte extérieure tombe (cf. Battle._check_ring_fall), la
    défense se replie sur le donjon.
    """
    grid = [[0] * height for _ in range(width)]
    wx1 = int(width * 0.55)
    wx2 = max(wx1 + 9, int(width * 0.80))
    wx2 = min(wx2, width - 5)
    walls, ramparts, stairs = [], [], []
    outer_gates, keep_gates = [], []

    outer_centers = [height // 3, 2 * height // 3]
    outer_rows = set()
    for c in outer_centers:
        outer_rows.update(range(c - 2, c + 2))
    keep_center = height // 2
    keep_rows = set(range(keep_center - 2, keep_center + 2))
    _build_wall(grid, wx1, outer_rows, width, height, walls, outer_gates, ramparts, stairs)
    _build_wall(grid, wx2, keep_rows, width, height, walls, keep_gates, ramparts, stairs)

    # ── Palissades de l'assaillant (comme le Siège) ──
    for line_x, zones, n in ((wx1 // 3, [height // 5, height // 2, 4 * height // 5], (2, 4)),
                             (2 * wx1 // 3, [height // 4, height // 2, 3 * height // 4], (2, 3))):
        for zone_y in zones:
            for _ in range(random.randint(*n)):
                ox = line_x + random.randint(-3, 3)
                oy = zone_y + random.randint(-2, 2)
                if 1 < ox < wx1 - 5 and 1 < oy < height - 1 and grid[ox][oy] == 0:
                    grid[ox][oy] = 1

    terr = tr.make_grid(width, height)
    # Fossé au pied du mur extérieur, chaussée devant chaque porte
    for x in (wx1 - 2, wx1 - 1):
        for y in range(1, height - 1):
            if grid[x][y] == 0 and y not in outer_rows:
                terr[x][y] = tr.MARSH
    # Glacis derrière le mur extérieur, butte devant le donjon
    for y in range(1, height - 1):
        if grid[wx1 + 4][y] == 0:
            terr[wx1 + 4][y] = tr.HILL
    for x in range(wx2 - 3, wx2):
        for y in range(keep_center - 5, keep_center + 5):
            if 0 < y < height - 1 and grid[x][y] == 0:
                terr[x][y] = tr.HILL

    # ── Basse-cour: chemins protégés, maisons, jardins ──
    bx0, bx1 = wx1 + 5, wx2 - 4
    roads = set()
    for c in outer_centers:
        y = c
        for x in range(wx1 + 1, wx2):
            # la route glisse d'une porte extérieure vers la porte du donjon
            if x >= bx0 and y != keep_center:
                y += 1 if keep_center > y else -1
            for dy in (-1, 0, 1):
                roads.add((x, y + dy))
    houses = []
    if bx1 - bx0 >= 3:
        for _ in range(max(1, (bx1 - bx0) * height // 60)):
            for _try in range(20):
                w, h = random.randint(2, 3), random.randint(2, 3)
                hx = random.randint(bx0, max(bx0, bx1 - w))
                hy = random.randint(2, height - 3 - h)
                cells = [(hx + i, hy + j) for i in range(w) for j in range(h)]
                if any(c in roads or grid[c[0]][c[1]] != 0 or c[0] > bx1 for c in cells):
                    continue
                if any(0 <= c[0] + dx < width and 0 <= c[1] + dy < height
                       and grid[c[0] + dx][c[1] + dy] != 0
                       for c in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    continue
                for (x, y) in cells:
                    grid[x][y] = 1
                houses.extend(cells)
                break
        for _ in range(max(1, (bx1 - bx0) * height // 120)):
            gx = random.uniform(bx0, bx1)
            gy = random.uniform(3, height - 4)
            for x in range(int(gx) - 2, int(gx) + 3):
                for y in range(int(gy) - 2, int(gy) + 3):
                    if (bx0 <= x <= bx1 and 0 < y < height - 1 and grid[x][y] == 0
                            and (x, y) not in roads and (x - gx) ** 2 + (y - gy) ** 2 <= 2.2):
                        terr[x][y] = tr.WOOD

    _siege_copses(grid, terr, width, height, wx1, outer_centers)

    structs = {(x, y): st.PALISADE for x in range(wx1) for y in range(height) if grid[x][y] == 1}
    for c in houses:
        structs[c] = st.HOUSE
    for (x, y) in walls:
        if x in (wx1, wx2):
            structs[(x, y)] = st.WALL

    return grid, {
        'walls': walls,
        'ramparts': ramparts,
        'stairs': stairs,
        'gates': {pos: 10 for pos in outer_gates + keep_gates},
        'gate_save': 3,
        'gate_positions': outer_centers,
        'wall_x': wx1,
        'rings': [{'wall_x': wx1, 'gates': outer_gates},
                  {'wall_x': wx2, 'gates': keep_gates}],
        'terrain': terr,
        'structures': structs,
    }


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
    gate_rows = set(range(gate_center - gate_half, gate_center + gate_half))
    _build_wall(grid, wall_x, gate_rows, width, height, walls, gates, ramparts, stairs)

    # ── Palissades de l'assaillant: deux lignes de pieux épars ──
    # Chaque pieu couvre le tireur posté juste derrière (cf. terrain.
    # combat_mods) et brûle. Des pans continus de 2 à 4 pieux ont été
    # essayés: la première ligne tombe sur la colonne de déploiement et
    # bouchait l'avance de l'assaillant (23 % → 8 % de victoires); les
    # pieux épars, qui se touchent parfois, laissent passer (33 %).
    # Ligne 1 (proche des attaquants, x ≈ wall_x // 3)
    line1_x = wall_x // 3
    for zone_y in [height // 5, height // 2, 4 * height // 5]:
        for _ in range(random.randint(2, 4)):
            ox = line1_x + random.randint(-3, 3)
            oy = zone_y + random.randint(-2, 2)
            if 1 < ox < wall_x - 5 and 1 < oy < height - 1 and grid[ox][oy] == 0:
                grid[ox][oy] = 1

    # Ligne 2 (avancée, x ≈ 2*wall_x // 3)
    line2_x = 2 * wall_x // 3
    for zone_y in [height // 4, height // 2, 3 * height // 4]:
        for _ in range(random.randint(2, 3)):
            ox = line2_x + random.randint(-3, 3)
            oy = zone_y + random.randint(-2, 2)
            if 1 < ox < wall_x - 5 and 1 < oy < height - 1 and grid[ox][oy] == 0:
                grid[ox][oy] = 1

    # ── Terrain: fossé boueux au pied du mur, chaussée devant la porte,
    # glacis (butte) derrière les escaliers ──
    terr = tr.make_grid(width, height)
    for x in (wall_x - 2, wall_x - 1):
        for y in range(1, height - 1):
            if 0 <= x < width and grid[x][y] == 0 and y not in gate_rows:
                terr[x][y] = tr.MARSH
    glacis_x = wall_x + 4
    if glacis_x < width:
        for y in range(1, height - 1):
            if grid[glacis_x][y] == 0:
                terr[glacis_x][y] = tr.HILL

    _siege_copses(grid, terr, width, height, wall_x, gate_positions)

    structs = {(x, y): st.PALISADE for x in range(wall_x) for y in range(height)
               if grid[x][y] == 1}
    for (x, y) in walls:
        if x == wall_x:
            structs[(x, y)] = st.WALL

    siege_data = {
        'walls': walls,
        'ramparts': ramparts,
        'stairs': stairs,
        'gates': {pos: 10 for pos in gates},
        'gate_save': 3,
        'gate_positions': gate_positions,
        'wall_x': wall_x,
        'terrain': terr,
        'structures': structs,
    }

    return grid, siege_data


def generate_defile(width, height):
    """Défilé montagneux: goulet central avec flancs impraticables.

    Structure:
      • Parois rocheuses au nord et au sud, aux bords découpés et irréguliers
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
    cx = width // 2
    mid = (width - 1) / 2

    # ── Parois: bords découpés par un bruit lisse, étranglement en douceur ──
    # (une cloche en cosinus, pas une marche d'escalier). Tiré sur la moitié
    # ouest, lu en miroir à l'est.
    amp = 1.0 if height < 40 else 2.2
    n_top = procgen.smooth_noise(width // 2 + 1, amp)
    n_bot = procgen.smooth_noise(width // 2 + 1, amp)
    throat_squeeze = random.randint(3, 5)
    throat_half = max(3.0, width / 8 * 1.5)
    min_gap = 2 if height < 40 else 5

    def bump(x):
        d = min(1.0, abs(x - mid) / throat_half)
        return 0.5 * (1.0 + math.cos(math.pi * d))

    tops, bots = [], []
    for x in range(width):
        i = min(x, width - 1 - x)
        sq = throat_squeeze * bump(x)
        # Bords droits dans les zones de déploiement, découpés au-delà: un bord
        # irrégulier sous les colonnes de départ décalait les deux armées
        # différemment (test_miroir_colonnes_de_deploiement).
        fade = max(0.0, min(1.0, (i - width // 6) / max(1, width // 12)))
        t = int(round(pass_top + n_top[i] * fade + sq))
        b = int(round(pass_bot - n_bot[i] * fade - sq))
        if b - t < min_gap:
            c = (t + b) // 2
            t, b = c - min_gap // 2, c - min_gap // 2 + min_gap
        tops.append(max(1, t))
        bots.append(min(height - 2, b))
    for x in range(width):
        for y in range(height):
            if y < tops[x] or y > bots[x]:
                grid[x][y] = 1

    # ── Éperons: quelques avancées rocheuses qui cassent la ligne du bord ──
    for x in range(width // 6, width // 2):
        for edge, sgn in ((tops, 1), (bots, -1)):
            if random.random() < 0.06 and bots[x] - tops[x] > min_gap + 3:
                for j in range(random.randint(1, 2)):
                    y = edge[x] + sgn * j
                    for xx in (x, x + random.choice((0, 1))):
                        if 0 <= xx < width // 2 and tops[xx] <= y <= bots[xx]:
                            grid[xx][y] = 1

    # ── Rochers/couverts dans le goulet (abris tactiques) ──
    # 3 zones de couverts: 1/4, 1/2 et 3/4 de la largeur, jamais dans
    # l'étranglement (trop difficile à traverser)
    for zone_x in [width // 4, width // 2, 3 * width // 4]:
        num_rocks = random.randint(2, 4)
        placed = 0
        attempts = 0
        while placed < num_rocks and attempts < 40:
            attempts += 1
            rx = zone_x + random.randint(-4, 4)
            ry = pass_center_y + random.randint(-4, 4)
            if abs(rx - mid) < throat_half + 2:
                continue
            if min(rx, width - 1 - rx) < deploy_front(width) + 3:
                continue            # jamais sur les colonnes de déploiement
            if 0 <= rx < width and tops[rx] + 1 < ry < bots[rx] - 1 and grid[rx][ry] == 0:
                grid[rx][ry] = 1
                placed += 1

    # ── Dégager les zones de déploiement (x < width//6 et le reflet) ──
    for x in list(range(0, width // 6)) + list(range(width - width // 6, width)):
        for y in range(tops[x], bots[x] + 1):
            grid[x][y] = 0
    # Éperons et rochers tirés au hasard: même goulet des deux côtés
    _mirror_grid(grid, width, height)

    # ── Terrain ──
    terr = tr.make_grid(width, height)
    # Les pentes restent hors des zones de déploiement: les armées se
    # déploient en plaine, comme sur les autres cartes (cf. deploy_front).
    slope_start_x = deploy_front(width) + 3
    slope_end_x = width - slope_start_x
    marsh_n = procgen.smooth_noise(width // 2 + 1, 1.0)
    for x in range(width):
        top_b, bot_b = tops[x], bots[x]
        # Pentes au pied des parois: les tireurs y dominent le couloir
        if slope_start_x <= x < slope_end_x:
            for y in (top_b, top_b + 1, bot_b - 1, bot_b):
                if 0 <= y < height and grid[x][y] == 0:
                    terr[x][y] = tr.HILL
        # Éboulis boueux près du torrent, seulement si le couloir est
        # assez large pour laisser un passage sec au milieu
        if bot_b - top_b >= 6:
            wob = int(round(marsh_n[min(x, width - 1 - x)]))
            if cx - 6 <= x <= cx - 3:
                terr[x][top_b + 2 + max(0, wob)] = tr.MARSH
            if cx - 9 <= x <= cx - 6:
                terr[x][bot_b - 2 - max(0, wob)] = tr.MARSH
    _mirror_terrain(terr, width, height)

    # Torrent à l'étranglement: un pont et un gué à disputer
    t_top = max(tops[cx - 1], tops[cx])
    t_bot = min(bots[cx - 1], bots[cx])
    rcols = (cx - 1, cx)
    free = list(range(t_top, t_bot + 1))
    for x in rcols:
        for y in free:
            grid[x][y] = 0          # les éperons cèdent la place au torrent
            terr[x][y] = tr.RIVER
    if len(free) >= 4:
        m = len(free) // 2
        bridge = free[m - 2:m]
        ford = free[m + 1:m + 3]
    else:
        bridge, ford = free, []
    for x in rcols:
        for y in bridge:
            terr[x][y] = tr.BRIDGE
        for y in ford:
            terr[x][y] = tr.FORD

    return grid, {'terrain': terr}


def deploy_front(width, deploy_gap=None, siege=False):
    """Colonne de front de l'armée 1 (source unique: Battle._place_armies
    l'utilise aussi). Rien de procédural ne doit tomber à sa gauche
    (principe « zones de déploiement en plaine »)."""
    mid_x = width // 2
    if siege:
        gap = 12
    elif deploy_gap:
        gap = int(deploy_gap)
    else:
        gap = max(12, int(width * 0.12))
    return mid_x - max(4, min(gap, mid_x - 8))


def generate_desert(width, height):
    """Désert: un reg ouvert où l'eau et l'ombre sont les objectifs.

    Structure:
      • Affleurements rocheux en petits amas (couverts destructibles), plus
        nombreux vers le centre
      • Dunes: longues crêtes nord-sud (collines) — on les tient, elles
        masquent ce qui se cache derrière
      • Oasis centrale: mare boueuse cernée de palmiers (bois)
    Aucun obstacle ni relief devant les lignes de déploiement.
    """
    grid = [[0] * height for _ in range(width)]
    terr = tr.make_grid(width, height)
    lo = deploy_front(width) + 3
    mx, cy = (width - 1) / 2, (height - 1) / 2

    # ── Affleurements rocheux (ouest tiré, est recopié) ──
    n_rocks = max(3, (width * height) // 420)
    procgen.scatter_rocks(grid, width, height, n_rocks, (lo, width // 2 - 3),
                          (2, height - 3), cluster=(2, 5), symmetric=True)

    # ── Oasis: mare boueuse et palmeraie ──
    pond_r = max(1.2, min(height, width) * 0.05)
    for x in range(width):
        for y in range(height):
            d = math.hypot(x - mx, y - cy)
            if d <= pond_r + 3.2:
                grid[x][y] = 0
            if d <= pond_r:
                terr[x][y] = tr.MARSH
    for x in range(width // 2):
        for y in range(1, height - 1):
            d = math.hypot(x - mx, y - cy)
            if pond_r < d <= pond_r + 2.2 and random.random() < 0.55:
                terr[x][y] = tr.WOOD
    _mirror_terrain(terr, width, height)

    # ── Dunes ──
    n_dunes = max(2, (width * height) // 900)
    size = (1.4, max(2.0, height * 0.07))
    procgen.scatter_blobs(terr, grid, width, height, n_dunes, (lo, width // 2 - 2),
                          (2, height - 3), size, tr.HILL, elongated=True, symmetric=True)
    return grid, {'terrain': terr}


# ═══════════════════════════════════════════════════════════════
#                 COUCHES DE THÈME (relief, biome)
# ═══════════════════════════════════════════════════════════════

def _field_x_range(map_name, width, data):
    """Bande de terrain où les couches procédurales ont le droit de peindre:
    entre le front de l'armée 1 et le centre (cartes symétriques), ou entre
    le front de l'assaillant et le fossé (sièges)."""
    if map_name in SIEGE_MAPS:
        wall_x = data['rings'][0]['wall_x'] if data.get('rings') else data['wall_x']
        return deploy_front(width, siege=True) + 3, wall_x - 6
    return deploy_front(width, data.get('deploy_gap')) + 3, width // 2 - 2


def _gate_rows(data):
    return list(data.get('gate_positions', ()))


def _clear_village_houses_near(grid, width, height, cells):
    """Une maison coupée par la rivière n'est plus une maison: on retire
    les blocs d'obstacles qui touchent le lit (le miroir est préservé,
    le lit étant symétrique)."""
    near = {(x + dx, y) for (x, y) in cells for dx in (-1, 0, 1)}
    obstacles = [(x, y) for x in range(width) for y in range(height) if grid[x][y] == 1]
    for comp in st._components(obstacles):
        if any(c in near for c in comp):
            for (x, y) in comp:
                grid[x][y] = 0


def _add_river(map_name, grid, data, width, height, biome):
    terr = data['terrain']
    cy = height // 2
    if map_name in SIEGE_MAPS:
        x_lo, x_hi = _field_x_range(map_name, width, data)
        if x_hi - x_lo < 3:
            return
        spans = procgen.river_spans_meander(height, (x_lo + x_hi) // 2, x_lo, x_hi,
                                            width_cells=2 if width < 90 else 3)
        gates = _gate_rows(data)
        crossings = procgen.pick_rows(height, 1 if height < 40 else 2, forced=gates)
        _, approach = procgen.paint_river(grid, terr, width, height, spans, crossings,
                                          bridge_rows=gates)
        # Les palissades ne se dressent pas au milieu de l'eau
        structs = data.get('structures')
        if structs:
            for c in [c for c in structs if grid[c[0]][c[1]] == 0]:
                del structs[c]
        if biome == "Forêt":
            procgen.paint_banks(grid, terr, width, height, spans, tr.WOOD, 0.3, skip=approach)
        return

    amp = 1 if width < 90 else 2
    spans = procgen.river_spans_symmetric(width, height, amp)
    if map_name == "Village":
        bed = {(x, y) for y, v in spans.items()
               for x0, x1 in procgen._segs(v) for x in range(x0, x1 + 1)}
        _clear_village_houses_near(grid, width, height, bed)
    # Un pont là où l'on marche déjà (grand-rue du village, couloir central)
    forced = [cy]
    crossings = procgen.pick_rows(height, 2 if height < 40 else 3, margin=4, forced=forced)
    _, approach = procgen.paint_river(grid, terr, width, height, spans, crossings,
                                      bridge_rows=forced)
    bank = {"Forêt": (tr.WOOD, 0.35), "Désert": (tr.WOOD, 0.45),
            "Prairie": (tr.WOOD, 0.12)}[biome]
    procgen.paint_banks(grid, terr, width, height, spans, bank[0], bank[1],
                        skip=approach, symmetric=True)


def _remove_river(map_name, data, width, height):
    """Le ruisseau de la Forêt redevient sous-bois; ses gués, des sentiers."""
    terr = data['terrain']
    procgen.strip(terr, width, height, (tr.RIVER,), to=tr.WOOD)
    procgen.strip(terr, width, height, (tr.FORD, tr.BRIDGE), to=tr.PLAIN)


def _add_hills(map_name, grid, data, width, height):
    terr = data['terrain']
    x_lo, x_hi = _field_x_range(map_name, width, data)
    n = max(2, (width * height) // 1100)
    size = (1.6, max(2.2, height * 0.06))
    if map_name in SIEGE_MAPS:
        procgen.scatter_blobs(terr, grid, width, height, n, (x_lo, x_hi), (2, height - 3),
                              size, tr.HILL, avoid_rows=_gate_rows(data))
    else:
        if map_name == "Forêt":
            x_lo = max(x_lo, width // 2 - int(width * 0.16))
        procgen.scatter_blobs(terr, grid, width, height, n, (x_lo, x_hi), (2, height - 3),
                              size, tr.HILL, symmetric=True)


def _apply_biome(map_name, grid, data, width, height, biome):
    """Végétation d'une disposition bâtie hors de sa prairie natale."""
    terr = data['terrain']
    x_lo, x_hi = _field_x_range(map_name, width, data)
    cy = height // 2
    if biome == "Forêt":
        n = max(3, (width * height) // 450)
        size = (1.4, max(2.0, height * 0.06))
        if map_name in SIEGE_MAPS:
            procgen.scatter_blobs(terr, grid, width, height, n, (x_lo, x_hi), (1, height - 2),
                                  size, tr.WOOD, avoid_rows=_gate_rows(data))
        else:
            procgen.scatter_blobs(terr, grid, width, height, n, (x_lo, x_hi), (1, height - 2),
                                  size, tr.WOOD, avoid_rows=[cy], symmetric=True)
    elif biome == "Désert":
        # Plus de jardins ni de vergers: seuls restent les palmiers au bord
        # de l'eau. Règle déterministe → la symétrie est préservée.
        wet = set(procgen.WET)
        for x in range(width):
            for y in range(height):
                if terr[x][y] != tr.WOOD:
                    continue
                if not any(0 <= x + dx < width and 0 <= y + dy < height
                           and terr[x + dx][y + dy] in wet
                           for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)):
                    terr[x][y] = tr.PLAIN
        if map_name == "Village":
            # La mare du village devient une oasis: palmiers tout autour
            for x in range(width):
                for y in range(1, height - 1):
                    if (terr[x][y] == tr.PLAIN and grid[x][y] == 0 and abs(y - cy) > 2
                            and any(0 <= x + dx < width and terr[x + dx][y + dy] == tr.MARSH
                                    for dx in (-1, 0, 1) for dy in (-1, 0, 1))):
                        terr[x][y] = tr.WOOD


def _ensure_crossing(map_name, grid, data, width, height):
    """Filet de sécurité: si les couches ont coupé le passage d'un bord à
    l'autre (ou jusqu'au fossé), on ouvre un gué sur la rangée centrale."""
    terr = data['terrain']
    cy = height // 2
    x_end = _field_x_range(map_name, width, data)[1] + 3 if map_name in SIEGE_MAPS else width - 2
    left = [(1, y) for y in range(1, height - 1) if grid[1][y] == 0 and tr.MOVE[terr[1][y]] is not None]
    right = [(x_end, y) for y in range(1, height - 1)
             if grid[x_end][y] == 0 and tr.MOVE[terr[x_end][y]] is not None]
    if _bfs_path(grid, width, height, left, right, terr):
        return
    for x in range(1, x_end + 1):
        for y in (cy - 1, cy, cy + 1):
            if grid[x][y] == 1:
                grid[x][y] = 0
            if terr[x][y] == tr.RIVER:
                terr[x][y] = tr.FORD
    structs = data.get('structures')
    if structs:
        for c in [c for c in structs if grid[c[0]][c[1]] == 0]:
            del structs[c]


def apply_theme(map_name, grid, data, width, height, opts):
    """Pose les couches de thème sur une carte générée. Ne fait RIEN (et ne
    tire aucun dé) quand `opts` est le thème naturel de la carte."""
    if map_name not in THEMED_MAPS or data.get('terrain') is None:
        return
    nat_river, nat_hills = NATURAL_RELIEF[map_name]
    changed = False
    if opts['biome'] != natural_biome(map_name):
        _apply_biome(map_name, grid, data, width, height, opts['biome'])
        changed = True
    if opts['hills'] != nat_hills:
        if opts['hills']:
            _add_hills(map_name, grid, data, width, height)
        else:
            procgen.strip(data['terrain'], width, height, (tr.HILL,))
        changed = True
    if opts['river'] != nat_river:
        if opts['river']:
            _add_river(map_name, grid, data, width, height, opts['biome'])
        else:
            _remove_river(map_name, data, width, height)
        changed = True
    if changed:
        _ensure_crossing(map_name, grid, data, width, height)


# ═══════════════════════════════════════════════════════════════
#                 AVANTAGE DE TERRAIN (option du menu)
# ═══════════════════════════════════════════════════════════════
# Par défaut, une bataille rangée se joue sur une carte en miroir: aucun
# camp n'a meilleur terrain. On peut au contraire en favoriser un:
#   Léger   une crête sous et devant son front (hauteur: +1 portée à ses
#           tireurs, mêlée plus difficile contre lui)
#   Marqué  des hauteurs plus étendues et des bosquets de couverture à ses
#           deux ailes. (Mesuré et écarté: marais sur l'approche adverse et
#           haies devant le front desservaient le camp favorisé, qui devait
#           les franchir à son tour pour contre-attaquer.)
# Les sièges n'ont pas l'option: la forteresse EST l'avantage du défenseur.

ADVANTAGE_NONE = "Aucun"
ADVANTAGE_SIDES = {ADVANTAGE_NONE: 0, "Armée 1": 1, "Armée 2": 2}
ADVANTAGE_LEVELS = ("Léger", "Marqué")


def advantage_of(options):
    """(camp favorisé 0/1/2, niveau 1/2) lu dans les options de carte."""
    options = options or {}
    side = options.get('advantage', 0)
    if isinstance(side, str):
        side = ADVANTAGE_SIDES.get(side, 0)
    level = 2 if options.get('advantage_level') == ADVANTAGE_LEVELS[1] else 1
    return side, level


def apply_advantage(map_name, grid, data, width, height, side, level):
    """Façonne le terrain en faveur d'un camp. Ne tire aucun dé si side == 0."""
    if not side or map_name in SIEGE_MAPS or data.get('terrain') is None:
        return []
    terr = data['terrain']
    front = deploy_front(width, data.get('deploy_gap'))
    mid = width // 2

    def X(x):                       # coordonnée du côté du camp favorisé
        return x if side == 1 else width - 1 - x

    def band(lo, hi):               # bande de colonnes, du bon côté
        a, b = X(lo), X(hi)
        return (min(a, b), max(a, b))

    painted = []
    cy = height / 2.0
    # Hauteurs à cheval sur le front: une CHAÎNE de buttes irrégulières,
    # décalées et inclinées (une bande droite faisait une carte « en
    # ligne »), qui couvre la zone de déploiement du camp favorisé.
    n = 2 if level == 1 else 3
    span = height * (0.48 if level == 1 else 0.72)
    step = span / n
    for i in range(n):
        ry = step * random.uniform(0.40, 0.50)      # des cols entre les buttes
        y = cy - span / 2 + step * (i + 0.5) + random.uniform(-1.5, 1.5)
        x = front + 1 + random.uniform(-2.5, 2.5)
        rx = random.uniform(2.8, 4.2) + (0.6 if level >= 2 else 0.0)
        painted += procgen.paint_blob(terr, grid, width, height, X(x), y, rx, ry,
                                      random.uniform(-0.35, 0.35), tr.HILL,
                                      x_range=band(front - 4, front + 6), rough=0.26)
    ry = span / 2
    if level >= 2:
        # Bosquets aux deux ailes, un peu en avant: couvert pour les tireurs
        for sgn in (-1, 1):
            y = cy + sgn * (ry + 2.5)
            if 2 <= y <= height - 3:
                painted += procgen.paint_blob(terr, grid, width, height, X(front + 4), y,
                                              2.2, 2.6, random.uniform(0, math.pi), tr.WOOD,
                                              x_range=band(front + 1, front + 8))
    return painted


# ═══════════════════════════════════════════════════════════════
#                    FONCTION PRINCIPALE
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#                 DÉCOR (purement visuel)
# ═══════════════════════════════════════════════════════════════
# Ces objets n'ont AUCUN effet de jeu: ils ne bloquent rien, ne coupent
# aucune ligne de vue, n'entrent pas dans la grille. Ils existent pour que
# le champ de bataille ressemble à un lieu plutôt qu'à un damier.
#
# Règle de lisibilité: les gros objets (arbres, charrettes, troncs) ne se
# posent que sur les marges et autour des couverts existants — jamais en
# plein milieu du champ où se joue le combat, sinon ils masquent les
# unités.

# Sous-bois: c'est là, et plus au hasard, que poussent les arbres
_WOOD_DECOR = {
    'density': 0.45,
    'big': [("arbre_pin", 3), ("arbre_rond", 4), ("buisson", 3)],
}
# Au désert, le « bois » est une palmeraie clairsemée
_WOOD_DECOR_DESERT = {
    'density': 0.35,
    'big': [("arbre_rond", 3), ("buisson", 2), ("buisson_sec", 3)],
}
# Ce que devient un objet de décor verdoyant sous le soleil du désert
_DESERT_SWAP = {
    "herbe": "caillou", "herbe_haute": "buisson_sec", "fleurs": "caillou",
    "fougere": "buisson_sec", "champignon": "caillou", "buisson": "buisson_sec",
    "arbre_pin": "buisson_sec", "arbre_rond": "rocher", "botte_foin": "caisse",
    "souche": "rocher", "tronc": "buisson_sec",
}
_NO_DECOR_TERRAIN = {tr.RIVER, tr.FORD, tr.BRIDGE}

# (nature, poids) par carte — "petit" = herbes, fleurs, cailloux…
_DECOR_TABLES = {
    "Prairie": {
        'density': 0.13,
        'small': [("herbe", 5), ("fleurs", 2), ("caillou", 2), ("herbe_haute", 2)],
        'big':   [("buisson", 4), ("arbre_rond", 2), ("souche", 1), ("rocher", 2)],
    },
    "Forêt": {
        'density': 0.20,
        'small': [("herbe", 4), ("fougere", 5), ("champignon", 1), ("caillou", 1)],
        'big':   [("buisson", 4), ("arbre_pin", 3), ("arbre_rond", 3), ("souche", 2),
                  ("tronc", 2)],
    },
    "Village": {
        'density': 0.10,
        'small': [("herbe", 3), ("caillou", 2), ("seau", 1), ("paves", 3)],
        'big':   [("caisse", 3), ("tonneau", 3), ("botte_foin", 2), ("charrette", 1),
                  ("buisson", 2)],
    },
    "Citadelle": {
        'density': 0.08,
        'small': [("caillou", 3), ("gravats", 2), ("herbe", 2)],
        'big':   [("caisse", 2), ("tonneau", 2), ("brasero", 1), ("pieux", 2),
                  ("gravats_tas", 2)],
    },
    "Siège": {
        'density': 0.09,
        'small': [("caillou", 3), ("gravats", 3), ("herbe", 1)],
        'big':   [("gravats_tas", 3), ("caisse", 2), ("tonneau", 2), ("brasero", 1),
                  ("pieux", 2)],
    },
    "Défilé": {
        'density': 0.15,
        'small': [("caillou", 5), ("gravats", 2), ("herbe", 1)],
        'big':   [("rocher", 4), ("buisson_sec", 3), ("souche", 1)],
    },
    "Désert": {
        'density': 0.09,
        'small': [("caillou", 5), ("gravats", 2)],
        'big':   [("rocher", 4), ("buisson_sec", 4), ("gravats_tas", 1)],
    },
}


def _decor_table(map_name, biome=None):
    """Table de décor d'une disposition, adaptée à son biome."""
    table = _DECOR_TABLES.get(map_name, _DECOR_TABLES["Prairie"])
    if biome is None or biome == natural_biome(map_name):
        return table
    if biome == "Désert":
        def swap(entries):
            merged = {}
            for kind, w in entries:
                k = _DESERT_SWAP.get(kind, kind)
                merged[k] = merged.get(k, 0) + w
            return list(merged.items())
        return {'density': table['density'] * 0.8,
                'small': swap(table['small']), 'big': swap(table['big'])}
    if biome == "Forêt":
        return {'density': table['density'] * 1.2,
                'small': table['small'] + [("fougere", 3), ("champignon", 1)],
                'big': table['big'] + [("buisson", 3), ("souche", 2), ("tronc", 1)]}
    return table


def _weighted_pick(rng, table):
    total = sum(w for _, w in table)
    r = rng.uniform(0, total)
    acc = 0.0
    for kind, w in table:
        acc += w
        if r <= acc:
            return kind
    return table[-1][0]


def generate_decor(map_name, grid, width, height, terrain=None, biome=None):
    """Sème le décor sur les cases libres. Retourne [(x, y, kind, seed)].

    Utilise sa propre RNG (une seule ponction sur le flux global) pour ne
    pas décaler les dés de la bataille.
    """
    table = _decor_table(map_name, biome)
    wood_decor = _WOOD_DECOR_DESERT if (biome or natural_biome(map_name)) == "Désert" else _WOOD_DECOR
    rng = random.Random(random.randrange(1 << 30))

    density = table['density']
    margin_top = height // 4          # au-delà: zone de manœuvre, on allège
    margin_bottom = height - height // 4
    props = []
    occupied = set()

    for x in range(1, width - 1):
        for y in range(1, height - 1):
            if grid[x][y] != 0:
                continue
            tname = terrain[x][y] if terrain is not None else tr.PLAIN
            if tname in _NO_DECOR_TERRAIN:
                continue
            if tname == tr.WOOD:
                if rng.random() > wood_decor['density']:
                    continue
                if any((x + dx, y + dy) in occupied
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    continue
                occupied.add((x, y))
                props.append((x, y, _weighted_pick(rng, wood_decor['big']),
                              rng.randrange(1 << 16)))
                continue
            if rng.random() > density:
                continue
            # Un gros objet n'a droit de cité que sur les marges ou en
            # lisière d'un couvert existant.
            near_cover = any(
                0 <= x + dx < width and 0 <= y + dy < height
                and grid[x + dx][y + dy] in (1, 2)
                for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            on_margin = y < margin_top or y > margin_bottom
            if (on_margin or near_cover) and rng.random() < 0.55:
                kind = _weighted_pick(rng, table['big'])
                if terrain is not None and kind in ("arbre_pin", "arbre_rond"):
                    kind = "buisson"
                # Les gros objets ne se collent pas les uns aux autres
                if any((x + dx, y + dy) in occupied
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    continue
                occupied.add((x, y))
            else:
                kind = _weighted_pick(rng, table['small'])
            props.append((x, y, kind, rng.randrange(1 << 16)))

    return props


def generate_ground_patches(map_name, width, height, biome=None):
    """Grandes taches de sol (terre battue, herbe rase, mousse, gravier).

    Le bruit calculé par case produit forcément des carrés alignés sur la
    grille. Ces ellipses, elles, ignorent la grille: c'est ce qui enlève
    l'aspect « tableur » du terrain.
    """
    rng = random.Random(random.randrange(1 << 30))
    n = max(12, (width * height) // 55)
    # (teinte RGB relative au fond, opacité)
    palettes = {
        "Prairie": [((-16, -10, -8), 70), ((14, 26, -10), 60), ((30, 10, -16), 48)],
        "Forêt":   [((-18, -14, -10), 74), ((4, 28, 2), 54), ((26, 12, -12), 44)],
        "Village": [((26, 16, -6), 60), ((-22, -18, -14), 62), ((10, 14, 18), 42)],
        "Siège":   [((-20, -20, -16), 60), ((22, 18, 14), 46), ((26, 10, -8), 38)],
        "Citadelle": [((-20, -20, -16), 60), ((22, 18, 14), 46), ((26, 10, -8), 38)],
        "Défilé":  [((26, 18, 2), 56), ((-24, -22, -18), 58), ((14, 14, 18), 40)],
        "Désert":  [((24, 18, 6), 58), ((-22, -20, -14), 52), ((14, 4, -10), 44)],
    }
    if biome is not None and biome != natural_biome(map_name):
        pal = palettes[biome]
    else:
        pal = palettes.get(map_name, palettes["Prairie"])

    patches = []
    for _ in range(n):
        fx = rng.uniform(1, width - 1)
        fy = rng.uniform(1, height - 1)
        rw = rng.uniform(1.8, 5.5)
        rh = rw * rng.uniform(0.45, 0.85)
        tint, alpha = pal[rng.randrange(len(pal))]
        patches.append((fx, fy, rw, rh, tint, alpha))
    return patches


def generate_structures(map_name, grid, width, height):
    """Ce que sont les obstacles `1` d'une carte, pour la destruction
    (cf. structures.py). Calculé sur la grille finale, donc déjà en miroir.
    Les masses rocheuses du Défilé restent indestructibles: pas de structure."""
    obstacles = [(x, y) for x in range(width) for y in range(height) if grid[x][y] == 1]
    if map_name == "Village":
        return st.classify_village(grid, width, height)
    if map_name == "Forêt":
        return {c: st.GROVE for c in obstacles}
    if map_name in ("Prairie", "Désert"):
        return {c: st.ROCK for c in obstacles}
    return {}


def generate_map(map_name, width, height, options=None):
    """Génère la grille et les données spéciales pour un type de map.

    options: {'biome', 'relief'} ou {'biome', 'river', 'hills'} (cf.
    resolve_options), plus 'advantage' (0/1/2 ou "Armée 1"…) et
    'advantage_level' (cf. apply_advantage). Sans options, la carte
    historique.

    Retourne (grid, map_data) où:
        grid: [[int]] — grille 2D (0=vide, 1=obstacle, 2=mur, 3=porte)
        map_data: dict — données spéciales (siege_data, etc.), dont
            'theme': les options résolues {'biome', 'river', 'hills'}
    """
    generators = {
        "Prairie": generate_prairie,
        "Forêt": generate_forest,
        "Désert": generate_desert,
        "Village": generate_village,
        "Siège": generate_siege,
        "Citadelle": generate_citadel,
        "Défilé": generate_defile,
    }

    gen = generators.get(map_name, generate_prairie)
    opts = resolve_options(map_name, options)
    grid, map_data = gen(width, height)
    map_data = dict(map_data or {})
    apply_theme(map_name, grid, map_data, width, height, opts)
    side, level = advantage_of(options)
    if side and map_name not in SIEGE_MAPS:
        apply_advantage(map_name, grid, map_data, width, height, side, level)
        opts = dict(opts, advantage=side, advantage_level=level)
    map_data['theme'] = opts
    map_data['decor'] = generate_decor(map_name, grid, width, height,
                                       map_data.get('terrain'), opts['biome'])
    map_data['ground_patches'] = generate_ground_patches(map_name, width, height,
                                                         opts['biome'])
    if 'structures' not in map_data:
        map_data['structures'] = generate_structures(map_name, grid, width, height)
    return grid, map_data
