"""Tests du lot D (interface de bataille). Script exécutable:
    python test_ui.py            # tout
    python test_ui.py zoom       # seulement les tests dont le nom contient 'zoom'
"""
import os, sys, random, traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pygame
pygame.init()
pygame.display.set_mode((1, 1))

import ui
import unit_library as ul
from battle import Battle

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def battle(map_name="Prairie", seed=1, w=90, h=40):
    random.seed(seed)
    comp = [("Infanterie régulière", 6), ("Arbaletrier régulier", 3), ("Mage de guerre", 1)]
    return Battle(ul.build_army("Armée Skaldienne", comp),
                  ul.build_army("Armée Skaldienne", comp), w, h, 8, map_name=map_name)


@test
def test_zoom_niveaux_et_point_fixe():
    assert ui.next_zoom(1.0, 1) == 1.25 and ui.next_zoom(1.0, -1) == 0.8
    assert ui.next_zoom(2.0, 1) == 2.0 and ui.next_zoom(0.5, -1) == 0.5
    cam = (300.0, 120.0)
    before = ui.screen_to_world(640, 360, *cam, 1.0)
    new_cam = ui.zoom_around(*cam, 640, 360, 1.0, 1.6)
    after = ui.screen_to_world(640, 360, *new_cam, 1.6)
    assert abs(before[0] - after[0]) < 1e-6 and abs(before[1] - after[1]) < 1e-6


@test
def test_camera_bornee_et_centree():
    x, y = ui.clamp_camera(-500, 99999, 4000, 1800, 1600, 900, 1.0)
    assert x == 0 and y == 1800 - 900
    x, y = ui.clamp_camera(10, 10, 4000, 1800, 1600, 900, 0.5)
    assert y == 0 and x == 10
    x, y = ui.clamp_camera(10, 10, 1000, 500, 1600, 900, 1.0)
    assert x < 0 and y < 0, "monde plus petit que la vue: centré"


@test
def test_unite_survolee():
    b = battle()
    u = b.army1[0]
    cs = 20
    assert ui.unit_at(b, u.position[0] * cs + 5, u.position[1] * cs + 5, cs) is u
    assert ui.unit_at(b, -50, -50, cs) is None


@test
def test_fiche_d_unite():
    b = battle()
    for _ in range(3):
        b.simulate_round()
    mage = next(u for u in b.army1 if u.spells)
    lines = [t for t, _ in ui.unit_card_lines(mage, b)]
    assert "Armée 1" in lines[0] and lines[1].startswith("PV ")
    assert any(t.startswith("• Sort") for t in lines)
    assert any(t.startswith("Ordre:") for t in lines)
    screen = pygame.Surface((1200, 800))
    rect = ui.draw_unit_card(screen, mage, b, 1150, 780, pygame.font.SysFont("arial", 14),
                             pygame.Rect(0, 0, 1200, 800))
    assert pygame.Rect(0, 0, 1200, 800).contains(rect), "la fiche reste à l'écran"


@test
def test_minicarte_clic_centre_la_camera():
    b = battle()
    mm = ui.Minimap(b, 20, 1600, 38)
    assert mm.thumb.get_size() == (mm.w, mm.h)
    cx, cy = mm.rect.center
    cam = mm.camera_for(b, cx, cy, 1600, 820, 1.0)
    world_w = b.battlefield.width * 20
    assert abs((cam[0] + 800) - world_w / 2) <= 20
    assert mm.camera_for(b, 5, 5, 1600, 820, 1.0) is None
    screen = pygame.Surface((1600, 900))
    mm.draw(screen, b, 0, 0, 1600, 820, 1.0)
    b.battlefield.fires[(3, 3)] = 2
    mm._frames = 60
    mm.refresh(b)
    assert mm._sig[0] == 1, "un incendie rafraîchit la vignette"


