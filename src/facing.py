"""Orientation des unités: de face, de flanc, de dos.

Chaque unité regarde dans une direction (vecteur unitaire `unit.facing`).
Elle se tourne vers ce qu'elle frappe, sinon vers là où elle marche. Une
attaque est classée selon l'angle entre ce regard et la direction d'où
vient l'attaquant:

    de face   angle ≤ ~67°       aucun modificateur
    de flanc  entre les deux     mêlée: -1 au seuil de toucher
    de dos    angle ≥ ~113°      mêlée: -1 au toucher, sauvegarde -1, choc
                                 tir: sauvegarde -1 (le bouclier est devant)

C'est ce qui rend un bloc vulnérable sur ses côtés et donne un sens au
marteau qui contourne: une troupe qui se retourne vers un nouvel agresseur
présente son dos à l'ancien.

Les modificateurs passent par terrain.combat_mods: le moteur et
l'estimation de l'IA (tactics.expected_damage) lisent la même règle.
"""
import math

FRONT, FLANK, REAR = "front", "flank", "rear"

# cos(67,5°): les 3 directions de devant (sur 8) sont « de face », les 3 de
# derrière « de dos », les 2 latérales « de flanc ».
_COS_FRONT = 0.38

# Préférence de l'IA pour une case d'attaque (plus petit = meilleur)
ARC_RANK = {REAR: 0, FLANK: 1, FRONT: 2}
# Surcoût, en pas, d'une case d'attaque selon l'arc: le flanc ou le dos ne
# l'emportent qu'à distance (presque) égale — sinon les mêlées adverses se
# tournaient autour en cherchant chacune le flanc de l'autre.
ARC_COST = {REAR: 0.0, FLANK: 0.25, FRONT: 0.5}

# Libellés affichés au moment du coup
LABELS = {FLANK: "Flanc!", REAR: "Dans le dos!"}


def _dims(unit):
    size = getattr(unit, 'size', 1)
    if size <= 1:
        return 1, 1
    if size == 2:
        return 2, 2
    return 2, 4


def center(unit):
    w, h = _dims(unit)
    x, y = unit.position
    return x + (w - 1) / 2.0, y + (h - 1) / 2.0


def direction(a, b):
    """Vecteur unitaire de a vers b (points), None s'ils sont confondus."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    if n < 1e-9:
        return None
    return dx / n, dy / n


def face_towards(unit, point):
    """Tourne l'unité vers un point de la grille (sans effet si confondu)."""
    d = direction(center(unit), point)
    if d is not None:
        unit.facing = d


def face_unit(unit, other):
    face_towards(unit, center(other))


def arc(attacker, target):
    """D'où vient le coup, vu de la cible: FRONT, FLANK ou REAR."""
    if attacker.position is None:
        return FRONT
    return arc_from(center(attacker), target)


def arc_from(point, target):
    """Arc d'une attaque qui partirait de `point` (case de la grille)."""
    f = getattr(target, 'facing', None)
    if f is None or target.position is None:
        return FRONT
    d = direction(center(target), point)
    if d is None:
        return FRONT
    c = f[0] * d[0] + f[1] * d[1]
    if c >= _COS_FRONT:
        return FRONT
    if c <= -_COS_FRONT:
        return REAR
    return FLANK


def arc_mods(attacker, target, ranged):
    """(toucher, save) selon l'arc, même convention que terrain.combat_mods:
    toucher -1 = plus facile à toucher, save +1 = sauvegarde plus mauvaise."""
    a = arc(attacker, target)
    if a == FRONT:
        return 0, 0
    if ranged:
        return 0, (1 if a == REAR else 0)
    if a == FLANK:
        return -1, 0
    return -1, 1
