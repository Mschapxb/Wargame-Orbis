"""Tests de l'orientation (facing.py): arcs, modificateurs, rotation.

    python test_facing.py            # tout
    python test_facing.py dos        # seulement les tests dont le nom contient 'dos'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import facing
import tactics
import terrain as tr
import unit_library as ul
from battle import Battle
from battlefield import Battlefield
from models import Arme
from unit import Unit

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def soldier(pos, facing_vec=None, pv=1, save=7):
    u = Unit("Soldat", pv=pv, vitesse=4, morale=5, sauvegarde=save, color=(1, 1, 1),
             armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    u.position = pos
    u.facing = facing_vec
    return u


def flat_bf(w=12, h=12):
    grid = [[0] * h for _ in range(w)]
    return Battlefield(w, h, 0, "Prairie", grid, {'terrain': tr.make_grid(w, h)})


@test
def test_arcs_de_face_flanc_dos():
    t = soldier((5, 5), (1.0, 0.0))             # regarde vers l'est
    assert facing.arc(soldier((6, 5)), t) == facing.FRONT
    assert facing.arc(soldier((6, 6)), t) == facing.FRONT   # diagonale avant
    assert facing.arc(soldier((5, 6)), t) == facing.FLANK
    assert facing.arc(soldier((5, 4)), t) == facing.FLANK
    assert facing.arc(soldier((4, 6)), t) == facing.REAR    # diagonale arrière
    assert facing.arc(soldier((4, 5)), t) == facing.REAR


@test
def test_sans_orientation_tout_est_de_face():
    t = soldier((5, 5), None)
    assert facing.arc(soldier((4, 5)), t) == facing.FRONT


@test
def test_modificateurs_de_flanc_et_de_dos():
    bf = flat_bf()
    t = soldier((5, 5), (1.0, 0.0))
    assert tr.combat_mods(bf, soldier((6, 5)), t, False) == {'toucher': 0, 'save': 0}
    assert tr.combat_mods(bf, soldier((5, 6)), t, False) == {'toucher': -1, 'save': 0}
    assert tr.combat_mods(bf, soldier((4, 5)), t, False) == {'toucher': -1, 'save': 1}
    # Au tir, seul le dos compte (le bouclier est devant)
    assert tr.combat_mods(bf, soldier((5, 11)), t, True) == {'toucher': 0, 'save': 0}
    assert tr.combat_mods(bf, soldier((0, 5)), t, True) == {'toucher': 0, 'save': 1}


@test
def test_coup_dans_le_dos_moteur_egal_estimation():
    bf = flat_bf()
    a = soldier((4, 5), (1.0, 0.0))
    t = soldier((5, 5), (1.0, 0.0), pv=100000, save=4)
    bf.place_unit(a)
    bf.place_unit(t)
    est = tactics.expected_damage(a, t, 1, bf)
    # Toucher 4+ -1 → 3+, blesser 4+, sauvegarde 4+ dégradée d'un cran → 5+
    assert abs(est - (4 / 6) * (3 / 6) * (4 / 6)) < 1e-9, est
    total, n = 0, 4000
    for _ in range(n):
        t.facing = (1.0, 0.0)
        before = t.hp
        a.perform_attacks(t, bf)
        total += before - t.hp
        t.hp = t.max_hp
    assert abs(total / n - est) / est < 0.1, (total / n, est)


@test
def test_attaquant_se_tourne_vers_sa_cible_et_dos_ebranle():
    bf = flat_bf()
    a = soldier((5, 4), (1.0, 0.0))              # regarde l'est, cible au sud
    t = soldier((5, 5), (0.0, -1.0))             # regarde au nord... vers a
    b = soldier((5, 6), (1.0, 0.0))              # dans le dos de t
    for u in (a, t, b):
        bf.place_unit(u)
    a.perform_attacks(t, bf)
    assert a.facing == (0.0, 1.0), a.facing
    shock = t._shock
    b.perform_attacks(t, bf)
    assert t._shock == shock + 1


@test
def test_au_contact_on_fait_face_a_qui_nous_touche():
    random.seed(3)
    a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 1)])
    a2 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 2)])
    b = Battle(a1, a2, 30, 20, 0, map_name="Prairie", map_options={'relief': "Plat"})
    bf = b.battlefield
    u, e1, e2 = b.army1[0], b.army2[0], b.army2[1]
    for x in (u, e1, e2):
        bf.remove_unit(x)
    u.position, e1.position, e2.position = (10, 10), (11, 10), (20, 3)
    for x in (u, e1, e2):
        bf.place_unit(x)
    u.current_target = e2            # visait un ennemi lointain
    u.facing = (0.0, -1.0)
    b._update_facings({})
    assert u.facing == (1.0, 0.0), u.facing   # face à l'ennemi collé à lui


@test
def test_armees_face_a_face_au_deploiement():
    random.seed(1)
    a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 2)])
    a2 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 2)])
    b = Battle(a1, a2, 40, 30, 8, map_name="Prairie")
    assert all(u.facing == (1.0, 0.0) for u in b.army1)
    assert all(u.facing == (-1.0, 0.0) for u in b.army2)


@test
def test_ia_prefere_la_case_de_flanc():
    bf = flat_bf(20, 20)
    t = soldier((10, 10), (-1.0, 0.0))           # regarde l'ouest
    a = soldier((7, 11), (1.0, 0.0))
    for u in (a, t):
        bf.place_unit(u)

    class _B:
        def get_allies(self, u):
            return []
    pos = bf.find_best_attack_position(a, t, _B())
    assert facing.arc_from(pos, t) != facing.FRONT, pos


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests orientation passent.")
    sys.exit(1 if fails else 0)
