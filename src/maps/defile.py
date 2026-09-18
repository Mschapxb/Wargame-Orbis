"""Carte du Défilé: goulet montagneux entre deux parois."""

import math

from rng_scope import RNG
import procgen
import terrain as tr

from .common import _mirror_grid, _mirror_terrain, deploy_front


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
    throat_squeeze = RNG.randint(3, 5)
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
            if RNG.random() < 0.06 and bots[x] - tops[x] > min_gap + 3:
                for j in range(RNG.randint(1, 2)):
                    y = edge[x] + sgn * j
                    for xx in (x, x + RNG.choice((0, 1))):
                        if 0 <= xx < width // 2 and tops[xx] <= y <= bots[xx]:
                            grid[xx][y] = 1

    # ── Rochers/couverts dans le goulet (abris tactiques) ──
    # 3 zones de couverts: 1/4, 1/2 et 3/4 de la largeur, jamais dans
    # l'étranglement (trop difficile à traverser)
    for zone_x in [width // 4, width // 2, 3 * width // 4]:
        num_rocks = RNG.randint(2, 4)
        placed = 0
        attempts = 0
        while placed < num_rocks and attempts < 40:
            attempts += 1
            rx = zone_x + RNG.randint(-4, 4)
            ry = pass_center_y + RNG.randint(-4, 4)
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
