"""Carte du Village: bourg circulaire au centre du champ."""

import math

from rng_scope import RNG
import procgen
import terrain as tr

from .common import _mirror_grid, _mirror_terrain, _paint_disc, deploy_front


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
    n_side = RNG.randint(5, 6)
    streets = [(0.0, 1.6), (math.pi, 1.6)]
    base = RNG.uniform(0, math.pi / n_side)
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
        offset = RNG.uniform(0, math.tau / n_slots)
        for k in range(n_slots):
            a = offset + k * math.tau / n_slots
            sizes = [(RNG.randint(3, 4), RNG.randint(2, 3)), (3, 2), (2, 3), (2, 2)]
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
    for _ in range(RNG.randint(2, 4)):
        for _try in range(30):
            a = RNG.uniform(0, math.tau)
            if abs(math.sin(a)) < 0.6:
                continue
            d = RNG.uniform(R + 4, R + 8)
            w, h = RNG.randint(2, 3), RNG.randint(2, 3)
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
                       (R + 1.2) * RNG.uniform(0.92, 1.0), RNG.uniform(0, math.pi),
                       tr.HILL, x_range=(0, width // 2 - 1), rough=0.08)
    # Bosquets dans les champs, au nord et au sud du bourg
    lo_v = deploy_front(width, R + 5) + 3
    for _ in range(RNG.randint(2, 4)):
        r = RNG.uniform(1.2, 2.6)
        wx = RNG.uniform(lo_v + r * 1.4 + 1, max(lo_v + r * 1.4 + 1, mx - 2))
        wy = RNG.choice((RNG.uniform(2, cy - R * 0.7), RNG.uniform(cy + R * 0.7, height - 3)))
        if math.hypot(wx - mx, wy - cy) < R + 3 + r or abs(wy - cy) < 3:
            continue
        procgen.paint_blob(terr, grid, width, height, wx, wy, r * RNG.uniform(1.0, 1.5), r,
                           RNG.uniform(0, math.pi), tr.WOOD, x_range=(0, width // 2 - 1),
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
            if RNG.random() < 0.30:
                terr[x][y] = tr.WOOD
    # Mare boueuse au bord de la place, hors de la grand-rue
    _paint_disc(terr, mx - (plaza + 2.5), cy + plaza + 1.5, 1.6, tr.MARSH, width, height)
    _mirror_terrain(terr, width, height)

    return grid, {'deploy_gap': R + 5, 'terrain': terr}
