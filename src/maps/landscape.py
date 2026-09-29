"""Paysage purement visuel: chemins, champs cultivés, camp de siège.

Rien ici n'entre dans la grille ni dans le terrain: aucune incidence sur
le déplacement, le tir ou l'IA. Ces éléments font d'une carte un LIEU —
la route qui mène à la porte, les rues du bourg, les sillons autour des
fermes, les tentes de l'assiégeant.

Tout tire ses dés d'un générateur local (`rng`), lui-même semé d'un seul
dé du flux de la carte (cf. maps.generate_map): la carte ne change pas.
"""

import math

import terrain as tr

from .catalog import SIEGE_MAPS
from .common import deploy_front

_BAD_ROAD = (tr.RIVER, tr.LAKE, tr.MARSH, tr.WOOD)


def _wobbly(rng, x0, y0, x1, y1, amp, step=2.0):
    """Polyligne de (x0, y0) à (x1, y1) qui ondule doucement (amplitude
    `amp` cases au milieu, nulle aux extrémités)."""
    L = math.hypot(x1 - x0, y1 - y0)
    n = max(2, int(L / step))
    phase = rng.uniform(0, math.tau)
    freq = rng.uniform(0.7, 1.8)
    nx, ny = -(y1 - y0) / (L or 1), (x1 - x0) / (L or 1)
    pts = []
    for i in range(n + 1):
        t = i / n
        off = amp * math.sin(math.pi * t) * math.sin(math.tau * freq * t + phase)
        pts.append((x0 + (x1 - x0) * t + nx * off, y0 + (y1 - y0) * t + ny * off))
    return pts


def _badness(path, grid, terr, width, height):
    bad = 0
    for (x, y) in path:
        ix, iy = int(x), int(y)
        if not (0 <= ix < width and 0 <= iy < height):
            continue
        if grid[ix][iy] != 0 or (terr is not None and terr[ix][iy] in _BAD_ROAD):
            bad += 1
    return bad


def _best_road(candidates, grid, terr, width, height):
    return min(candidates, key=lambda p: _badness(p, grid, terr, width, height))


def _bridge_center(terr, width, height):
    if terr is None:
        return None
    cells = [(x, y) for x in range(width) for y in range(height) if terr[x][y] == tr.BRIDGE]
    if not cells:
        return None
    return (sum(c[0] for c in cells) / len(cells) + 0.5, sum(c[1] for c in cells) / len(cells) + 0.5)


def _open_road(rng, grid, terr, width, height):
    """Route de campagne d'un bord à l'autre (par le pont s'il y en a un),
    choisie parmi quelques tracés pour éviter l'eau, les bois et les
    rochers."""
    bridge = _bridge_center(terr, width, height)
    cands = []
    for _ in range(8):
        ya = rng.uniform(height * 0.2, height * 0.8)
        yb = rng.uniform(height * 0.2, height * 0.8)
        amp = rng.uniform(1.5, max(1.6, height * 0.08))
        if bridge:
            bx, by = bridge
            cands.append(_wobbly(rng, 0, ya, bx - 1.5, by, amp)
                         + _wobbly(rng, bx + 1.5, by, width, yb, amp))
        else:
            cands.append(_wobbly(rng, 0, ya, width, yb, amp))
    roads = [_best_road(cands, grid, terr, width, height)]
    # Parfois un chemin de traverse nord-sud, sur un flanc
    if rng.random() < 0.45:
        x = rng.choice((rng.uniform(width * 0.12, width * 0.3), rng.uniform(width * 0.7, width * 0.88)))
        side = [_wobbly(rng, x + rng.uniform(-4, 4), 0, x + rng.uniform(-4, 4), height,
                        rng.uniform(1, 3)) for _ in range(4)]
        roads.append(_best_road(side, grid, terr, width, height))
    return roads


def _gate_roads(rng, data, width, height):
    """Routes de l'arrière de l'assaillant jusqu'aux portes (et, dans la
    Citadelle, des portes extérieures à celle du donjon)."""
    rings = data.get('rings')
    if rings:
        wall_x, gates = rings[0]['wall_x'], [tuple(g) for g in rings[0]['gates']]
    else:
        wall_x = data.get('wall_x')
        gates = [tuple(g) for g in data.get('gates', {})]
    if wall_x is None or not gates:
        return []
    # Cases de porte voisines (une porte de trois cases) → une route
    groups = []
    for y in sorted({g[1] for g in gates}):
        if groups and y - groups[-1][-1] <= 1:
            groups[-1].append(y)
        else:
            groups.append([y])
    roads = []
    for grp in groups:
        gy = sum(grp) / len(grp) + 0.5
        y0 = min(height - 3.0, max(2.0, gy + rng.uniform(-height * 0.2, height * 0.2)))
        roads.append(_wobbly(rng, 0, y0, wall_x - 0.5, gy, rng.uniform(1.5, 4.0)))
    if rings and len(rings) > 1:
        keep_x = rings[1]['wall_x']
        kg = [tuple(g) for g in rings[1]['gates']]
        ky = sum(g[1] for g in kg) / len(kg) + 0.5
        for grp in groups:
            gy = sum(grp) / len(grp) + 0.5
            roads.append(_wobbly(rng, wall_x + 4.5, gy, keep_x - 0.5, ky, 1.0))
    return roads


