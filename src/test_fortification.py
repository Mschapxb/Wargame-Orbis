"""Tests des niveaux de fortification (Siège, Citadelle). Script exécutable:
    python test_fortification.py          # tout
    python test_fortification.py piege    # seulement les tests dont le nom contient 'piege'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import maps
import unit_library as ul
from battle import Battle, TRAP_BURN

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def siege(level, map_name="Siège", seed=5, att=None, dfd=None, w=40, h=30):
    random.seed(seed)
    att = att or {"Infanterie régulière": 4}
    dfd = dfd or {"Infanterie régulière": 3, "Arbaletrier régulier": 2}
    opts = {'fortification': level, 'seed': 11}
    return Battle(ul.build_army("Armée Skaldienne", list(att.items())),
                  ul.build_army("Armée Skaldienne", list(dfd.items())), w, h, 8,
                  map_name=map_name, map_options=opts)


def crews(b):
    """Balistes de tour (sans leurs artilleurs)."""
    return [u for u in b.army2 if u.contingent == "Garnison" and u.is_artillery]


def servants(b):
    return [u for u in b.army2 if u.contingent == "Garnison" and u.artilleur]


# ── Carte ──

@test
def test_niveau_1_identique_a_la_carte_historique():
    for name in maps.SIEGE_MAPS:
        random.seed(4)
        g0, d0 = maps.generate_map(name, 40, 30)
        random.seed(4)
        g1, d1 = maps.generate_map(name, 40, 30, {'fortification': 1})
        assert g0 == g1 and d0['gates'] == d1['gates'], name
        assert not d1.get('towers') and not d1.get('gate_trap'), name


@test
def test_portes_renforcees_par_niveau():
    for name in maps.SIEGE_MAPS:
        for level in (1, 2, 3):
            random.seed(4)
            _g, d = maps.generate_map(name, 40, 30, {'fortification': level})
            assert set(d['gates'].values()) == {maps.GATE_HP[level]}, (name, level)
    assert maps.GATE_HP[1] < maps.GATE_HP[2] < maps.GATE_HP[3]


@test
def test_libelles_et_valeurs_du_niveau():
    assert maps.fortification_of(None) == 1
    assert maps.fortification_of({'fortification': "Niveau 3"}) == 3
    assert maps.fortification_of({'fortification': 2}) == 2
    assert maps.fortification_of({'fortification': 9}) == 3


@test
def test_tour_sur_le_chemin_de_ronde_de_l_enceinte_exterieure():
    for name in maps.SIEGE_MAPS:
        for w, h in ((40, 30), (60, 40)):
            random.seed(2)
            _g, d = maps.generate_map(name, w, h, {'fortification': 2})
            outer = [t for t in d['towers'] if t['ring'] == 0]
            assert len(outer) == 1, (name, w, h)
            t = outer[0]
            ramparts = set(map(tuple, d['ramparts']))
            assert all(c in ramparts for c in t['cells']), (name, w, h)
            wx = (d.get('rings') or [{'wall_x': d['wall_x']}])[0]['wall_x']
            assert all(wx < c[0] <= wx + 2 for c in t['cells']), "tour sur l'enceinte extérieure"


@test
def test_autres_cartes_non_touchees():
    random.seed(4)
    _g, d = maps.generate_map("Prairie", 40, 30, {'fortification': 3})
    assert 'towers' not in d and 'fortification' not in d


# ── Bataille ──

@test
def test_niveau_1_sans_baliste_de_tour():
    b = siege(1)
    assert not crews(b) and not b.battlefield.towers
    assert len(b.army2) == 5 and b.army2_initial_size == 5


@test
def test_baliste_de_tour_posee_et_immobile():
    for name in ("Siège",):
        b = siege(2, name)
        bf = b.battlefield
        (crew,) = crews(b)
        assert crew in b.army2 and crew in b.army2_roster
        assert b.army2_initial_size == 8, "baliste + ses deux artilleurs"
        assert len(servants(b)) == 2
        assert all(bf.is_rampart(*s.position) and s._attends is crew for s in servants(b))
        assert crew.position == bf.towers[0]['anchor']
        assert set(bf.get_unit_cells(crew)) == set(bf.towers[0]['cells'])
        assert crew.vitesse == 0 and crew.is_artillery
        assert bf.on_active_rampart(*crew.position, crew, b)
        # aucune unité de la garnison ne partage ses cases
        others = {c for u in b.army2 if u is not crew for c in bf.get_unit_cells(u)}
        import siege_engines as se
        assert se.manned(bf, b, crew), "servie dès le déploiement"
        assert not others & set(bf.tower_cells)
        for _ in range(3):
            b.simulate_round()
        assert crew.position == bf.towers[0]['anchor'], "la baliste ne quitte pas la tour"


@test
def test_baliste_de_tour_tuable():
    b = siege(2)
    (crew,) = crews(b)
    crew.take_damage(crew.max_pv)
    assert not crew.is_alive
    b.simulate_round()
    assert b.is_battle_over() is None, "la garnison continue sans sa tour"


@test
def test_redemarrage_ne_duplique_pas_la_tour():
    b = siege(2)
    assert all(u.contingent != "Garnison" for u in b._restart_army2)
    b2 = Battle(b._restart_army1, b._restart_army2, 40, 30, 8,
                map_name="Siège", map_options=b.map_options)
    assert len(crews(b2)) == 1


@test
def test_munitions_doublees_au_niveau_3():
    n2 = siege(2)
    n3 = siege(3)
    archers2 = [u for u in n2.army2 if u.max_ammo]
    archers3 = [u for u in n3.army2 if u.max_ammo]
    assert archers2 and archers3
    assert all(u3.max_ammo == 2 * u2.max_ammo for u2, u3 in zip(archers2, archers3))


@test
def test_citadelle_tombe_malgre_la_baliste_fixe():
    """Règle (b): une pièce fixe restée sur l'enceinte extérieure ne la
    retient pas quand toute la garnison mobile s'est repliée."""
    b = siege(2, "Citadelle")
    bf = b.battlefield
    next_x = bf.rings[1]['wall_x']
    for u in b.army2:
        if u.vitesse > 0:
            bf.remove_unit(u)
            u.position = next(((x, y) for x in range(next_x + 1, bf.width - 1)
                               for y in range(1, bf.height - 1) if bf.can_place_unit(x, y, u)))
            bf.place_unit(u)
    assert b._check_ring_fall() and bf.active_ring == 1


