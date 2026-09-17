"""Tests des formations en bloc (formation.py + CommanderAI._plan_formations).
Script exécutable:
    python test_formation.py            # tout
    python test_formation.py rupture    # seulement les tests dont le nom contient 'rupture'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import formation
import unit_library as ul
from ai_commander import CommanderAI
from battle import Battle

TESTS = []

INF = ("Armée Skaldienne", {"Infanterie régulière": 8, "Arbaletrier régulier": 4, "Officier": 1})


def test(fn):
    TESTS.append(fn)
    return fn


def battle(army=INF, map_name="Prairie", seed=1, w=178, h=64, map_options=None):
    random.seed(seed)
    return Battle(ul.build_army(army[0], list(army[1].items())),
                  ul.build_army(army[0], list(army[1].items())), w, h, 8,
                  map_name=map_name, map_options=map_options)


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def orders(army):
    return [u._tactical_order.order_type for u in army
            if u.is_alive and getattr(u, '_tactical_order', None)]


# ── Géométrie ──

@test
def test_geometrie_bloc_plus_large_que_profond():
    for n in (1, 3, 4, 8, 12, 20):
        w = formation.files_per_rank(n)
        assert 1 <= w <= n and formation.depth(n) <= w, (n, w)


@test
def test_cases_uniques_praticables_derriere_l_ancre():
    b = battle(seed=2)
    bf = b.battlefield
    units = [u for u in b.army1 if u._max_range < 4][:8]
    anchor, axis = (60.0, 32.0), (1.0, 0.0)
    ordered = formation.arrange(units, anchor, axis)
    cells = formation.slots(bf, ordered, anchor, axis, start_rank=2)
    assert len(cells) == len(units)
    assert len(set(cells.values())) == len(cells)
    for (x, y) in cells.values():
        assert bf.is_valid(x, y)
        assert x <= 60 - 2 + 3, (x, y)          # rangs 2 et suivants: derrière l'ancre


@test
def test_ordre_stable_tant_que_le_bloc_ne_change_pas():
    b = battle(seed=3)
    units = [u for u in b.army1 if u._max_range < 4]
    first = formation.arrange(units, (50, 30), (1.0, 0.0))
    memory = [id(u) for u in first]
    random.shuffle(units)
    again = formation.arrange(units, (50, 30), (1.0, 0.0), memory)
    assert [id(u) for u in again] == memory


# ── Marche ──

@test
def test_marche_en_formation_puis_blocs_serres():
    b = battle(seed=4)
    b.simulate_round()
    for army in (b.army1, b.army2):
        assert orders(army).count("form") >= len(army) // 2, orders(army)
    for _ in range(3):
        b.simulate_round()
    for army in (b.army1, b.army2):
        mob = [u for u in army if u.is_alive and u.vitesse > 0]
        packed = sum(1 for u in mob
                     if sorted(cheb(u.position, a.position) for a in mob if a is not u)[1] <= 2)
        assert packed * 10 >= len(mob) * 7, (packed, len(mob))


@test
def test_tireurs_derriere_la_melee_pendant_la_marche():
    b = battle(seed=5)
    for _ in range(3):
        b.simulate_round()
    cmd = b.commander1
    melee = [u for u in b.army1 if u.is_alive and u._max_range < 4 and u.encouragement_range == 0]
    shooters = [u for u in b.army1 if u.is_alive and u._max_range >= 4
                and u._tactical_order.order_type == "form"]
    assert shooters
    front = max(cmd._proj(u.position) for u in melee)
    for u in shooters:
        assert cmd._proj(u.position) < front, (u.name, u.position)


@test
def test_rupture_des_rangs_au_contact():
    """Au contact, plus personne ne marche en formation: on charge."""
    b = battle(seed=6, w=60, h=40)
    contact = False
    for _ in range(30):
        b.simulate_round()
        if any(cheb(u.position, e.position) <= 3 for u in b.army1 if u.is_alive
               for e in b.army2 if e.is_alive):
            contact = True
            break
    assert contact
    b.simulate_round()
    for army, en in ((b.army1, b.army2), (b.army2, b.army1)):
        for u in army:
            if not u.is_alive or u._max_range >= 4:
                continue
            o = u._tactical_order
            near = min(cheb(u.position, e.position) for e in en if e.is_alive)
            if near <= 3:
                assert o.order_type != "form", (u.name, near)


# ── Cas exclus ──

@test
def test_pas_de_formation_en_siege_ni_en_sous_bois_ni_desactivee():
    b = battle(map_name="Siège", seed=7, w=60, h=40)
    b.simulate_round()
    assert "form" not in orders(b.army1) + orders(b.army2)

    b = battle(map_name="Forêt", seed=7)
    b.simulate_round()
    assert "form" not in orders(b.army1) + orders(b.army2)

    CommanderAI.use_formations = False
    try:
        b = battle(seed=7)
        b.simulate_round()
        assert "form" not in orders(b.army1) + orders(b.army2)
    finally:
        CommanderAI.use_formations = True


@test
def test_bataille_complete_sur_chaque_carte():
    for name in ("Prairie", "Désert", "Village", "Défilé"):
        b = battle(map_name=name, seed=8, w=60, h=40)
        while not b.is_battle_over() and b.round <= 90:
            b.simulate_round()
        assert b.is_battle_over(), name


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests formations passent.")
    sys.exit(1 if fails else 0)
