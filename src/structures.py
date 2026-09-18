"""Structures destructibles — la SEULE source de vérité des règles de
destruction (maisons, haies, bosquets, rochers, palissades) et d'incendie.

Comme terrain.py, ce module ne dépend pas de Pygame: le moteur, l'IA et les
tests appellent les mêmes fonctions.

Une structure occupe des cases `grid == 1` tant qu'elle tient. Ses points de
vie sont portés par GROUPE: une maison de 3×2 est une seule structure de six
cases, qu'on entame en frappant n'importe laquelle et qui s'effondre d'un
bloc. Haies et bosquets forment un groupe par case (ils brûlent de proche en
proche). À l'effondrement, les cases redeviennent franchissables et prennent
le terrain laissé par la structure (décombres ou brûlé).

État porté par le Battlefield (cf. attach):
    structures        {(x, y): (kind, gid)}
    structure_hp      {gid: pv restants}
    structure_max_hp  {gid: pv initiaux}
    structure_members {gid: [(x, y), ...]}
    structure_kind    {gid: kind}
    fires             {(x, y): rounds de combustion restants}
    dirty_cells       set des cases dont l'aspect a changé (lu par le rendu)
"""

import terrain as tr
import weather

HOUSE, HEDGE, GROVE, ROCK, PALISADE, WALL = (
    "maison", "haie", "bosquet", "rocher", "palissade", "mur")

KINDS = {
    HOUSE:    dict(hp=14, save=4, flammable=0.15, burn=4, leaves=tr.RUBBLE, heavy_only=False),
    HEDGE:    dict(hp=4,  save=6, flammable=0.35, burn=2, leaves=tr.BURNT,  heavy_only=False),
    GROVE:    dict(hp=6,  save=5, flammable=0.25, burn=3, leaves=tr.BURNT,  heavy_only=False),
    ROCK:     dict(hp=16, save=3, flammable=0.0,  burn=0, leaves=tr.RUBBLE, heavy_only=True),
    PALISADE: dict(hp=8,  save=5, flammable=0.20, burn=3, leaves=tr.RUBBLE, heavy_only=False),
    # Mur de siège (grid 2): seules les machines de guerre le percent
    WALL:     dict(hp=24, save=2, flammable=0.0,  burn=0, leaves=tr.RUBBLE, heavy_only=True),
}
WALL_SEGMENT = 3             # cases de mur par tronçon (un tronçon = une brèche)

# Structures d'un seul tenant: toutes les cases 4-connexes forment un groupe
_MERGED = frozenset((HOUSE, PALISADE))

# Sous-bois (terrain WOOD sans structure): il brûle aussi
UNDERBRUSH_FLAMMABLE = 0.20
UNDERBRUSH_BURN = 2

FIREBALL_IGNITE = 0.5        # chance d'allumer chaque case combustible touchée
FIRE_DAMAGE = 2              # PV perdus par round par une structure en feu
MAX_IGNITIONS_PER_ROUND = 8  # un feu de forêt reste un événement, pas la fin de la carte
HEAVY_AVG_DAMAGE = 3.0       # dégâts moyens d'une arme lourde (catapulte)

_N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


# ═══════════════════════════════════════════════════════════════
#                     CONSTRUCTION
# ═══════════════════════════════════════════════════════════════

def _components(cells):
    """Composantes 4-connexes d'un ensemble de cases, dans un ordre stable."""
    cells = set(cells)
    seen = set()
    comps = []
    for start in sorted(cells):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        comp = []
        while stack:
            cx, cy = stack.pop()
            comp.append((cx, cy))
            for dx, dy in _N4:
                n = (cx + dx, cy + dy)
                if n in cells and n not in seen:
                    seen.add(n)
                    stack.append(n)
        comps.append(sorted(comp))
    return comps


def classify_village(grid, width, height):
    """Maisons et haies d'un village. Une maison est un bloc PLEIN d'au moins
    2×2; tout le reste (anneau de haie, alignements d'une case) est une haie.
    Le rendu (renderer.draw_village_buildings) suit la même règle."""
    obstacles = [(x, y) for x in range(width) for y in range(height) if grid[x][y] == 1]
    out = {}
    for comp in _components(obstacles):
        xs = [c[0] for c in comp]
        ys = [c[1] for c in comp]
        bw, bh = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        kind = HOUSE if (len(comp) == bw * bh and bw >= 2 and bh >= 2) else HEDGE
        for c in comp:
            out[c] = kind
    return out


def _wall_segments(cells):
    """Tronçons de mur: portions verticales contiguës découpées par 3."""
    segs, run = [], []
    for c in sorted(cells):
        if run and (c[0] != run[-1][0] or c[1] != run[-1][1] + 1):
            segs.append(run)
            run = []
        run.append(c)
    if run:
        segs.append(run)
    out = []
    for run in segs:
        for i in range(0, len(run), WALL_SEGMENT):
            out.append(run[i:i + WALL_SEGMENT])
    return out


