"""Tests des engins de siège (bélier, tour de siège). Script exécutable:
    python test_siege_engines.py          # tout
    python test_siege_engines.py tour     # seulement les tests dont le nom contient 'tour'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import combat
import siege_engines as se
import unit_library as ul
from battle import Battle

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def siege(engines, map_name="Siège", level=1, seed=5, att=None, dfd=None):
    random.seed(seed)
    att = att or {"Infanterie régulière": 4}
    dfd = dfd or {"Infanterie régulière": 3, "Arbaletrier régulier": 2}
    a1 = ul.build_army("Armée Skaldienne", list(att.items()))
    a1 += ul.build_army("Engins de siège", list(engines.items()))
    return Battle(a1, ul.build_army("Armée Skaldienne", list(dfd.items())), 40, 30, 8,
                  map_name=map_name, map_options={'fortification': level, 'seed': 11})


def engine(b, kind):
    return next(u for u in b.army1_roster if u.siege_engine == kind)


def place(b, unit, pos):
    bf = b.battlefield
    bf.remove_unit(unit)
    unit.position = pos
    assert bf.can_place_unit(*pos, unit), pos
    bf.place_unit(unit)


# ── Bibliothèque ──

@test
def test_engins_dans_la_bibliotheque():
    ram = ul.make_unit("Engins de siège", "Bélier")
    tower = ul.make_unit("Engins de siège", "Tour de siège")
    assert ram.siege_engine == se.RAM and ram.size == 2
    assert tower.siege_engine == se.TOWER and tower.size == 3 and tower._max_range >= 4
    assert ul.make_unit("Armée Skaldienne", "Officier").siege_engine is None


# ── Bélier ──

@test
def test_belier_ne_frappe_pas_les_troupes():
    b = siege({"Bélier": 1})
    ram = engine(b, se.RAM)
    assert ram.perform_attacks(b.army2[0], b.battlefield, b) == []


@test
def test_belier_enfonce_la_porte_avec_bonus():
    b = siege({"Bélier": 1})
    bf = b.battlefield
    ram = engine(b, se.RAM)
    gate = min(bf.active_gates)
    place(b, ram, (gate[0] - 2, gate[1]))
    b._refresh_army_sets()
    assert se.gate_distance(bf, ram, gate) == 1
    random.seed(4)
    before = sum(bf.gate_hp.values())
    for _ in range(4):
        b._attack_gate(ram)
    dealt = before - sum(bf.gate_hp.values())
    assert dealt >= 9, f"×{se.RAM_GATE_FACTOR}: {dealt} dégâts en 4 coups"


@test
def test_belier_marche_vers_la_porte_puis_se_range():
    b = siege({"Bélier": 1})
    bf = b.battlefield
    ram = engine(b, se.RAM)
    gate = se.ram_target_gate(bf, ram)
    start = se.gate_distance(bf, ram, gate)
    for _ in range(4):
        b.simulate_round()
    assert se.gate_distance(bf, ram, gate) < start, "le bélier avance vers la porte"
    for g in list(bf.active_gates):
        bf.gate_hp[g] = 0
    goal = se.engine_goal(bf, ram)
    rows = [g[1] for g in bf.active_gates]
    assert goal is not None and (goal[1] + 1 < min(rows) or goal[1] > max(rows)), \
        "passage ouvert: il se range hors de l'axe des portes"


@test
def test_huile_du_piege_brule_le_belier_sans_sauvegarde():
    b = siege({"Bélier": 1}, level=3)
    bf = b.battlefield
    ram = engine(b, se.RAM)
    gate = min(bf.active_gates)
    place(b, ram, (gate[0] - 2, gate[1]))
    b._refresh_army_sets()
    ram.base_sauvegarde = 1          # même une sauvegarde parfaite ne sert à rien
    pv = ram.pv
    random.seed(1)
    assert ram in b._spring_gate_trap(*gate)
    assert ram.pv < pv


# ── Tour de siège ──

@test
def test_tour_trouve_un_poste_d_accostage():
    for name in ("Siège", "Citadelle"):
        b = siege({"Tour de siège": 1}, name)
        bf = b.battlefield
        tower = engine(b, se.TOWER)
        site = se.tower_dock_site(bf, tower)
        assert site is not None, name
        assert site[0] == bf.wall_x - 2
        assert all(bf.grid[bf.wall_x][y] == 2 for y in range(site[1], site[1] + 4))


@test
def test_tour_accostee_devient_rampe_et_breche():
    b = siege({"Tour de siège": 1})
    bf = b.battlefield
    tower = engine(b, se.TOWER)
    site = se.tower_dock_site(bf, tower)
    place(b, tower, site)
    docked = b._dock_siege_towers()
    assert docked == [tower] and tower.docked
    assert tower not in b.army1 and tower in b.army1_roster
    assert not any(u is tower for u in bf.units.values())
    assert len(bf.siege_ramp_cells) == 8 and len(bf.bridge_cells) == 2
    assert all(bf.is_valid(*c) for c in bf.siege_ramp_cells | bf.bridge_cells)
    assert bf.active_breaches, "la passerelle compte comme une brèche"
    # Un fantassin passe du champ au chemin de ronde par la tour
    inf = b.army1[0]
    rampart = (bf.wall_x + 1, site[1] + 1)
    occupant = bf.units.get(rampart)
    if occupant is not None:
        bf.remove_unit(occupant)
    path = bf.a_star_path((site[0] - 1, site[1] + 1), rampart, inf, b, max_nodes=3000)
    assert path and path[-1] == rampart


@test
def test_tour_tire_a_hauteur_du_rempart():
    b = siege({"Tour de siège": 1})
    bf = b.battlefield
    tower = engine(b, se.TOWER)
    archer = next(u for u in b.army2 if u._max_range >= 4)
    assert bf.is_rampart(*archer.position)
    place(b, tower, (bf.wall_x - 5, min(bf.height - 5, archer.position[1])))
    assert bf.has_line_of_fire(tower, archer)
    prof = combat.attack_profile(tower, archer, tower.armes[0], bf)
    assert not any("rempart" in d[0].lower() for d in prof.details)
    inf = b.army1[0]
    prof_inf = combat.attack_profile(inf, archer, inf.armes[0], bf)
    assert any("rempart" in d[0].lower() for d in prof_inf.details)


@test
def test_engins_seuls_ne_tiennent_pas_le_terrain():
    b = siege({"Bélier": 1})
    for u in b.army1:
        if not u.siege_engine:
            u.take_damage(99)
    assert b.is_battle_over() == "Armée 2"


# ── Servants et pousseurs ──

def field(att, dfd, map_name="Prairie", seed=5):
    random.seed(seed)
    return Battle(att, dfd, 40, 30, 8, map_name=map_name)


@test
def test_baliste_sans_artilleurs_ne_tire_ni_ne_bouge():
    a1 = ul.build_army("Armée Skaldienne", [("Baliste", 1), ("Infanterie régulière", 2)])
    b = field(a1, ul.build_army("Armée Skaldienne", [("Infanterie régulière", 3)]))
    bf = b.battlefield
    bal = next(u for u in b.army1 if u.is_artillery)
    assert not se.manned(bf, b, bal)
    assert bf.compute_move(bal, b, set()) == (None, None)
    assert bal.perform_attacks(b.army2[0], bf, b) == []


@test
def test_artilleurs_rejoignent_leur_baliste_et_la_servent():
    a1 = ul.build_army("Armée Skaldienne", [("Baliste", 1)])
    a1 += ul.build_army("Engins de siège", [("Artilleur", 2)])
    b = field(a1, ul.build_army("Armée Skaldienne", [("Infanterie régulière", 3)]))
    bf = b.battlefield
    bal = next(u for u in b.army1 if u.is_artillery)
    for _ in range(5):
        b.simulate_round()
        if se.manned(bf, b, bal):
            break
    assert se.manned(bf, b, bal), "les deux artilleurs au contact"
    crew = [u for u in b.army1 if u.artilleur]
    assert all(u._attends is bal for u in crew)
    # Un seul artilleur ne suffit pas
    crew[0].take_damage(9)
    assert not se.manned(bf, b, bal)


@test
def test_tour_de_garnison_reduite_au_silence():
    b = siege({"Bélier": 1}, level=2)
    bf = b.battlefield
    bal = next(u for u in b.army2 if u.is_artillery)
    assert se.manned(bf, b, bal)
    for u in [u for u in b.army2 if u.artilleur]:
        u.take_damage(9)
    assert not se.manned(bf, b, bal)
    assert bal.perform_attacks(b.army1[0], bf, b) == []


@test
def test_engin_sans_pousseurs_reste_sur_place():
    a1 = ul.build_army("Armée Skaldienne", [("Arbaletrier régulier", 2)])
    a1 += ul.build_army("Engins de siège", [("Bélier", 1)])
    random.seed(5)
    b = Battle(a1, ul.build_army("Armée Skaldienne", [("Infanterie régulière", 3)]),
               40, 30, 8, map_name="Siège")
    ram = engine(b, se.RAM)
    start = ram.position
    for _ in range(3):
        b.simulate_round()
    assert ram.position == start, "des arbalétriers ne poussent pas un bélier"


@test
def test_guerriers_poussent_l_engin():
    b = siege({"Bélier": 1}, att={"Infanterie régulière": 4})
    bf = b.battlefield
    ram = engine(b, se.RAM)
    start = ram.position
    for _ in range(6):
        b.simulate_round()
    pushers = [u for u in b.army1 if getattr(u, '_attends', None) is ram]
    assert len(pushers) == se.PUSHERS_NEEDED[se.RAM]
    assert all(se.can_push(u) for u in pushers)
    assert ram.position != start, "poussé, le bélier avance"
    assert se.pusher_count(bf, b, ram) >= 1


@test
def test_avertissement_machines_sans_servants():
    bal = ul.build_army("Armée Skaldienne", [("Baliste", 1), ("Arbaletrier régulier", 2)])
    assert "artilleur" in se.staffing_warning(bal)
    bal += ul.build_army("Engins de siège", [("Artilleur", 2)])
    assert se.staffing_warning(bal) is None
    ram = ul.build_army("Engins de siège", [("Bélier", 1)])
    assert "guerrier" in se.staffing_warning(ram)
    ram += ul.build_army("Armée Skaldienne", [("Infanterie régulière", 2)])
    assert se.staffing_warning(ram) is None


@test
def test_batailles_completes_avec_engins():
    for name in ("Siège", "Citadelle"):
        for level in (1, 3):
            b = siege({"Bélier": 1, "Tour de siège": 1}, name, level,
                      att={"Infanterie régulière": 6, "Arbaletrier régulier": 2})
            while not b.is_battle_over() and b.round <= 60:
                b.simulate_round()


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests engins de siège passent.")
    sys.exit(1 if fails else 0)
