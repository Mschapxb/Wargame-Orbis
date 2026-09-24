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
import spatial
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


class Sides(spatial.Neighbourhood):
    """Battle minimal: deux camps, rien d'autre. Le mixin lui donne les
    requêtes de voisinage que le moteur attend d'une bataille."""
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
def test_traits_de_contact_lus_depuis_la_bibliotheque():
    import unit_library as ul
    cav = ul.make_unit("Armée Orlandar", "Cavalier covaliir")
    ecl = ul.make_unit("Armée Skaldienne", "Eclaireur")
    inf = ul.make_unit("Armée Skaldienne", "Infanterie régulière")
    assert cav.contact_breakthrough and cav.contact_slip == 0
    assert ecl.contact_slip == 1 and not ecl.contact_breakthrough
    assert not inf.contact_breakthrough and inf.contact_slip == 0


@test
def test_debordement_n_est_pas_arrete_au_contact():
    bf = flat_bf()
    u = soldier((2, 5), vitesse=8)
    u.contact_breakthrough = True
    foe = soldier((6, 4))
    b = Sides(bf, [u], [foe])
    path = bf.a_star_path((2, 5), (9, 5), u, b)
    assert bf._advance_along(u, path, u.vitesse, set(), b) == (9, 5)


@test
def test_tirailleur_fait_une_case_de_plus_au_contact():
    bf = flat_bf()
    u = soldier((2, 5), vitesse=8)
    foe = soldier((6, 4))
    b = Sides(bf, [u], [foe])
    path = bf.a_star_path((2, 5), (9, 5), u, b)
    stop = bf._advance_along(u, path, u.vitesse, set(), b)
    u.contact_slip = 1
    slip = bf._advance_along(u, path, u.vitesse, set(), b)
    assert path.index(slip) == path.index(stop) + 1, (stop, slip, path)


@test
def test_debordement_paie_un_coup_d_opportunite_plus_dur():
    import combat
    cav = soldier((5, 5))
    inf = soldier((6, 5))
    arme = inf.armes[0]
    normal = combat.attack_profile(inf, cav, arme, kind="opportunity")
    cav.contact_breakthrough = True
    dur = combat.attack_profile(inf, cav, arme, kind="opportunity")
    assert dur.toucher == normal.toucher - 1


@test
def test_reculer_coute_double_ou_demi_tour():
    bf = flat_bf()
    u = soldier((10, 5), vitesse=6)
    u.facing = (1.0, 0.0)                       # regarde vers l'est
    b = Sides(bf, [u], [soldier((19, 11))])
    # 1 case vers l'arrière: reculer (2) = demi-tour (1+1) → on recule, face à l'est
    assert bf._walk_costs(u, [(9, 5)]) == ([2.0], False)
    # 2 cases: demi-tour (1+1+1 = 3) < reculer (2+2 = 4)
    costs, turned = bf._walk_costs(u, [(9, 5), (8, 5)])
    assert turned and sum(costs) == 3.0
    # 5 cases vers l'arrière: demi-tour (1) puis 5 pas = 6 < reculer (10)
    far = [(9 - i, 5) for i in range(5)]
    costs, turned = bf._walk_costs(u, far)
    assert turned and costs[0] == 2.0 and sum(costs) == 6.0
    assert bf._walk_costs(u, [(11, 5), (12, 5)]) == ([1.0, 1.0], False)
    assert bf._advance_along(u, far, u.vitesse, set(), b) == (5, 5)


@test
def test_demi_tour_sur_place_coute_une_case():
    import facing
    u = soldier((5, 5), vitesse=4)
    u.facing = (1.0, 0.0)
    facing.turn_toward(u, (1, 5))               # derrière lui
    assert u.facing[0] < -0.9 and u._cells_moved == 1
    v = soldier((5, 5), vitesse=4)
    v.facing = (1.0, 0.0)
    v._cells_moved = 4                          # a déjà tout marché
    facing.turn_toward(v, (1, 5))
    assert abs(v.facing[0]) < 1e-9 and abs(v.facing[1]) == 1.0   # quart de tour seulement
    w = soldier((5, 5), vitesse=4)
    w.facing = (1.0, 0.0)
    w._cells_moved = 4
    facing.turn_toward(w, (5, 9))               # 90°: gratuit
    assert w.facing == (0.0, 1.0) and w._cells_moved == 4


@test
def test_releve_la_fraiche_prend_la_place_de_la_lasse():
    bf = flat_bf()
    tired, fresh = soldier((6, 5)), soldier((5, 5))
    foe = soldier((7, 5))
    tired.fatigue = 4
    b = Sides(bf, [tired, fresh], [foe])
    reserved, moves = set(), {}
    taken = Battle._plan_reliefs(b, [tired, fresh, foe], reserved, moves)
    assert taken == {id(tired), id(fresh)}
    assert moves == {tired: (5, 5), fresh: (6, 5)}
    order = Battle._dependency_order(b, list(moves.items()))
    assert {u for u, _ in order} == {tired, fresh}
    for u, dest in order:
        bf.move_unit(u, dest)
    assert bf.units[(6, 5)] is fresh and bf.units[(5, 5)] is tired


@test
def test_pas_de_releve_si_la_fraiche_est_deja_au_contact():
    bf = flat_bf()
    tired, busy = soldier((6, 5)), soldier((6, 6))
    tired.fatigue = 4
    b = Sides(bf, [tired, busy], [soldier((7, 5)), soldier((7, 6))])
    assert Battle._plan_reliefs(b, [tired, busy], set(), {}) == set()


@test
def test_zone_atteignable_respecte_ennemis_et_contact():
    bf = flat_bf()
    u = soldier((3, 5), vitesse=6)
    b = Sides(bf, [u], enemy_wall(8, bf.height))
    zone = bf.reachable_cells(u, b)
    assert zone and all(x < 8 for x, _ in zone)            # la ligne ne se traverse pas
    assert (7, 5) in zone and (6, 5) in zone
    assert not any(bf.units.get(c) for c in zone)


@test
def test_chef_de_bloc_contourne_l_obstacle():
    import formation
    from ai_commander import CommanderAI
    bf = flat_bf(30, 16)
    for y in range(3, 12):
        bf.grid[12][y] = 1                              # mur de rochers devant le bloc
    ai = CommanderAI.__new__(CommanderAI)
    ai.battlefield = bf
    straight = (12.0, 7.0)                              # tombe dans le mur
    anchor = ai._leader_anchor((8.0, 7.0), straight, (20.0, 7.0), 4)
    assert anchor != straight and formation.walkable(bf, int(anchor[0]), int(anchor[1]))
    # Terrain dégagé: la marche droite d'avant est conservée
    assert ai._leader_anchor((8.0, 13.5), (12.0, 13.5), (20.0, 13.5), 4) == (12.0, 13.5)


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
