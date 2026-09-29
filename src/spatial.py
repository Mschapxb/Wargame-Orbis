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
from bisect import bisect_left
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
# Plus grand que toute distance sur une carte (cf. NearestDistance)
_FAR = 1 << 60


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

    def in_box(self, x0, y0, x1, y1, ids=None):
        """Unités dont l'ANCRE tombe dans [x0..x1]×[y0..y1]. Ordre non garanti.

        Un compartiment entièrement contenu dans le rectangle est repris en
        bloc: seuls ceux du bord demandent un test case par case.

        ids: ne garder que les unités VIVANTES dont l'id y figure — le tri
        se fait dans le même parcours, sans liste intermédiaire (cf.
        Neighbourhood._near_in: c'était la moitié du coût d'une requête)."""
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
                    if ids is None:
                        out.extend(b)
                    else:
                        out.extend([u for u in b if u.is_alive and id(u) in ids])
                    continue
                for u in b:
                    px, py = u.position
                    if (x0 <= px <= x1 and y0 <= py <= y1
                            and (ids is None or (u.is_alive and id(u) in ids))):
                        out.append(u)
        return out

    def near_box(self, x0, y0, x1, y1, radius, ids=None):
        """Unités dont l'EMPREINTE peut être à `radius` cases ou moins du
        rectangle donné. Surensemble (cf. FOOT_MARGIN_X/Y). ids: cf. in_box."""
        r = ceil(radius)                 # un rayon fractionnaire s'arrondit
        mx, my = r + FOOT_MARGIN_X, r + FOOT_MARGIN_Y      # vers le haut
        return self.in_box(x0 - mx, y0 - my, x1 + mx, y1 + my, ids)

    def near(self, pos, radius, ids=None):
        """Unités dont l'empreinte peut être à `radius` cases ou moins de
        `pos`. Surensemble. ids: cf. in_box."""
        x, y = pos
        r = ceil(radius)
        return self.in_box(x - r - FOOT_MARGIN_X, y - r - FOOT_MARGIN_Y,
                           x + r + FOOT_MARGIN_X, y + r + FOOT_MARGIN_Y, ids)


class NearestDistance:
    """Distance de Manhattan d'un point au plus proche d'un semis de points,
    EXACTE — la même valeur que min(|dx| + |dy|) sur tout le semis.

    L'IA pose la question pour chaque unité d'une armée face à chaque unité
    de l'autre (« à quelle distance est le plus proche des nôtres ? »): du
    quadratique, qui dominait la phase de commandement à plusieurs centaines
    d'unités. Ici les points sont rangés par colonne (y triés): on part de
    la colonne du point demandé et on s'en écarte des deux côtés, en
    s'arrêtant dès que l'écart en x seul atteint la meilleure distance
    trouvée. Une armée occupe peu de colonnes: quelques bissections."""

    __slots__ = ('xs', 'cols')

    def __init__(self, points):
        cols = {}
        for x, y in points:
            c = cols.get(x)
            if c is None:
                cols[x] = [y]
            else:
                c.append(y)
        self.xs = sorted(cols)
        self.cols = [sorted(cols[x]) for x in self.xs]

    def __bool__(self):
        return bool(self.xs)

    def dist(self, x, y, default=None):
        """Distance au plus proche point, `default` si le semis est vide."""
        xs, cols = self.xs, self.cols
        n = len(xs)
        if not n:
            return default
        best = _FAR
        i = bisect_left(xs, x)
        for j in range(i, n):                 # colonnes à droite (x compris)
            dx = xs[j] - x
            if dx >= best:
                break
            d = dx + _col_gap(cols[j], y)
            if d < best:
                best = d
        for j in range(i - 1, -1, -1):        # colonnes à gauche
            dx = x - xs[j]
            if dx >= best:
                break
            d = dx + _col_gap(cols[j], y)
            if d < best:
                best = d
        return best


class NearestUnit:
    """L'unité la plus proche (Manhattan d'ancre à ancre) d'une liste, et à
    égalité la PREMIÈRE dans l'ordre de la liste: exactement ce que rend
    min(units, key=distance). Même rangement par colonnes que
    NearestDistance, mais une colonne à la même distance que le meilleur
    trouvé est encore visitée (elle peut cacher un ex æquo mieux classé)."""

    __slots__ = ('units', 'xs', 'ys', 'idx')

    def __init__(self, units):
        self.units = units
        cols = {}
        for i, u in enumerate(units):
            x, y = u.position
            c = cols.get(x)
            if c is None:
                cols[x] = [(y, i)]
            else:
                c.append((y, i))
        self.xs = sorted(cols)
        self.ys, self.idx = [], []
        for x in self.xs:
            c = sorted(cols[x])
            self.ys.append([t[0] for t in c])
            self.idx.append([t[1] for t in c])

    def nearest(self, x, y):
        """Unité la plus proche de (x, y), None si la liste est vide."""
        xs = self.xs
        n = len(xs)
        if not n:
            return None
        best = [_FAR, _FAR]                 # (distance, rang dans la liste)
        i = bisect_left(xs, x)
        for j in range(i, n):
            dx = xs[j] - x
            if dx > best[0]:
                break
            self._scan(j, x, y, dx, best)
        for j in range(i - 1, -1, -1):
            dx = x - xs[j]
            if dx > best[0]:
                break
            self._scan(j, x, y, dx, best)
        return self.units[best[1]]

    def _scan(self, j, x, y, dx, best):
        """Meilleur candidat de la colonne j: au plus près au-dessus et
        au-dessous, et pour une même ligne le premier de la liste."""
        ys, idx = self.ys[j], self.idx[j]
        k = bisect_left(ys, y)
        if k < len(ys):
            d, r = dx + ys[k] - y, idx[k]
            if d < best[0] or (d == best[0] and r < best[1]):
                best[0], best[1] = d, r
        if k:
            yb = ys[k - 1]
            d, r = dx + y - yb, idx[bisect_left(ys, yb)]
            if d < best[0] or (d == best[0] and r < best[1]):
                best[0], best[1] = d, r


def _col_gap(col, y):
    """|y - y'| minimal pour y' dans la colonne triée `col` (non vide)."""
    k = bisect_left(col, y)
    if k == len(col):
        return y - col[-1]
    gap = col[k] - y
    if k and y - col[k - 1] < gap:
        gap = y - col[k - 1]
    return gap


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
        out = (idx.near_box(*box, radius, ids) if box is not None
               else idx.near(pos, radius, ids))
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
        if cache is not None:
            # Même fenêtre: un rangement par colonnes de chaque camp, bâti
            # une fois, au lieu d'un balayage de l'armée adverse par unité
            enemies = self.get_enemies(unit)
            key = ('nearest', id(enemies))
            got = cache.get(key)
            if got is None:
                got = cache[key] = (enemies, NearestUnit([e for e in enemies if e.is_alive]))
            best = got[1].nearest(ux, uy)
            got = (None, 999) if best is None else (
                best, abs(best.position[0] - ux) + abs(best.position[1] - uy))
            cache[id(unit)] = got
            return got
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
