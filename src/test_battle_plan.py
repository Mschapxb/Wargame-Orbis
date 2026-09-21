"""Tests du lot C (plans de bataille). Script exécutable:
    python test_battle_plan.py            # tout
    python test_battle_plan.py marteau    # seulement les tests dont le nom contient 'marteau'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tactics
import terrain as tr
import unit_library as ul
from battle import Battle

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


CAV = ("Armée Orlandar", {"Fantassin covaliir": 6, "Archer covaliir": 3,
                          "Cavalier covaliir": 3, "Officier covaliir": 1})
INF = ("Armée Skaldienne", {"Infanterie régulière": 8, "Arbaletrier régulier": 3, "Housecarl": 2})


def battle(army=CAV, map_name="Prairie", seed=1, w=60, h=40):
    random.seed(seed)
    return Battle(ul.build_army(army[0], list(army[1].items())),
                  ul.build_army(army[0], list(army[1].items())), w, h, 8, map_name=map_name)


def prime(b, cmd):
    """Prépare un commandant comme au début d'issue_orders (sans plan)."""
    alive = [u for u in cmd.army if u.is_alive and not u.fleeing]
    enemies = [e for e in cmd.enemy_army if e.is_alive]
    s = cmd.assess()
    cmd._threat = tactics.ThreatField(enemies, b.battlefield)
    cmd._compute_formation(alive, cmd._center(enemies))
    cmd.plan._frame(cmd, enemies)
    return alive, enemies, s


def start(b, cmd, kind):
    alive, enemies, s = prime(b, cmd)
    cmd.plan._start(kind, cmd, alive, enemies)
    return alive, enemies, s


def is_front_melee(plan, u):
    return (plan.roles.get(id(u)) is None and u._max_range < 4 and not u.spells
            and u.encouragement_range == 0)


# ── Choix ──

@test
def test_petite_armee_joue_direct():
    b = battle(("Armée Skaldienne", {"Infanterie régulière": 3, "Arbaletrier régulier": 2}))
    alive, enemies, s = prime(b, b.commander1)
    b.commander1.plan.choose(b.commander1, alive, enemies, s)
    assert b.commander1.plan.kind == "direct"


@test
def test_une_grande_melee_ouvre_le_marteau():
    kinds = set()
    for seed in range(12):
        b = battle(INF, "Prairie", seed)
        cmd = b.commander1
        alive, enemies, s = prime(b, cmd)
        cmd.plan.choose(cmd, alive, enemies, s)
        kinds.add(cmd.plan.kind)
    assert "marteau" in kinds, kinds
    assert len(kinds) >= 2, "le tirage entre les deux meilleurs plans varie les batailles"


@test
def test_pas_de_manoeuvre_en_foret():
    checked = 0
    for seed in range(6):
        b = battle(INF, "Forêt", seed)
        cmd = b.commander1
        alive, enemies, s = prime(b, cmd)
        if cmd.plan._contact_zone_is_close(cmd, alive, enemies):
            checked += 1
            cmd.plan.choose(cmd, alive, enemies, s)
            assert cmd.plan.kind in ("direct", "colline"), cmd.plan.kind
    assert checked, "le massif de la Forêt doit être reconnu comme zone fermée"


@test
def test_sans_plans_aucun_role():
    b = battle()
    b.commander1.use_plans = False
    b.commander2.use_plans = False
    for _ in range(3):
        b.simulate_round()
    assert b.commander1.plan.kind is None and not b.commander1.plan.roles


@test
def test_pas_de_plan_au_siege():
    """Pas de plan de BATAILLE au siège: c'est un plan de siège
    (siege_plan.py, testé par test_siege_plan.py)."""
    from battle_plan import NAMES as FIELD_PLANS
    from siege_plan import SiegePlan
    b = battle(CAV, "Siège", 2, 40, 30)
    for _ in range(3):
        b.simulate_round()
    for cmd in (b.commander1, b.commander2):
        assert isinstance(cmd.plan, SiegePlan)
        assert cmd.plan.kind not in set(FIELD_PLANS) - {"direct"}


# ── Marteau ──

@test
def test_marteau_roles_et_phases():
    b = battle(INF, "Prairie", 3)
    cmd = b.commander1
    alive, enemies, s = start(b, cmd, "marteau")
    plan = cmd.plan
    hammer = [u for u in alive if plan.roles.get(id(u)) == "hammer"]
    assert len(hammer) >= 2
    fastest = max(u.vitesse for u in alive if is_front_melee(plan, u) or u in hammer)
    assert max(u.vitesse for u in hammer) == fastest, "le marteau prend les plus rapides"
    assert plan.phase == "approche"
    cmd.posture = "balanced"
    plan.update(cmd, alive, enemies, s)
    order = plan.order_for(cmd, hammer[0], enemies)
    assert order[0] == "support" and order[2] == plan.points['attente']
    # L'enclume au contact: le marteau frappe
    bf = b.battlefield
    anvil = [u for u in alive if is_front_melee(plan, u)]
    for u, e in zip(anvil, enemies):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pos = (e.position[0] + dx, e.position[1] + dy)
            if bf.is_valid(*pos) and pos not in bf.units:
                bf.move_unit(u, pos)
                break
    plan.rounds = 5
    plan.update(cmd, alive, enemies, s)
    assert plan.phase == "frappe", plan.phase
    assert any("marteau frappe" in t for t, _ in plan.pop_events())
    order = plan.order_for(cmd, hammer[0], enemies)
    assert order[0] in ("flank", "attack")


