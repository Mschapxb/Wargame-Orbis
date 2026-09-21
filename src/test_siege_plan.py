"""Tests des stratégies de siège (siege_plan.py). Script exécutable:
    python test_siege_plan.py            # tout
    python test_siege_plan.py defense    # seulement les tests dont le nom contient 'defense'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import combat
import siege_engines as se
import siege_plan as sp
import unit_library as ul
from battle import Battle
from battle_plan import BattlePlan

TESTS = []

ATT = [("Infanterie régulière", 8), ("Arbaletrier régulier", 4), ("Officier", 1)]
DEF = [("Infanterie régulière", 5), ("Arbaletrier régulier", 4), ("Officier", 1)]


def test(fn):
    TESTS.append(fn)
    return fn


def siege(extra=None, map_name="Siège", level=1, seed=5):
    random.seed(seed)
    a1 = ul.build_army("Armée Skaldienne", ATT)
    if extra:
        a1 += ul.build_army("Engins de siège", extra)
    a2 = ul.build_army("Armée Skaldienne", DEF)
    return Battle(a1, a2, 40, 30, 8, map_name=map_name,
                  map_options={'fortification': level, 'seed': 11})


def rounds(b, n):
    for _ in range(n):
        if b.is_battle_over():
            break
        b.simulate_round()


def move(b, unit, pos):
    bf = b.battlefield
    bf.remove_unit(unit)
    unit.position = pos
    bf.place_unit(unit)


# ── Choix du plan ──

@test
def test_plan_de_siege_seulement_en_siege():
    random.seed(1)
    b = Battle(ul.build_army("Armée Skaldienne", ATT), ul.build_army("Armée Skaldienne", DEF),
               40, 30, 8, map_name="Prairie")
    assert isinstance(b.commander1.plan, BattlePlan) and isinstance(b.commander2.plan, BattlePlan)
    b = siege()
    assert isinstance(b.commander1.plan, sp.SiegePlan) and b.commander1.plan.attacker
    assert isinstance(b.commander2.plan, sp.SiegePlan) and b.commander2.plan.kind == "defense"


def _pilonnage():
    random.seed(5)
    a1 = ul.build_army("Armée Skaldienne", ATT + [("Baliste", 1)])
    a1 += ul.build_army("Engins de siège", [("Artilleur", 2)])
    return Battle(a1, ul.build_army("Armée Skaldienne", DEF), 40, 30, 8, map_name="Siège")


@test
def test_choix_du_plan_selon_l_armee():
    cases = [(None, "Siège", "direct"),
             ([("Bélier", 1)], "Siège", "engins"),
             ([("Tour de siège", 1)], "Siège", "engins"),
             (None, "Citadelle", "feinte")]
    for extra, name, kind in cases:
        b = siege(extra, name)
        rounds(b, 1)
        assert b.commander1.plan.kind == kind, (extra, name, b.commander1.plan.kind)
    b = _pilonnage()
    rounds(b, 1)
    assert b.commander1.plan.kind == "pilonnage"
    assert b.commander1.plan.label().startswith("Pilonnage")


# ── Offensive ──

@test
def test_pilonnage_l_infanterie_attend_hors_de_portee():
    b = _pilonnage()
    rounds(b, 3)
    plan = b.commander1.plan
    assert plan.phase == "bombardement"
    reach = max(e._max_range for e in b.army2 if e._max_range >= 4)
    assert plan.staging_x <= b.battlefield.wall_x - reach
    melee = [u for u in b.army1 if u.is_alive and sp._is_melee(u)]
    assert melee
    for u in melee:
        if any(abs(u.position[0] - e.position[0]) + abs(u.position[1] - e.position[1]) <= 2
               for e in b.army2 if e.is_alive):
            continue
        o = u._tactical_order
        assert o.order_type in ("support", "hold"), o.order_type
        assert o.target_pos[0] <= plan.staging_x


@test
def test_pilonnage_passe_a_l_assaut():
    b = _pilonnage()
    rounds(b, sp.BOMBARD_MAX + 2)
    assert b.commander1.plan.phase == "assaut"
    b = _pilonnage()
    rounds(b, 1)
    for g in b.battlefield.active_gates:
        b.battlefield.gate_hp[g] = 0            # passage ouvert
    rounds(b, 1)
    assert b.commander1.plan.phase == "assaut"


@test
def test_assaut_coordonne_suit_les_engins():
    b = siege([("Tour de siège", 1)])
    rounds(b, 1)
    plan = b.commander1.plan
    assert plan.phase == "approche"
    tower = next(u for u in b.army1 if u.siege_engine == se.TOWER)
    for _ in range(40):
        if plan.phase == "assaut" or b.is_battle_over():
            break
        b.simulate_round()
    assert plan.phase == "assaut"
    assert (not tower.is_alive or tower.docked or se.passage_open(b.battlefield)
            or plan._engine_left(b.battlefield, tower) <= sp.ENGINE_ASSAULT_DIST)


@test
def test_feinte_envoie_deux_leurres_devant_l_autre_porte():
    b = siege(None, "Citadelle")
    rounds(b, 2)
    plan = b.commander1.plan
    lures = [u for u in b.army1 if plan.roles.get(id(u)) == "lure"]
    assert len(lures) == sp.LURES
    spot = plan.points['leurre']
    assert spot is not None and abs(spot[1] - plan.points['attente'][1]) > 3
    for u in lures:
        if u._tactical_order.order_type in ("support", "hold"):
            assert u._tactical_order.target_pos == spot


# ── Défensive ──

@test
def test_defense_suit_la_menace_du_belier():
    b = siege([("Bélier", 1)])
    rounds(b, 1)
    plan = b.commander2.plan
    ram = next(u for u in b.army1 if u.siege_engine == se.RAM)
    gate = se.ram_target_gate(b.battlefield, ram)
    assert plan.phase == "porte" and plan.points['menace'] == gate
    post = plan._reserve_post(b.commander2, 0)
    assert post[0] > b.battlefield.wall_x and abs(post[1] - gate[1]) <= 2


@test
def test_defense_monte_au_devant_de_la_tour():
    b = siege([("Tour de siège", 1)])
    bf = b.battlefield
    tower = next(u for u in b.army1 if u.siege_engine == se.TOWER)
    site = se.tower_dock_site(bf, tower)
    move(b, tower, (site[0] - 3, site[1]))
    b.commander2.plan.update(b.commander2, [u for u in b.army2 if u.is_alive],
                             [u for u in b.army1 if u.is_alive], {})
    plan = b.commander2.plan
    assert plan.phase == "tour"
    post = plan._reserve_post(b.commander2, 0)
    assert bf.is_rampart(*post) and post[1] in (site[1] + 1, site[1] + 2)


@test
def test_defense_tient_la_breche():
    b = siege()
    bf = b.battlefield
    breach = (bf.wall_x, 5)
    bf.breaches.add(breach)
    rounds(b, 1)
    plan = b.commander2.plan
    assert plan.phase == "breche" and plan.points['menace'] == breach


@test
def test_garnison_vise_les_pousseurs():
    b = siege([("Bélier", 1)])
    bf = b.battlefield
    ram = next(u for u in b.army1 if u.siege_engine == se.RAM)
    pusher = next(u for u in b.army1 if getattr(u, '_attends', None) is ram)
    far = b.commander2.plan.target_bonus(b.commander2, pusher)
    move(b, ram, (bf.wall_x - 4, ram.position[1]))
    assert b.commander2.plan.target_bonus(b.commander2, pusher) > far


@test
def test_passerelle_seule_ne_fait_pas_abandonner_l_enceinte():
    b = siege([("Tour de siège", 1)], "Citadelle")
    bf = b.battlefield
    tower = next(u for u in b.army1 if u.siege_engine == se.TOWER)
    site = se.tower_dock_site(bf, tower)
    move(b, tower, site)
    assert b._dock_siege_towers() == [tower]
    # un assaillant au pied du mur, personne derrière
    foe = next(u for u in b.army1 if u.is_alive and not u.siege_engine
               and not getattr(u, '_attends', None))
    spot = next((bf.wall_x - 1, y) for y in range(1, bf.height - 1)
                if bf.can_place_unit(bf.wall_x - 1, y, foe))
    move(b, foe, spot)
    assert bf.active_breaches
    assert not b.commander2._ring_about_to_fall(b.commander2.assess())


# ── Règles touchées ──

@test
def test_rempart_ne_protege_que_des_tirs():
    b = siege()
    bf = b.battlefield
    archer = next(u for u in b.army2 if u._max_range >= 4 and bf.is_rampart(*u.position))
    shooter = next(u for u in b.army1 if u._max_range >= 4)
    melee = next(u for u in b.army1 if u._max_range < 4)
    ranged = combat.attack_profile(shooter, archer, shooter.armes[0], bf)
    blade = combat.attack_profile(melee, archer, melee.armes[0], bf)
    assert any("rempart" in d[0].lower() for d in ranged.details)
    assert not any("rempart" in d[0].lower() for d in blade.details)


@test
def test_batailles_completes():
    for extra, name in ((None, "Siège"), (None, "Citadelle"),
                        ([("Bélier", 1), ("Tour de siège", 1)], "Siège")):
        b = siege(extra, name, level=2)
        rounds(b, 60)


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests de stratégie de siège passent.")
    sys.exit(1 if fails else 0)