@test
def test_citadelle_balistes_sur_le_donjon_selon_le_niveau():
    for level, keep_towers in ((1, 0), (2, 1), (3, 2)):
        b = siege(level, "Citadelle")
        bf = b.battlefield
        keep = [t for t in bf.towers if t['ring'] == 1]
        assert len(keep) == keep_towers, (level, len(keep))
        kx = bf.rings[1]['wall_x']
        for t in keep:
            assert all(kx < c[0] <= kx + 2 for c in t['cells'])
            gun = next(u for u in crews(b) if u.position == t['anchor'])
            assert sum(1 for s in servants(b) if s._attends is gun) == 2
        assert len(crews(b)) == (0 if level == 1 else 1 + keep_towers)


@test
def test_portee_des_armes_de_siege_allongee():
    bal = ul.make_unit("Armée Skaldienne", "Baliste")
    assert bal.armes[0].porte == 18 + ul.SIEGE_RANGE_BONUS
    assert bal.armes[0].base_porte == bal.armes[0].porte
    tower = next(u for u in siege(2).army2 if u.is_artillery)
    assert tower.armes[0].porte == 18 + ul.SIEGE_RANGE_BONUS
    xbow = ul.make_unit("Armée Skaldienne", "Arbaletrier régulier")
    assert xbow._max_range < 18, "les armes ordinaires ne changent pas"


# ── Porte piégée ──

def _break_gate(b):
    bf = b.battlefield
    gate = min(bf.active_gates)
    x, y = gate[0] - 1, gate[1]
    attacker = b.army1[0]
    bf.remove_unit(attacker)
    attacker.position = (x, y)
    bf.place_unit(attacker)
    b._refresh_army_sets()
    for g in bf.gate_group(*gate):
        bf.gate_hp[g] = 1
    return gate, attacker


@test
def test_piege_de_porte_niveau_3():
    b = siege(3)
    bf = b.battlefield
    gate, attacker = _break_gate(b)
    group = bf.gate_group(*gate)
    random.seed(1)
    hit = b._spring_gate_trap(*gate)
    assert attacker in hit
    assert not bf.trapped_gates & set(group), "le piège ne joue qu'une fois"
    assert all(bf.fires.get(g) == TRAP_BURN for g in group), "flaque d'huile en feu"
    assert b._spring_gate_trap(*gate) == []


@test
def test_piege_declenche_par_la_destruction_de_la_porte():
    b = siege(3)
    bf = b.battlefield
    gate, attacker = _break_gate(b)
    attacker.armes[0].nb_attaque = 20       # la porte cède à coup sûr
    random.seed(2)
    b._attack_gate(attacker)
    assert any(bf.gate_hp[g] <= 0 for g in bf.gate_group(*gate))
    assert any("PIÈGE" in e[0] for e in b.round_events)


@test
def test_pas_de_piege_avant_le_niveau_3():
    b = siege(2)
    gate, _attacker = _break_gate(b)
    assert not b.battlefield.trapped_gates
    assert b._spring_gate_trap(*gate) == []


@test
def test_bataille_complete_par_niveau():
    for name in maps.SIEGE_MAPS:
        for level in (2, 3):
            b = siege(level, name, att={"Infanterie régulière": 6, "Arbaletrier régulier": 2})
            while not b.is_battle_over() and b.round <= 60:
                b.simulate_round()


# ── Écran de carte ──

@test
def test_ecran_de_carte_transmet_le_niveau():
    from map_screen import MapSetup
    s = MapSetup("Siège")
    assert 'fortification' not in s.options()
    s.fortification = maps.FORTIFICATION_LEVELS[2]
    assert s.options()['fortification'] == 3
    s.set_map("Prairie")
    assert 'fortification' not in s.options(), "pas de défenses hors siège"


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests fortification passent.")
    sys.exit(1 if fails else 0)
