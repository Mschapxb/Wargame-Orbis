"""Avantage de terrain: hauteurs (et bosquets) sous le front d'un camp."""

import math

from rng_scope import RNG
import procgen
import terrain as tr

from .catalog import SIEGE_MAPS
from .common import deploy_front


# ═══════════════════════════════════════════════════════════════
#                 AVANTAGE DE TERRAIN (option du menu)
# ═══════════════════════════════════════════════════════════════
# Par défaut, une bataille rangée se joue sur une carte en miroir: aucun
# camp n'a meilleur terrain. On peut au contraire en favoriser un:
#   Léger   une crête sous et devant son front (hauteur: +1 portée à ses
#           tireurs, mêlée plus difficile contre lui)
#   Marqué  des hauteurs plus étendues et des bosquets de couverture à ses
#           deux ailes. (Mesuré et écarté: marais sur l'approche adverse et
#           haies devant le front desservaient le camp favorisé, qui devait
#           les franchir à son tour pour contre-attaquer.)
# Les sièges n'ont pas l'option: la forteresse EST l'avantage du défenseur.

ADVANTAGE_NONE = "Aucun"
ADVANTAGE_SIDES = {ADVANTAGE_NONE: 0, "Armée 1": 1, "Armée 2": 2}
ADVANTAGE_LEVELS = ("Léger", "Marqué")


def advantage_of(options):
    """(camp favorisé 0/1/2, niveau 1/2) lu dans les options de carte."""
    options = options or {}
    side = options.get('advantage', 0)
    if isinstance(side, str):
        side = ADVANTAGE_SIDES.get(side, 0)
    level = 2 if options.get('advantage_level') == ADVANTAGE_LEVELS[1] else 1
    return side, level


def apply_advantage(map_name, grid, data, width, height, side, level):
    """Façonne le terrain en faveur d'un camp. Ne tire aucun dé si side == 0."""
    if not side or map_name in SIEGE_MAPS or data.get('terrain') is None:
        return []
    terr = data['terrain']
    front = deploy_front(width, data.get('deploy_gap'))

    def X(x):                       # coordonnée du côté du camp favorisé
        return x if side == 1 else width - 1 - x

    def band(lo, hi):               # bande de colonnes, du bon côté
        a, b = X(lo), X(hi)
        return (min(a, b), max(a, b))

    painted = []
    cy = height / 2.0
    # Hauteurs à cheval sur le front: une CHAÎNE de buttes irrégulières,
    # décalées et inclinées (une bande droite faisait une carte « en
    # ligne »), qui couvre la zone de déploiement du camp favorisé.
    n = 2 if level == 1 else 3
    span = height * (0.48 if level == 1 else 0.72)
    step = span / n
    for i in range(n):
        ry = step * RNG.uniform(0.40, 0.50)      # des cols entre les buttes
        y = cy - span / 2 + step * (i + 0.5) + RNG.uniform(-1.5, 1.5)
        x = front + 1 + RNG.uniform(-2.5, 2.5)
        rx = RNG.uniform(2.8, 4.2) + (0.6 if level >= 2 else 0.0)
        painted += procgen.paint_blob(terr, grid, width, height, X(x), y, rx, ry,
                                      RNG.uniform(-0.35, 0.35), tr.HILL,
                                      x_range=band(front - 4, front + 6), rough=0.26)
    ry = span / 2
    if level >= 2:
        # Bosquets aux deux ailes, un peu en avant: couvert pour les tireurs
        for sgn in (-1, 1):
            y = cy + sgn * (ry + 2.5)
            if 2 <= y <= height - 3:
                painted += procgen.paint_blob(terr, grid, width, height, X(front + 4), y,
                                              2.2, 2.6, RNG.uniform(0, math.pi), tr.WOOD,
                                              x_range=band(front + 1, front + 8))
    return painted
