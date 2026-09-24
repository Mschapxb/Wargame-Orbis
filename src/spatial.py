"""Index spatial des unités — « qui est près d'ici ? » sans balayer l'armée.

Le moteur pose sans arrêt la même question: quels ennemis sont à portée, au
contact, dans le rayon d'une aura. Chaque réponse coûtait un balayage de
l'armée adverse entière. À 200 unités par camp, une dizaine de balayages par
unité et par round font des centaines de milliers de comparaisons — le gros
du temps de calcul d'une grande bataille.

L'index découpe la carte en compartiments de BUCKET cases de côté: une
requête ne lit que les compartiments qui touchent la zone demandée. Le coût
passe de « toute l'armée » à « ce qu'il y a autour ».

Il est tenu à jour À LA CASE, depuis Battlefield.place_unit /
remove_unit — les deux seuls endroits par où passent les poses, les retraits
et les déplacements. Pas de reconstruction, pas de péremption possible: si
une unité est sur la grille, elle est dans l'index, et à la bonne place.

Deux propriétés dont le moteur dépend:

- SURENSEMBLE. L'index travaille sur l'ANCRE des unités (coin haut-gauche).
  Une unité de plusieurs cases déborde de son ancre: les requêtes élargissent
  donc le rectangle de FOOT_MARGIN_X/Y cases. Le résultat contient toujours
  les unités cherchées, parfois quelques-unes de trop — l'appelant garde son
  test exact (unit_distance, ligne de vue…), qui tranche.
- L'ORDRE n'est PAS celui de l'armée: il suit les compartiments. L'appelant
  qui en dépend (l'ordre des unités fixe l'ordre des tirages aléatoires) doit
  retrier — cf. Battle.enemies_near, qui trie par uid.
"""
from math import ceil
from operator import attrgetter

BUCKET = 8
# Débordement d'une empreinte autour de son ancre. Les empreintes font 1×1,
# 2×2 ou 2×4 cases (cf. Battlefield.get_unit_dims): entre deux unités dont
# les empreintes se touchent à `d` cases, les ANCRES sont au plus à d + 1 en
# x et d + 3 en y. C'est un majorant sur la plus grande des deux empreintes,
# pas une somme — d'où des marges dissymétriques, et des rectangles de
# requête un tiers plus petits qu'avec une marge unique.
FOOT_MARGIN_X = 1
FOOT_MARGIN_Y = 3

_uid = attrgetter('uid')


