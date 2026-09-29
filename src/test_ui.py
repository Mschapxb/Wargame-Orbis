"""Tests du lot D (interface de bataille). Script exécutable:
    python test_ui.py            # tout
    python test_ui.py zoom       # seulement les tests dont le nom contient 'zoom'
"""
import os, sys, random, traceback
os.environ.setdefault("WARGAME_ORBIS_SETTINGS", "memory")  # réglages du joueur intacts

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
    # Aperçu d'attaque (détail testé dans test_combat) et traits
    assert any(t.startswith("Contre ") for t in lines), lines
    assert any(t.startswith("Traits: Sort de bataille") for t in lines), lines
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
    # Synchrone: le round se joue à l'image où il s'affiche (déterministe)
    view = battle_view.BattleView(b, 20, threaded=False)
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


@test
def test_barre_d_outils_panneaux_et_souris():
    """Tout se fait aussi à la souris: boutons de la barre (retrouvés par leur
    infobulle), Échap → menu en pause, options, glisser pour déplacer la vue,
    vue globale, clic sur une unité pour la suivre."""
    import battle_view
    pygame.display.set_mode((1400, 800))
    view = battle_view.BattleView(battle(seed=4), 20, threaded=False)
    E = pygame.event.Event
    real_pos = pygame.mouse.get_pos
    try:
        pygame.mouse.get_pos = lambda: (5, 5)
        view.draw(0)

        def click_tooltip(start):
            zone = next(z for z in view.clicks.zones if z[2] and z[2].startswith(start))
            view.handle_event(E(pygame.MOUSEBUTTONDOWN, button=1, pos=zone[0].center))
            view.handle_event(E(pygame.MOUSEBUTTONUP, button=1, pos=zone[0].center))
            view.draw(0)

        assert view.paused
        click_tooltip("Lecture")                    # ▶ de la barre
        assert not view.paused
        click_tooltip("Vitesse ×4")
        assert view.speed == "faster" and view.settings.get("battle", "speed") == "faster"
        click_tooltip("Lignes de ciblage")
        assert view.show_lines is False
        view.handle_event(E(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0))
        assert view.overlay == "menu" and view.paused
        view.handle_event(E(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0))
        assert view.overlay is None and not view.paused   # l'état d'avant revient
        view.handle_event(E(pygame.KEYDOWN, key=pygame.K_o, mod=0, unicode="o", scancode=0))
        view.draw(0)
        assert view.overlay == "options"
        view.handle_event(E(pygame.MOUSEBUTTONDOWN, button=1, pos=(3, 3)))   # hors du panneau
        assert view.overlay is None

        view.view_all()
        assert abs(view.zoom - min(1.0, view.fit_zoom())) < 0.01
        view.zoom = 1.0
        view.cam_x, view.cam_y = 200.0, 20.0         # dans les bornes de la caméra
        view.draw(0)
        start = (600, 300)
        view.handle_event(E(pygame.MOUSEBUTTONDOWN, button=1, pos=start))
        view.handle_event(E(pygame.MOUSEMOTION, pos=(560, 280), rel=(-40, -20), buttons=(1, 0, 0)))
        view.handle_event(E(pygame.MOUSEBUTTONUP, button=1, pos=(560, 280)))
        assert (view.cam_x, view.cam_y) == (240.0, 40.0), "glisser déplace la vue"
        assert view.follow_uid is None, "un glisser n'est pas un clic"

        u = view.battle.army1[0]
        cs = view.cell_size
        view.cam_x, view.cam_y = u.position[0] * cs - 400, u.position[1] * cs - 300
        view.clamp_camera()
        sx = int((u.position[0] + 0.5) * cs - view.cam_x)
        sy = int((u.position[1] + 0.5) * cs - view.cam_y)
        view.draw(0)
        view.handle_event(E(pygame.MOUSEBUTTONDOWN, button=1, pos=(sx, sy)))
        view.handle_event(E(pygame.MOUSEBUTTONUP, button=1, pos=(sx, sy)))
        assert view.follow_uid == u.uid, "clic sur une unité: suivie"

        # Fin de bataille: les actions sont des boutons du rapport
        view.winner = "Armée 1"
        view.battle_report = view.battle.get_battle_report()
        view.draw(0)
        labels = {z[1] for z in view.clicks.zones if z[1] is not None}
        assert view.restart in labels and view.to_menu in labels and view.export_video in labels
    finally:
        pygame.mouse.get_pos = real_pos
        view.pipeline.close()


def _units_state(battle):
    return [(u.position, u.hp, u.is_alive, u.fleeing)
            for u in battle.army1_roster + battle.army2_roster]


@test
def test_simulation_en_tache_de_fond_meme_bataille():
    """Le round suivant se calcule dans un autre fil pendant l'animation:
    la bataille jouée reste EXACTEMENT celle de simulate_round() à la main,
    l'écran n'anime que des instantanés, et la bataille vivante ne garde rien
    de ce qu'elle a transmis à l'écran (effets, textes, flashs)."""
    import time
    import battle_view
    pygame.display.set_mode((1400, 800))
    comp1 = [("Infanterie régulière", 8), ("Arbaletrier régulier", 4), ("Housecarl", 2)]
    comp2 = [("Fantassin covaliir", 8), ("Archer covaliir", 4), ("Cavalier covaliir", 2)]
    rounds = 6

    def new_battle():
        random.seed(21)
        return Battle(ul.build_army("Armée Skaldienne", comp1),
                      ul.build_army("Armée Orlandar", comp2), 60, 36, 8, map_name="Village")

    ref = new_battle()
    expected = []
    for _ in range(rounds):
        ref.simulate_round()
        expected.append(_units_state(ref))

    live = new_battle()
    view = battle_view.BattleView(live, 20)          # fil de simulation
    try:
        assert view.pipeline.threaded and view.battle is not live
        view.speed_fast()
        seen = {}
        deadline = time.time() + 60
        while view.battle.round <= rounds and view.winner is None:
            assert time.time() < deadline, "le fil de simulation ne rend pas la main"
            view.update()
            view.draw(0)
            shown = view.battle.round - 1          # rounds joués dans l'instantané
            if shown >= 1 and shown not in seen:
                assert view.battle is not live
                seen[shown] = _units_state(view.battle)
            view.pipeline.wait(0.01)
        for k, state in seen.items():
            assert state == expected[k - 1], f"round {k}: la bataille affichée diverge"
        assert len(seen) >= min(rounds, 3)
    finally:
        view.pipeline.close()
    for u in live.army1_roster + live.army2_roster:
        assert not u.floating_texts and u._hit_flash == 0 and u._lunge_timer == 0
    assert not any(live.visual_effects.values())


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
