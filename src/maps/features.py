"""Éléments de paysage tirés au hasard, communs aux cartes de rase campagne.

Chaque carte de rase campagne tire un STYLE (cf. PRAIRIE_STYLES,
DESERT_STYLES): le même champ de bataille change alors de caractère d'une
partie à l'autre — vallonné, semé d'étangs, bocager, rocailleux… Les
éléments se peignent dans la moitié ouest; le générateur recopie ensuite
l'ouest à l'est (équité).

Règles communes (celles des cartes historiques):
  • rien ne se pose devant les lignes de déploiement (x < front + 3), sauf
    le relief doux (collines);
  • le couloir central reste ouvert: bois et étangs vont sur les flancs
    (un bois entre les armées fait renoncer l'IA à ses manœuvres);
  • un camp doit pouvoir rejoindre l'autre (vérifié, sinon l'élément
    fautif est retiré).
"""

import math

from rng_scope import RNG
import procgen
import terrain as tr

from .common import _bfs_path


def _octave(width, height, cell):
    nx = int(width / cell) + 3
    ny = int(height / cell) + 3
    lat = [[RNG.random() for _ in range(ny)] for _ in range(nx)]
    out = [[0.0] * height for _ in range(width)]
    for x in range(width):
        fx = x / cell
        ix = int(fx)
        tx = fx - ix
        tx = tx * tx * (3 - 2 * tx)
        col = out[x]
        for y in range(height):
            fy = y / cell
            iy = int(fy)
            ty = fy - iy
            ty = ty * ty * (3 - 2 * ty)
            a = lat[ix][iy] + (lat[ix + 1][iy] - lat[ix][iy]) * tx
            b = lat[ix][iy + 1] + (lat[ix + 1][iy + 1] - lat[ix][iy + 1]) * tx
            col[y] = a + (b - a) * ty
    return out


def value_noise(width, height, cell=6.0, octaves=3):
    """Bruit fractal 2D, dans [0, 1]: des treillis de valeurs tirées au
    hasard (tous les `cell` cases, puis deux fois plus serrés…),
    interpolés en douceur et sommés à poids décroissants. Une seule octave
    dessine des plateaux aux bords alignés sur le treillis; les octaves
    fines les rendent organiques."""
    total = 0.0
    out = [[0.0] * height for _ in range(width)]
    w = 1.0
    for k in range(octaves):
        layer = _octave(width, height, max(1.5, cell / (2 ** k)))
        for x in range(width):
            o, l_ = out[x], layer[x]
            for y in range(height):
                o[y] += l_[y] * w
        total += w
        w *= 0.5
    for x in range(width):
        o = out[x]
        for y in range(height):
            o[y] /= total
    return out


def pond(terr, grid, width, height, cx, cy, r, x_range, reeds=0.6):
    """Étang: eau dormante au cœur (infranchissable), berges de marais
    discontinues. Retourne les cases peintes."""
    ang = RNG.uniform(0, math.pi)
    stretch = RNG.uniform(1.0, 1.8)
    rim = procgen.paint_blob(terr, grid, width, height, cx, cy, r * stretch + 1.1, r + 1.1, ang,
                             tr.MARSH, x_range=x_range, rough=0.3)
    water = procgen.paint_blob(terr, grid, width, height, cx, cy, r * stretch, r, ang, tr.LAKE,
                               allowed=(tr.MARSH,), x_range=x_range, rough=0.22)
    # Berges: on patauge par endroits, ailleurs la prairie vient au bord
    for (x, y) in rim:
        if terr[x][y] == tr.MARSH and RNG.random() > reeds:
            terr[x][y] = tr.PLAIN
    return rim + water


def rock_ridge(terr, grid, width, height, x0, y0, length, angle, x_range, keep=()):
    """Crête rocheuse: une échine de rochers sur un dos de colline, en arc
    léger. Couvert pour les tireurs, obstacle pour la cavalerie."""
    keep = set(keep)
    bend = RNG.uniform(-0.25, 0.25)
    cells = []
    for k in range(int(length) + 1):
        a = angle + bend * (k / max(1, length) - 0.5)
        x = int(round(x0 + math.cos(a) * k))
        y = int(round(y0 + math.sin(a) * k))
        if not (x_range[0] <= x <= x_range[1] and 2 <= y < height - 2):
            continue
        procgen.paint_blob(terr, grid, width, height, x, y, 1.6, 1.3, a, tr.HILL,
                           allowed=(tr.PLAIN,), x_range=x_range, rough=0.2)
        if (x, y) not in keep and RNG.random() < 0.6 and terr[x][y] in (tr.PLAIN, tr.HILL):
            grid[x][y] = 1
            cells.append((x, y))
    return cells


def mesa(terr, grid, width, height, cx, cy, r, x_range, keep=()):
    """Mesa: plateau de roche (obstacle) aux flancs d'éboulis (collines).
    Retourne les cases de roche."""
    keep = set(keep)
    procgen.paint_blob(terr, grid, width, height, cx, cy, r + 1.4, r + 1.2, RNG.uniform(0, math.pi),
                       tr.HILL, allowed=(tr.PLAIN,), x_range=x_range, rough=0.3)
    ang = RNG.uniform(0, math.pi)
    stretch = RNG.uniform(1.0, 1.6)
    ca, sa = math.cos(ang), math.sin(ang)
    cells = []
    for x in range(int(cx - r * 2) - 1, int(cx + r * 2) + 2):
        for y in range(int(cy - r * 2) - 1, int(cy + r * 2) + 2):
            if not (x_range[0] <= x <= x_range[1] and 2 <= y < height - 2) or (x, y) in keep:
                continue
            dx, dy = x - cx, y - cy
            u = (dx * ca + dy * sa) / (r * stretch)
            v = (-dx * sa + dy * ca) / r
            if u * u + v * v <= 1.0 and terr[x][y] in (tr.PLAIN, tr.HILL) and grid[x][y] == 0:
                grid[x][y] = 1
                cells.append((x, y))
    return cells


def undo(terr, grid, cells, to=tr.PLAIN):
    """Retire un élément (il coupait le passage)."""
    for (x, y) in cells:
        grid[x][y] = 0
        if terr[x][y] in (tr.LAKE, tr.MARSH):
            terr[x][y] = to


def crossing_ok(grid, terr, width, height):
    """Un camp rejoint-il l'autre (bord ouest → bord est) ?"""
    left = [(1, y) for y in range(1, height - 1)
            if grid[1][y] == 0 and tr.MOVE[terr[1][y]] is not None]
    right = [(width - 2, y) for y in range(1, height - 1)
             if grid[width - 2][y] == 0 and tr.MOVE[terr[width - 2][y]] is not None]
    return _bfs_path(grid, width, height, left, right, terr) is not None