def build_groups(struct_map):
    """{(x, y): kind} → (cells, hp, members, kinds), gid stables (ordre des cases)."""
    by_kind = {}
    for pos, kind in struct_map.items():
        by_kind.setdefault(kind, []).append(tuple(pos))
    groups = []
    for kind in sorted(by_kind):
        if kind in _MERGED:
            groups.extend((kind, comp) for comp in _components(by_kind[kind]))
        elif kind == WALL:
            groups.extend((kind, seg) for seg in _wall_segments(by_kind[kind]))
        else:
            groups.extend((kind, [c]) for c in sorted(by_kind[kind]))
    groups.sort(key=lambda g: g[1][0])
    cells, hp, members, kinds = {}, {}, {}, {}
    for gid, (kind, comp) in enumerate(groups):
        for c in comp:
            cells[c] = (kind, gid)
        hp[gid] = KINDS[kind]['hp']
        members[gid] = comp
        kinds[gid] = kind
    return cells, hp, members, kinds


def attach(bf, struct_map):
    """Installe les structures (et l'état d'incendie) sur un Battlefield."""
    cells, hp, members, kinds = build_groups(struct_map or {})
    bf.structures = cells
    bf.structure_hp = hp
    bf.structure_max_hp = dict(hp)
    bf.structure_members = members
    bf.structure_kind = kinds
    bf.fires = {}
    bf.dirty_cells = set()
    bf.breaches = set()      # entrées ouvertes dans le mur de siège
    if cells and bf.terrain is None:
        # Une structure détruite laisse un terrain: il faut une grille (plaine
        # partout = neutre, cf. terrain.py)
        bf.terrain = tr.make_grid(bf.width, bf.height)


# ═══════════════════════════════════════════════════════════════
#                     REQUÊTES
# ═══════════════════════════════════════════════════════════════

def group_at(bf, x, y):
    entry = bf.structures.get((x, y)) if getattr(bf, 'structures', None) else None
    return None if entry is None else entry[1]


def flammability(bf, x, y):
    """Probabilité qu'une case prenne feu depuis une voisine (0 = incombustible)."""
    entry = bf.structures.get((x, y)) if getattr(bf, 'structures', None) else None
    if entry is not None:
        return KINDS[entry[0]]['flammable']
    terr = bf.terrain
    if terr is not None and bf.grid[x][y] == 0 and terr[x][y] == tr.WOOD:
        return UNDERBRUSH_FLAMMABLE
    return 0.0


def is_heavy(arme):
    """Arme capable d'entamer la pierre (rocher)."""
    from tactics import _avg_roll
    return _avg_roll(arme) >= HEAVY_AVG_DAMAGE


def weapon_factor(kind, arme):
    """Part des dégâts d'une arme qui porte sur une structure.

    Le mur ne cède qu'aux machines de guerre: la catapulte (dégâts moyens
    ≥ 3) frappe plein pot, la baliste (≥ 2) à moitié — elle perce, mais
    lentement; le reste ne fait rien. La pierre d'un rocher exige une arme
    lourde. Bois, haies et palissades encaissent tout."""
    from tactics import _avg_roll
    avg = _avg_roll(arme)
    if kind == WALL:
        if arme.porte < 12:
            return 0.0
        return 1.0 if avg >= HEAVY_AVG_DAMAGE else (0.5 if avg >= 2.0 else 0.0)
    if KINDS[kind]['heavy_only']:
        return 1.0 if avg >= HEAVY_AVG_DAMAGE else 0.0
    return 1.0


def first_structure_on_line(bf, x0, y0, x1, y1):
    """Première case de structure rencontrée entre deux cases (extrémités
    exclues), ou None — y compris si un obstacle indestructible masque avant."""
    if not getattr(bf, 'structures', None):
        return None
    for (x, y) in tr.line_cells(x0, y0, x1, y1):
        if (x, y) in bf.structures:
            return (x, y)
        if bf.grid[x][y] in (1, 2):
            return None
    return None


def damage_level(bf, gid):
    """État visible: 0 intact, 1 entamé, 2 ruiné. Le rendu ne repeint une
    structure qu'au changement de niveau."""
    return _level(bf.structure_hp.get(gid, 0), bf.structure_max_hp.get(gid, 1))


def _level(hp, max_hp):
    pct = hp / max(1, max_hp)
    return 0 if pct > 0.66 else (1 if pct > 0.33 else 2)


# ═══════════════════════════════════════════════════════════════
#                     DESTRUCTION
# ═══════════════════════════════════════════════════════════════

def damage(bf, gid, amount, heavy=False):
    """Inflige des dégâts à un groupe. True s'il s'effondre."""
    if gid not in bf.structure_members or bf.structure_hp.get(gid, 0) <= 0:
        return False
    if KINDS[bf.structure_kind[gid]]['heavy_only'] and not heavy:
        return False
    max_hp = bf.structure_max_hp[gid]
    before = bf.structure_hp[gid]
    bf.structure_hp[gid] = max(0, before - int(amount))
    if _level(before, max_hp) != _level(bf.structure_hp[gid], max_hp):
        bf.dirty_cells.update(bf.structure_members[gid])
    if bf.structure_hp[gid] <= 0:
        collapse(bf, gid)
        return True
    return False


