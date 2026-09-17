"""Couches procédurales des cartes: rivières, collines, bois, rochers.

Primitives de peinture sur `grid` (bâti) et `terr` (terrain à effets),
sans politique de carte: c'est `maps.py` qui décide où et quand les poser.

Toutes les couches tirent leurs dés dans le flux `random` global (comme les
générateurs historiques): une graine rejoue la même carte. Une couche qui
n'a rien à faire ne tire AUCUN dé, pour que les cartes par défaut restent
identiques à la case près.

Symétrie: une carte de bataille rangée doit rester équitable. Les couches
`symmetric=True` peignent la moitié ouest puis la recopient à l'est
(x → width-1-x), comme `maps._mirror_terrain`.
"""

import math
import random

import terrain as tr

WET = (tr.RIVER, tr.FORD, tr.BRIDGE)


def _in(width, height, x, y):
    return 0 <= x < width and 0 <= y < height


def smooth_walk(n, lo, hi, step_p=0.35, start=None):
    """Marche aléatoire bornée de longueur n (entiers dans [lo, hi]): un
    tracé qui ondule sans zigzaguer à chaque case."""
    v = random.randint(lo, hi) if start is None else start
    out = []
    for _ in range(n):
        if random.random() < step_p:
            v = max(lo, min(hi, v + random.choice((-1, 1))))
        out.append(v)
    return out


