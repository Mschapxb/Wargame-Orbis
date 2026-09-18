"""Tests du lot B1 (structures destructibles, incendie, ruines). Script exécutable:
    python test_destruction.py            # tout
    python test_destruction.py feu        # seulement les tests dont le nom contient 'feu'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import maps
import structures as st
import tactics
import terrain as tr
import unit_library as ul
from ai_commander import CommanderAI
from battle import Battle
from battlefield import Battlefield
from models import Arme
from unit import Unit

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def make_bf(w=20, h=12, structs=None, terrain_cells=None):
    """Battlefield de test: `structs` = {(x, y): kind} (cases mises à 1)."""
    grid = [[0] * h for _ in range(w)]
    terr = tr.make_grid(w, h)
    for (x, y), name in (terrain_cells or {}).items():
        terr[x][y] = name
    for (x, y) in (structs or {}):
        grid[x][y] = 1
    return Battlefield(w, h, 0, "Prairie", grid,
                       {'terrain': terr, 'structures': dict(structs or {})})


class RiggedRng:
    """Tirage constant: propagation certaine (0.0) ou nulle (0.99)."""
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value

    def shuffle(self, seq):
        pass


def soldier(pos, save=7, pv=10):
    u = Unit("Soldat", pv=pv, vitesse=4, morale=3, sauvegarde=save, color=(1, 1, 1),
             armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    u.position = pos
    return u


def ballista(pos):
    u = Unit("Baliste", pv=10, vitesse=1, morale=3, sauvegarde=7, color=(1, 1, 1),
             armes=[Arme("Carreau", nb_attaque=1, toucher=4, blesser=2, perforation=-2,
                         degats="1d4", porte=18)],
             unit_type="Artillerie")
    u.position = pos
    return u


# ── Terrain: décombres, brûlé, feu ──

@test
def test_terrain_decombres_et_brule():
    bf = make_bf(terrain_cells={(3, 0): tr.RUBBLE, (4, 0): tr.BURNT})
    assert tr.step_cost(bf, (2, 0), (3, 0)) == 2.0
    assert tr.step_cost(bf, (3, 0), (4, 0)) == 1.0
    assert not tr.charge_ok(bf, 3, 0) and tr.charge_ok(bf, 4, 0)
    shooter, target = soldier((0, 0)), soldier((3, 0))
    assert tr.combat_mods(bf, shooter, target, True)['toucher'] == 1
    assert not tr.blocks_line(bf, 0, 0, 8, 0)


@test
def test_feu_cout_et_fumee():
    bf = make_bf()
    bf.fires = {(3, 0): 2, (4, 0): 2}
    assert tr.step_cost(bf, (2, 0), (3, 0)) == tr.FIRE_MOVE_FACTOR
    assert not tr.blocks_line(bf, 0, 0, 8, 0), "2 cases de fumée ne masquent pas"
    bf.fires[(5, 0)] = 2
    assert tr.blocks_line(bf, 0, 0, 8, 0), "3 cases de fumée masquent"


@test
def test_feu_astar_contourne():
    bf = make_bf(w=12, h=5)
    bf.fires = {(5, 2): 2}
    u = soldier((2, 2))
    bf.place_unit(u)

    class FB:
        def get_allies(self, unit):
            return []
    path = bf.a_star_path((2, 2), (8, 2), u, FB(), max_nodes=4000)
    assert path and (5, 2) not in path, path


# ── Structures: construction ──

@test
def test_maison_est_un_seul_groupe():
    house = {(x, y): st.HOUSE for x in (2, 3, 4) for y in (1, 2)}
    hedge = {(8, y): st.HEDGE for y in range(1, 4)}
    bf = make_bf(structs={**house, **hedge})
    gids = {bf.structures[c][1] for c in house}
    assert len(gids) == 1
    assert bf.structure_hp[gids.pop()] == st.KINDS[st.HOUSE]['hp']
    assert len({bf.structures[c][1] for c in hedge}) == 3, "une haie = un groupe par case"


@test
def test_classification_village():
    random.seed(3)
    grid, data = maps.generate_map("Village", 60, 40)
    structs = data['structures']
    assert set(structs) == {(x, y) for x in range(60) for y in range(40) if grid[x][y] == 1}
    assert set(structs.values()) == {st.HOUSE, st.HEDGE}, set(structs.values())
    bf = Battlefield(60, 40, 0, "Village", grid, data)
    for gid, cells in bf.structure_members.items():
        if bf.structure_kind[gid] == st.HOUSE:
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            assert len(cells) == (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1) >= 4


@test
def test_structures_par_carte():
    expected = {"Prairie": {st.ROCK}, "Forêt": {st.GROVE}, "Défilé": set(),
                "Siège": {st.PALISADE, st.WALL}}
    for name, kinds in expected.items():
        random.seed(5)
        grid, data = maps.generate_map(name, 60, 40)
        got = set(data['structures'].values())
        assert got <= kinds, (name, got)
        for (x, y), kind in data['structures'].items():
            assert grid[x][y] == (2 if kind == st.WALL else 1), (name, kind)


@test
def test_structures_en_miroir():
    for name in ("Prairie", "Forêt", "Village"):
        for (w, h) in ((40, 30), (178, 64)):
            random.seed(11)
            grid, data = maps.generate_map(name, w, h)
            s = data['structures']
            for (x, y), kind in s.items():
                assert s.get((w - 1 - x, y)) == kind, (name, w, x, y)


# ── Destruction ──

@test
def test_effondrement_coherent():
    house = {(x, y): st.HOUSE for x in (2, 3) for y in (1, 2)}
    bf = make_bf(structs=house)
    gid = bf.structures[(2, 1)][1]
    assert not st.damage(bf, gid, 5)
    assert bf.dirty_cells, "le passage à l'état entamé doit être repeint"
    bf.dirty_cells.clear()
    bf.fires[(2, 1)] = 3
    assert st.damage(bf, gid, 100)
    for (x, y) in house:
        assert bf.grid[x][y] == 0
        assert bf.terrain[x][y] == tr.RUBBLE
        assert (x, y) not in bf.structures
        assert (x, y) in bf.dirty_cells
    assert not bf.fires
    assert bf.is_valid(2, 1)


@test
def test_rocher_insensible_aux_armes_legeres():
    bf = make_bf(structs={(5, 5): st.ROCK})
    gid = bf.structures[(5, 5)][1]
    assert not st.damage(bf, gid, 50, heavy=False)
    assert bf.structure_hp[gid] == st.KINDS[st.ROCK]['hp']
    assert st.damage(bf, gid, 50, heavy=True)


# ── Incendie ──

@test
def test_feu_se_propage_et_s_eteint():
    bf = make_bf(w=12, h=3, structs={(x, 1): st.HEDGE for x in range(2, 6)})
    assert st.ignite(bf, 2, 1)
    res = st.fire_step(bf, RiggedRng(0.0))
    assert (3, 1) in res['ignited']
    for _ in range(20):
        st.fire_step(bf, RiggedRng(0.0))
    assert not bf.fires, "tout le combustible consumé, le feu s'éteint"
    for x in range(2, 6):
        assert bf.terrain[x][1] == tr.BURNT and bf.grid[x][1] == 0


@test
def test_feu_arrete_par_l_eau_et_la_plaine():
    structs = {(2, 1): st.HEDGE, (4, 1): st.HEDGE, (6, 1): st.HEDGE}
    bf = make_bf(w=10, h=3, structs=structs, terrain_cells={(5, 1): tr.RIVER})
    st.ignite(bf, 4, 1)
    for _ in range(10):
        st.fire_step(bf, RiggedRng(0.0))
    assert (2, 1) in bf.structures, "une case de plaine est un coupe-feu"
    assert (6, 1) in bf.structures, "la rivière est un coupe-feu"


@test
def test_feu_plafond_d_allumages():
    bf = make_bf(w=40, h=40, terrain_cells={(x, y): tr.WOOD for x in range(40) for y in range(40)})
    for x in range(0, 40, 2):
        bf.fires[(x, 20)] = 2
    res = st.fire_step(bf, RiggedRng(0.0))
    assert len(res['ignited']) == st.MAX_IGNITIONS_PER_ROUND, len(res['ignited'])


@test
def test_sous_bois_brule():
    bf = make_bf(w=6, h=3, terrain_cells={(2, 1): tr.WOOD})
    assert st.flammability(bf, 2, 1) == st.UNDERBRUSH_FLAMMABLE
    st.ignite(bf, 2, 1)
    for _ in range(st.UNDERBRUSH_BURN + 1):
        st.fire_step(bf, RiggedRng(0.99))
    assert bf.terrain[2][1] == tr.BURNT and not bf.fires


# ── Moteur ──

def mini_battle(map_name="Prairie"):
    random.seed(1)
    comp = [("Infanterie régulière", 2)]
    return Battle(ul.build_army("Armée Skaldienne", comp),
                  ul.build_army("Armée Skaldienne", comp), 40, 30, 8, map_name=map_name)


@test
def test_unite_dans_les_flammes_brulee():
    b = mini_battle()
    u = b.army1[0]
    u.sauvegarde = 7
    hp0 = u.hp
    b.battlefield.fires[u.position] = 3
    b._fire_phase()
    assert u.hp == hp0 - 1, (u.hp, hp0)
    assert u._suppression >= 1


@test
def test_effondrement_blesse_l_adjacent():
    b = mini_battle()
    bf = b.battlefield
    u = b.army1[0]
    ux, uy = u.position
    cells = [(ux + 1, uy), (ux + 2, uy), (ux + 1, uy + 1), (ux + 2, uy + 1)]
    for (x, y) in cells:
        bf.units.pop((x, y), None)
        bf.grid[x][y] = 1
    st.attach(bf, {c: st.HOUSE for c in cells})
    u.sauvegarde = 7
    hp0 = u.hp
    gid = bf.structures[cells[0]][1]
    assert st.damage(bf, gid, 999)
    b._structure_collapsed(gid, st.HOUSE, cells)
    assert u.hp < hp0
    b._flush_structure_changes()
    assert b.pending_repaints and set(cells) <= b.pending_repaints[-1][1]


@test
def test_baliste_demolit_la_maison_qui_masque():
    b = mini_battle()
    bf = b.battlefield
    for u in list(b.army1) + list(b.army2):
        bf.remove_unit(u)
    b.army1[:] = [ballista((5, 10))]
    b.army2[:] = [soldier((15, 10))]
    for u in b.army1 + b.army2:
        bf.place_unit(u)
    wall = [(10, 9), (10, 10), (10, 11), (11, 9), (11, 10), (11, 11)]
    for (x, y) in wall:
        bf.grid[x][y] = 1
    st.attach(bf, {c: st.HOUSE for c in wall})
    cmd = CommanderAI(b.army1, b.army2, bf, is_army1=True)
    prio = cmd._rank_targets(b.army2)
    order = cmd._demolish_order(b.army1[0], b.army2, prio)
    assert order is not None and order.order_type == "demolish", order
    assert order.target_pos in wall
    gid = bf.structures[order.target_pos][1]
    b.army1[0]._tactical_order = order
    random.seed(4)
    for _ in range(12):
        if bf.structure_hp[gid] <= 0:
            break
        assert b._attack_structure(b.army1[0])
    assert bf.structure_hp[gid] < st.KINDS[st.HOUSE]['hp']

    # Cible visible: pas de démolition
    for (x, y) in wall:
        bf.grid[x][y] = 0
    st.attach(bf, {})
    assert cmd._demolish_order(b.army1[0], b.army2, prio) is None


@test
def test_evacuation_du_feu():
    b = mini_battle()
    bf = b.battlefield
    u = b.army1[0]
    bf.fires[u.position] = 3
    cmd = b.commander1
    cmd._threat = tactics.ThreatField(b.army2, bf)
    order = cmd._escape_fire(u)
    assert order is not None and order.order_type == "withdraw"
    assert order.target_pos not in bf.fires
    assert cmd._threat.at(u.position) >= tactics.ThreatField.FIRE_THREAT


@test
def test_boule_de_feu_allume_le_bosquet():
    lit = 0
    for seed in range(20):
        random.seed(seed)
        b = Battle(ul.build_army("Armée Skaldienne", [("Mage de guerre", 1)]),
                   ul.build_army("Armée Skaldienne", [("Infanterie régulière", 1)]),
                   40, 30, 8, map_name="Prairie")
        bf = b.battlefield
        mage, foe = b.army1[0], b.army2[0]
        for u in (mage, foe):
            bf.remove_unit(u)
        mage.position, foe.position = (10, 15), (16, 15)
        for u in (mage, foe):
            bf.place_unit(u)
        grove = [(16, 14), (17, 15), (16, 16)]
        for (x, y) in grove:
            bf.units.pop((x, y), None)
            bf.grid[x][y] = 1
        st.attach(bf, {c: st.GROVE for c in grove})
        spell = next(s for s in mage.spells if s.spell_type == "fireball")
        mage._cast_fireball(spell, b, [])
        lit += any(c in bf.fires for c in grove)
    assert lit >= 10, lit


# ── Siège (lot B2) ──

def siege_battle(seed=1, attackers=None, defenders=None):
    random.seed(seed)
    att = attackers or ("Armée Skaldienne", {"Infanterie régulière": 3})
    dfd = defenders or ("Armée Skaldienne", {"Infanterie régulière": 3})
    return Battle(ul.build_army(att[0], list(att[1].items())),
                  ul.build_army(dfd[0], list(dfd[1].items())), 40, 30, 8, map_name="Siège")


@test
def test_siege_fosse_glacis_palissades():
    random.seed(9)
    grid, data = maps.generate_map("Siège", 60, 40)
    wx = data['wall_x']
    terr = data['terrain']
    gate_rows = {y for (x, y) in data['gates']}
    for y in range(2, 38):
        if grid[wx - 1][y] == 0:
            expected = tr.PLAIN if y in gate_rows else tr.MARSH
            assert terr[wx - 1][y] == expected, (y, terr[wx - 1][y])
    assert any(terr[wx + 4][y] == tr.HILL for y in range(40))
    bf = Battlefield(60, 40, 0, "Siège", grid, data)
    walls = [g for g, k in bf.structure_kind.items() if k == st.WALL]
    assert walls and all(len(bf.structure_members[g]) <= st.WALL_SEGMENT for g in walls)
    palis = [g for g, k in bf.structure_kind.items() if k == st.PALISADE]
    assert palis, "les couverts de l'assaillant sont des palissades"


@test
def test_breche_coherente_et_chute_du_rempart():
    b = siege_battle()
    bf = b.battlefield
    wx = bf.siege_data['wall_x']
    gid = next(g for g, k in bf.structure_kind.items()
               if k == st.WALL and all((wx + 1, y) in bf.ramparts for _, y in bf.structure_members[g]))
    cells = list(bf.structure_members[gid])
    y0 = cells[0][1]
    guard = soldier((wx + 1, y0), save=7)
    bf.place_unit(guard)
    b.army2.append(guard)
    assert not st.damage(bf, gid, 999, heavy=False), "le mur ne cède pas à une arme légère"
    assert st.damage(bf, gid, 999, heavy=True)
    b._structure_collapsed(gid, st.WALL, cells)
    for (x, y) in cells:
        assert (x, y) not in bf.walls and bf.grid[x][y] == 0 and bf.terrain[x][y] == tr.RUBBLE
        for dx in (1, 2, 3):
            c = (x + dx, y)
            assert c not in bf.ramparts and c not in bf.stairs
            assert bf.grid[c[0]][c[1]] == 0 and bf.terrain[c[0]][c[1]] == tr.RUBBLE
    assert bf.breaches and next(iter(bf.breaches)) in cells
    assert bf.is_valid(wx, y0)
    assert guard.hp < guard.max_hp and not bf.is_rampart(*guard.position)


@test
def test_facteur_des_armes_sur_le_mur():
    def arme(degats, porte):
        return Arme("x", nb_attaque=1, toucher=4, blesser=2, perforation=0, degats=degats, porte=porte)
    assert st.weapon_factor(st.WALL, arme("2+1d4", 24)) == 1.0     # catapulte
    assert st.weapon_factor(st.WALL, arme("1d4", 18)) == 0.5       # baliste
    assert st.weapon_factor(st.WALL, arme("1d2", 13)) == 0.0       # scorpion
    assert st.weapon_factor(st.WALL, arme("1d6", 8)) == 0.0        # arbalète
    assert st.weapon_factor(st.PALISADE, arme("1", 8)) == 1.0


@test
def test_couvert_palissade_moteur_egal_estimation():
    # Un tireur au sol ne voit pas à travers la palissade: le couvert joue
    # pour celui qui tire par-dessus, depuis le rempart.
    w, h = 20, 12
    grid = [[0] * h for _ in range(w)]
    grid[5][1] = 1
    grid[19][11] = 2
    bf = Battlefield(w, h, 0, "Siège", grid,
                     {'terrain': tr.make_grid(w, h), 'structures': {(5, 1): st.PALISADE},
                      'walls': [(19, 11)], 'ramparts': [(0, 1)]})
    a = Unit("Archer", pv=100, vitesse=4, morale=3, sauvegarde=7, color=(1, 1, 1),
             armes=[Arme("Arc", nb_attaque=1, toucher=3, blesser=1, perforation=0, degats="1", porte=8)])
    a.position = (0, 1)
    a.ammo = None     # on mesure le taux par volée, pas l'épuisement du carquois
    t = Unit("Cible", pv=100000, vitesse=4, morale=5, sauvegarde=7, color=(2, 2, 2),
             armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    t.position = (6, 1)
    bf.place_unit(a)
    bf.place_unit(t)
    assert tr.combat_mods(bf, a, t, True)['toucher'] == 1
    est = tactics.expected_damage(a, t, 6, bf)
    assert abs(est - 3 / 6) < 1e-9, est
    total, n = 0, 3000
    for _ in range(n):
        before = t.hp
        a.perform_attacks(t, bf)
        total += before - t.hp
        t.hp = t.max_hp
    assert abs(total / n - est) / est < 0.1, (total / n, est)


@test
def test_catapulte_ouvre_une_breche_et_l_assaut_la_prend():
    opened, switched = 0, 0
    att = ("Armée Orlandar", {"Fantassin covaliir": 8, "Archer covaliir": 4,
                             "Officier covaliir": 1, "Catapulte covaliir": 1})
    dfd = ("Armée Skaldienne", {"Infanterie régulière": 5, "Arbaletrier régulier": 4, "Officier": 1})
    # La brèche s'ouvre avant le round 25 dans ~60 % des sièges (mesuré sur
    # 40 graines): 16 graines, pas 8, pour ne pas dépendre d'un tirage.
    for seed in range(16):
        b = siege_battle(1000 + seed, att, dfd)
        bf = b.battlefield
        while not b.is_battle_over() and b.round <= 25 and not bf.breaches:
            b.simulate_round()
        if not bf.breaches:
            continue
        opened += 1
        if not b.is_battle_over():
            b.simulate_round()
            switched += b.commander1.assault_gate in bf.breaches or bf.gates_open
    assert opened >= 6, opened
    assert switched >= opened - 1, (switched, opened)


@test
def test_baliste_ne_perce_pas_quand_elle_voit_une_cible():
    b = siege_battle(3, ("Armée Skaldienne", {"Infanterie régulière": 2, "Baliste": 1}))
    bf = b.battlefield
    bal = next(u for u in b.army1 if u.is_artillery)
    cmd = b.commander1
    cmd._threat = tactics.ThreatField(b.army2, bf)
    visible = [e for e in b.army2
               if bf.has_line_of_fire(bal, e)
               and abs(bal.position[0] - e.position[0]) + abs(bal.position[1] - e.position[1])
               <= tr.effective_range(bf, bal, e)]
    order = cmd._breach_order(bal, b.army2)
    if visible:
        assert order is None
    for e in b.army2:
        bf.remove_unit(e)
        e.position = (bf.width - 2, 1)
    order = cmd._breach_order(bal, b.army2)
    wx = bf.siege_data['wall_x']
    in_reach = any(abs(bal.position[0] - wx) + abs(bal.position[1] - y) <= 18
                   for (x, y) in bf.walls if x == wx)
    if in_reach:
        assert order is not None and order.order_type == "demolish"
        assert bf.structures[order.target_pos][0] == st.WALL


# ── Rendu ──

def _pygame():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    return pygame


def _village_battle(seed=21):
    random.seed(seed)
    comp = [("Infanterie régulière", 2)]
    return Battle(ul.build_army("Armée Skaldienne", comp),
                  ul.build_army("Armée Skaldienne", comp), 60, 40, 8, map_name="Village")


@test
def test_rendu_repeint_egal_reconstruction():
    """Après un effondrement et un incendie, repeindre la région donne
    exactement les pixels d'une reconstruction complète — et rien ne bouge
    hors du rectangle repeint."""
    pygame = _pygame()
    from renderer import build_grid_surface, repaint_region
    cs = 16
    b = _village_battle()
    bf = b.battlefield
    surf = build_grid_surface(b, cs)
    before = surf.copy()
    house = next(g for g, k in bf.structure_kind.items() if k == st.HOUSE)
    hedge = next(g for g, k in bf.structure_kind.items() if k == st.HEDGE)
    house_cells = list(bf.structure_members[house])
    st.damage(bf, house, 999)
    st.ignite(bf, *bf.structure_members[hedge][0])
    dirty = set(bf.dirty_cells)
    bf.dirty_cells.clear()
    repaint_region(surf, b, cs, dirty)
    full = build_grid_surface(b, cs)

    xs = [c[0] for c in dirty]
    ys = [c[1] for c in dirty]
    clip = pygame.Rect((min(xs) - 1) * cs, (min(ys) - 1) * cs,
                       (max(xs) - min(xs) + 3) * cs, (max(ys) - min(ys) + 3) * cs)
    diff_in, diff_out = 0, 0
    W, H = surf.get_size()
    for px in range(0, W, 3):
        for py in range(0, H, 3):
            if clip.collidepoint(px, py):
                diff_in += surf.get_at((px, py)) != full.get_at((px, py))
            else:
                diff_out += surf.get_at((px, py)) != before.get_at((px, py))
    assert diff_out == 0, diff_out
    assert diff_in == 0, diff_in
    # La maison a bien disparu de l'image
    cx, cy = house_cells[0]
    assert full.get_at((cx * cs + cs // 2, cy * cs + cs // 2)) != before.get_at((cx * cs + cs // 2, cy * cs + cs // 2))


@test
def test_rendu_budget_repeint():
    import time
    _pygame()
    from renderer import build_grid_surface, repaint_region
    b = _village_battle(22)
    bf = b.battlefield
    cs = 28
    surf = build_grid_surface(b, cs)
    cells = sorted(bf.structures)[:20]
    t0 = time.perf_counter()
    for _ in range(5):
        repaint_region(surf, b, cs, cells[:4])
    per_call = (time.perf_counter() - t0) / 5 * 1000
    assert per_call < 4.0 * 3, f"{per_call:.1f} ms (budget 4 ms, marge machine ×3)"


@test
def test_rendu_feux_et_effondrement():
    pygame = _pygame()
    from fx_render import FxRenderer
    from renderer import build_grid_surface, apply_destruction, load_token
    b = _village_battle(23)
    bf = b.battlefield
    cs = 16
    surf = build_grid_surface(b, cs)
    house = next(g for g, k in bf.structure_kind.items() if k == st.HOUSE)
    cells = list(bf.structure_members[house])
    st.ignite(bf, *cells[0])
    b._flush_structure_changes()
    st.damage(bf, house, 999)
    b._structure_collapsed(house, st.HOUSE, cells)
    b._flush_structure_changes()
    b.pending_craters.append((0, 100, 100, 20))
    apply_destruction(surf, b, cs, 10 ** 6)
    assert not b.pending_repaints and not b.pending_craters
    fxr = FxRenderer(cs, load_token, pygame.font.SysFont("arial", 10))
    fxr.reset(surf.get_width(), surf.get_height())
    bf.fires[(3, 3)] = 2
    screen = pygame.Surface((800, 600))
    for frame in range(30):
        fxr.round_frame = frame
        fxr.draw_fires(screen, b, 0, 0, 800, 600, frame * 16)
        fxr.update(b)
        fxr.draw_overlay(screen, b, 0, 0, 800, 600, frame * 16)
    assert fxr.particles, "fumée, braises et poussière doivent être émises"


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests destruction passent.")
    sys.exit(1 if fails else 0)
