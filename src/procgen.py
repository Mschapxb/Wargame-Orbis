"""Couches procédurales des cartes: rivières, collines, bois, rochers.

Primitives de peinture sur `grid` (bâti) et `terr` (terrain à effets),
sans politique de carte: c'est `maps.py` qui décide où et quand les poser.

Toutes les couches tirent leurs dés via `rng_scope.RNG` (random global, ou
générateur de la graine de carte): une graine rejoue la même carte. Une couche qui
n'a rien à faire ne tire AUCUN dé, pour que les cartes par défaut restent
identiques à la case près.

Symétrie: une carte de bataille rangée doit rester équitable. Les couches
`symmetric=True` peignent la moitié ouest puis la recopient à l'est
(x → width-1-x), comme `maps._mirror_terrain`.
"""

import math
from rng_scope import RNG

import terrain as tr

WET = (tr.RIVER, tr.FORD, tr.BRIDGE)


def _in(width, height, x, y):
    return 0 <= x < width and 0 <= y < height


def smooth_walk(n, lo, hi, step_p=0.35, start=None):
    """Marche aléatoire bornée de longueur n (entiers dans [lo, hi]): un
    tracé qui ondule sans zigzaguer à chaque case."""
    v = RNG.randint(lo, hi) if start is None else start
    out = []
    for _ in range(n):
        if RNG.random() < step_p:
            v = max(lo, min(hi, v + RNG.choice((-1, 1))))
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
        y = RNG.randint(a, b)
        if all(abs(y - r) > 4 for r in rows):
            rows.append(y)
    return sorted(rows)


# ───────────────────────────── Bruit ─────────────────────────────

def smooth_noise(n, amp, waves=((0.9, 1.0), (0.4, 0.55), (0.17, 0.3))):
    """Bruit 1D lisse de longueur n, dans [-amp, amp]: somme de sinus de
    longueurs d'onde (en fraction de n) et de phases tirées au hasard. Donne
    des courbes douces — une marche aléatoire case à case fait des dents."""
    comps = [(max(2.0, n * wl * RNG.uniform(0.8, 1.25)), w, RNG.uniform(0, math.tau))
             for wl, w in waves]
    total = sum(w for _, w, _ in comps)
    return [amp * sum(w * math.sin(math.tau * i / L + ph) for L, w, ph in comps) / total
            for i in range(n)]


def segments(cells_x):
    """Abscisses → segments contigus [(x0, x1), ...]."""
    out = []
    for x in sorted(set(cells_x)):
        if out and x == out[-1][1] + 1:
            out[-1] = (out[-1][0], x)
        else:
            out.append((x, x))
    return out


def _segs(v):
    return [v] if isinstance(v, tuple) else list(v)


def span_bounds(v):
    segs = _segs(v)
    return min(a for a, _ in segs), max(b for _, b in segs)


# ───────────────────────────── Rivières ─────────────────────────────

def river_spans_symmetric(width, height, amp):
    """Rivière nord-sud au centre, en miroir (équitable), au tracé naturel:
    deux bras qui s'écartent et se rejoignent en enserrant des îlots, largeur
    qui respire doucement. {y: [(x0, x1), ...]} (un ou deux segments)."""
    mx = (width - 1) / 2.0
    spread = smooth_noise(height, 1.0)
    breathe = smooth_noise(height, 1.0, waves=((0.6, 1.0), (0.23, 0.6)))
    out = {}
    for y in range(height):
        # Écart du bras au centre: souvent 0 (lit unique), parfois un îlot
        # Un îlot seulement aux crêtes du bruit: rare et court. Ailleurs un
        # lit unique dont la largeur respire.
        o = max(0.0, spread[y] - 0.45) * (amp + 3.0)
        hw = 0.7 + 0.5 * (breathe[y] + 1.0) * (0.6 + 0.25 * amp) + (0.4 if o > 0 else 0.0)
        c = mx - o
        west = [x for x in range(int(math.floor(c - hw)), int(math.ceil(c + hw)) + 1)
                if abs(x - c) <= hw and x <= mx]
        xs = set(west) | {width - 1 - x for x in west}
        if not xs:
            xs = {int(math.floor(mx)), int(math.ceil(mx))}
        out[y] = segments(xs)
    return out


def river_spans_meander(height, x_center, x_lo, x_hi, width_cells=2):
    """Rivière nord-sud qui SERPENTE en courbes douces autour de x_center,
    bornée à [x_lo, x_hi]. Pour les cartes asymétriques (siège)."""
    half = max(0.0, min(x_center - x_lo, x_hi - width_cells + 1 - x_center))
    offs = smooth_noise(height, half)
    breathe = smooth_noise(height, 0.6)
    out = {}
    for y in range(height):
        x0 = int(round(x_center + offs[y]))
        wc = max(2, int(round(width_cells + breathe[y])))
        x0 = max(x_lo, min(x_hi - wc + 1, x0))
        out[y] = [(x0, x0 + wc - 1)]
    return out


def paint_river(grid, terr, width, height, spans, crossings, bridge_rows=(),
                clear_approach=2):
    """Peint une rivière décrite par `spans` {y: segment ou [segments]}.

    Chaque rangée de `crossings` devient un franchissement sur 3 rangées:
    un pont si elle figure dans `bridge_rows`, un gué sinon — d'une berge à
    l'autre, îlot compris. Le lit et les abords des franchissements sont
    dégagés de tout obstacle. Retourne (cases du lit, cases d'abord)."""
    cells = set()
    for y in range(1, height - 1):
        for x0, x1 in _segs(spans[y]):
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
            x0, x1 = span_bounds(spans[y])
            for x in range(max(0, x0), min(width - 1, x1) + 1):
                grid[x][y] = 0
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
    sur les cases qui bordent le lit. `skip`: abords de franchissement."""
    skip = set(skip)
    half = (width - 1) / 2.0
    for y in range(1, height - 1):
        for x0, x1 in _segs(spans[y]):
            for x in (x0 - 1, x1 + 1):
                if symmetric and x > half:
                    continue
                if (_in(width, height, x, y) and (x, y) not in skip and grid[x][y] == 0
                        and terr[x][y] == tr.PLAIN and RNG.random() < p):
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
    ph = (RNG.uniform(0, math.tau), RNG.uniform(0, math.tau))
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
            cx = RNG.uniform(x_lo, x_hi)
            cy = RNG.uniform(*y_range)
            if all(abs(cy - r) > size[1] + 1 for r in avoid_rows):
                break
        else:
            continue
        r = RNG.uniform(*size)
        if elongated:
            rx, ry = r * 0.6, r * RNG.uniform(1.8, 2.6)
            ang = RNG.uniform(-0.6, 0.6)
        else:
            rx, ry = r, r * RNG.uniform(0.7, 1.0)
            ang = RNG.uniform(0, math.pi)
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
        cx = RNG.randint(x_lo, x_hi)
        cy = RNG.randint(*y_range)
        for _k in range(RNG.randint(*cluster)):
            x = cx + RNG.randint(-1, 1)
            y = cy + RNG.randint(-1, 1)
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
