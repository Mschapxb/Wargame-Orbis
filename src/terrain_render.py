"""Rendu du terrain à effets.

Règle de lisibilité: chaque terrain a une teinte ET un motif (courbes de
niveau, eau et berges, roseaux, arbres, blocs, cendres…). On ne doit jamais
avoir besoin de distinguer deux couleurs proches pour savoir où l'on marche.

Formes: le terrain est une grille, mais il ne doit pas s'en voir. Chaque
zone (colline, rivière, marais, bois…) est tracée comme un champ de
« métaboules »: un noyau radial doux par case, sommé, puis seuillé. Les
bords droits restent sur la limite des cases, les angles s'arrondissent, une
case isolée devient une tache ronde; un léger décalage pseudo-aléatoire par
case rend les contours organiques. Tout est local (une case n'influence que
ses voisines): repeindre une région donne exactement les mêmes pixels que
reconstruire la carte.

Deux familles:
    statique (collines, eau, gués, ponts, marais, falaises du Défilé) —
        cuite une fois dans la couche de sol (`draw_static`);
    vivante (bois, décombres, brûlé) — change avec la destruction,
        repeinte par région (`draw_dynamic`, `tall_sprites`).
"""
import pygame

import scenery
import theme as T

import terrain as tr

# Pseudo-terrain de légende: une case en feu n'est pas un terrain, mais le
# joueur doit pouvoir lire ce qu'elle fait.
FIRE = "feu"

LEGEND = {
    tr.HILL:   "Colline — tir depuis la hauteur: +1 portée · mêlée contre une unité en hauteur: +1 au seuil de toucher (plus difficile) · monter ×1,5",
    tr.WOOD:   "Bois — déplacement ×2 · tirs reçus: +1 au seuil de toucher (plus difficile) · pas de charge · 3 cases masquent la vue",
    tr.RIVER:  "Rivière — infranchissable",
    tr.LAKE:   "Étang — eau dormante, infranchissable",
    tr.FORD:   "Gué — déplacement ×2 · sauvegarde -1 · pas de charge",
    tr.BRIDGE: "Pont — passage étroit, déplacement normal",
    tr.MARSH:  "Marais — déplacement ×3 · sauvegarde -1 · pas de charge",
    tr.RUBBLE: "Décombres — déplacement ×2 · tirs reçus: +1 au seuil de toucher (couvert) · pas de charge",
    tr.BURNT:  "Brûlé — terrain dégagé: ne ralentit, ne couvre ni ne masque plus rien",
    FIRE:      "En feu — déplacement ×4 · 1 dégât par round · la fumée masque comme un bois",
}
_ORDER = (tr.HILL, tr.WOOD, tr.RIVER, tr.LAKE, tr.FORD, tr.BRIDGE, tr.MARSH, tr.RUBBLE, tr.BURNT, FIRE)

STATIC = (tr.HILL, tr.RIVER, tr.LAKE, tr.FORD, tr.BRIDGE, tr.MARSH)
DYNAMIC = (tr.WOOD, tr.RUBBLE, tr.BURNT)
WATER = (tr.RIVER, tr.FORD, tr.BRIDGE, tr.LAKE)


def _h(x, y, k=0):
    """Hachage déterministe d'une case → 0..255 (aucun dé tiré)."""
    n = (x * 73856093 ^ y * 19349663 ^ k * 83492791) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return (n >> 8) & 0xFF


def _u(x, y, k):
    """Valeur pseudo-aléatoire dans [-1, 1]."""
    return _h(x, y, k) / 127.5 - 1.0


# ═══════════════════════════════════════════════════════════════
#   CHAMP DE MÉTABOULES
# ═══════════════════════════════════════════════════════════════

PEAK = 160          # alpha au centre d'un noyau
_KERNELS = {}
_EDGE = {}


def _kernel(r):
    """Noyau radial (alpha seul, RGB noir: s'ajoute sans teinter)."""
    s = _KERNELS.get(r)
    if s is None:
        s = pygame.Surface((2 * r + 1, 2 * r + 1), pygame.SRCALPHA)
        s.fill((0, 0, 0, 0))
        for rr in range(r, 0, -1):
            t = 1.0 - rr / (r + 0.5)
            a = int(PEAK * t * t * (3 - 2 * t) + 0.5)
            if a:
                pygame.draw.circle(s, (0, 0, 0, a), (r, r), rr)
        _KERNELS[r] = s
    return s


def _radius(cs, rel):
    return max(2, int(round(cs * rel)))