def collapse(bf, gid):
    """Effondrement: cases libérées, terrain laissé, feu éteint. Retourne les
    cases touchées."""
    kind = bf.structure_kind[gid]
    leaves = KINDS[kind]['leaves']
    cells = bf.structure_members[gid]
    bf.structure_hp[gid] = 0
    for (x, y) in cells:
        bf.grid[x][y] = 0
        bf.terrain[x][y] = leaves
        bf.structures.pop((x, y), None)
        bf.fires.pop((x, y), None)
        bf.dirty_cells.add((x, y))
    extra = []
    if kind == WALL:
        # Brèche: le chemin de ronde et l'escalier de ces rangées
        # s'écroulent avec le mur; l'entrée est enregistrée pour l'assaut.
        for (x, y) in cells:
            bf.walls.discard((x, y))
            for dx in (1, 2, 3):
                c = (x + dx, y)
                if c in bf.ramparts or c in bf.stairs:
                    bf.ramparts.discard(c)
                    bf.stairs.discard(c)
                    bf.grid[c[0]][c[1]] = 0
                    bf.terrain[c[0]][c[1]] = tr.RUBBLE
                    bf.dirty_cells.add(c)
                    extra.append(c)
        bf.breaches.add(cells[len(cells) // 2])
    return list(cells) + extra


def ignite(bf, x, y):
    """Met le feu à une case (et à toute sa structure). True si ça prend."""
    if (x, y) in bf.fires or flammability(bf, x, y) <= 0:
        return False
    entry = bf.structures.get((x, y))
    if entry is not None:
        kind, gid = entry
        burn = KINDS[kind]['burn']
        for c in bf.structure_members[gid]:
            bf.fires.setdefault(c, burn)
            bf.dirty_cells.add(c)
    else:
        bf.fires[(x, y)] = UNDERBRUSH_BURN
        bf.dirty_cells.add((x, y))
    return True


def fire_step(bf, rng):
    """Un round d'incendie: propagation (plafonnée), combustion, fin de feu.

    Retourne {'ignited': [(x, y)], 'collapsed': [(gid, kind, cells)],
    'burnt': [(x, y)]}. Tout le hasard passe par `rng` (le random global du
    moteur), dans un ordre déterministe."""
    out = {'ignited': [], 'collapsed': [], 'burnt': []}
    if not bf.fires:
        return out
    burning = sorted(bf.fires)

    # ── Propagation, depuis les foyers du début de round ──
    seen = set(burning)
    candidates = []
    spread_dx = {}           # sens de propagation (vent: weather.py)
    for (x, y) in burning:
        for dx, dy in _N4:
            n = (x + dx, y + dy)
            if n in seen or not (0 <= n[0] < bf.width and 0 <= n[1] < bf.height):
                continue
            seen.add(n)
            if flammability(bf, *n) > 0:
                candidates.append(n)
                spread_dx[n] = dx
    w = weather.of(bf)
    # Mélangés, pas triés: sous le plafond, un tri par position servirait
    # toujours l'ouest en premier et recréerait un biais de côté.
    rng.shuffle(candidates)
    for c in candidates:
        if len(out['ignited']) >= MAX_IGNITIONS_PER_ROUND:
            break
        if c in bf.fires:
            continue  # gagné entre-temps par l'allumage d'une maison entière
        if rng.random() < flammability(bf, *c) * w.ignite_factor(spread_dx[c]) and ignite(bf, *c):
            out['ignited'].append(c)

    # ── Combustion (les nouveaux foyers ne brûlent qu'au round suivant) ──
    hurt = []
    for c in burning:
        if c not in bf.fires:
            continue
        bf.fires[c] -= 1 + w.extra_burn()
        entry = bf.structures.get(c)
        if entry is not None and entry[1] not in hurt:
            hurt.append(entry[1])
    for gid in hurt:
        if bf.structure_hp.get(gid, 0) <= 0:
            continue
        kind = bf.structure_kind[gid]
        cells = list(bf.structure_members[gid])
        consumed = any(bf.fires.get(c, 1) <= 0 for c in cells)
        if damage(bf, gid, FIRE_DAMAGE):
            out['collapsed'].append((gid, kind, cells))
        elif consumed:
            collapse(bf, gid)
            out['collapsed'].append((gid, kind, cells))

    # ── Sous-bois consumé ──
    for c in burning:
        if c in bf.fires and bf.fires[c] <= 0 and c not in bf.structures:
            del bf.fires[c]
            bf.terrain[c[0]][c[1]] = tr.BURNT
            bf.dirty_cells.add(c)
            out['burnt'].append(c)
    return out