class UnitIndex:
    """Compartimentage des unités posées sur la grille."""

    __slots__ = ('buckets', 'where')

    def __init__(self):
        self.buckets = {}       # (bx, by) → [unités]
        self.where = {}         # id(unité) → (bx, by) où elle est rangée

    def add(self, unit):
        """(Re)range une unité d'après sa position courante."""
        self.discard(unit)
        pos = unit.position
        if pos is None:
            return
        key = (pos[0] // BUCKET, pos[1] // BUCKET)
        self.where[id(unit)] = key
        b = self.buckets.get(key)
        if b is None:
            self.buckets[key] = [unit]
        else:
            b.append(unit)

    def discard(self, unit):
        """Retire une unité de l'index (sans effet si elle n'y est pas).

        Le compartiment vient de `where`, pas de la position: une unité qu'on
        déplace a déjà sa nouvelle position quand on la retire de l'ancienne."""
        key = self.where.pop(id(unit), None)
        if key is None:
            return
        b = self.buckets.get(key)
        if b is None:
            return
        for i, u in enumerate(b):
            if u is unit:
                del b[i]
                break
        if not b:
            del self.buckets[key]

    def clear(self):
        self.buckets.clear()
        self.where.clear()

    def in_box(self, x0, y0, x1, y1):
        """Unités dont l'ANCRE tombe dans [x0..x1]×[y0..y1]. Ordre non garanti.

        Un compartiment entièrement contenu dans le rectangle est repris en
        bloc: seuls ceux du bord demandent un test case par case."""
        buckets = self.buckets
        if not buckets:
            return []
        out = []
        for bx in range(x0 // BUCKET, x1 // BUCKET + 1):
            bx0 = bx * BUCKET
            inside_x = x0 <= bx0 and bx0 + BUCKET - 1 <= x1
            for by in range(y0 // BUCKET, y1 // BUCKET + 1):
                b = buckets.get((bx, by))
                if b is None:
                    continue
                by0 = by * BUCKET
                if inside_x and y0 <= by0 and by0 + BUCKET - 1 <= y1:
                    out.extend(b)
                    continue
                for u in b:
                    px, py = u.position
                    if x0 <= px <= x1 and y0 <= py <= y1:
                        out.append(u)
        return out

    def near_box(self, x0, y0, x1, y1, radius):
        """Unités dont l'EMPREINTE peut être à `radius` cases ou moins du
        rectangle donné. Surensemble (cf. FOOT_MARGIN_X/Y)."""
        r = ceil(radius)                 # un rayon fractionnaire s'arrondit
        mx, my = r + FOOT_MARGIN_X, r + FOOT_MARGIN_Y      # vers le haut
        return self.in_box(x0 - mx, y0 - my, x1 + mx, y1 + my)

    def near(self, pos, radius):
        """Unités dont l'empreinte peut être à `radius` cases ou moins de
        `pos`. Surensemble."""
        x, y = pos
        r = ceil(radius)
        return self.in_box(x - r - FOOT_MARGIN_X, y - r - FOOT_MARGIN_Y,
                           x + r + FOOT_MARGIN_X, y + r + FOOT_MARGIN_Y)


class Neighbourhood:
    """Questions de voisinage d'un champ de bataille, adossées à l'index.

    Mixin: Battle l'hérite, et les doublures de test aussi (tout ce qu'il
    demande, c'est `battlefield`, `get_enemies` et `get_allies`). Les
    réponses sortent dans l'ORDRE DE L'ARMÉE — le moteur en dépend, l'ordre
    des unités fixant l'ordre des tirages de dés — et forment un
    SURENSEMBLE: l'appelant garde son test exact.
    """

    def army_ids(self, units):
        """Set des id() d'une liste d'unités. Battle en tient deux à jour en
        permanence (ses armées) et redéfinit cette méthode; la version par
        défaut recalcule, ce qui suffit aux doublures de test."""
        return {id(u) for u in units}

    def _near_in(self, units, pos, radius, box=None, ids=None):
        if ids is None:
            ids = self.army_ids(units)
        idx = self.battlefield.index
        found = idx.near_box(*box, radius) if box is not None else idx.near(pos, radius)
        out = [u for u in found if u.is_alive and id(u) in ids]
        if len(out) > 1:
            # Les uid croissent dans l'ordre des listes d'armée (attribués au
            # déploiement, jamais réordonnés — test_fondations le vérifie).
            out.sort(key=_uid)
        return out

    def units_near(self, army, pos, radius, ids=None):
        """Unités vivantes de `army` autour de `pos`.

        `army` peut être une liste de passage (un groupe adverse isolé, par
        exemple): fournir alors `ids` une fois pour toutes, sans quoi le set
        d'appartenance serait reconstruit à chaque appel."""
        return self._near_in(army, pos, radius, ids=ids)

    def enemies_near(self, unit, radius, pos=None):
        """Ennemis vivants dont l'empreinte peut être à `radius` cases ou
        moins de `pos` (l'ancre de `unit` par défaut)."""
        return self._near_in(self.get_enemies(unit),
                             unit.position if pos is None else pos, radius)

    def enemies_near_box(self, unit, box, radius):
        """Comme enemies_near, autour d'un rectangle (x0, y0, x1, y1)."""
        return self._near_in(self.get_enemies(unit), None, radius, box)

    def allies_near(self, unit, radius, pos=None):
        """Alliés vivants (unité comprise) autour de `pos`."""
        return self._near_in(self.get_allies(unit),
                             unit.position if pos is None else pos, radius)

    def nearest_enemy(self, unit):
        """(ennemi vivant le plus proche, distance de Manhattan d'ancre à
        ancre), ou (None, 999) s'il n'en reste aucun — la carte ne fait
        jamais 999 cases de diagonale. À égalité, le premier dans l'ordre de
        l'armée, comme le faisait min().

        Les trois passes du mouvement posaient cette question cinq fois par
        unité et par round, chacune en balayant l'armée adverse. Tant que
        rien ne bouge (planification), `_near_enemy_cache` la garde."""
        cache = getattr(self, '_near_enemy_cache', None)
        if cache is not None:
            got = cache.get(id(unit))
            if got is not None:
                return got
        ux, uy = unit.position
        best, best_d = None, 999
        for e in self.get_enemies(unit):
            if not e.is_alive:
                continue
            ex, ey = e.position
            d = (ex - ux if ex > ux else ux - ex) + (ey - uy if ey > uy else uy - ey)
            if d < best_d:
                best, best_d = e, d
        if cache is not None:
            cache[id(unit)] = (best, best_d)
        return best, best_d

    def nearest_enemy_dist(self, unit):
        """Distance au plus proche ennemi vivant (999 s'il n'en reste aucun)."""
        return self.nearest_enemy(unit)[1]
