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

from battlefield import Battlefield


class FakeBattle:
    def get_allies(self, unit):
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
