"""Cartes de rase campagne: Prairie, Forêt, Désert.

Chaque carte tire un STYLE parmi plusieurs (cf. PRAIRIE_STYLES,
DESERT_STYLES, FOREST_STYLES): mêmes règles, paysage différent d'une
partie à l'autre. Le style tiré voyage dans les données de la carte
(clé privée `_style`, rangée dans le thème par maps.generate_map).
"""

import math

from rng_scope import RNG
import procgen
import terrain as tr

from . import features
from .common import _carve, _connected, _mirror_grid, _mirror_terrain, deploy_front

PRAIRIE_STYLES = ("buttes", "vallons", "étangs", "bocage", "rocailles")
DESERT_STYLES = ("oasis", "oasis jumelles", "mesas", "erg", "reg")
FOREST_STYLES = ("futaie", "massifs", "clairières")


# ═══════════════════════════════════════════════════════════════
#                      GÉNÉRATEURS
# ═══════════════════════════════════════════════════════════════

def generate_prairie(width, height):
    """Prairie: une campagne ouverte, sans règle ni équerre, au caractère
    tiré au sort:

      • buttes     — buttes éparses au nord et au sud, parfois rocheuses
      • vallons    — relief ondulé en nappes (bruit), plus étendu mais doux
      • étangs     — une ou deux mares cernées de roseaux sur les flancs
      • bocage     — bosquets nombreux et étendus sur les flancs
      • rocailles  — crêtes rocheuses et amas de rochers

    Toujours: une butte irrégulière au centre (objectif du couloir
    principal), un couloir central ouvert, rien devant les lignes de
    déploiement que du relief doux. La moitié ouest est tirée au hasard puis
    recopiée à l'est (équitable).
    """
    grid = [[0] * height for _ in range(width)]
    terr = tr.make_grid(width, height)
    half = width // 2
    mx, cy = (width - 1) / 2, (height - 1) / 2
    lo = deploy_front(width) + 3
    small = height < 40
    west = (1, half - 1)
    style = RNG.choice(PRAIRIE_STYLES)
    k_hills = {"buttes": 1.0, "vallons": 0.0, "étangs": 0.6, "bocage": 0.7, "rocailles": 0.7}[style]
    k_woods = {"buttes": 1.0, "vallons": 0.8, "étangs": 0.8, "bocage": 2.2, "rocailles": 0.5}[style]

    # ── Collines: buttes éparses au nord et au sud, de tailles et
    # d'orientations variées — le centre reste un couloir ouvert ──
    hill_x0 = max(2, int(width * 0.16))
    n_hills = int(round((3 + (width * height) // 3000) * k_hills))
    for k in range(n_hills):
        side = -1 if k % 2 == 0 else 1
        hy = cy + side * height * RNG.uniform(0.14, 0.38)
        hx = RNG.uniform(hill_x0, half - 2)
        r = RNG.uniform(1.3, 2.2 if small else 3.6)
        stretch = RNG.uniform(1.0, 2.2)
        procgen.paint_blob(terr, grid, width, height, hx, hy, r * stretch, r,
                           RNG.uniform(-1.0, 1.0), tr.HILL, x_range=west, rough=0.3)
        # Quelques rochers sur les plus grandes, hors des lignes de départ
        if r > 1.8 and hx >= lo and RNG.random() < 0.6:
            for _ in range(RNG.randint(1, 3)):
                rx = int(round(hx + RNG.uniform(-r, r)))
                ry = int(round(hy + RNG.uniform(-r * 0.6, r * 0.6)))
                if lo <= rx < half and 1 < ry < height - 2 and terr[rx][ry] == tr.HILL:
                    grid[rx][ry] = 1

    # ── Vallons: nappes de relief doux tirées d'un bruit, hors du couloir ──
    if style == "vallons":
        noise = features.value_noise(half, height, cell=RNG.uniform(5.0, 8.0))
        thr = RNG.uniform(0.65, 0.71)
        corridor = max(2, int(height * 0.12))
        for x in range(hill_x0, half):
            for y in range(2, height - 2):
                if abs(y - cy) < corridor and x > half - width * 0.14:
                    continue
                if noise[x][y] > thr:
                    terr[x][y] = tr.HILL

    # ── Butte centrale ──
    r = max(2.2, min(width, height) * 0.055)
    procgen.paint_blob(terr, grid, width, height, mx, cy + RNG.uniform(-1.5, 1.5),
                       r * RNG.uniform(1.0, 1.35), r, RNG.uniform(0, math.pi),
                       tr.HILL, x_range=west, rough=0.3)

    # ── Étangs sur les flancs ──
    if style == "étangs":
        side = RNG.choice((-1, 1))
        for _k in range(1 if small else RNG.randint(1, 2)):
            py = cy + side * height * RNG.uniform(0.25, 0.38)
            px = RNG.uniform(lo + 3, half - 5)
            pr = RNG.uniform(1.1, 1.8) if small else RNG.uniform(1.6, 3.0)
            cells = features.pond(terr, grid, width, height, px, py, pr, (lo, half - 2))
            if not features.crossing_ok(grid, terr, width, height):
                features.undo(terr, grid, cells)
            side = -side

    # ── Bosquets et broussailles, sur les flancs ──
    # Le couloir central reste ouvert: une Prairie boisée entre les armées
    # se jouerait comme une forêt (l'IA y renonce aux manœuvres et aux rangs).
    n_woods = int(round((2 + (width * height) // 2600) * k_woods))
    grow = 1.25 if style == "bocage" else 1.0
    for k in range(n_woods):
        r = RNG.uniform(1.0, 1.8 if small else 2.6) * grow
        x_min = lo + r * 1.4 + 1
        if x_min > half - 2:
            break
        wx = RNG.uniform(x_min, half - 2)
        side = -1 if k % 2 == 0 else 1
        wy = cy + side * RNG.uniform(height * 0.3, height * 0.44)
        procgen.paint_blob(terr, grid, width, height, wx, wy, r * RNG.uniform(1.0, 1.6), r,
                           RNG.uniform(0, math.pi), tr.WOOD, x_range=west, rough=0.35)

    # ── Rocailles: crêtes rocheuses et amas ──
    if style == "rocailles":
        for k in range(1 if small else RNG.randint(1, 2)):
            side = -1 if k % 2 == 0 else 1
            y0 = cy + side * height * RNG.uniform(0.18, 0.34)
            x0 = RNG.uniform(lo + 2, max(lo + 2, half - 8))
            features.rock_ridge(terr, grid, width, height, x0, y0,
                                RNG.uniform(4, 7 if small else 11), RNG.uniform(-0.5, 0.5),
                                (lo, half - 2))
        procgen.scatter_rocks(grid, width, height, RNG.randint(2, 4), (lo, half - 3),
                              (2, height - 3), cluster=(2, 4), terr=terr)

    # ── Rochers isolés près du centre (abris pour tireurs) ──
    for _ in range(RNG.randint(2, 4)):
        rx = RNG.randint(max(lo, half - max(3, width // 6)), max(lo, half - 2))
        ry = int(round(cy + RNG.randint(-4, 4)))
        if 1 < ry < height - 2 and grid[rx][ry] == 0 and terr[rx][ry] != tr.LAKE:
            grid[rx][ry] = 1

    _mirror_grid(grid, width, height)
    _mirror_terrain(terr, width, height)
    return grid, {'terrain': terr, '_style': style}


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

    Style tiré au sort: futaie (la carte historique), massifs (plus étroit,
    bosquets plus gros et plus serrés), clairières (plus large et aéré).
    """
    grid = [[0] * height for _ in range(width)]
    cx, cy = width // 2, height // 2
    style = RNG.choice(FOREST_STYLES)
    k_rx, k_ry, density, n_clear, grove_max = {
        "futaie": (0.10, 0.40, 11.0, (3, 5), 2.6),
        "massifs": (0.085, 0.43, 9.0, (2, 4), 3.0),
        "clairières": (0.12, 0.38, 14.0, (5, 7), 2.6),
    }[style]
    rx = max(5, int(width * k_rx))
    ry = max(4, int(height * k_ry))

    phases = [RNG.uniform(0, math.tau) for _ in range(3)]
    amps, freqs = (0.10, 0.07, 0.05), (3, 5, 8)

    def edge(theta):
        return 1.0 + sum(a * math.sin(f * theta + p) for a, f, p in zip(amps, freqs, phases))

    def inside(x, y, scale=1.0):
        dx, dy = (x - cx) / rx, (y - cy) / ry
        return math.hypot(dx, dy) < edge(math.atan2(dy, dx)) * scale

    # ── Bosquets ──
    area = math.pi * rx * ry
    for _ in range(int(area / density)):
        for _try in range(20):
            gx = RNG.randint(cx - rx, cx + rx)
            gy = RNG.randint(cy - ry, cy + ry)
            if inside(gx, gy, 0.95):
                break
        else:
            continue
        gr = RNG.uniform(1.0, grove_max)
        ri = int(math.ceil(gr))
        for dx in range(-ri, ri + 1):
            for dy in range(-ri, ri + 1):
                nx, ny = gx + dx, gy + dy
                if not (0 <= nx < width and 1 <= ny < height - 1):
                    continue
                if dx * dx + dy * dy <= gr * gr and RNG.random() < 0.85 and inside(nx, ny, 1.02):
                    grid[nx][ny] = 1

    # ── Lisière: arbres isolés autour du massif ──
    for x in range(max(0, cx - int(rx * 1.6)), min(width, cx + int(rx * 1.6) + 1)):
        for y in range(1, height - 1):
            if grid[x][y] == 0 and inside(x, y, 1.4) and not inside(x, y, 1.0):
                if RNG.random() < 0.07:
                    grid[x][y] = 1

    # ── Clairières ──
    for _ in range(RNG.randint(*n_clear)):
        for _try in range(20):
            kx = RNG.randint(cx - rx // 2, cx + rx // 2)
            ky = RNG.randint(cy - int(ry * 0.7), cy + int(ry * 0.7))
            if inside(kx, ky, 0.7):
                _carve(grid, kx, ky, RNG.uniform(1.8, 3.2), width, height)
                break

    # ── Sentiers ouest → est ──
    n_trails = 3 if height < 40 else 4
    x_start = max(0, cx - int(rx * 1.6))
    x_end = min(width - 1, cx + int(rx * 1.6))
    trail_ys = []
    trails = []
    for i in range(n_trails):
        y0 = int(cy + (i - (n_trails - 1) / 2) * (ry * 1.5 / max(1, n_trails - 1)))
        y = y0
        half = 1.2 if abs(y0 - cy) <= 2 else 0.8
        line = []
        for x in range(x_start, x_end + 1):
            if RNG.random() < 0.35:
                y += RNG.choice((-1, 1))
                y = max(y0 - 3, min(y0 + 3, y))
            yy = max(1, min(height - 2, y))
            _carve(grid, x, yy, half, width, height)
            if x < cx:
                line.append((x + 0.5, yy + 0.5))
            if x == cx - 1:
                trail_ys.append(yy)
        trails.append(line)

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
                    and RNG.random() < 0.25):
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

    # Sentiers (visuels): la moitié ouest tracée, l'est en miroir
    paths = [line + [(width - px, py) for (px, py) in reversed(line)]
             for line in trails if len(line) >= 2]
    return grid, {'deploy_gap': deploy_gap, 'terrain': terr, '_style': style, '_paths': paths}


def _oasis(grid, terr, width, height, ox, oy, pond_r, palm_p=0.55):
    """Oasis centrée sur l'axe de symétrie: eau libre au cœur (si la mare
    est assez grande), mare boueuse, palmeraie en couronne (tirée à l'ouest,
    recopiée ensuite)."""
    for x in range(width):
        for y in range(height):
            d = math.hypot(x - ox, y - oy)
            if d <= pond_r + 3.2:
                grid[x][y] = 0
            if d <= pond_r:
                terr[x][y] = tr.MARSH
            if pond_r >= 1.6 and d <= pond_r * 0.45:
                terr[x][y] = tr.LAKE
    for x in range(width // 2):
        for y in range(1, height - 1):
            d = math.hypot(x - ox, y - oy)
            if pond_r < d <= pond_r + 2.2 and RNG.random() < palm_p:
                terr[x][y] = tr.WOOD


def generate_desert(width, height):
    """Désert: un reg ouvert où l'eau et l'ombre sont les objectifs.

    Style tiré au sort:
      • oasis           — mare et palmeraie au centre
      • oasis jumelles  — deux oasis au nord et au sud, centre découvert
      • mesas           — plateaux rocheux aux flancs d'éboulis
      • erg             — mer de dunes, peu de rochers
      • reg             — plaine de cailloux semée d'affleurements

    Toujours: affleurements rocheux en amas (couverts destructibles), dunes
    en longues crêtes nord-sud, aucun obstacle ni relief devant les lignes
    de déploiement.
    """
    grid = [[0] * height for _ in range(width)]
    terr = tr.make_grid(width, height)
    lo = deploy_front(width) + 3
    mx, cy = (width - 1) / 2, (height - 1) / 2
    style = RNG.choice(DESERT_STYLES)
    k_rocks = {"oasis": 1.0, "oasis jumelles": 1.0, "mesas": 0.5, "erg": 0.4, "reg": 1.7}[style]
    k_dunes = {"oasis": 1.0, "oasis jumelles": 1.0, "mesas": 0.7, "erg": 2.2, "reg": 0.5}[style]
    west = (lo, width // 2 - 3)

    # ── Affleurements rocheux (ouest tiré, est recopié) ──
    n_rocks = max(2, int(round(max(3, (width * height) // 420) * k_rocks)))
    procgen.scatter_rocks(grid, width, height, n_rocks, west,
                          (2, height - 3), cluster=(2, 5), symmetric=True)

    # ── Mesas: plateaux de roche sur les flancs ──
    if style == "mesas":
        for k in range(1 if height < 40 else RNG.randint(2, 3)):
            side = -1 if k % 2 == 0 else 1
            my_ = cy + side * height * RNG.uniform(0.2, 0.36)
            mx_ = RNG.uniform(lo + 4, max(lo + 4, width // 2 - 6))
            cells = features.mesa(terr, grid, width, height, mx_, my_,
                                  RNG.uniform(1.2, 1.8 if height < 40 else 2.6), west)
            _mirror_grid(grid, width, height)
            if not features.crossing_ok(grid, terr, width, height):
                features.undo(terr, grid, cells + [(width - 1 - x, y) for (x, y) in cells])

    # ── Oasis: mare boueuse, eau libre et palmeraie ──
    pond_r = max(1.2, min(height, width) * 0.05)
    if style == "oasis jumelles":
        for side in (-1, 1):
            _oasis(grid, terr, width, height, mx, cy + side * height * RNG.uniform(0.24, 0.32),
                   pond_r * RNG.uniform(0.9, 1.2))
    else:
        _oasis(grid, terr, width, height, mx, cy, pond_r * (0.8 if style == "reg" else 1.0))
    _mirror_terrain(terr, width, height)

    # ── Dunes ──
    n_dunes = max(2, int(round(max(2, (width * height) // 900) * k_dunes)))
    size = (1.4, max(2.0, height * 0.07) * (1.25 if style == "erg" else 1.0))
    procgen.scatter_blobs(terr, grid, width, height, n_dunes, (lo, width // 2 - 2),
                          (2, height - 3), size, tr.HILL, elongated=True, symmetric=True)
    _mirror_grid(grid, width, height)
    return grid, {'terrain': terr, '_style': style}
