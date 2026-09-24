"""Tests du terrain à effets (chantier 1a). Script exécutable:
    python test_terrain.py            # tout
    python test_terrain.py charge     # seulement les tests dont le nom contient 'charge'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import terrain as tr

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


class FakeBF:
    def __init__(self, w=12, h=8, cells=None, with_terrain=True):
        self.width, self.height = w, h
        self.terrain = tr.make_grid(w, h) if with_terrain else None
        for (x, y), name in (cells or {}).items():
            self.terrain[x][y] = name


class U:
    def __init__(self, pos, max_range=1):
        self.position = pos
        self._max_range = max_range
        self.size = 1


# ── terrain.py: règles pures ──

@test
def test_no_terrain_is_neutral():
    bf = FakeBF(with_terrain=False)
    a, b = U((1, 1), 8), U((6, 1))
    assert tr.at(bf, 3, 3) == tr.PLAIN
    assert tr.is_passable(bf, 3, 3)
    assert tr.step_cost(bf, (1, 1), (2, 2)) == 1.0
    assert tr.range_bonus(bf, a, b) == 0
    assert tr.combat_mods(bf, a, b, True) == {'toucher': 0, 'save': 0}
    assert tr.blocks_line(bf, 0, 0, 10, 0) is False
    assert tr.steps_within(bf, (0, 0), [(1, 0), (2, 0), (3, 0)], 2) == 2


@test
def test_step_costs():
    bf = FakeBF(cells={(2, 0): tr.WOOD, (3, 0): tr.MARSH, (4, 0): tr.RIVER,
                       (5, 0): tr.HILL, (6, 0): tr.HILL, (7, 0): tr.FORD, (8, 0): tr.BRIDGE})
    assert tr.step_cost(bf, (1, 0), (2, 0)) == 2.0
    assert tr.step_cost(bf, (2, 0), (3, 0)) == 3.0
    assert tr.step_cost(bf, (3, 0), (4, 0)) == float('inf')
    assert not tr.is_passable(bf, 4, 0)
    assert tr.step_cost(bf, (4, 1), (5, 0)) == 1.5   # on monte
    assert tr.step_cost(bf, (5, 0), (6, 0)) == 1.0   # déjà en haut
    assert tr.step_cost(bf, (6, 0), (7, 0)) == 2.0
    assert tr.step_cost(bf, (7, 0), (8, 0)) == 1.0
    assert tr.move_cost(bf, (0, 2), (2, 0)) == 2.0 * 2.0  # 2 pas vers un bois


@test
def test_steps_within_budget():
    bf = FakeBF(cells={(1, 0): tr.WOOD, (2, 0): tr.WOOD, (3, 0): tr.MARSH})
    path = [(1, 0), (2, 0), (3, 0)]
    assert tr.steps_within(bf, (0, 0), path, 4) == 2        # 2 + 2
    assert tr.steps_within(bf, (0, 0), path, 3) == 1
    assert tr.steps_within(bf, (2, 0), [(3, 0)], 2) == 1    # au moins 1 pas
    assert tr.steps_within(bf, (0, 0), path, 0) == 0
    assert tr.steps_within(bf, (0, 0), [], 5) == 0
    assert tr.path_cost(bf, (0, 0), path) == 7.0


@test
def test_charge_rules():
    bf = FakeBF(cells={(2, 2): tr.WOOD, (3, 3): tr.FORD, (4, 4): tr.MARSH, (5, 5): tr.HILL})
    assert tr.can_charge(bf, (0, 0), (1, 1))
    assert not tr.can_charge(bf, (2, 2), (1, 1))   # départ en bois
    assert not tr.can_charge(bf, (0, 0), (2, 2))   # impact en bois
    assert not tr.can_charge(bf, (0, 0), (3, 3))
    assert not tr.can_charge(bf, (0, 0), (4, 4))
    assert tr.can_charge(bf, (0, 0), (5, 5))


@test
def test_hill_range_bonus():
    bf = FakeBF(cells={(1, 1): tr.HILL, (6, 1): tr.HILL})
    archer_up = U((1, 1), 8)
    assert tr.range_bonus(bf, archer_up, U((5, 1))) == 1
    assert tr.effective_range(bf, archer_up, U((5, 1))) == 9
    assert tr.range_bonus(bf, archer_up, U((6, 1))) == 0     # cible aussi en hauteur
    assert tr.range_bonus(bf, U((2, 2), 8), U((5, 1))) == 0  # tireur en plaine
    assert tr.range_bonus(bf, U((1, 1), 1), U((2, 1))) == 0  # mêlée: pas de bonus

    class A:
        porte = 8
    class M:
        porte = 1
    assert tr.weapon_reach(bf, A, archer_up, U((5, 1))) == 9
    assert tr.weapon_reach(bf, M, archer_up, U((5, 1))) == 1


@test
def test_combat_mods():
    bf = FakeBF(cells={(5, 1): tr.WOOD, (5, 2): tr.HILL, (5, 3): tr.FORD,
                       (5, 4): tr.MARSH, (4, 2): tr.HILL})
    shooter = U((0, 0), 8)
    assert tr.combat_mods(bf, shooter, U((5, 1)), True) == {'toucher': 1, 'save': 0}
    assert tr.combat_mods(bf, U((4, 1)), U((5, 1)), False) == {'toucher': 0, 'save': 0}
    assert tr.combat_mods(bf, U((6, 2)), U((5, 2)), False) == {'toucher': 1, 'save': 0}
    assert tr.combat_mods(bf, U((4, 2)), U((5, 2)), False) == {'toucher': 0, 'save': 0}
    assert tr.combat_mods(bf, shooter, U((5, 2)), True) == {'toucher': 0, 'save': 0}
    assert tr.combat_mods(bf, U((4, 3)), U((5, 3)), False) == {'toucher': 0, 'save': 1}
    assert tr.combat_mods(bf, shooter, U((5, 4)), True) == {'toucher': 0, 'save': 1}


@test
def test_line_of_sight():
    bf = FakeBF(w=14, cells={(3, 0): tr.WOOD, (4, 0): tr.WOOD, (5, 0): tr.WOOD,
                             (3, 2): tr.WOOD, (4, 2): tr.WOOD,
                             (0, 0): tr.PLAIN})
    assert tr.line_cells(0, 0, 3, 0) == [(1, 0), (2, 0)]
    assert tr.blocks_line(bf, 0, 0, 8, 0) is True     # 3 bois intermédiaires
    assert tr.blocks_line(bf, 0, 2, 8, 2) is False    # 2 bois seulement
    bf.terrain[0][0] = tr.HILL
    assert tr.blocks_line(bf, 0, 0, 8, 0) is False    # tireur en hauteur
    bf2 = FakeBF(w=14, cells={(4, 4): tr.HILL})
    assert tr.blocks_line(bf2, 0, 4, 8, 4) is True    # colline entre les deux
    bf2.terrain[8][4] = tr.HILL
    assert tr.blocks_line(bf2, 0, 4, 8, 4) is False   # cible sur la colline


# ── Battlefield ──

import spatial
from battlefield import Battlefield


class FakeBattle(spatial.Neighbourhood):
    army1 = army2 = ()

    def get_allies(self, unit):
        return []

    def get_enemies(self, unit):
        return []


def real_bf(w=16, h=9, cells=None, grid=None):
    terr = tr.make_grid(w, h)
    for (x, y), name in (cells or {}).items():
        terr[x][y] = name
    g = grid or [[0] * h for _ in range(w)]
    return Battlefield(w, h, 0, "Prairie", g, {'terrain': terr})


@test
def test_bf_terrain_not_siege():
    bf = real_bf()
    assert bf.terrain is not None
    assert not bf.siege_data, "le terrain ne doit pas faire croire à un siège"
    plain = Battlefield(10, 6, 0, "Prairie", [[0] * 6 for _ in range(10)], {})
    assert plain.terrain is None


@test
def test_bf_river_invalid():
    bf = real_bf(cells={(5, 3): tr.RIVER})
    assert not bf.is_valid(5, 3)
    assert bf.is_valid(5, 4)


@test
def test_astar_avoids_marsh_and_river():
    w, h = 16, 9
    marsh = {(x, y): tr.MARSH for x in range(6, 10) for y in range(0, 6)}
    bf = real_bf(w, h, cells=marsh)
    u = U((2, 3))
    path = bf.a_star_path((2, 3), (13, 3), u, FakeBattle())
    assert path and path[-1] == (13, 3)
    assert not any(bf.terrain[x][y] == tr.MARSH for x, y in path), path
    river = {(8, y): tr.RIVER for y in range(h)}
    river[(8, 7)] = tr.FORD
    bf2 = real_bf(w, h, cells=river)
    path2 = bf2.a_star_path((2, 3), (13, 3), u, FakeBattle(), max_nodes=5000)
    assert (8, 7) in path2, path2
    assert not any(bf2.terrain[x][y] == tr.RIVER for x, y in path2)


@test
def test_los_uses_terrain_without_walls():
    bf = real_bf(cells={(3, 0): tr.WOOD, (4, 0): tr.WOOD, (5, 0): tr.WOOD})
    assert bf.has_line_of_fire(U((0, 0), 8), U((8, 0))) is False
    assert bf.has_line_of_fire(U((0, 1), 8), U((8, 1))) is True


# ── Combat ──

from models import Arme
from unit import Unit
import tactics


def archer(pos, save=7):
    u = Unit("Archer", pv=100, vitesse=4, morale=3, sauvegarde=save, color=(1, 1, 1),
             armes=[Arme("Arc", nb_attaque=1, toucher=3, blesser=1, perforation=0,
                         degats="1", porte=8)])
    u.position = pos
    return u


def target(pos, save=7):
    u = Unit("Cible", pv=100000, vitesse=4, morale=5, sauvegarde=save, color=(2, 2, 2),
             armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    u.position = pos
    return u


def mean_damage(bf, a, t, n=3000):
    a.ammo = None     # on mesure le taux par volée, pas l'épuisement du carquois
    total = 0
    for _ in range(n):
        before = t.hp
        a.perform_attacks(t, bf)
        total += before - t.hp
        t.hp = t.max_hp
        t.is_alive = True
    return total / n


@test
def test_wood_cover_engine_matches_estimate():
    bf = real_bf(cells={(6, 1): tr.WOOD})
    a, t = archer((0, 1)), target((6, 1))
    bf.place_unit(a); bf.place_unit(t)
    est = tactics.expected_damage(a, t, 6, bf)
    assert abs(est - 3 / 6) < 1e-9, est          # toucher 3 → 4+ en bois: 3/6
    got = mean_damage(bf, a, t)
    assert abs(got - est) / est < 0.10, (got, est)


@test
def test_marsh_worsens_save_engine_matches_estimate():
    bf = real_bf(cells={(1, 1): tr.MARSH})
    a, t = archer((0, 1)), target((1, 1), save=4)
    a.armes[0].porte = 1
    a._max_range = 1
    est = tactics.expected_damage(a, t, 1, bf)
    # toucher 3+ (4/6) × blesser 1+ (1) × échec de sauvegarde 5+ (4/6)
    assert abs(est - (4 / 6) * (4 / 6)) < 1e-9, est
    got = mean_damage(bf, a, t)
    assert abs(got - est) / est < 0.10, (got, est)


@test
def test_hill_gives_range():
    bf = real_bf(w=16, cells={(0, 1): tr.HILL})
    a, t = archer((0, 1)), target((9, 1))
    assert tactics.expected_damage(a, t, 9, bf) > 0
    assert mean_damage(bf, a, t, 400) > 0
    a2 = archer((0, 2))
    assert mean_damage(bf, a2, target((9, 2)), 50) == 0


def charge_setup(cells):
    from battle import Battle
    random.seed(3)
    rider = Unit("Cavalier", pv=10, vitesse=6, morale=5, sauvegarde=4, color=(9, 9, 9),
                 armes=[Arme("Lance", 2, 3, 3, 1, "2", porte=1)])
    rider.charge_montee = True
    foe = Unit("Fantassin", pv=10, vitesse=0, morale=5, sauvegarde=5, color=(8, 8, 8),
               armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    b = Battle([rider], [foe], 30, 12, 0, map_name="Prairie")
    bf = b.battlefield
    bf.grid = [[0] * bf.height for _ in range(bf.width)]
    bf.terrain = tr.make_grid(bf.width, bf.height)
    for (x, y), name in cells.items():
        bf.terrain[x][y] = name
    r, f = b.army1[0], b.army2[0]
    bf.move_unit(r, (10, 5))
    bf.move_unit(f, (15, 5))
    r._cells_moved = 0
    return b, r, f


@test
def test_charge_blocked_by_wood_impact():
    around = {(15 + dx, 5 + dy): tr.WOOD for dx in (-1, 0, 1) for dy in (-1, 0, 1)
              if (dx, dy) != (0, 0)}
    b, r, f = charge_setup(around)
    b._charge_phase([r, f])
    assert r.position == (10, 5) and not getattr(r, '_charged_this_round', False)


@test
def test_charge_allowed_on_plain():
    b, r, f = charge_setup({})
    b._charge_phase([r, f])
    assert r.position != (10, 5)


@test
def test_charge_blocked_from_marsh():
    b, r, f = charge_setup({(10, 5): tr.MARSH})
    b._charge_phase([r, f])
    assert r.position == (10, 5)


@test
def test_charge_blocked_when_path_cost_exceeds_budget():
    """Un couloir de marais plein entre le cavalier et sa proie doit pouvoir
    dépasser le budget de charge même quand le nombre de CASES tiendrait:
    le budget se mesure en coût de terrain, pas en pas comptés."""
    around = {(x, y): tr.MARSH for x in (11, 12, 13) for y in range(12)}
    b, r, f = charge_setup(around)
    b._charge_phase([r, f])
    assert r.position == (10, 5) and not getattr(r, '_charged_this_round', False)


@test
def test_cells_moved_uses_real_path_cost_not_chebyshev_jump():
    """Un déplacement multi-cases qui traverse un marais doit décompter le
    VRAI coût du chemin suivi (steps_within/path_cost), pas un saut
    Chebyshev vers la destination qui multiplierait le nombre de pas par
    le coût d'UNE seule case d'arrivée."""
    from battle import Battle
    random.seed(3)
    mover = Unit("Eclaireur", pv=1000, vitesse=6, morale=5, sauvegarde=7,
                 color=(3, 3, 3),
                 armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    enemy = Unit("Cible", pv=1000, vitesse=0, morale=5, sauvegarde=7,
                 color=(4, 4, 4),
                 armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    b = Battle([mover], [enemy], 16, 9, 0, map_name="Prairie")
    bf = b.battlefield
    bf.grid = [[0] * bf.height for _ in range(bf.width)]
    bf.terrain = tr.make_grid(bf.width, bf.height)
    for y in range(bf.height):
        bf.terrain[3][y] = tr.MARSH
        bf.terrain[4][y] = tr.MARSH
    m, e = b.army1[0], b.army2[0]
    bf.move_unit(m, (0, 5))
    bf.move_unit(e, (10, 5))
    m._cells_moved = 0
    b.simulate_round()
    assert m.position == (3, 5), m.position
    # 2 pas de plaine (1.0 chacun) + 1 pas de marais (3.0) = 5.0
    assert abs(m._cells_moved - 5.0) < 1e-9, m._cells_moved
    # Le bug corrigé aurait compté un saut Chebyshev vers la destination:
    # 3 pas × coût marais (3.0) = 9, très différent du vrai coût (5).
    buggy = tr.move_cost(bf, (0, 5), m.position)
    assert buggy == 9.0 and m._cells_moved != buggy, (m._cells_moved, buggy)


# ── Cartes ──

import maps

SIZES = [(40, 30), (178, 64)]


def map_checks(name, seeds=10, sizes=SIZES, min_paths=2):
    for w, h in sizes:
        for seed in range(seeds):
            random.seed(500 + seed)
            grid, data = maps.generate_map(name, w, h)
            terr = data.get('terrain')
            assert terr is not None, f"{name}: pas de terrain"
            # Symétrie en miroir sur les cases libres des deux côtés
            for x in range(w // 2):
                for y in range(h):
                    xm = w - 1 - x
                    if grid[x][y] == 0 and grid[xm][y] == 0:
                        assert terr[x][y] == terr[xm][y], (name, w, h, seed, x, y, terr[x][y], terr[xm][y])
            left = [(1, y) for y in range(h) if grid[1][y] == 0 and tr.MOVE[terr[1][y]] is not None]
            right = [(w - 2, y) for y in range(h) if grid[w - 2][y] == 0 and tr.MOVE[terr[w - 2][y]] is not None]
            p1 = maps._bfs_path(grid, w, h, left, right, terr)
            assert p1, f"{name} {w}x{h} graine {seed}: aucun passage"
            if min_paths >= 2:
                blocked = set(p1[1:-1])
                p2 = maps._bfs_path(grid, w, h, left, right, terr, blocked=blocked)
                assert p2, f"{name} {w}x{h} graine {seed}: un seul passage"
            assert maps._bfs_path(grid, w, h, left, right, terr, avoid=(tr.MARSH,)), \
                f"{name} {w}x{h} graine {seed}: aucun passage sans marais"


def deploy_check(name, sizes=SIZES, seeds=4):
    import unit_library as ul
    from battle import Battle
    for w, h in sizes:
        for seed in range(seeds):
            random.seed(900 + seed)
            a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 12), ("Arbaletrier régulier", 6)])
            a2 = ul.build_army("Armée Orlandar", [("Fantassin covaliir", 12), ("Archer covaliir", 6), ("Cavalier covaliir", 3)])
            b = Battle(a1, a2, w, h, 8, map_name=name)
            bf = b.battlefield
            for u in b.army1 + b.army2:
                t = tr.at(bf, *u.position)
                assert tr.MOVE[t] == 1.0, f"{name} {w}x{h}: {u.name} déployé sur {t} en {u.position}"
                # Défilé: les pentes (colline) sont exclues de la zone de
                # déploiement (principe "zones de déploiement en plaine").
                # Prairie/Village ont été vérifiées: leurs crêtes/butte ne
                # chevauchent déjà aucune case de déploiement mesurée, donc
                # on ne durcit pas l'assertion pour elles ici.
                if name == "Défilé":
                    assert t == tr.PLAIN, \
                        f"{name} {w}x{h}: {u.name} déployé sur {t} (pas plaine) en {u.position}"


@test
def test_connected_is_terrain_aware():
    grid = [[0] * 5 for _ in range(7)]
    terr = tr.make_grid(7, 5)
    for y in range(5):
        terr[3][y] = tr.RIVER
    assert maps._connected(grid, 7, 5, (0, 2), (6, 2))            # ancien appel
    assert not maps._connected(grid, 7, 5, (0, 2), (6, 2), terr)
    terr[3][4] = tr.MARSH
    assert maps._connected(grid, 7, 5, (0, 2), (6, 2), terr)
    assert not maps._connected(grid, 7, 5, (0, 2), (6, 2), terr, avoid=(tr.MARSH,))


@test
def test_map_prairie():
    map_checks("Prairie")
    deploy_check("Prairie")
    random.seed(1)
    grid, data = maps.generate_map("Prairie", 178, 64)
    names = {n for col in data['terrain'] for n in col}
    assert {tr.HILL, tr.WOOD} <= names, names


@test
def test_map_forest():
    map_checks("Forêt")
    deploy_check("Forêt")
    random.seed(2)
    grid, data = maps.generate_map("Forêt", 178, 64)
    names = {n for col in data['terrain'] for n in col}
    assert {tr.WOOD, tr.RIVER, tr.FORD} <= names, names
    assert data.get('deploy_gap'), "deploy_gap doit être conservé"


@test
def test_forest_grove_core_is_wood():
    # Le cœur d'un bosquet (case obstacle dont les 8 voisines sont aussi
    # des obstacles) reste impassable, mais doit être du bois pour bloquer
    # la ligne de vue comme le sous-bois qui l'entoure.
    random.seed(3)
    w, h = 178, 64
    grid, data = maps.generate_map("Forêt", w, h)
    terr = data['terrain']
    found_core = False
    for x in range(w):
        for y in range(h):
            if grid[x][y] != 1:
                continue
            is_core = all(
                not (0 <= x + dx < w and 0 <= y + dy < h) or grid[x + dx][y + dy] == 1
                for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            if is_core:
                found_core = True
                assert terr[x][y] == tr.WOOD, (x, y, terr[x][y])
    assert found_core, "aucune case de cœur de bosquet trouvée pour cette graine"


@test
def test_map_village():
    map_checks("Village")
    deploy_check("Village")
    random.seed(4)
    grid, data = maps.generate_map("Village", 178, 64)
    names = {n for col in data['terrain'] for n in col}
    assert {tr.HILL, tr.WOOD, tr.MARSH} <= names, names


@test
def test_map_defile():
    map_checks("Défilé", sizes=[(178, 64)])
    map_checks("Défilé", sizes=[(40, 30)], min_paths=1)
    deploy_check("Défilé")
    random.seed(5)
    grid, data = maps.generate_map("Défilé", 178, 64)
    names = {n for col in data['terrain'] for n in col}
    assert {tr.HILL, tr.MARSH, tr.RIVER, tr.BRIDGE, tr.FORD} <= names, names
@test
def test_decor_follows_terrain():
    random.seed(6)
    grid, data = maps.generate_map("Forêt", 178, 64)
    terr = data['terrain']
    wet = {tr.RIVER, tr.FORD, tr.BRIDGE}
    trees = {"arbre_pin", "arbre_rond"}
    on_wood = off_wood = 0
    for x, y, kind, _ in data['decor']:
        assert terr[x][y] not in wet, (x, y, kind, terr[x][y])
        if kind in trees:
            if terr[x][y] == tr.WOOD:
                on_wood += 1
            else:
                off_wood += 1
    assert on_wood > off_wood, (on_wood, off_wood)


@test
def test_render_terrain_smoke():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    import terrain_render as trr
    from renderer import build_grid_surface
    from battle import Battle
    import unit_library as ul
    random.seed(8)
    for name in ("Prairie", "Forêt", "Village", "Défilé", "Siège"):
        a = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 3)])
        b = Battle(a, a, 60, 40, 8, map_name=name)
        surf = build_grid_surface(b, 16)
        assert surf.get_width() == 60 * 16
        leg = trr.legend_surface(b.battlefield, pygame.font.SysFont("arial", 14))
        # Le Siège a lui aussi son terrain (fossé, glacis) depuis le lot B2
        assert leg is not None and leg.get_height() > 20
    # Une case de rivière est dessinée en bleu
    random.seed(5)
    b = Battle(a, a, 178, 64, 8, map_name="Défilé")
    bf = b.battlefield
    surf = build_grid_surface(b, 16)
    rx, ry = next((x, y) for x in range(bf.width) for y in range(bf.height)
                  if bf.terrain[x][y] == tr.RIVER and bf.grid[x][y] == 0)
    r, g, bl, _ = surf.get_at((rx * 16 + 8, ry * 16 + 8))
    assert bl > r and bl > g - 10, (r, g, bl)
    assert set(trr.LEGEND) >= {tr.HILL, tr.WOOD, tr.RIVER, tr.FORD, tr.BRIDGE, tr.MARSH}


@test
def test_legend_swatches_opaque():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    import terrain_render as trr
    from battle import Battle
    import unit_library as ul
    random.seed(8)
    a = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 3)])
    b = Battle(a, a, 60, 40, 8, map_name="Prairie")
    bf = b.battlefield
    font = pygame.font.SysFont("arial", 14)
    leg = trr.legend_surface(bf, font)
    assert leg is not None
    present = {n for col in bf.terrain for n in col}
    rows = [n for n in trr._ORDER if n in present]
    assert rows, "Prairie devrait avoir au moins un terrain dans la légende"
    # Reproduit la mise en page de legend_surface pour localiser chaque case.
    sw, pad, gap = 22, 10, 6
    texts = [font.render(trr.LEGEND[n], True, (228, 228, 220)) for n in rows]
    title = font.render("Terrain  (L pour masquer)", True, (255, 220, 120))
    y = pad + title.get_height() + gap
    for n, t in zip(rows, texts):
        cx, cy = pad + sw // 2, y + sw // 2
        r, g, bl, al = leg.get_at((cx, cy))
        assert al == 255, (n, (r, g, bl, al))
        y += max(sw, t.get_height()) + gap


# ── Runner (ajouter les nouveaux tests AU-DESSUS de cette ligne) ──

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    fails = []
    for fn in TESTS:
        if only and only not in fn.__name__:
            continue
        try:
            random.seed(7)
            fn()
            print(f"  OK    {fn.__name__}")
        except Exception:
            fails.append(fn.__name__)
            print(f"  ECHEC {fn.__name__}")
            traceback.print_exc()
    print()
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests terrain passent.")
    sys.exit(1 if fails else 0)
