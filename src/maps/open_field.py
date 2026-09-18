"""Cartes de rase campagne: Prairie, Forêt, Désert."""

import math

from rng_scope import RNG
import procgen
import terrain as tr

from .common import _carve, _connected, _mirror_grid, _mirror_terrain, deploy_front


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

    # ── Butte centrale ──
    r = max(2.2, min(width, height) * 0.055)
    procgen.paint_blob(terr, grid, width, height, mx, cy + RNG.uniform(-1.5, 1.5),
                       r * RNG.uniform(1.0, 1.35), r, RNG.uniform(0, math.pi),
                       tr.HILL, x_range=west, rough=0.3)

    # ── Bosquets et broussailles, sur les flancs ──
    # Le couloir central reste ouvert: une Prairie boisée entre les armées
    # se jouerait comme une forêt (l'IA y renonce aux manœuvres et aux rangs).
    n_woods = 2 + (width * height) // 2600
    for k in range(n_woods):
        r = RNG.uniform(1.0, 1.8 if small else 2.6)
        x_min = lo + r * 1.4 + 1
        if x_min > half - 2:
            break
        wx = RNG.uniform(x_min, half - 2)
        side = -1 if k % 2 == 0 else 1
        wy = cy + side * RNG.uniform(height * 0.3, height * 0.44)
        procgen.paint_blob(terr, grid, width, height, wx, wy, r * RNG.uniform(1.0, 1.6), r,
                           RNG.uniform(0, math.pi), tr.WOOD, x_range=west, rough=0.35)

    # ── Rochers isolés près du centre (abris pour tireurs) ──
    for _ in range(RNG.randint(2, 4)):
        rx = RNG.randint(max(lo, half - max(3, width // 6)), max(lo, half - 2))
        ry = int(round(cy + RNG.randint(-4, 4)))
        if 1 < ry < height - 2 and grid[rx][ry] == 0:
            grid[rx][ry] = 1

    _mirror_grid(grid, width, height)
    _mirror_terrain(terr, width, height)
    return grid, {'terrain': terr}


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

    phases = [RNG.uniform(0, math.tau) for _ in range(3)]
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
            gx = RNG.randint(cx - rx, cx + rx)
            gy = RNG.randint(cy - ry, cy + ry)
            if inside(gx, gy, 0.95):
                break
        else:
            continue
        gr = RNG.uniform(1.0, 2.6)
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
    for _ in range(RNG.randint(3, 5)):
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
    for i in range(n_trails):
        y0 = int(cy + (i - (n_trails - 1) / 2) * (ry * 1.5 / max(1, n_trails - 1)))
        y = y0
        half = 1.2 if abs(y0 - cy) <= 2 else 0.8
        for x in range(x_start, x_end + 1):
            if RNG.random() < 0.35:
                y += RNG.choice((-1, 1))
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

    return grid, {'deploy_gap': deploy_gap, 'terrain': terr}


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
            if pond_r < d <= pond_r + 2.2 and RNG.random() < 0.55:
                terr[x][y] = tr.WOOD
    _mirror_terrain(terr, width, height)

    # ── Dunes ──
    n_dunes = max(2, (width * height) // 900)
    size = (1.4, max(2.0, height * 0.07))
    procgen.scatter_blobs(terr, grid, width, height, n_dunes, (lo, width // 2 - 2),
                          (2, height - 3), size, tr.HILL, elongated=True, symmetric=True)
    return grid, {'terrain': terr}