def _edge_level(cs, rel):
    """Valeur du champ au milieu d'un bord droit (zone pleine d'un côté,
    vide de l'autre): le seuil qui pose le contour sur la limite des cases.
    Mesurée sur le noyau réel plutôt que calculée."""
    key = (cs, rel)
    lvl = _EDGE.get(key)
    if lvl is None:
        r = _radius(cs, rel)
        n = 3 + r // cs
        acc = pygame.Surface(((2 * n) * cs, (2 * n + 1) * cs), pygame.SRCALPHA)
        acc.fill((255, 255, 255, 0))
        k = _kernel(r)
        for x in range(n):
            for y in range(2 * n + 1):
                acc.blit(k, (int((x + 0.5) * cs) - r, int((y + 0.5) * cs) - r),
                         special_flags=pygame.BLEND_RGBA_ADD)
        yy = n * cs + cs // 2
        lvl = (acc.get_at((n * cs - 1, yy))[3] + acc.get_at((n * cs, yy))[3]) // 2
        _EDGE[key] = lvl = max(8, lvl)
    return lvl


class _Win:
    """Fenêtre de calcul: les cases [cx0..cx1]×[cy0..cy1] (marge comprise),
    en pixels à partir du coin (cx0·cs, cy0·cs). Les cases hors carte
    prolongent celles du bord (une rivière ne s'arrondit pas au bord)."""

    def __init__(self, bf, cs, region, margin=2):
        x0, y0, x1, y1 = region
        self.bf = bf
        self.cs = cs
        self.cx0, self.cy0 = x0 - margin, y0 - margin
        self.cx1, self.cy1 = x1 + margin, y1 + margin
        self.w = (self.cx1 - self.cx0 + 1) * cs
        self.h = (self.cy1 - self.cy0 + 1) * cs
        self.ox, self.oy = self.cx0 * cs, self.cy0 * cs

    def cells(self, grid, names):
        """Cases de la fenêtre dont `grid` (colonnes x → y) vaut l'un des
        `names`."""
        names = set(names)
        W, H = self.bf.width, self.bf.height
        out = []
        for x in range(self.cx0, self.cx1 + 1):
            col = grid[min(W - 1, max(0, x))]
            for y in range(self.cy0, self.cy1 + 1):
                if col[min(H - 1, max(0, y))] in names:
                    out.append((x, y))
        return out

    def px(self, x, y):
        """Centre de la case (x, y) dans la fenêtre."""
        return (x - self.cx0 + 0.5) * self.cs, (y - self.cy0 + 0.5) * self.cs

    def sub(self, cells, margin=2):
        """Fenêtre réduite au rectangle des cases `cells` (+ marge)."""
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        return _Win(self.bf, self.cs, (min(xs), min(ys), max(xs), max(ys)), margin)


def _clusters(cells, gap=3):
    """Groupes de cases séparés de plus de `gap` cases (distance de
    Chebyshev). Deux groupes aussi éloignés n'ont aucun pixel de champ en
    commun (un noyau porte à moins d'une case et demie): chacun se calcule
    dans sa petite fenêtre, au même pixel près, sans balayer le vide entre
    eux. Triés pour un ordre de dessin stable."""
    todo = set(cells)
    out = []
    span = range(-gap, gap + 1)
    for start in sorted(todo):
        if start not in todo:
            continue
        todo.discard(start)
        comp, stack = [start], [start]
        while stack:
            x, y = stack.pop()
            for dx in span:
                for dy in span:
                    n = (x + dx, y + dy)
                    if n in todo:
                        todo.discard(n)
                        comp.append(n)
                        stack.append(n)
        out.append(comp)
    return out


def _field(win, cells, rel=1.2, jitter=0.12):
    """Somme des noyaux des cases: surface RGB blanche, alpha = champ.

    Une case entourée de ses huit voisines est au cœur de la zone, où le
    champ est de toute façon saturé: au lieu de son noyau, on remplit
    d'un coup le carré de deux cases qui l'entoure (même image, dix fois
    moins de blits sur un massif)."""
    acc = pygame.Surface((win.w, win.h), pygame.SRCALPHA)
    acc.fill((255, 255, 255, 0))
    cs = win.cs
    base = _radius(cs, rel)
    add = pygame.BLEND_RGBA_ADD
    cset = set(cells)
    cores = []
    for (x, y) in cells:
        if ((x - 1, y) in cset and (x + 1, y) in cset and (x, y - 1) in cset and (x, y + 1) in cset
                and (x - 1, y - 1) in cset and (x + 1, y - 1) in cset
                and (x - 1, y + 1) in cset and (x + 1, y + 1) in cset):
            cores.append((x, y))
            continue
        cx, cy = win.px(x, y)
        if jitter:
            cx += _u(x, y, 1) * jitter * cs
            cy += _u(x, y, 2) * jitter * cs
            r = max(2, int(base * (1.0 + 0.12 * _u(x, y, 3))))
        else:
            r = base
        acc.blit(_kernel(r), (int(cx) - r, int(cy) - r), special_flags=add)
    # Cœurs regroupés en segments horizontaux: un remplissage par segment
    full = (255, 255, 255, 255)
    cores.sort(key=lambda c: (c[1], c[0]))
    i = 0
    while i < len(cores):
        x0, y = cores[i]
        j = i
        while j + 1 < len(cores) and cores[j + 1] == (cores[j][0] + 1, y):
            j += 1
        acc.fill(full, ((x0 - win.cx0) * cs - cs // 2, (y - win.cy0) * cs - cs // 2,
                        (cores[j][0] - x0 + 2) * cs, 2 * cs))
        i = j + 1
    return acc