def _pass_track(grid, terr, width, height):
    """Piste du Défilé: le milieu du passage, colonne par colonne, lissé."""
    mids = []
    for x in range(0, width, 2):
        free = [y for y in range(height) if grid[x][y] == 0]
        if free:
            mids.append((x + 0.5, (min(free) + max(free)) / 2 + 0.5))
    if len(mids) < 3:
        return []
    smooth = []
    for i in range(len(mids)):
        ys = [mids[j][1] for j in range(max(0, i - 3), min(len(mids), i + 4))]
        smooth.append((mids[i][0], sum(ys) / len(ys)))
    return [smooth]


def generate_paths(map_name, grid, width, height, data, hint, rng):
    """Chemins de terre (visuels): polylignes en coordonnées de cases.

    `hint`: tracés fournis par le générateur (rues du Village, sentiers de
    la Forêt), repris tels quels."""
    terr = data.get('terrain')
    paths = [list(p) for p in (hint or [])]
    if map_name in SIEGE_MAPS:
        paths += _gate_roads(rng, data, width, height)
    elif map_name == "Défilé":
        paths += _pass_track(grid, terr, width, height)
    elif map_name in ("Prairie", "Désert"):
        paths += _open_road(rng, grid, terr, width, height)
    return paths


# ═══════════════════════════════════════════════════════════════
#   CHAMPS CULTIVÉS
# ═══════════════════════════════════════════════════════════════

CROPS = ("blé", "labour", "pré")


def generate_fields(map_name, grid, width, height, data, style, rng):
    """Parcelles cultivées (visuelles) autour des fermes: [(cx, cy, w, h,
    angle, culture)] en cases. Seulement là où l'on cultive: autour du
    Village, et dans la Prairie de bocage, de buttes ou de vallons."""
    terr = data.get('terrain')
    if map_name == "Village":
        n = rng.randint(4, 8)
    elif map_name == "Prairie" and style in ("bocage", "buttes", "vallons"):
        n = rng.randint(2, 5)
    else:
        return []
    cy = height / 2
    fields = []
    for _ in range(n * 8):
        if len(fields) >= n:
            break
        w = rng.uniform(4, 9)
        h = rng.uniform(3, 6)
        # Sur les flancs, loin du couloir central
        fx = rng.uniform(3, width - 3)
        if cy - 6 > 2 + h / 2 and rng.random() < 0.5:
            fy = rng.uniform(2 + h / 2, cy - 6)
        else:
            fy = rng.uniform(cy + 6, max(cy + 6.1, height - 2 - h / 2))
        ang = rng.uniform(-0.35, 0.35)
        ok = True
        for dx in (-0.45, 0, 0.45):
            for dy in (-0.45, 0, 0.45):
                x, y = int(fx + dx * w), int(fy + dy * h)
                if not (0 <= x < width and 0 <= y < height) or grid[x][y] != 0:
                    ok = False
                elif terr is not None and terr[x][y] not in (tr.PLAIN, tr.HILL):
                    ok = False
        if ok and all(math.hypot(fx - f[0], fy - f[1]) > (w + f[2]) / 2 + 1 for f in fields):
            fields.append((fx, fy, w, h, ang, rng.choice(CROPS)))
    return fields


# ═══════════════════════════════════════════════════════════════
#   CAMP DE L'ASSIÉGEANT
# ═══════════════════════════════════════════════════════════════

def siege_camp(grid, width, height, rng):
    """Camp de l'assaillant, loin derrière ses lignes: rangées de tentes,
    feux, oriflammes, bois et vivres. Objets de décor [(x, y, nature, graine)]."""
    x_hi = max(4, deploy_front(width, siege=True) - 20)
    props = []
    used = set()

    def put(x, y, kind):
        if 1 <= x < width - 1 and 1 <= y < height - 1 and grid[x][y] == 0 and (x, y) not in used:
            used.add((x, y))
            props.append((x, y, kind, rng.randrange(1 << 16)))

    for gx in range(2, x_hi, 4):
        for gy in range(3, height - 3, 5):
            if rng.random() < 0.55:
                put(gx + rng.randint(0, 1), gy + rng.randint(-1, 1), "tente")
                if rng.random() < 0.5:
                    put(gx + 2, gy + rng.randint(-1, 1),
                        rng.choice(("feu_camp", "bois_pile", "sacs", "caisse", "tonneau", "banniere")))
    return props
