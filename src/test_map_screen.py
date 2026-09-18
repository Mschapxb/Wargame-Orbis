"""Tests de l'écran « Champ de bataille » (map_screen.py), de la graine de
carte et de l'avantage de terrain (maps.apply_advantage).

    python test_map_screen.py            # tout
    python test_map_screen.py avantage   # seulement les tests dont le nom contient 'avantage'
"""
import os, sys, random, traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pygame

import maps
import terrain as tr
import unit_library as ul
from battle import Battle

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def armies():
    a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 6), ("Arbaletrier régulier", 3)])
    a2 = ul.build_army("Armée Orlandar", [("Fantassin covaliir", 6), ("Archer covaliir", 3)])
    return a1, a2


def hills_by_half(terr, w, h):
    west = sum(1 for x in range(w // 2) for y in range(h) if terr[x][y] == tr.HILL)
    east = sum(1 for x in range(w // 2, w) for y in range(h) if terr[x][y] == tr.HILL)
    return west, east


# ── Graine de carte ──

@test
def test_graine_rejoue_carte_meteo_et_deploiement():
    a1, a2 = armies()
    opts = {'relief': "Aléatoire", 'weather': "Aléatoire", 'seed': 4242}

    def snap(before):
        random.seed(before)
        b = Battle(a1, a2, 120, 40, 8, map_name="Forêt", map_options=opts)
        bf = b.battlefield
        return (bf.terrain, bf.grid, bf.weather.name,
                [u.position for u in b.army1 + b.army2])
    assert snap(1) == snap(987)


@test
def test_graine_ne_fige_pas_le_hasard_de_la_bataille():
    a1, a2 = armies()
    random.seed(5)
    Battle(a1, a2, 60, 30, 8, map_name="Prairie", map_options={'seed': 1})
    after_seeded = random.random()
    random.seed(5)
    Battle(a1, a2, 60, 30, 8, map_name="Prairie", map_options={'seed': 2})
    assert random.random() == after_seeded      # état restauré, quelle que soit la graine


# ── Avantage de terrain ──

@test
def test_sans_avantage_aucun_de_tire():
    random.seed(11)
    g1, d1 = maps.generate_map("Prairie", 120, 40, {'relief': "Plat"})
    random.seed(11)
    g2, d2 = maps.generate_map("Prairie", 120, 40, {'relief': "Plat", 'advantage': "Aucun"})
    assert d1['terrain'] == d2['terrain'] and g1 == g2


@test
def test_avantage_du_bon_cote_et_en_miroir():
    for side, lvl in (("Armée 1", "Léger"), ("Armée 2", "Marqué")):
        random.seed(3)
        _g, d = maps.generate_map("Prairie", 120, 40, {'relief': "Plat", 'advantage': side,
                                                       'advantage_level': lvl})
        west, east = hills_by_half(d['terrain'], 120, 40)
        if side == "Armée 1":
            assert west > 20 and east == 0, (west, east)
        else:
            assert east > 20 and west == 0, (west, east)
        assert d['theme']['advantage'] == (1 if side == "Armée 1" else 2)


@test
def test_avantage_marque_plus_etendu_que_leger():
    sizes = {}
    for lvl in maps.ADVANTAGE_LEVELS:
        random.seed(8)
        _g, d = maps.generate_map("Désert", 120, 40, {'relief': "Plat", 'advantage': "Armée 1",
                                                      'advantage_level': lvl})
        sizes[lvl] = hills_by_half(d['terrain'], 120, 40)[0]
    assert sizes["Marqué"] > sizes["Léger"], sizes


@test
def test_pas_d_avantage_en_siege():
    random.seed(2)
    _g, d = maps.generate_map("Siège", 60, 30, {'advantage': "Armée 1"})
    assert 'advantage' not in d['theme']


@test
def test_avantage_deploiement_sur_les_hauteurs_et_plan_colline():
    a1, a2 = armies()
    random.seed(4)
    b = Battle(a1, a2, 120, 40, 8, map_name="Prairie",
               map_options={'relief': "Plat", 'advantage': "Armée 1", 'seed': 17})
    terr = b.battlefield.terrain
    on_hill = sum(1 for u in b.army1 if terr[u.position[0]][u.position[1]] == tr.HILL)
    assert on_hill >= len(b.army1) // 3, on_hill
    b.simulate_round()
    assert b.commander1.plan.kind == "colline", b.commander1.plan.kind


# ── Écran ──

@test
def test_mapsetup_options_et_nouvelle_graine():
    from map_screen import MapSetup
    s = MapSetup("Prairie")
    s.advantage = "Armée 2"
    opts = s.options()
    assert opts['advantage'] == "Armée 2" and opts['seed'] == s.seed
    old = s.seed
    s.new_seed()
    assert s.seed != old
    s.set_map("Citadelle")
    assert not s.advantage_allowed and 'advantage' not in s.options()
    s.set_map("Forêt")
    assert s.relief == maps.natural_relief_name("Forêt")


@test
def test_boucle_reelle_de_l_ecran_carte():
    """Vraie boucle: « Nouvelle carte » change la graine, ÉCHAP revient aux
    armées, ENTRÉE lance le combat."""
    import map_screen as M
    pygame.init()
    screen = pygame.display.set_mode((1200, 720))
    a1, a2 = armies()
    real_get, real_pos = pygame.event.get, pygame.mouse.get_pos
    E = pygame.event.Event

    def drive(script):
        st = {"n": 0}

        def fake():
            st["n"] += 1
            return real_get() + script.get(st["n"], [])
        pygame.event.get = fake
        try:
            return M.run_map_screen(screen, 1200, 720, a1, a2, setup, (120, 40))
        finally:
            pygame.event.get = real_get

    setup = M.MapSetup("Prairie")
    seed0 = setup.seed
    # Le bouton « Nouvelle carte » est en bas à droite
    pygame.mouse.get_pos = lambda: (1200 - 15 - 100, 720 - 58 + 20)
    try:
        res = drive({2: [E(pygame.MOUSEBUTTONDOWN, button=1, pos=(1085, 682))],
                     4: [E(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0)]})
    finally:
        pygame.mouse.get_pos = real_pos
    assert res == "back" and setup.seed != seed0
    res = drive({2: [E(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="\r", scancode=0)]})
    assert res == "launch"


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests écran carte passent.")
    sys.exit(1 if fails else 0)