_CONST = {}


def _const(size, alpha):
    s = _CONST.get(size)
    if s is None:
        if len(_CONST) > 8:
            _CONST.clear()
        s = _CONST[size] = pygame.Surface(size, pygame.SRCALPHA)
    s.fill((0, 0, 0, alpha))
    return s


def _threshold(acc, level, gain_pow=4):
    """Seuil adouci, en place: alpha = (champ − niveau)·2^gain + 128, borné.
    Le contour tombe au niveau voulu avec un bord lissé de 1-2 pixels."""
    g = 1 << gain_pow
    sub = max(0, level - 128 // g)
    if sub:
        acc.blit(_const(acc.get_size(), sub), (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
    for _ in range(gain_pow):
        acc.blit(acc, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return acc


def _mask(win, cells, rel=1.2, jitter=0.12, offset=0, raw=None):
    """Masque lissé des cases (`offset` > 0: contour rentré vers
    l'intérieur). Renvoie (masque, champ brut) — le champ resservant aux
    liserés."""
    if raw is None:
        raw = _field(win, cells, rel, jitter)
    m = raw.copy()
    _threshold(m, _edge_level(win.cs, rel) + offset)
    return m, raw


def _minus(a, b, dx=0, dy=0):
    """a − b (b décalé de dx, dy): bande d'un masque privé d'un autre."""
    out = a.copy()
    out.blit(b, (dx, dy), special_flags=pygame.BLEND_RGBA_SUB)
    return out


def _shifted(m, dx, dy):
    out = pygame.Surface(m.get_size(), pygame.SRCALPHA)
    out.fill((255, 255, 255, 0))
    out.blit(m, (dx, dy))
    return out


def _paint(target, win, mask, color, alpha):
    """Pose `color` (opacité `alpha`) là où le masque est plein."""
    if alpha <= 0:
        return
    layer = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
    layer.fill((color[0], color[1], color[2], alpha))
    layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    target.blit(layer, (win.ox, win.oy))


def _fill_holes(cells, max_hole):
    """La zone et ses trous fermés d'au plus `max_hole` cases."""
    cset = set(cells)
    if not max_hole or not cells:
        return cset
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    seen = set()
    holes = []
    for x in range(bx0, bx1 + 1):
        for y in range(by0, by1 + 1):
            if (x, y) in cset or (x, y) in seen:
                continue
            comp, stack, border = [], [(x, y)], False
            seen.add((x, y))
            while stack:
                c = stack.pop()
                comp.append(c)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (c[0] + dx, c[1] + dy)
                    if not (bx0 <= n[0] <= bx1 and by0 <= n[1] <= by1):
                        border = True
                    elif n not in cset and n not in seen:
                        seen.add(n)
                        stack.append(n)
            if not border and len(comp) <= max_hole:
                holes.extend(comp)
    cset.update(holes)
    return cset


def _levels(cells, maxd=3, fill_holes=0):
    """Distance (4-voisinage) de chaque case au bord de sa zone, bornée:
    {case: 1..maxd}. Sert aux courbes de niveau et aux eaux profondes.

    fill_holes: les trous de la zone d'au plus ce nombre de cases (un
    bosquet sur une butte) ne creusent pas de courbes de niveau autour
    d'eux — une butte percée de dix cercles se lit comme un labyrinthe."""
    cset = _fill_holes(cells, fill_holes)
    dist = {}
    frontier = []
    for (x, y) in cset:
        if any((x + dx, y + dy) not in cset for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            dist[(x, y)] = 1
            frontier.append((x, y))
    d = 1
    while frontier and d < maxd:
        d += 1
        nxt = []
        for (x, y) in frontier:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c = (x + dx, y + dy)
                if c in cset and c not in dist:
                    dist[c] = d
                    nxt.append(c)
        frontier = nxt
    for c in cset:
        dist.setdefault(c, maxd)
    return dist


# ═══════════════════════════════════════════════════════════════
#   PALETTE DU LIEU
# ═══════════════════════════════════════════════════════════════

def look(bf):
    """(biome, saison) du champ de bataille, pour les couleurs et le décor."""
    theme = getattr(bf, 'theme', None) or {}
    biome = theme.get('biome') or ("Désert" if bf.map_name == "Désert" else
                                   "Forêt" if bf.map_name == "Forêt" else "Prairie")
    return biome, theme.get('season') or scenery.DEFAULT_SEASON


def is_winter(bf):
    """Carte enneigée (hiver hors du désert)."""
    return scenery.palette(*look(bf))['snow']


_winter = is_winter


def _in_map(bf, x, y):
    return 0 <= x < bf.width and 0 <= y < bf.height


# ═══════════════════════════════════════════════════════════════
#   COUCHES STATIQUES (cuites dans le sol)
# ═══════════════════════════════════════════════════════════════

def _bbox(cells, pad, bf):
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return (max(0, min(xs) - pad), max(0, min(ys) - pad),
            min(bf.width - 1, max(xs) + pad), min(bf.height - 1, max(ys) + pad))


def _all_cells(bf, grid, names):
    names = set(names)
    return [(x, y) for x in range(bf.width) for y in range(bf.height) if grid[x][y] in names]


def _draw_hills(surf, bf, cs, grid, bg):
    """Collines: aplat clair, une courbe de niveau par case de hauteur,
    versants sud-est dans l'ombre, rebords nord-ouest éclairés."""
    cells = _all_cells(bf, grid, (tr.HILL,))
    if not cells:
        return
    big = _Win(bf, cs, _bbox(cells, 0, bf), margin=2)
    if _winter(bf):
        fill, lit, dark, line = (230, 235, 242), (250, 252, 255), (120, 134, 160), (150, 160, 186)
    else:
        fill = scenery.tint(bg, (34, 30, 12))
        lit = scenery.tint(bg, (64, 58, 30))
        dark = scenery.shade(bg, -34)
        line = scenery.mix(scenery.shade(bg, -30), (86, 64, 30), 0.4)
    s = max(2, cs // 5)
    for hills in _clusters(big.cells(grid, (tr.HILL,))):
        win = big.sub(hills)
        dist = _levels(hills, 3, fill_holes=12)
        for lvl in (1, 2, 3):
            group = hills if lvl == 1 else [c for c in dist if dist[c] >= lvl]
            if not group:
                break
            m, raw = _mask(win, group, jitter=0.14)
            inner, _ = _mask(win, group, raw=raw, offset=14)
            if lvl == 1:
                _paint(surf, win, _minus(_shifted(m, s, s + s // 2), m), (0, 0, 0), 38)
                _paint(surf, win, m, fill, 128)
            else:
                _paint(surf, win, _minus(_shifted(m, s, s), m), dark, 40)
                _paint(surf, win, m, lit, 30)
            _paint(surf, win, _minus(_shifted(m, -s, -s), m), lit, 34)
            # Courbe de niveau: le liseré entre le contour et son retrait
            _paint(surf, win, _minus(m, inner), line, 125 if lvl == 1 else 80)


def _draw_marsh(surf, bf, cs, grid, bg):
    """Marais: vase olive, flaques d'eau croupie, touffes de roseaux."""
    cells = _all_cells(bf, grid, (tr.MARSH,))
    if not cells:
        return
    big = _Win(bf, cs, _bbox(cells, 0, bf), margin=2)
    winter = _winter(bf)
    mud = (74, 78, 46) if not winter else (150, 158, 150)
    for marsh in _clusters(big.cells(grid, (tr.MARSH,))):
        win = big.sub(marsh)
        m, raw = _mask(win, marsh, jitter=0.22)
        inner, _ = _mask(win, marsh, raw=raw, offset=30)
        _paint(surf, win, m, mud, 175)
        _paint(surf, win, _minus(m, inner), scenery.shade(mud, -26), 120)
    biome, season = look(bf)
    pool = (46, 70, 64) if not winter else (184, 200, 214)
    for (x, y) in cells:
        cx, cy = x * cs + cs // 2, y * cs + cs // 2
        if _h(x, y, 5) < 150:
            w = int(cs * (0.35 + 0.25 * _h(x, y, 6) / 255))
            h = max(2, w // 2)
            px = cx + int(_u(x, y, 7) * cs * 0.25)
            py = cy + int(_u(x, y, 8) * cs * 0.25)
            pygame.draw.ellipse(surf, pool, (px - w // 2, py - h // 2, w, h))
            pygame.draw.ellipse(surf, scenery.shade(pool, 30),
                                (px - w // 2 + 1, py - h // 2, max(1, w // 2), max(1, h // 3)))
        if cs >= 10 and _h(x, y, 9) < 170:
            scenery.blit(surf, "roseaux", _h(x, y, 10), cx + int(_u(x, y, 11) * cs * 0.3),
                         cy + int(_u(x, y, 12) * cs * 0.3), cs, biome, season)


def _draw_water(surf, bf, cs, grid, bg):
    """Rivières: berge de vase ou de sable, eau claire au bord et sombre au
    milieu, écume du rivage, rides; gués sablonneux à pierres de passage."""
    cells = _all_cells(bf, grid, WATER)
    if not cells:
        return
    big = _Win(bf, cs, _bbox(cells, 1, bf), margin=2)
    winter = _winter(bf)
    biome, _season = look(bf)
    if biome == "Désert":
        bank_c = (176, 150, 100)
    elif winter:
        bank_c = (170, 170, 164)
    else:
        bank_c = scenery.mix(bg, (104, 86, 56), 0.55)
    shallow = (60, 108, 146) if not winter else (96, 128, 150)
    deep_c = (36, 76, 116) if not winter else (70, 98, 124)
    foam = (206, 226, 236) if not winter else (240, 246, 252)
    W, H = bf.width, bf.height
    dist = {}
    for water in _clusters(big.cells(grid, WATER)):
        win = big.sub(water, margin=3)
        braw = _field(win, water, rel=1.45, jitter=0.18)
        bank = _threshold(braw, _edge_level(cs, 1.45) - 30)
        _paint(surf, win, bank, bank_c, 190)
        m, raw = _mask(win, water, jitter=0.10)
        inner, _ = _mask(win, water, raw=raw, offset=34)
        _paint(surf, win, m, shallow, 255)
        d = _levels(water, 3)
        dist.update(d)
        deep = [c for c in water if d[c] >= 2]
        if deep:
            dm, _ = _mask(win, deep, jitter=0.2)
            _paint(surf, win, dm, deep_c, 170)
        _paint(surf, win, _minus(m, inner), foam, 120 if not winter else 200)
        fords = [c for c in water
                 if grid[min(W - 1, max(0, c[0]))][min(H - 1, max(0, c[1]))] == tr.FORD]
        if fords:
            fm, _ = _mask(win, fords, jitter=0.08)
            _paint(surf, win, fm, (104, 146, 150) if not winter else (170, 190, 204), 150)
    for (x, y) in cells:
        name = grid[x][y]
        cx, cy = x * cs + cs // 2, y * cs + cs // 2
        if name == tr.FORD and cs >= 10:
            for k in range(2):
                if _h(x, y, 20 + k) < 200:
                    r = max(2, int(cs * 0.12))
                    px = cx + int(_u(x, y, 22 + k) * cs * 0.32)
                    py = cy + int(_u(x, y, 24 + k) * cs * 0.32)
                    pygame.draw.ellipse(surf, (80, 78, 70), (px - r + 1, py - r // 2 + 1, 2 * r, r + 1))
                    pygame.draw.ellipse(surf, (168, 162, 146), (px - r, py - r // 2, 2 * r, r + 1))
        elif name in (tr.RIVER, tr.LAKE) and dist.get((x, y), 1) >= 2 and _h(x, y, 30) < 110 and cs >= 10:
            px = cx + int(_u(x, y, 31) * cs * 0.3)
            py = cy + int(_u(x, y, 32) * cs * 0.3)
            w = max(4, int(cs * 0.45))
            pygame.draw.arc(surf, (140, 186, 214) if not winter else (214, 228, 238),
                            (px - w // 2, py - 2, w, max(4, cs // 4)), 0.4, 2.7, 1)
    _draw_bridges(surf, bf, cs, grid)


def _draw_bridges(surf, bf, cs, grid):
    """Ponts d'un seul tenant: tablier de planches posées en travers du
    passage, garde-corps et poteaux, ombre sur l'eau."""
    seen = set()
    for c in _all_cells(bf, grid, (tr.BRIDGE,)):
        if c in seen:
            continue
        comp, stack = [], [c]
        seen.add(c)
        while stack:
            x, y = stack.pop()
            comp.append((x, y))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if _in_map(bf, *n) and n not in seen and grid[n[0]][n[1]] == tr.BRIDGE:
                    seen.add(n)
                    stack.append(n)
        x0, x1 = min(p[0] for p in comp), max(p[0] for p in comp)
        y0, y1 = min(p[1] for p in comp), max(p[1] for p in comp)
        # Un pont franchit une rivière nord-sud: on le traverse d'ouest en est
        horizontal = (x1 - x0) >= (y1 - y0) or (y1 - y0) <= 2
        if horizontal:
            r = pygame.Rect(x0 * cs - cs // 4, y0 * cs + cs // 6, (x1 - x0 + 1) * cs + cs // 2,
                            (y1 - y0 + 1) * cs - cs // 3)
        else:
            r = pygame.Rect(x0 * cs + cs // 6, y0 * cs - cs // 4, (x1 - x0 + 1) * cs - cs // 3,
                            (y1 - y0 + 1) * cs + cs // 2)
        sh = pygame.Surface(r.size, pygame.SRCALPHA)
        sh.fill((0, 0, 0, 80))
        surf.blit(sh, (r.x + cs // 6, r.y + cs // 4))
        wood, dark = (132, 96, 58), (78, 54, 32)
        pygame.draw.rect(surf, wood, r)
        step = max(3, cs // 5)
        rail = max(2, cs // 8)
        if horizontal:
            for xx in range(r.left + step, r.right, step):
                pygame.draw.line(surf, dark, (xx, r.top + 1), (xx, r.bottom - 2), 1)
            for yy in (r.top, r.bottom - rail):
                pygame.draw.rect(surf, (96, 68, 40), (r.left, yy, r.w, rail))
                for xx in range(r.left, r.right, cs):
                    pygame.draw.rect(surf, (60, 42, 26), (xx, yy - 1, rail, rail + 2))
        else:
            for yy in range(r.top + step, r.bottom, step):
                pygame.draw.line(surf, dark, (r.left + 1, yy), (r.right - 2, yy), 1)
            for xx in (r.left, r.right - rail):
                pygame.draw.rect(surf, (96, 68, 40), (xx, r.top, rail, r.h))
        pygame.draw.rect(surf, (54, 38, 22), r, 1)


def _draw_cliffs(surf, bf, cs, bg):
    """Masses rocheuses du Défilé (obstacles indestructibles): un seul bloc
    lissé, paliers plus clairs vers le cœur, arête éclairée au nord-ouest,
    pied dans l'ombre, strates et éboulis."""
    if bf.map_name != "Défilé":
        return
    structs = getattr(bf, 'structures', None) or {}
    cells = [(x, y) for x in range(bf.width) for y in range(bf.height)
             if bf.grid[x][y] == 1 and (x, y) not in structs]
    if not cells:
        return
    big = _Win(bf, cs, _bbox(cells, 0, bf), margin=2)
    W, H = bf.width, bf.height
    all_rock = [(x, y) for x in range(big.cx0, big.cx1 + 1) for y in range(big.cy0, big.cy1 + 1)
                if bf.grid[min(W - 1, max(0, x))][min(H - 1, max(0, y))] == 1]
    s = max(2, cs // 4)
    winter = _winter(bf)
    dist = {}
    for rock in _clusters(all_rock):
        # Les poches d'une case prises dans la paroi (inaccessibles) font des
        # taches sombres: la falaise les recouvre
        rock = sorted(_fill_holes(rock, 3))
        win = big.sub(rock)
        m, _raw = _mask(win, rock, jitter=0.16)
        _paint(surf, win, _minus(_shifted(m, s, s * 2), m), (0, 0, 0), 90)
        _paint(surf, win, m, (96, 90, 80), 255)
        d = _levels(rock, 3)
        dist.update(d)
        group = [c for c in rock if d[c] >= 2]
        if group:
            # Plateau: plus clair loin du bord (enneigé l'hiver)
            gm, _ = _mask(win, group, jitter=0.25)
            _paint(surf, win, gm, (236, 240, 246) if winter else (116, 110, 100), 170 if winter else 210)
        _paint(surf, win, _minus(m, _shifted(m, s // 2 + 1, s // 2 + 1)), (150, 144, 132), 170)
        _paint(surf, win, _minus(m, _shifted(m, -s, -s)), (52, 48, 42), 150)
    # Fissures: courtes lignes brisées, plus nombreuses loin du bord
    for (x, y) in cells:
        if _h(x, y, 40) < 40 and dist.get((x, y), 1) >= 2:
            px = x * cs + (_h(x, y, 41) * cs) // 255
            py = y * cs + (_h(x, y, 42) * cs) // 255
            pts = [(px, py)]
            for k in range(3):
                px += int(_u(x, y, 43 + k) * cs * 0.35)
                py += int(cs * 0.22 + _u(x, y, 46 + k) * cs * 0.12)
                pts.append((px, py))
            pygame.draw.lines(surf, (66, 60, 52), False, pts, 1)


def draw_static(surf, bf, cs, grid, bg):
    """Terrain immuable, cuit dans la couche de sol: marais, eau (berges,
    gués, ponts), collines, falaises. `grid` = terrain de référence (celui
    du début de bataille, cf. renderer.build_ground_layer)."""
    if grid is None:
        return
    _draw_marsh(surf, bf, cs, grid, bg)
    _draw_water(surf, bf, cs, grid, bg)
    _draw_hills(surf, bf, cs, grid, bg)
    _draw_cliffs(surf, bf, cs, bg)


# ═══════════════════════════════════════════════════════════════
#   COUCHES VIVANTES (repeintes par région)
# ═══════════════════════════════════════════════════════════════

def _near(region, x, y):
    x0, y0, x1, y1 = region
    return x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1


def draw_dynamic(surf, bf, cs, region):
    """Sous-bois, décombres et brûlé des cases de `region` (x0, y0, x1, y1),
    au niveau du sol. Les arbres viennent après (tall_sprites)."""
    terr = getattr(bf, 'terrain', None)
    if terr is None:
        return
    big = _Win(bf, cs, region, margin=2)
    winter = _winter(bf)
    biome, season = look(bf)
    wood = big.cells(terr, (tr.WOOD,))
    if wood:
        floor = (104, 96, 56) if biome == "Désert" else ((170, 176, 172) if winter else (30, 46, 24))
        for group in _clusters(wood):
            win = big.sub(group)
            m, raw = _mask(win, group, jitter=0.18)
            inner, _ = _mask(win, group, raw=raw, offset=30)
            _paint(surf, win, m, floor, 150)
            _paint(surf, win, _minus(m, inner), scenery.shade(floor, -18), 90)
        litter = scenery.palette(biome, season).get('litter')
        for (x, y) in wood:
            if not _near(region, x, y) or not _in_map(bf, x, y):
                continue
            for k in range(3):
                px = x * cs + int((_h(x, y, 50 + k) / 255) * cs)
                py = y * cs + int((_h(x, y, 53 + k) / 255) * cs)
                c = litter[k % len(litter)] if litter else scenery.shade(floor, 24 - 16 * k)
                pygame.draw.circle(surf, c, (px, py), max(1, cs // 14))
    rubble = big.cells(terr, (tr.RUBBLE,))
    if rubble:
        for group in _clusters(rubble):
            win = big.sub(group)
            m, _raw = _mask(win, group, jitter=0.2)
            _paint(surf, win, m, (168, 166, 164) if winter else (96, 88, 78), 200)
        for (x, y) in rubble:
            if not _near(region, x, y) or not _in_map(bf, x, y):
                continue
            cx, cy = x * cs + cs // 2, y * cs + cs // 2
            scenery.blit(surf, "gravats_tas" if _h(x, y, 60) < 128 else "gravats",
                         _h(x, y, 61), cx + int(_u(x, y, 62) * cs * 0.2),
                         cy + int(_u(x, y, 63) * cs * 0.2), cs, biome, season)
            if _h(x, y, 64) < 70 and cs >= 10:
                pygame.draw.line(surf, (44, 32, 24), (x * cs + 2, y * cs + cs - 3),
                                 (x * cs + cs - 3, y * cs + cs // 3), max(2, cs // 9))
    burnt = big.cells(terr, (tr.BURNT,))
    if burnt:
        for group in _clusters(burnt):
            win = big.sub(group)
            m, raw = _mask(win, group, jitter=0.2)
            inner, _ = _mask(win, group, raw=raw, offset=30)
            _paint(surf, win, m, (30, 26, 22), 185)
            _paint(surf, win, inner, (18, 16, 14), 90)
        for (x, y) in burnt:
            if not _near(region, x, y) or not _in_map(bf, x, y):
                continue
            for k in range(4):
                px = x * cs + int((_h(x, y, 70 + k) / 255) * cs)
                py = y * cs + int((_h(x, y, 74 + k) / 255) * cs)
                pygame.draw.circle(surf, (86, 80, 74), (px, py), max(1, cs // 16))
            if _h(x, y, 78) < 90 and cs >= 10:
                sx = x * cs + cs // 2 + int(_u(x, y, 79) * cs * 0.2)
                sy = y * cs + cs // 2
                pygame.draw.circle(surf, (12, 10, 8), (sx, sy), max(2, cs // 7))
                pygame.draw.circle(surf, (58, 46, 34), (sx - 1, sy - 1), max(1, cs // 12))


# Essences des bois, par biome: (nature, poids)
_WOOD_TREES = {
    "Prairie": (("arbre_rond", 7), ("arbre_pin", 2)),
    "Forêt": (("arbre_rond", 5), ("arbre_pin", 4)),
    "Désert": (("palmier", 1),),
}


def _pick(table, v):
    total = sum(w for _, w in table)
    r = v * total / 256.0
    acc = 0
    for kind, w in table:
        acc += w
        if r < acc:
            return kind
    return table[-1][0]


def tall_sprites(bf, cs, region):
    """Arbres des cases de bois autour de `region` (une case de plus: les
    houppiers débordent): [(y, nature, variante, x, y, état)]. Une case sur
    deux environ porte un arbre, les autres un buisson ou une fougère: le
    bois reste un sous-bois praticable, on y voit passer les troupes. Les
    cœurs de bosquet (obstacles) sont dessinés plus denses (renderer)."""
    terr = getattr(bf, 'terrain', None)
    if terr is None:
        return []
    x0, y0, x1, y1 = region
    biome, _season = look(bf)
    table = _WOOD_TREES.get(biome, _WOOD_TREES["Prairie"])
    fires = getattr(bf, 'fires', None) or {}
    out = []
    for x in range(max(0, x0 - 1), min(bf.width - 1, x1 + 1) + 1):
        col = terr[x]
        for y in range(max(0, y0 - 1), min(bf.height - 1, y1 + 1) + 1):
            if col[y] != tr.WOOD or bf.grid[x][y] != 0:
                continue
            v = _h(x, y, 90)
            px = x * cs + cs // 2 + int(_u(x, y, 91) * cs * 0.28)
            py = y * cs + cs // 2 + int(_u(x, y, 92) * cs * 0.28)
            if v < 140:
                state = 3 if (x, y) in fires else 0
                out.append((py, _pick(table, _h(x, y, 93)), _h(x, y, 94), px, py, state))
            elif v < 205:
                kind = "buisson_sec" if biome == "Désert" else "buisson"
                out.append((py, kind, _h(x, y, 95), px, py, 0))
            elif biome != "Désert":
                out.append((py, "fougere", _h(x, y, 96), px, py, 0))
    return out


# ═══════════════════════════════════════════════════════════════
#   LÉGENDE
# ═══════════════════════════════════════════════════════════════

def draw_cell(ov, name, r, cs, sd=0, edges=(False, False, False, False)):
    """Case isolée à motif plat (la légende du feu)."""
    x0, y0 = r.x, r.y
    if name == FIRE:
        ov.fill((70, 26, 8, 230), r)
        for k in range(3):
            fx = x0 + cs * (k + 1) // 4
            pygame.draw.polygon(ov, (255, 150 + 40 * k, 40, 255),
                                [(fx - cs // 8, y0 + cs - 3), (fx, y0 + cs // 4 + k * 2),
                                 (fx + cs // 8, y0 + cs - 3)])


class _FakeField:
    """Petit champ de bataille pour dessiner une vignette de légende avec
    les vrais moteurs de rendu."""

    def __init__(self, name, n=5, theme=None):
        self.width = self.height = n
        self.map_name = "Prairie"
        self.theme = theme
        self.grid = [[0] * n for _ in range(n)]
        c = n // 2
        blob = {(c, c), (c + 1, c), (c - 1, c), (c, c + 1), (c, c - 1), (c + 1, c + 1)}
        self.terrain = [[name if (x, y) in blob else tr.PLAIN for y in range(n)] for x in range(n)]
        if name in (tr.FORD, tr.BRIDGE):
            for x in range(n):
                for y in range(n):
                    self.terrain[x][y] = name if x == c else (tr.RIVER if abs(y - c) <= 1 else tr.PLAIN)
        self.fires = {}
        self.structures = {}


def swatch(name, size, bg, theme=None):
    """Vignette `size`×`size` d'un terrain, rendue comme sur la carte."""
    s = pygame.Surface((size, size))
    s.fill(bg)
    if name == FIRE:
        draw_cell(s, FIRE, pygame.Rect(0, 0, size, size), size)
        return s
    n = 5
    cs = max(6, size // 2)
    fake = _FakeField(name, n, theme)
    big = pygame.Surface((n * cs, n * cs))
    big.fill(bg)
    if name in STATIC:
        draw_static(big, fake, cs, fake.terrain, bg)
    else:
        draw_dynamic(big, fake, cs, (0, 0, n - 1, n - 1))
        for (_y, kind, v, px, py, st) in sorted(tall_sprites(fake, cs, (0, 0, n - 1, n - 1))):
            scenery.blit(big, kind, v, px, py, cs, *look(fake), state=st)
    crop = pygame.Rect(0, 0, int(cs * 2.4), int(cs * 2.4))
    crop.center = (n * cs // 2, n * cs // 2)
    return pygame.transform.smoothscale(big.subsurface(crop), (size, size))


def legend_surface(bf, font):
    """Encart des terrains présents sur la carte (None s'il n'y en a pas)."""
    if getattr(bf, 'terrain', None) is None:
        return None
    present = {n for col in bf.terrain for n in col}
    if getattr(bf, 'structures', None):
        # Tout ce qui peut brûler ou s'effondrer: la légende l'annonce d'emblée
        present |= {tr.RUBBLE, tr.BURNT, FIRE}
    rows = [n for n in _ORDER if n in present]
    if not rows:
        return None
    sw, pad, gap = 22, 10, 6
    texts = [font.render(LEGEND[n], True, T.PARCHMENT) for n in rows]
    title = T.gold_text("Terrain  (L pour masquer)", T.font('title', max(12, font.get_height())))
    w = pad * 2 + max([sw + 10 + t.get_width() for t in texts] + [title.get_width()])
    h = pad * 2 + title.get_height() + gap + sum(max(sw, t.get_height()) + gap for t in texts)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    T.glass(surf, surf.get_rect(), 225, 8)
    T.corner_marks(surf, surf.get_rect(), T.GOLD_DIM, 6)
    surf.blit(title, (pad, pad))
    from maps import theme_info
    bg = theme_info(bf)["bg_color"]
    theme = getattr(bf, 'theme', None)
    y = pad + title.get_height() + gap
    for n, t in zip(rows, texts):
        box = pygame.Rect(pad, y, sw, sw)
        surf.blit(swatch(n, sw, bg, theme), box)
        pygame.draw.rect(surf, (*T.GOLD_DIM, 220), box, 1)
        surf.blit(t, (pad + sw + 10, y + (sw - t.get_height()) // 2))
        y += max(sw, t.get_height()) + gap
    return surf
