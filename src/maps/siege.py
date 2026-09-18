"""Cartes de siège: Siège (une enceinte) et Citadelle (deux enceintes)."""

import math

from rng_scope import RNG
import procgen
import structures as st
import terrain as tr

from .common import deploy_front


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
    for _ in range(RNG.randint(2, 4)):
        r = RNG.uniform(1.0, 2.2 if height >= 40 else 1.5)
        wx = RNG.uniform(x_lo + r, x_hi - r)
        wy = RNG.uniform(2, height - 3)
        if any(abs(wy - g) < 6 + r for g in gate_rows):
            continue
        procgen.paint_blob(terr, grid, width, height, wx, wy, r * RNG.uniform(1.0, 1.6), r,
                           RNG.uniform(0, math.pi), tr.WOOD, x_range=(x_lo, x_hi), rough=0.35)


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
            for _ in range(RNG.randint(*n)):
                ox = line_x + RNG.randint(-3, 3)
                oy = zone_y + RNG.randint(-2, 2)
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
                w, h = RNG.randint(2, 3), RNG.randint(2, 3)
                hx = RNG.randint(bx0, max(bx0, bx1 - w))
                hy = RNG.randint(2, height - 3 - h)
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
            gx = RNG.uniform(bx0, bx1)
            gy = RNG.uniform(3, height - 4)
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
        for _ in range(RNG.randint(2, 4)):
            ox = line1_x + RNG.randint(-3, 3)
            oy = zone_y + RNG.randint(-2, 2)
            if 1 < ox < wall_x - 5 and 1 < oy < height - 1 and grid[ox][oy] == 0:
                grid[ox][oy] = 1

    # Ligne 2 (avancée, x ≈ 2*wall_x // 3)
    line2_x = 2 * wall_x // 3
    for zone_y in [height // 4, height // 2, 3 * height // 4]:
        for _ in range(RNG.randint(2, 3)):
            ox = line2_x + RNG.randint(-3, 3)
            oy = zone_y + RNG.randint(-2, 2)
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