def pick_rows(height, n, margin=3, forced=()):
    """Rangées de franchissement: celles imposées (`forced`: grand-rue,
    portes) plus n rangées réparties, une par tranche de hauteur."""
    rows = list(forced)
    lo, hi = margin, height - 1 - margin
    if hi <= lo:
        return rows or [height // 2]
    span = (hi - lo) / max(1, n)
    for i in range(n):
        a = int(lo + i * span)
        b = max(a, int(lo + (i + 1) * span) - 1)
        y = random.randint(a, b)
        if all(abs(y - r) > 4 for r in rows):
            rows.append(y)
    return sorted(rows)


# ───────────────────────────── Rivières ─────────────────────────────

def river_spans_symmetric(width, height, amp):
    """Rivière nord-sud au centre, à berges irrégulières mais symétriques:
    {y: (x_min, x_max)}. La largeur ondule de 2 à 2 + 2·amp cases."""
    mx = (width - 1) / 2
    base = 0.5 if width % 2 == 0 else 1.0
    offs = smooth_walk(height, 0, amp)
    return {y: (int(math.ceil(mx - base - offs[y])), int(math.floor(mx + base + offs[y])))
            for y in range(height)}


def river_spans_meander(height, x_center, x_lo, x_hi, width_cells=2):
    """Rivière nord-sud qui serpente autour de x_center, bornée à [x_lo, x_hi].
    Pour les cartes asymétriques (siège): aucun miroir à respecter."""
    lo = min(0, x_lo - x_center)
    hi = max(0, x_hi - width_cells + 1 - x_center)
    offs = smooth_walk(height, lo, hi, step_p=0.3, start=0)
    return {y: (x_center + offs[y], x_center + offs[y] + width_cells - 1) for y in range(height)}


def paint_river(grid, terr, width, height, spans, crossings, bridge_rows=(),
                clear_approach=2):
    """Peint une rivière décrite par `spans` {y: (x0, x1)}.

    Chaque rangée de `crossings` devient un franchissement sur 3 rangées:
    un pont si elle figure dans `bridge_rows`, un gué sinon. Le lit et les
    abords des franchissements sont dégagés de tout obstacle.
    Retourne (cases du lit, cases d'abord)."""
    cells = set()
    for y in range(1, height - 1):
        x0, x1 = spans[y]
        for x in range(max(0, x0), min(width - 1, x1) + 1):
            grid[x][y] = 0
            terr[x][y] = tr.RIVER
            cells.add((x, y))

    approach = set()
    for cy in crossings:
        kind = tr.BRIDGE if cy in bridge_rows else tr.FORD
        for y in (cy - 1, cy, cy + 1):
            if not 0 < y < height - 1:
                continue
            x0, x1 = spans[y]
            for x in range(max(0, x0), min(width - 1, x1) + 1):
                terr[x][y] = kind
            for x in list(range(x0 - clear_approach, x0)) + list(range(x1 + 1, x1 + 1 + clear_approach)):
                if _in(width, height, x, y):
                    grid[x][y] = 0
                    if terr[x][y] in (tr.MARSH, tr.WOOD):
                        terr[x][y] = tr.PLAIN
                    approach.add((x, y))
    return cells, approach


def paint_banks(grid, terr, width, height, spans, name, p, skip=(), symmetric=False):
    """Berges: `name` (bois de ripisylve, palmeraie, roselière) posé au hasard
    sur la case qui borde le lit. `skip`: abords de franchissement."""
    skip = set(skip)
    for y in range(1, height - 1):
        x0, x1 = spans[y]
        sides = (x0 - 1,) if symmetric else (x0 - 1, x1 + 1)
        for x in sides:
            if (_in(width, height, x, y) and (x, y) not in skip and grid[x][y] == 0
                    and terr[x][y] == tr.PLAIN and random.random() < p):
                terr[x][y] = name
                if symmetric:
                    xm = width - 1 - x
                    if grid[xm][y] == 0 and terr[xm][y] == tr.PLAIN:
                        terr[xm][y] = name


# ───────────────────────────── Taches ─────────────────────────────

def paint_blob(terr, grid, width, height, cx, cy, rx, ry, angle, name,
               allowed=(tr.PLAIN,), x_range=None, rough=0.18):
    """Ellipse irrégulière orientée (dune, butte, bosquet). Ne peint que sur
    les terrains `allowed` et les cases libres, bornée à x_range=(lo, hi).
    Retourne les cases peintes."""
    ca, sa = math.cos(angle), math.sin(angle)
    ph = (random.uniform(0, math.tau), random.uniform(0, math.tau))
    R = int(math.ceil(max(rx, ry) * (1 + rough))) + 1
    painted = []
    for x in range(int(cx) - R, int(cx) + R + 2):
        if x_range and not (x_range[0] <= x <= x_range[1]):
            continue
        for y in range(int(cy) - R, int(cy) + R + 2):
            if not (0 <= x < width and 1 <= y < height - 1):
                continue
            dx, dy = x - cx, y - cy
            u = (dx * ca + dy * sa) / max(0.5, rx)
            v = (-dx * sa + dy * ca) / max(0.5, ry)
            th = math.atan2(v, u)
            edge = 1.0 + rough * (math.sin(3 * th + ph[0]) + 0.6 * math.sin(5 * th + ph[1])) / 1.6
            if u * u + v * v <= edge * edge and grid[x][y] == 0 and terr[x][y] in allowed:
                terr[x][y] = name
                painted.append((x, y))
    return painted


def scatter_blobs(terr, grid, width, height, n, x_range, y_range, size, name,
                  elongated=False, allowed=(tr.PLAIN,), avoid_rows=(), symmetric=False):
    """Sème n taches de terrain dans la zone x_range × y_range; size=(r_min,
    r_max). elongated: dunes étirées nord-sud. avoid_rows: rangées que le
    centre d'une tache évite (grand-rue, portes). symmetric: tirées dans la
    moitié ouest puis recopiées à l'est."""
    x_lo, x_hi = x_range
    if symmetric:
        x_hi = min(x_hi, width // 2 - 1)
    if x_hi < x_lo or y_range[1] < y_range[0]:
        return []
    painted = []
    for _ in range(n):
        for _try in range(12):
            cx = random.uniform(x_lo, x_hi)
            cy = random.uniform(*y_range)
            if all(abs(cy - r) > size[1] + 1 for r in avoid_rows):
                break
        else:
            continue
        r = random.uniform(*size)
        if elongated:
            rx, ry = r * 0.6, r * random.uniform(1.8, 2.6)
            ang = random.uniform(-0.6, 0.6)
        else:
            rx, ry = r, r * random.uniform(0.7, 1.0)
            ang = random.uniform(0, math.pi)
        painted += paint_blob(terr, grid, width, height, cx, cy, rx, ry, ang, name,
                              allowed=allowed, x_range=(x_lo, x_hi))
    if symmetric:
        for (x, y) in painted:
            xm = width - 1 - x
            if grid[xm][y] == 0 and terr[xm][y] in allowed:
                terr[xm][y] = name
            elif grid[xm][y] == 0 and terr[xm][y] != name:
                terr[x][y] = terr[xm][y]      # l'est refuse: l'ouest s'aligne
    return painted


def scatter_rocks(grid, width, height, n, x_range, y_range, cluster=(2, 4),
                  keep=(), symmetric=False, terr=None):
    """Affleurements rocheux (obstacles `1`) en petits amas. `keep`: cases à
    ne jamais obstruer. Pas sur l'eau ni les marais si `terr` est donné."""
    keep = set(keep)
    x_lo, x_hi = x_range
    if symmetric:
        x_hi = min(x_hi, width // 2 - 1)
    if x_hi < x_lo:
        return
    for _ in range(n):
        cx = random.randint(x_lo, x_hi)
        cy = random.randint(*y_range)
        for _k in range(random.randint(*cluster)):
            x = cx + random.randint(-1, 1)
            y = cy + random.randint(-1, 1)
            if not (x_lo <= x <= x_hi and 1 < y < height - 2) or (x, y) in keep:
                continue
            if terr is not None and terr[x][y] in WET + (tr.MARSH,):
                continue
            grid[x][y] = 1
            if symmetric:
                grid[width - 1 - x][y] = 1


def strip(terr, width, height, names, to=tr.PLAIN):
    """Retire un type de terrain (carte « sans colline », « sans rivière »)."""
    names = set(names)
    for x in range(width):
        col = terr[x]
        for y in range(height):
            if col[y] in names:
                col[y] = to


def has(terr, name):
    return any(name in col for col in terr)
