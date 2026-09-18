"""Tests de l'agressivité de l'IA (ai_commander): réflexe d'engagement,
choix de cible, recul des tireurs réservé à la défense.

    python test_aggression.py            # tout
    python test_aggression.py reflexe    # seulement les tests dont le nom contient 'reflexe'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ai_commander as AC
import unit_library as ul
from ai_commander import TacticalOrder
from battle import Battle

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def open_battle(a1, a2, w=40, h=20):
    random.seed(3)
    b = Battle(ul.build_army("Armée Skaldienne", a1), ul.build_army("Armée Skaldienne", a2),
               w, h, 0, map_name="Prairie", map_options={'relief': "Plat"})
    b.commander1.issue_orders(b)
    b.commander2.issue_orders(b)
    return b


def place(b, unit, pos):
    b.battlefield.remove_unit(unit)
    unit.position = pos
    b.battlefield.place_unit(unit)


@test
def test_postures_defensives_ne_sont_pas_agressives():
    b = open_battle([("Infanterie régulière", 2)], [("Infanterie régulière", 2)])
    cmd = b.commander1
    cmd.posture = "balanced"
    assert cmd.aggressive()
    for p in ("hold_line", "regroup", "screen"):
        cmd.posture = p
        assert not cmd.aggressive(), p


@test
def test_garnison_de_siege_attend_sauf_en_sortie():
    random.seed(2)
    b = Battle(ul.build_army("Armée Skaldienne", [("Infanterie régulière", 3)]),
               ul.build_army("Armée Skaldienne", [("Infanterie régulière", 3)]),
               40, 30, 8, map_name="Siège")
    d = b.commander2
    d.posture = "hold_walls"
    assert not d.aggressive()
    d.posture = "sortie"
    assert d.aggressive()
    b.commander1.posture = "balanced"
    assert b.commander1.aggressive()                  # l'assaillant va au contact


@test
def test_reflexe_combat_l_ennemi_au_contact_au_lieu_d_une_cible_lointaine():
    b = open_battle([("Infanterie régulière", 1)], [("Infanterie régulière", 2)])
    cmd = b.commander1
    u, near, far = b.army1[0], b.army2[0], b.army2[1]
    place(b, u, (10, 10))
    place(b, near, (11, 10))
    place(b, far, (25, 3))
    cmd.posture = "balanced"
    cmd._claims = {}
    order = cmd._engage_reflex(u, b.army2, TacticalOrder("attack", target_unit=far, priority=3))
    assert order.order_type == "attack" and order.target_unit is near
    # Un repli (unité à l'agonie) n'est pas contredit
    wd = TacticalOrder("withdraw", target_pos=(2, 10), priority=6)
    assert cmd._engage_reflex(u, b.army2, wd) is wd


@test
def test_reflexe_ignore_le_defenseur_abrite_sur_le_rempart():
    random.seed(5)
    b = Battle(ul.build_army("Armée Skaldienne", [("Infanterie régulière", 1)]),
               ul.build_army("Armée Skaldienne", [("Arbaletrier régulier", 2)]),
               40, 30, 8, map_name="Siège")
    bf = b.battlefield
    gar = next(e for e in b.army2 if bf.is_rampart(*e.position))
    att = b.army1[0]
    spot = next((bf.wall_x - 1, gar.position[1] + dy) for dy in (0, 1, -1, 2, -2)
                if bf.is_valid(bf.wall_x - 1, gar.position[1] + dy)
                and (bf.wall_x - 1, gar.position[1] + dy) not in bf.units)
    place(b, att, spot)
    assert not b.commander1._melee_can_reach(att, gar)


@test
def test_choix_de_cible_ne_passe_pas_a_cote_d_un_ennemi_proche():
    b = open_battle([("Infanterie régulière", 1)],
                    [("Infanterie régulière", 1), ("Arbaletrier régulier", 1)])
    cmd = b.commander1
    u = b.army1[0]
    inf, xbow = b.army2
    place(b, u, (10, 10))
    place(b, inf, (13, 10))          # à 3 cases
    place(b, xbow, (19, 12))         # tireur « de valeur », 11 cases
    cmd.posture = "balanced"
    cmd._claims = {}
    order = cmd._melee_order(u, b.army2, cmd._rank_targets(b.army2))
    assert order.target_unit is inf, order.target_unit.name


@test
def test_tireur_ne_recule_qu_en_defense():
    b = open_battle([("Arbaletrier régulier", 1)], [("Infanterie régulière", 1)])
    cmd = b.commander1
    xbow, foe = b.army1[0], b.army2[0]
    place(b, xbow, (10, 10))
    place(b, foe, (12, 10))
    cmd.posture = "balanced"
    assert cmd._kite_threat(xbow, b.army2) is None          # à l'offensive: il tient
    cmd.posture = "hold_line"
    assert cmd._kite_threat(xbow, b.army2) is foe           # en défense: il recule
    cmd.posture = "balanced"
    xbow.hp = max(1, xbow.max_hp // 2)
    if xbow.max_hp >= 2:                                    # blessé: il peut décrocher
        assert cmd._kite_threat(xbow, b.army2) is foe


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests agressivité passent.")
    sys.exit(1 if fails else 0)
