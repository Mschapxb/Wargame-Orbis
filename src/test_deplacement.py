"""Tests du déplacement case par case: chemins, empreintes, contact, cases libérées.

    python test_deplacement.py            # tout
    python test_deplacement.py contact    # seulement les tests dont le nom contient 'contact'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import terrain as tr
from battle import Battle
from battlefield import Battlefield
from models import Arme
from unit import Unit

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def soldier(pos, size=1, vitesse=6):
    u = Unit("Soldat", pv=1, vitesse=vitesse, morale=5, sauvegarde=7, color=(1, 1, 1),
             armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)], size=size)
    u.position = pos
    return u


def flat_bf(w=20, h=12):
    grid = [[0] * h for _ in range(w)]
    return Battlefield(w, h, 0, "Prairie", grid, {'terrain': tr.make_grid(w, h)})


class Sides:
    """Battle minimal: deux camps, rien d'autre."""
    def __init__(self, bf, army1, army2):
        self.battlefield = bf
        self.army1, self.army2 = army1, army2
        for u in army1 + army2:
            bf.place_unit(u)

    def get_enemies(self, unit):
        return self.army2 if unit in self.army1 else self.army1

    def get_allies(self, unit):
        return self.army1 if unit in self.army1 else self.army2


def enemy_wall(x, h, gap=None):
    return [soldier((x, y)) for y in range(h) if y != gap]


@test
def test_astar_ne_traverse_pas_une_ligne_ennemie():
    bf = flat_bf()
    u = soldier((3, 5))
    b = Sides(bf, [u], enemy_wall(10, bf.height))
    assert bf.a_star_path((3, 5), (15, 5), u, b) == []
    # partial: on s'approche jusqu'à la ligne, sans la franchir
    path = bf.a_star_path((3, 5), (15, 5), u, b, partial=True)
    assert path and all(x < 10 for x, _ in path), path


@test
def test_astar_passe_par_la_breche():
    bf = flat_bf()
    u = soldier((3, 5))
    b = Sides(bf, [u], enemy_wall(10, bf.height, gap=2))
    path = bf.a_star_path((3, 5), (15, 5), u, b)
    assert path and path[-1] == (15, 5)
    assert (10, 2) in path, path


@test
def test_astar_traverse_les_allies():
    bf = flat_bf()
    u = soldier((3, 5))
    b = Sides(bf, [u] + enemy_wall(10, bf.height), [soldier((18, 0))])
    path = bf.a_star_path((3, 5), (15, 5), u, b)
    assert path and path[-1] == (15, 5), path


@test
def test_pas_de_faufilage_en_diagonale():
    bf = flat_bf()
    u = soldier((4, 4))
    # Deux ennemis qui se touchent par le coin: (5,4) et (4,5)
    b = Sides(bf, [u], [soldier((5, 4)), soldier((4, 5))])
    path = bf.a_star_path((4, 4), (5, 5), u, b)
    assert path and path[0] != (5, 5), path


@test
def test_grosse_unite_ne_passe_pas_par_un_trou_d_une_case():
    bf = flat_bf()
    for y in range(bf.height):
        if y != 5:
            bf.grid[10][y] = 1        # mur de rochers, trou d'une case en y=5
    big = soldier((3, 4), size=2)     # 2×2
    small = soldier((3, 8))
    b = Sides(bf, [big, small], [soldier((19, 11))])
    assert bf.a_star_path((3, 4), (14, 4), big, b) == []
    assert bf.a_star_path((3, 8), (14, 8), small, b)
    bf.grid[10][6] = 0                # trou de deux cases: le 2×2 passe
    path = bf.a_star_path((3, 4), (14, 4), big, b)
    assert path and path[-1] == (14, 4) and (10, 5) in path, path


@test
def test_arret_au_contact():
    bf = flat_bf()
    u = soldier((2, 5), vitesse=8)
    foe = soldier((6, 4))
    b = Sides(bf, [u], [foe])
    # Longer l'ennemi pour aller derrière lui: la marche s'arrête au contact
    path = bf.a_star_path((2, 5), (9, 5), u, b)
    step = bf._advance_along(u, path, u.vitesse, set(), b)
    assert bf.unit_distance(u, foe, a_pos=step) == 1, (step, path)
    assert u._planned_path[-1] == step


@test
def test_se_degager_du_contact_est_permis():
    bf = flat_bf()
    u = soldier((5, 5))
    foe = soldier((6, 5))
    b = Sides(bf, [u], [foe])
    path = bf.a_star_path((5, 5), (1, 5), u, b)
    assert bf._advance_along(u, path, u.vitesse, set(), b) == (1, 5)


@test
def test_route_to_refuse_un_saut_par_dessus_l_ennemi():
    bf = flat_bf()
    u = soldier((3, 5))
    b = Sides(bf, [u], enemy_wall(5, bf.height))
    u._planned_move_dest = u._planned_path = None
    # Un pas « direct » de 3 cases vers l'est franchirait la ligne ennemie
    assert bf.route_to(u, b, (6, 5), set(), u.vitesse) is None


@test
def test_rester_sur_place_n_est_pas_un_refus():
    bf = flat_bf()
    u = soldier((5, 5))
    b = Sides(bf, [u], [soldier((19, 11))])
    b.get_all_alive = lambda: [u]
    b.battlefield = bf
    reserved, moves = set(), {}
    bf.leaving = set()
    pos = Battle._legal_move(b, u, (5, 5), reserved)
    assert pos == (5, 5)
    Battle._commit_move(b, u, pos, reserved, moves)
    assert (5, 5) in reserved and id(u) not in bf.leaving


@test
def test_colonne_reprend_la_case_liberee():
    bf = flat_bf()
    head, tail = soldier((6, 5)), soldier((5, 5))
    b = Sides(bf, [head, tail], [soldier((19, 11))])
    # La queue veut la case de la tête, la tête avance: la queue passe après
    order = Battle._dependency_order(b, [(tail, (6, 5)), (head, (7, 5))])
    assert [u for u, _ in order] == [head, tail]


@test
def test_echange_de_places_bloque_sans_chevauchement():
    bf = flat_bf()
    a, c = soldier((6, 5)), soldier((7, 5))
    b = Sides(bf, [a, c], [soldier((19, 11))])
    assert Battle._dependency_order(b, [(a, (7, 5)), (c, (6, 5))]) == []


@test
def test_bataille_sans_chevauchement_ni_saut():
    import unit_library as ul
    random.seed(11)
    comp = [("Fantassin covaliir", 5), ("Archer covaliir", 3), ("Cavalier covaliir", 3)]
    bt = Battle(ul.build_army("Armée Orlandar", comp), ul.build_army("Armée Orlandar", comp),
                40, 30, 8, map_name="Forêt")
    bf = bt.battlefield
    while not bt.is_battle_over() and bt.round <= 40:
        bt.simulate_round()
        seen = set()
        for u in bt.army1 + bt.army2:
            if not (u.is_alive and u.position):
                continue
            cells = set(bf.get_unit_cells(u))
            assert not cells & seen, f"chevauchement au round {bt.round}"
            seen |= cells
            path = u._move_path or []
            for p, q in zip(path, path[1:]):
                assert max(abs(p[0] - q[0]), abs(p[1] - q[1])) == 1, path
            if path:
                assert path[-1] == u.position, (path, u.position)


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests de déplacement passent.")
    sys.exit(1 if fails else 0)
