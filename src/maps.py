"""Système de cartes — génère différents terrains pour le champ de bataille.

Types de cellules dans la grille:
    0 = vide (traversable)
    1 = obstacle (infranchissable, bloque vision)
    2 = mur (infranchissable, unités dessus = +2 svg, CaC ne passe pas)
    3 = porte (destructible, a des PV)
"""

import math
import random

import terrain as tr


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
        "bg_color": (64, 62, 50),
        "obstacle_color": (92, 88, 80),
        "grid_color": (70, 68, 56),
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

    # ── Terrain ──
    # Les crêtes deviennent des collines: on les tient au lieu d'y buter.
    # La moitié des rochers disparaît, le reste sert de couvert au sommet.
    for ry in ridge_ys:
        for x in range(ridge_start_x, ridge_end_x + 1):
            for y in range(ry - 2, ry + 3):
                if 0 <= x < width and 0 < y < height - 1 and grid[x][y] == 1 \
                        and random.random() < 0.5:
                    grid[x][y] = 0

    terr = tr.make_grid(width, height)
    half = width // 2
    for ry in ridge_ys:
        for x in range(ridge_start_x, half):
            for y in (ry - 1, ry, ry + 1):
                if 0 < y < height - 1:
                    terr[x][y] = tr.HILL
    # Broussailles sur les flancs, juste devant la ligne de déploiement:
    # de quoi masquer une cavalerie
    for by in (height / 8, 7 * height / 8):
        _paint_disc(terr, width * 0.44, by, 1.8, tr.WOOD, width, height)
    _mirror_terrain(terr, width, height)
    # Colline centrale basse: l'objectif naturel du couloir principal
    _paint_disc(terr, (width - 1) / 2, (height - 1) / 2, 3.0, tr.HILL, width, height)

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
    for x in range(width // 2):
        for y in range(height):
            grid[width - 1 - x][y] = grid[x][y]

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
    rcols = (cx - 1, cx)
    for y in range(1, height - 1):
        if inside(cx, y, 0.9):
            for x in rcols:
                grid[x][y] = 0
                terr[x][y] = tr.RIVER
    for ty in sorted(set(trail_ys), key=lambda t: abs(t - cy))[:2]:
        for y in (ty - 1, ty, ty + 1):
            if 0 < y < height - 1:
                for x in rcols:
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

    # ── Terrain ──
    terr = tr.make_grid(width, height)
    mx = (width - 1) / 2
    # Le bourg est sur une butte: ses rues dominent les champs
    _paint_disc(terr, mx, cy, R + 1.0, tr.HILL, width, height)
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

    # ── Terrain ──
    terr = tr.make_grid(width, height)
    cx = width // 2
    # Les pentes restent hors des zones de déploiement: les armées se
    # déploient en plaine, comme sur les autres cartes (principe "zones de
    # déploiement en plaine"). La colonne de front par défaut suit la même
    # formule que Battle.__init__ (gap = max(12, 12% de la largeur), borné
    # à mid_x - 8): on la reproduit ici pour que les pentes ne débordent
    # jamais sur la zone où les unités apparaissent, avec une petite marge.
    _deploy_gap = max(12, int(width * 0.12))
    _deploy_gap = max(4, min(_deploy_gap, cx - 8))
    slope_start_x = cx - _deploy_gap + 3
    slope_end_x = width - slope_start_x
    for x in range(width):
        in_throat = throat_start <= x < throat_end
        top_b = pass_top + (throat_squeeze if in_throat else 0)
        bot_b = pass_bot - (throat_squeeze if in_throat else 0)
        # Pentes au pied des parois: les tireurs y dominent le couloir
        if slope_start_x <= x < slope_end_x:
            for y in (top_b, top_b + 1, bot_b - 1, bot_b):
                if 0 <= y < height:
                    terr[x][y] = tr.HILL
        # Éboulis boueux près du torrent, seulement si le couloir est
        # assez large pour laisser un passage sec au milieu
        if bot_b - top_b >= 6:
            if cx - 6 <= x <= cx - 3:
                terr[x][top_b + 2] = tr.MARSH
            if cx - 9 <= x <= cx - 6:
                terr[x][bot_b - 2] = tr.MARSH
    _mirror_terrain(terr, width, height)

    # Torrent à l'étranglement: un pont et un gué à disputer
    t_top = pass_top + throat_squeeze
    t_bot = pass_bot - throat_squeeze
    rcols = (cx - 1, cx)
    free = list(range(t_top, t_bot + 1))
    for x in rcols:
        for y in free:
            grid[x][y] = 0          # les saillies cèdent la place au torrent
            terr[x][y] = tr.RIVER
    if len(free) >= 4:
        mid = len(free) // 2
        bridge = free[mid - 2:mid]
        ford = free[mid + 1:mid + 3]
    else:
        bridge, ford = free, []
    for x in rcols:
        for y in bridge:
            terr[x][y] = tr.BRIDGE
        for y in ford:
            terr[x][y] = tr.FORD

    return grid, {'terrain': terr}


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
}


def _weighted_pick(rng, table):
    total = sum(w for _, w in table)
    r = rng.uniform(0, total)
    acc = 0.0
    for kind, w in table:
        acc += w
        if r <= acc:
            return kind
    return table[-1][0]


def generate_decor(map_name, grid, width, height, terrain=None):
    """Sème le décor sur les cases libres. Retourne [(x, y, kind, seed)].

    Utilise sa propre RNG (une seule ponction sur le flux global) pour ne
    pas décaler les dés de la bataille.
    """
    table = _DECOR_TABLES.get(map_name, _DECOR_TABLES["Prairie"])
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
                if rng.random() > _WOOD_DECOR['density']:
                    continue
                if any((x + dx, y + dy) in occupied
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    continue
                occupied.add((x, y))
                props.append((x, y, _weighted_pick(rng, _WOOD_DECOR['big']),
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


def generate_ground_patches(map_name, width, height):
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
        "Défilé":  [((26, 18, 2), 56), ((-24, -22, -18), 58), ((14, 14, 18), 40)],
    }
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
    grid, map_data = gen(width, height)
    map_data = dict(map_data or {})
    map_data['decor'] = generate_decor(map_name, grid, width, height,
                                       map_data.get('terrain'))
    map_data['ground_patches'] = generate_ground_patches(map_name, width, height)
    return grid, map_data
