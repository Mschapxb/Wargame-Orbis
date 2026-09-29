"""Tests de l'écran « Champ de bataille » (map_screen.py), de la graine de
carte et de l'avantage de terrain (maps.apply_advantage).

    python test_map_screen.py            # tout
    python test_map_screen.py avantage   # seulement les tests dont le nom contient 'avantage'
"""
import os, sys, random, traceback
os.environ.setdefault("WARGAME_ORBIS_SETTINGS", "memory")  # réglages du joueur intacts

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


# ── Mémoire de session et ergonomie de l'écran des armées ──


@test
def test_reglages_relus_et_fichier_abime_ignore():
    import tempfile
    import settings
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "settings.json")
        s = settings.Settings(path)
        s.set("battle", "speed", "fast")
        s.set("video", "fps", 30)
        s.save()
        again = settings.Settings(path)
        assert again.get("battle", "speed") == "fast" and again.get("video", "fps") == 30
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"battle": {"speed": 3, "inconnu": 1}, "video": "x"')   # abîmé
        broken = settings.Settings(path)
        assert broken.get("battle", "speed") == "normal"
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"battle": {"speed": 3, "show_lines": false}}')         # mauvais type
        typed = settings.Settings(path)
        assert typed.get("battle", "speed") == "normal"
        assert typed.get("battle", "show_lines") is False


@test
def test_armees_et_carte_retrouvees_a_la_session_suivante():
    import tempfile
    import menu
    import settings
    pygame.display.set_mode((1200, 720))
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "settings.json")
        settings.reset(path)
        m = menu.ArmyMenu(1200, 720)
        m.states[0].add_unit("Armée Skaldienne", "Infanterie régulière", 7)
        m.states[0].add_group()
        m.states[0].add_unit("Armée Skaldienne", "Arbaletrier régulier", 2)
        m.states[1].add_unit("Armée Orlandar", "Cavalier covaliir", 3)
        m.states[1].bonuses["moral"] = 2
        m.setup.set_map("Village")
        m.setup.weather = "Pluie"
        seed = m.setup.seed
        m.remember()
        settings.reset(path)                      # « relance du jeu »
        m2 = menu.ArmyMenu(1200, 720)
        assert m2.states[0].groups == [{("Armée Skaldienne", "Infanterie régulière"): 7},
                                       {("Armée Skaldienne", "Arbaletrier régulier"): 2}]
        assert m2.states[1].composition == {("Armée Orlandar", "Cavalier covaliir"): 3}
        assert m2.states[1].bonuses["moral"] == 2
        assert (m2.setup.map_name, m2.setup.weather, m2.setup.seed) == ("Village", "Pluie", seed)
        # Combat immédiat: les mêmes armées sur la même carte, sans l'écran 2
        a1, a2, name, opts = m2.quick_launch()
        assert len(a1) == 9 and len(a2) == 3 and name == "Village" and opts['seed'] == seed
    settings.reset()


@test
def test_recherche_filtre_et_factions_repliees():
    import menu
    import settings
    settings.reset()
    pygame.display.set_mode((1200, 720))
    m = menu.ArmyMenu(1200, 720)
    m.search = "ARBALETRIER"                      # ni casse ni accents
    units = [r[2]["nom"] for r in m._unit_rows() if r[0] == "unit"]
    assert units and all("arbal" in menu.fold(n) for n in units)
    m.search = ""
    m.faction_filter = "Armée Orlandar"
    rows = m._unit_rows()
    assert {r[1] for r in rows} == {"Armée Orlandar"}
    m.collapsed = {"Armée Orlandar"}
    assert [r[0] for r in m._unit_rows()] == ["header"]   # repliée: son bandeau seul
    m.search = "cavalier"                          # une recherche montre tout
    assert any(r[0] == "unit" for r in m._unit_rows())


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