@test
def test_marteau_brise_revient_au_direct():
    b = battle(INF, "Prairie", 4)
    cmd = b.commander1
    alive, enemies, s = start(b, cmd, "marteau")
    for u in alive:
        if cmd.plan.roles.get(id(u)) == "hammer":
            u.is_alive = False
    cmd.posture = "balanced"
    alive = [u for u in alive if u.is_alive]
    cmd.plan.update(cmd, alive, enemies, s)
    assert cmd.plan.kind == "direct"


# ── Feinte, oblique ──

@test
def test_feinte_leurres_puis_assaut():
    b = battle(INF, "Prairie", 5)
    cmd = b.commander1
    alive, enemies, s = start(b, cmd, "feinte")
    plan = cmd.plan
    lures = [u for u in alive if plan.roles.get(id(u)) == "lure"]
    assert len(lures) == 2
    cmd.posture = "balanced"
    plan.update(cmd, alive, enemies, s)
    o = plan.order_for(cmd, lures[0], enemies)
    assert o is not None and o[0] == "support", "les leurres se montrent, ils ne chargent pas seuls"
    assert plan.lane_bias != (0.0, 0.0)
    for _ in range(5):
        plan.update(cmd, alive, enemies, s)
    assert plan.phase == "assaut"


@test
def test_oblique_aile_refusee_en_retrait():
    b = battle(INF, "Prairie", 6)
    cmd = b.commander1
    alive, enemies, s = start(b, cmd, "oblique")
    plan = cmd.plan
    refused = [u for u in alive if plan.roles.get(id(u)) == "refused"]
    assert refused and all(plan._lat(u.position) * plan.side < 0 for u in refused)
    cmd.posture = "balanced"
    plan.update(cmd, alive, enemies, s)
    orders = [plan.order_for(cmd, u, enemies) for u in refused]
    assert all(o is None or o[0] in ("hold", "support") for o in orders)


# ── Colline, plus de réserve ──

@test
def test_colline_tireurs_sur_la_colline():
    army = ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 4, "Officier": 1})
    for seed in range(8):
        b = battle(army, "Prairie", seed)
        cmd = b.commander1
        alive, enemies, s = prime(b, cmd)
        hill = cmd.plan._find_hill(cmd, alive, enemies)
        if hill is None:
            continue
        cmd.plan.points['colline'] = hill
        cmd.plan._start("colline", cmd, alive, enemies)
        bf = b.battlefield
        slots = list(cmd.plan.hill_slots.values())
        assert slots and all(bf.terrain[x][y] == tr.HILL for x, y in slots)
        shooter = next(u for u in alive if cmd.plan.roles.get(id(u)) == "hill")
        cmd.posture = "balanced"
        cmd.plan.update(cmd, alive, enemies, s)
        o = cmd.plan.order_for(cmd, shooter, enemies)
        assert o[2] == cmd.plan.hill_slots[id(shooter)]
        return
    raise AssertionError("aucune colline objectif trouvée sur 8 graines")


@test
def test_aucune_reserve_toute_la_melee_marche():
    """La réserve a été retirée: aucun plan ne met de mêlée de côté."""
    for kind in ("marteau", "feinte", "oblique"):
        b = battle(INF, "Prairie", 7)
        cmd = b.commander1
        alive, enemies, s = start(b, cmd, kind)
        assert "reserve" not in cmd.plan.roles.values(), kind
        assert not hasattr(cmd.plan, 'reserve_committed')


@test
def test_colline_contre_attaque_si_l_ennemi_ne_vient_pas():
    """Deux armées qui tiennent chacune leur hauteur ne se regardent pas:
    faute d'ennemi qui approche, la tenue tourne court."""
    army = ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 4, "Officier": 1})
    for seed in range(8):
        b = battle(army, "Prairie", seed)
        cmd = b.commander1
        alive, enemies, s = prime(b, cmd)
        hill = cmd.plan._find_hill(cmd, alive, enemies)
        if hill is None:
            continue
        cmd.plan.points['colline'] = hill
        cmd.plan._start("colline", cmd, alive, enemies)
        cmd.posture = "balanced"
        cmd.plan._set_phase("tenue")
        cmd.plan._enemy_proj0 = cmd.plan._enemy_front(cmd, enemies)
        for _ in range(3):
            cmd.plan.update(cmd, alive, enemies, s)   # l'ennemi reste immobile
            if cmd.plan.phase == "contre":
                return
        raise AssertionError(f"toujours en {cmd.plan.phase} après 3 rounds")
    raise AssertionError("aucune colline objectif trouvée sur 8 graines")


# ── Intentions, bataille complète ──

@test
def test_intentions_dans_la_carte():
    b = battle(seed=8)
    for _ in range(6):
        b.simulate_round()
    bf = b.battlefield
    for cmd in (b.commander1, b.commander2):
        for it in cmd.plan.intents(cmd):
            assert it['type'] in ('arrow', 'zone', 'flag')
            pts = it.get('points') or [it.get('center') or it.get('pos')]
            for (x, y) in pts:
                assert -1 <= x <= bf.width and -1 <= y <= bf.height, (x, y)


@test
def test_bataille_avec_plans_se_termine_et_annonce():
    announced = 0
    for seed in range(4):
        b = battle(seed=20 + seed)
        while not b.is_battle_over() and b.round <= 90:
            b.simulate_round()
            announced += sum(1 for t, _, _ in b.round_events if "plan" in t)
        assert b.is_battle_over(), seed
    assert announced >= 4


@test
def test_rendu_des_intentions():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    from renderer import draw_intents
    b = battle(seed=9)
    for _ in range(5):
        b.simulate_round()
    screen = pygame.Surface((1200, 800))
    draw_intents(screen, b, 20, -200, -100)


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests plans de bataille passent.")
    sys.exit(1 if fails else 0)
