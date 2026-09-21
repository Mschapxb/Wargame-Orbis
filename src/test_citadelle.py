"""Tests du lot B3 (Citadelle à double enceinte). Script exécutable:
    python test_citadelle.py            # tout
    python test_citadelle.py bascule    # seulement les tests dont le nom contient 'bascule'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import maps
import structures as st
import terrain as tr
import unit_library as ul
from battle import Battle
from battlefield import Battlefield

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def citadel(seed=1, w=60, h=40, att=None, dfd=None):
    random.seed(seed)
    att = att or {"Infanterie régulière": 3}
    dfd = dfd or {"Infanterie régulière": 3}
    return Battle(ul.build_army("Armée Skaldienne", list(att.items())),
                  ul.build_army("Armée Skaldienne", list(dfd.items())), w, h, 8,
                  map_name="Citadelle")


# ── Modèle d'enceintes ──

@test
def test_siege_une_seule_enceinte():
    random.seed(3)
    grid, data = maps.generate_map("Siège", 40, 30)
    bf = Battlefield(40, 30, 0, "Siège", grid, data)
    assert bf.is_siege and len(bf.rings) == 1 and not bf.has_next_ring
    assert bf.wall_x == data['wall_x']
    assert set(bf.active_gates) == set(bf.gate_hp)
    assert not bf.advance_ring()


@test
def test_portes_du_donjon_fermees_et_ouverture_par_case():
    b = citadel()
    bf = b.battlefield
    assert len(bf.rings) == 2 and bf.active_ring == 0
    kg = bf.rings[1]['gates'][0]
    assert not bf.is_valid(*kg), "le donjon est fermé tant que l'extérieur tient"
    bf.open_gates()
    assert bf.gates_open and not bf.is_valid(*kg), "ouvrir l'extérieur n'ouvre pas le donjon"
    assert all(bf.is_valid(*g) for g in bf.rings[0]['gates'])
    bf.open_ring_gates(1)
    assert bf.is_valid(*kg)
    assert bf.close_gates() and not bf.gates_open
    assert bf.is_valid(*kg), "refermer l'extérieur laisse le donjon ouvert"


@test
def test_advance_ring_force_les_portes():
    b = citadel()
    bf = b.battlefield
    outer = list(bf.rings[0]['gates'])
    assert bf.advance_ring()
    assert bf.active_ring == 1 and bf.wall_x == bf.rings[1]['wall_x']
    assert all(bf.gate_hp[g] <= 0 and bf.is_valid(*g) for g in outer)
    assert set(bf.active_gates) == set(bf.rings[1]['gates'])
    assert not bf.has_next_ring


# ── Géographie ──

@test
def test_geographie_citadelle():
    for (w, h) in ((40, 30), (60, 40), (178, 64)):
        random.seed(5)
        grid, data = maps.generate_map("Citadelle", w, h)
        wx1, wx2 = data['rings'][0]['wall_x'], data['rings'][1]['wall_x']
        assert wx1 < wx2 < w - 3
        assert len({g[1] for g in data['rings'][0]['gates']}) == 8, "deux portes de 4 cases"
        assert len(data['rings'][1]['gates']) == 4
        # Une fois toutes les portes tombées, l'assaillant rejoint le donjon
        open_grid = [[0 if c == 3 else c for c in col] for col in grid]
        start = next((x, h // 2) for x in range(2, 6) if open_grid[x][h // 2] == 0)
        goal = (wx2 + 4, h // 2)
        assert maps._bfs_path(open_grid, w, h, [start], [goal], data['terrain']) is not None, (w, h)
        kinds = set(data['structures'].values())
        assert st.WALL in kinds and st.PALISADE in kinds
        if w >= 60:
            assert st.HOUSE in kinds, "la basse-cour a des maisons"
        terr = data['terrain']
        assert any(terr[wx1 - 1][y] == tr.MARSH for y in range(h))
        assert any(terr[wx2 - 1][y] == tr.HILL for y in range(h))


# ── Bascule ──

@test
def test_bascule_quand_les_defenseurs_ont_rejoint_le_donjon():
    b = citadel()
    bf = b.battlefield
    kx = bf.rings[1]['wall_x']
    free = [(x, y) for x in range(kx + 4, bf.width - 1) for y in range(1, bf.height - 1)
            if bf.is_valid(x, y) and (x, y) not in bf.units]
    for u, pos in zip(b.army2, free):
        bf.move_unit(u, pos)
    assert b._check_ring_fall()
    assert bf.active_ring == 1
    assert any("ENCEINTE" in txt for txt, _, _ in b.round_events)


@test
def test_bascule_quand_l_assaillant_est_passe():
    b = citadel(att={"Infanterie régulière": 4})
    bf = b.battlefield
    wx = bf.wall_x
    assert not b._check_ring_fall(), "rien n'est tombé au départ"
    for g in bf.rings[0]['gates']:
        bf.gate_hp[g] = 0
    assert not b._check_ring_fall(), "portes tombées mais personne n'est passé"
    inside = [(x, y) for x in range(wx + 5, wx + 8) for y in range(1, bf.height - 1)
              if bf.is_valid(x, y) and (x, y) not in bf.units]
    for u, pos in zip(b.army1[:3], inside):
        bf.move_unit(u, pos)
    assert b._check_ring_fall() and bf.active_ring == 1


@test
def test_repli_vers_le_donjon_et_designe_l_arriere_garde():
    b = citadel(dfd={"Infanterie régulière": 6, "Arbaletrier régulier": 3})
    bf = b.battlefield
    cmd = b.commander2
    wx = bf.wall_x
    for g in bf.rings[0]['gates']:
        bf.gate_hp[g] = 2
    spots = [(wx - 1, g[1]) for g in bf.rings[0]['gates']]
    for u, pos in zip(b.army1, spots):
        if bf.is_valid(*pos) and pos not in bf.units:
            bf.move_unit(u, pos)
    cmd.issue_orders(b)
    assert cmd.posture == "fall_back", cmd.posture
    # Le donjon reste FERMÉ à l'assaillant: la garnison se fait ouvrir ses
    # portes pour elle seule (Battlefield.gate_cells_open_for)
    keep = bf.rings[1]['gates']
    assert not any(g in bf.open_gate_cells for g in keep)
    defender = next(u for u in b.army2 if u.is_alive)
    attacker = next(u for u in b.army1 if u.is_alive)
    assert all(g in bf.gate_cells_open_for(defender) for g in keep)
    assert not any(g in bf.gate_cells_open_for(attacker) for g in keep)
    assert cmd._rearguard
    kinds = {u._tactical_order.order_type for u in b.army2 if u.is_alive}
    assert "withdraw" in kinds, kinds


@test
def test_scenario_citadelle_se_termine():
    """Assaut fort: la bataille se termine, et l'enceinte extérieure tombe
    dans une partie des graines (repli ou percée). Depuis les stratégies de
    siège (réserve mobile de la garnison, cf. siege_plan.py), la chute est
    plus rare: 3 parties sur 40 (l'assaillant gagne 33 fois sur 40, en
    usant la garnison au goulet): 40 graines, pas 16."""
    falls, ended = 0, 0
    for seed in range(40):
        b = citadel(1000 + seed, 40, 30,
                    att={"Infanterie régulière": 10, "Arbaletrier régulier": 5, "Officier": 1},
                    dfd={"Infanterie régulière": 5, "Arbaletrier régulier": 4, "Officier": 1})
        while not b.is_battle_over() and b.round <= 90:
            b.simulate_round()
        ended += bool(b.is_battle_over())
        falls += b.battlefield.active_ring == 1
    assert ended >= 36, ended
    assert falls >= 1, falls


# ── Rendu ──

@test
def test_rendu_citadelle():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    from renderer import build_grid_surface, repaint_region, gate_visual_state
    b = citadel(7)
    bf = b.battlefield
    surf = build_grid_surface(b, 16)
    assert bf._has_buildings, "les maisons de la basse-cour sont dessinées d'un seul tenant"
    before = gate_visual_state(bf)
    bf.open_ring_gates(1)
    assert gate_visual_state(bf) != before, "ouvrir le donjon change l'aspect des portes"
    palis = next(c for c, e in bf.structures.items() if e[0] == st.PALISADE)
    repaint_region(surf, b, 16, [palis])


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests citadelle passent.")
    sys.exit(1 if fails else 0)