@test
def test_bandeau_et_chevron():
    from renderer import POSTURE_LABELS
    b = battle()
    for _ in range(4):
        b.simulate_round()
    screen = pygame.Surface((1600, 900))
    fonts = (pygame.font.SysFont("arial", 11), pygame.font.SysFont("arial", 16, bold=True))
    ui.draw_bottom_hud(screen, b, 1600, 820, 80, fonts, "> NORMAL", (110, 220, 110), 1.25, 60,
                       "aide", POSTURE_LABELS)
    a, f, d = ui.army_counts(b.army1, b.army1_roster, b.army1_fled)
    assert a + f + d == len(b.army1_roster)
    ui.draw_facing(screen, 100, 100, 12, ui.facing_angle(b.army1[0]), (60, 120, 220))


@test
def test_boucle_reelle_zoom_survol_minicarte():
    """La vraie boucle d'affichage: molette, touches de zoom, Tab, clic sur la
    mini-carte, sans erreur."""
    import renderer
    pygame.display.set_mode((1400, 800))
    b = battle(seed=5)
    st = {"n": 0}
    real_get = pygame.event.get
    real_pos = pygame.mouse.get_pos

    def fake_get():
        st["n"] += 1
        n = st["n"]
        ev = real_get()
        E = pygame.event.Event
        if n == 2:
            ev.append(E(pygame.KEYDOWN, key=pygame.K_f, mod=0, unicode="f", scancode=0))
        if n in (20, 40):
            ev.append(E(pygame.MOUSEWHEEL, x=0, y=1, flipped=False, precise_x=0.0, precise_y=1.0))
        if n == 60:
            ev.append(E(pygame.KEYDOWN, key=pygame.K_MINUS, mod=0, unicode="-", scancode=0))
        if n in (80, 90):
            ev.append(E(pygame.KEYDOWN, key=pygame.K_TAB, mod=0, unicode="\t", scancode=0))
        if n == 100:
            ev.append(E(pygame.MOUSEBUTTONDOWN, button=1, pos=(1400 - 60, 60)))
            ev.append(E(pygame.MOUSEBUTTONUP, button=1, pos=(1400 - 60, 60)))
        if n == 120:
            ev.append(E(pygame.KEYDOWN, key=pygame.K_0, mod=0, unicode="0", scancode=0))
        if n >= 260:
            ev.append(E(pygame.QUIT))
        return ev

    pygame.event.get = fake_get
    pygame.mouse.get_pos = lambda: (700, 400)
    real_clock = renderer.pygame.time.Clock
    renderer.pygame.time.Clock = lambda: type("C", (), {"tick": lambda self, fps=0: 0,
                                                        "get_fps": lambda self: 0.0})()
    try:
        renderer.run_visual(b, 20)
    finally:
        pygame.event.get = real_get
        pygame.mouse.get_pos = real_pos
        renderer.pygame.time.Clock = real_clock
    assert st["n"] >= 260


@test
def test_boucle_relance_et_retour_menu():
    """R relance la bataille (même carte si elle est graînée, état d'écran
    remis à zéro), M renvoie "menu"; chaque touche mène à une action."""
    import battle_view
    pygame.display.set_mode((1400, 800))
    random.seed(3)
    comp = [("Infanterie régulière", 6), ("Arbaletrier régulier", 3)]
    b = Battle(ul.build_army("Armée Skaldienne", comp), ul.build_army("Armée Skaldienne", comp),
               90, 40, 8, map_name="Village", map_options={'seed': 12})
    view = battle_view.BattleView(b, 20)
    view.speed_fast()
    for _ in range(30):
        view.update()
        view.draw(0)
    assert b.round > 1
    view._banner("test", (255, 255, 255), 50)
    view.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, mod=0, unicode="r",
                                         scancode=0))
    assert view.battle is not b and view.battle.round == 1
    assert view.event_banners == [] and view.winner is None
    assert view.battle.battlefield.grid == b.battlefield.grid   # même carte graînée
    view.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=0, unicode="m",
                                         scancode=0))
    assert not view.running and view.return_action == "menu"
    for action in set(battle_view.KEY_ACTIONS.values()):
        assert callable(getattr(view, action)), action


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests interface passent.")
    sys.exit(1 if fails else 0)
