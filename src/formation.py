"""Formations en bloc — géométrie pure (sans Pygame, sans IA).

Une armée ne marche pas en nuée: chaque groupe avance en BLOC, rangs serrés,
au pas de son membre le plus lent. La mêlée fait le front, les tireurs, mages
et officiers suivent en rangs derrière elle; la cavalerie forme son propre
bloc sur l'aile. Le commandant (ai_commander) décide quels blocs existent,
où ils vont et quand ils rompent la formation pour charger; ce module ne fait
que placer des cases.

Repère: `axis` (ax, ay) pointe vers l'ennemi, `perp` = (-ay, ax). Une
position s'exprime en (proj, lat) relatifs à une origine commune.
"""

import math

import tactics
import terrain as tr


def files_per_rank(n):
    """Largeur d'un bloc de n unités: plus large que profond (≈ 3 pour 1),
    comme une ligne de bataille, sans devenir une file indienne."""
    if n <= 3:
        return max(1, n)
    return max(3, min(n, int(math.ceil(math.sqrt(n * 3.0)))))


def spacing(bf, units):
    """Pas entre deux rangs/files: la plus grande emprise du bloc."""
    return max((max(bf.get_unit_dims(u)) for u in units), default=1)


def to_world(origin, axis, proj, lat):
    ax, ay = axis
    return (origin[0] + ax * proj - ay * lat, origin[1] + ay * proj + ax * lat)


def to_frame(origin, axis, pos):
    ax, ay = axis
    dx, dy = pos[0] - origin[0], pos[1] - origin[1]
    return dx * ax + dy * ay, -dx * ay + dy * ax


def walkable(bf, x, y):
    if not bf.is_valid(x, y):
        return False
    fires = getattr(bf, 'fires', None)
    return not (fires and (x, y) in fires)


def nearest_walkable(bf, x, y, taken, radius=3):
    """Case praticable et non attribuée la plus proche de (x, y)."""
    x = max(1, min(bf.width - 2, tactics.mirror_round_x(x, bf.width)))
    y = max(1, min(bf.height - 2, int(round(y))))
    s = tactics.mirror_sign(x, bf.width)
    for r in range(radius + 1):
        ring = [(x + dx, y + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                if max(abs(dx), abs(dy)) == r]
        # Départage en miroir (un tri sur la case brute préférait l'ouest)
        ring.sort(key=lambda c: (abs(c[0] - x) + abs(c[1] - y), (c[0] - x) * s, c[1]))
        for c in ring:
            if (0 < c[0] < bf.width - 1 and 0 < c[1] < bf.height - 1
                    and c not in taken and walkable(bf, *c)):
                return c
    return None


def arrange(units, origin, axis, memory=None):
    """Ordre des unités dans le bloc: rangs de l'avant vers l'arrière, files
    de gauche à droite. Tant que le bloc garde les mêmes membres, on reprend
    l'ordre précédent (`memory`: liste d'id): deux voisins de projection
    proche échangeraient sinon leurs places à chaque round."""
    ids = [id(u) for u in units]
    if memory and len(memory) == len(ids) and set(memory) == set(ids):
        by_id = {id(u): u for u in units}
        return [by_id[i] for i in memory]
    w = files_per_rank(len(units))
    frame = {id(u): to_frame(origin, axis, u.position) for u in units}
    ordered = sorted(units, key=lambda u: (-frame[id(u)][0], u.uid))
    out = []
    for r in range(0, len(ordered), w):
        out += sorted(ordered[r:r + w], key=lambda u: (frame[id(u)][1], u.uid))
    return out


def slots(bf, units, anchor, axis, start_rank=0, taken=None, step=None):
    """Cases d'un bloc dont le PREMIER rang est centré sur `anchor`.

    `units` est déjà ordonné (cf. arrange). start_rank recule le bloc (les
    tireurs derrière la mêlée). Retourne {id(unité): case}."""
    taken = set() if taken is None else taken
    if not units:
        return {}
    step = step or spacing(bf, units)
    w = files_per_rank(len(units))
    out = {}
    for i, u in enumerate(units):
        rank, file = divmod(i, w)
        in_rank = min(w, len(units) - rank * w)
        lat = (file - (in_rank - 1) / 2.0) * step
        proj = -(start_rank + rank) * step
        x, y = to_world(anchor, axis, proj, lat)
        cell = nearest_walkable(bf, x, y, taken)
        if cell is not None:
            out[id(u)] = cell
            taken.add(cell)
    return out


def depth(n):
    """Nombre de rangs d'un bloc de n unités."""
    return int(math.ceil(n / files_per_rank(n))) if n else 0


def half_width(bf, units):
    return files_per_rank(len(units)) * spacing(bf, units) / 2.0 if units else 0.0
