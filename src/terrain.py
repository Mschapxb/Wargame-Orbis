"""Terrain à effets — la SEULE source de vérité des règles de terrain.

Le moteur (déplacement, combat) et l'IA (estimation des dégâts, ciblage)
appellent ces fonctions: ils voient donc exactement les mêmes chiffres.

La grille `bf.terrain` est parallèle à `bf.grid` et ne la remplace pas:
`grid` dit ce qui est physiquement bâti (obstacle, mur, porte…), `terrain`
dit sur quoi l'on marche. Une carte sans terrain (`bf.terrain is None`) se
joue exactement comme avant: toutes les fonctions rendent la valeur neutre.

Convention des seuils (d6): un seuil plus HAUT est plus DIFFICILE.
`combat_mods` renvoie des valeurs à AJOUTER aux seuils.
"""

PLAIN, HILL, WOOD, RIVER, FORD, BRIDGE, MARSH = (
    "plaine", "colline", "bois", "riviere", "gue", "pont", "marais")

TERRAINS = {
    PLAIN:  dict(move=1.0,  passable=True,  charge=True,  save_mod=0,  cover=0, blocks_los=0, elevated=False),
    HILL:   dict(move=1.0,  passable=True,  charge=True,  save_mod=0,  cover=0, blocks_los=0, elevated=True),
    WOOD:   dict(move=2.0,  passable=True,  charge=False, save_mod=0,  cover=1, blocks_los=1, elevated=False),
    RIVER:  dict(move=None, passable=False, charge=False, save_mod=0,  cover=0, blocks_los=0, elevated=False),
    FORD:   dict(move=2.0,  passable=True,  charge=False, save_mod=-1, cover=0, blocks_los=0, elevated=False),
    BRIDGE: dict(move=1.0,  passable=True,  charge=True,  save_mod=0,  cover=0, blocks_los=0, elevated=False),
    MARSH:  dict(move=3.0,  passable=True,  charge=False, save_mod=-1, cover=0, blocks_los=0, elevated=False),
}

# Accès rapides pour les boucles chaudes (A*)
MOVE = {name: t['move'] for name, t in TERRAINS.items()}
ELEVATED = frozenset(name for name, t in TERRAINS.items() if t['elevated'])
# (coût, élevé?) en un seul lookup au lieu de deux (MOVE[name] puis
# name in ELEVATED) dans la boucle A* — dérivé de TERRAINS, qui ne
# change jamais en cours de partie: aucun risque de péremption, ce
# n'est pas un cache par bataille, juste une table de règles statique
# comme MOVE/ELEVATED ci-dessus.
MOVE_ELEV = {name: (t['move'], t['elevated']) for name, t in TERRAINS.items()}

UPHILL_FACTOR = 1.5     # monter sur une colline coûte plus cher
WOODS_BLOCKING = 3      # nombre de cases de bois qui masquent un tir
_NO_MODS = {'toucher': 0, 'save': 0}
_INF = float('inf')


def make_grid(width, height, fill=PLAIN):
    return [[fill] * height for _ in range(width)]


def at(bf, x, y):
    terr = getattr(bf, 'terrain', None)
    if terr is None:
        return PLAIN
    return terr[x][y]


def is_passable(bf, x, y):
    return TERRAINS[at(bf, x, y)]['passable']


def is_elevated(bf, x, y):
    return at(bf, x, y) in ELEVATED


def charge_ok(bf, x, y):
    return TERRAINS[at(bf, x, y)]['charge']


def step_cost(bf, frm, to):
    """Multiplicateur de coût d'un pas de `frm` vers la case voisine `to`."""
    if getattr(bf, 'terrain', None) is None:
        return 1.0
    dest = bf.terrain[to[0]][to[1]]
    m = MOVE[dest]
    if m is None:
        return _INF
    if dest in ELEVATED and bf.terrain[frm[0]][frm[1]] not in ELEVATED:
        m *= UPHILL_FACTOR
    return m


def move_cost(bf, frm, to):
    """Coût d'un déplacement direct (en pas de Chebyshev) vers `to`."""
    steps = max(abs(to[0] - frm[0]), abs(to[1] - frm[1]))
    return steps * step_cost(bf, frm, to)


def path_cost(bf, start, path):
    total, prev = 0.0, start
    for cell in path:
        total += step_cost(bf, prev, cell)
        prev = cell
    return total


def steps_within(bf, start, path, budget):
    """Nombre de pas du chemin que le budget permet. Au moins 1 pas si le
    budget vaut au moins 1 (sinon une unité lente resterait figée dans un
    marais)."""
    if not path or budget < 1:
        return 0
    if getattr(bf, 'terrain', None) is None:
        return min(int(budget), len(path))
    spent, prev, n = 0.0, start, 0
    for cell in path:
        c = step_cost(bf, prev, cell)
        if c == _INF:
            break
        if n >= 1 and spent + c > budget:
            break
        spent += c
        n += 1
        prev = cell
    return n


def can_charge(bf, frm, to):
    return charge_ok(bf, *frm) and charge_ok(bf, *to)


def range_bonus(bf, shooter, target):
    """+1 de portée pour un tireur en hauteur visant une cible en contrebas.

    Appelé très souvent (par ennemi, par unité, par round): le corps est
    inliné (au lieu de deux appels à is_elevated -> at -> getattr) pour
    rester bon marché, sans introduire de cache — `terr` est relu à
    chaque appel, donc toujours à jour même si bf.terrain est réassigné
    entre deux appels."""
    if shooter._max_range < 4:
        return 0
    terr = getattr(bf, 'terrain', None)
    if terr is None:
        return 0
    sx, sy = shooter.position
    if terr[sx][sy] not in ELEVATED:
        return 0
    tx, ty = target.position
    return 0 if terr[tx][ty] in ELEVATED else 1


def effective_range(bf, shooter, target):
    return shooter._max_range + range_bonus(bf, shooter, target)


def weapon_reach(bf, arme, shooter, target):
    if arme.porte >= 4:
        return arme.porte + range_bonus(bf, shooter, target)
    return arme.porte


def combat_mods(bf, attacker, target, ranged):
    if getattr(bf, 'terrain', None) is None:
        return dict(_NO_MODS)
    t = TERRAINS[at(bf, *target.position)]
    toucher = 0
    if ranged:
        toucher += t['cover']
    elif t['elevated'] and not is_elevated(bf, *attacker.position):
        toucher += 1
    return {'toucher': toucher, 'save': -t['save_mod']}


def line_cells(x0, y0, x1, y1):
    """Cases intermédiaires d'un tracé de Bresenham (extrémités exclues).
    Même tracé que Battlefield._los_clear."""
    cells = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x1 > x0 else -1
    sy = 1 if y1 > y0 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        if (x != x0 or y != y0) and (x != x1 or y != y1):
            cells.append((x, y))
        if x == x1 and y == y1:
            return cells
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def blocks_line(bf, x0, y0, x1, y1):
    """Vrai si le terrain masque la cible. Un tireur en hauteur voit tout;
    sinon une colline intermédiaire (cible hors colline) ou 3 cases de bois
    bloquent."""
    terr = getattr(bf, 'terrain', None)
    if terr is None or terr[x0][y0] in ELEVATED:
        return False
    target_up = terr[x1][y1] in ELEVATED
    woods = 0
    for x, y in line_cells(x0, y0, x1, y1):
        name = terr[x][y]
        if name in ELEVATED and not target_up:
            return True
        if TERRAINS[name]['blocks_los']:
            woods += 1
            if woods >= WOODS_BLOCKING:
                return True
    return False
