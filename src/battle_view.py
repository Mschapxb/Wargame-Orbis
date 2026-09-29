"""Écran de bataille: boucle d'affichage, caméra, commandes et HUD.

`BattleView(battle, cell_size).run()` joue la bataille à l'écran et renvoie
"menu" (touche M) ou None (quitter). renderer.py garde les primitives de
dessin (terrain, structures, rapport); ce module les orchestre.

Chaque image: événements → caméra → animation → dessin. Les commandes
clavier passent par la table KEY_ACTIONS (touche → méthode).

La simulation tourne en tâche de fond (battle_pipeline): le round suivant se
calcule pendant que l'écran anime le précédent, et `self.battle` n'est
jamais la bataille jouée mais l'INSTANTANÉ du dernier round calculé.
"""
import math
import os
import random
import sys

import pygame

import battle_pipeline as BP
import hud
import icons
import renderer as R
import settings as settings_mod
import terrain_render
import theme as T
import ui
import unit_sprites
from fx_render import FxRenderer
from weather_render import WeatherFx

CAM_SPEED = 12            # pixels écran par image (cf. réglage camera_speed)
EDGE_SCROLL_MARGIN = 30   # bande de défilement au bord de l'écran
DRAG_THRESHOLD = 5        # pixels avant qu'un clic gauche devienne un glisser
WORLD_BG = (25, 40, 30)

HELP_TEXT = "H  aide et raccourcis   ·   Échap  menu   ·   glisser  déplacer la vue"

# Vitesses: (images par round, libellé, icône)
SPEEDS = {
    "normal": (R.ROUND_FRAMES_NORMAL, "×1", "speed1"),
    "fast": (R.ROUND_FRAMES_FAST, "×2", "speed2"),
    "faster": (10, "×4", "speed3"),
}
CAMERA_SPEEDS = ((8, "Lente"), (12, "Normale"), (20, "Rapide"))

# Aide: (touches, action), dans l'ordre d'affichage
KEY_HELP = (
    (("Espace",), "Pause / reprise"),
    (("1", "2", "3"), "Vitesse ×1, ×2, ×4"),
    (("Molette", "+", "−"), "Zoom (0 : taille réelle)"),
    (("G",), "Vue globale de toute la carte"),
    (("Flèches", "ZQSD"), "Déplacer la vue"),
    (("Tab",), "Mini-carte"),
    (("T",), "Lignes de ciblage"),
    (("I",), "Intentions des généraux"),
    (("L",), "Légende du terrain"),
    (("V",), "Vidéo de la bataille (vue globale)"),
    (("R",), "Relancer la même bataille"),
    (("O",), "Options"),
    (("M",), "Retour au menu"),
    (("B",), "Plein écran"),
    (("Échap",), "Menu / fermer un panneau"),
)
MOUSE_HELP = (
    ("Glisser (clic gauche)", "Déplacer la vue"),
    ("Clic sur une unité", "La suivre (clic dans le vide : arrêter)"),
    ("Survol d'une unité", "Fiche, zone atteignable et chemin"),
    ("Clic sur la mini-carte", "Y centrer la vue"),
    ("Molette", "Zoom autour du curseur"),
)

_MANEUVER_FR = {"envelop": "débordement", "concentrate": "concentration",
                "collapse": "curée", "breach": "percée"}

# Bannière annonçant une manœuvre: (texte après « Armée N », couleur, durée)
_MANEUVER_BANNERS = {
    "envelop": ("déborde sur les ailes !", (255, 190, 80), 160),
    "concentrate": ("concentre ses forces !", (170, 230, 120), 160),
    "collapse": ("fond sur un isolé !", (255, 140, 140), 140),
    "breach": ("s'engouffre dans la brèche !", (255, 170, 90), 160),
}

# Couleur des lignes de ciblage, par type d'attaque
_TARGET_LINE_COLORS = {"spell": (120, 60, 180), "ranged": (60, 120, 180),
                       "reach": (180, 150, 40)}
_TARGET_LINE_MELEE = (180, 60, 60)

# Survol d'une unité: zone atteignable au prochain round et chemin suivi
_REACH_FILL = (120, 200, 255, 38)
_REACH_EDGE = (150, 215, 255, 90)
_PATH_COLOR = (255, 225, 120)

KEY_ACTIONS = {
    pygame.K_SPACE: "toggle_pause",
    pygame.K_1: "speed_normal", pygame.K_KP1: "speed_normal", pygame.K_n: "speed_normal",
    pygame.K_2: "speed_fast", pygame.K_KP2: "speed_fast", pygame.K_f: "speed_fast",
    pygame.K_3: "speed_faster", pygame.K_KP3: "speed_faster",
    pygame.K_p: "pause_on",
    pygame.K_ESCAPE: "escape",
    pygame.K_m: "to_menu",
    pygame.K_r: "restart",
    pygame.K_t: "toggle_lines",
    pygame.K_i: "toggle_intents",
    pygame.K_TAB: "toggle_minimap",
    pygame.K_PLUS: "zoom_in", pygame.K_KP_PLUS: "zoom_in", pygame.K_EQUALS: "zoom_in",
    pygame.K_MINUS: "zoom_out", pygame.K_KP_MINUS: "zoom_out",
    pygame.K_0: "zoom_reset", pygame.K_KP0: "zoom_reset",
    pygame.K_g: "view_all", pygame.K_HOME: "view_all",
    pygame.K_l: "toggle_legend",
    pygame.K_v: "export_video",
    pygame.K_h: "toggle_help", pygame.K_F1: "toggle_help",
    pygame.K_o: "toggle_options",
    pygame.K_b: "toggle_fullscreen",
}

# Défilement continu (touches maintenues, flèches et ZQSD): (dx, dy)
SCROLL_KEYS = (
    ((pygame.K_LEFT, pygame.K_q), (-1, 0)),
    ((pygame.K_RIGHT, pygame.K_d), (1, 0)),
    ((pygame.K_UP, pygame.K_z), (0, -1)),
    ((pygame.K_DOWN, pygame.K_s), (0, 1)),
)


def _open_folder(path):
    """Ouvre le dossier d'un fichier (Windows: l'Explorateur, fichier
    sélectionné)."""
    import subprocess
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except OSError:
        pass


def _unit_dims(u):
    """Empreinte en cases selon la taille de l'unité."""
    if u.size <= 1:
        return 1, 1
    if u.size == 2:
        return 2, 2
    return 2, 4


def _along_path(path, t):
    """Point (en cases, flottant) à la fraction `t` ∈ [0, 1] de la longueur
    de la ligne brisée `path` (une diagonale compte √2)."""
    segs = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])]
    total = sum(segs)
    if total <= 0:
        return path[-1]
    d = max(0.0, min(1.0, t)) * total
    for (a, b), s in zip(zip(path, path[1:]), segs):
        if d <= s and s > 0:
            k = d / s
            return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        d -= s
    return path[-1]


class BattleView:
    def __init__(self, battle, cell_size, threaded=True):
        """threaded=False: chaque round est simulé au moment de l'afficher,
        dans ce fil (ancien comportement, déterministe image par image)."""
        info = pygame.display.Info()
        screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
        pygame.display.set_caption("Wargame Orbis — bataille")
        self._setup(battle, cell_size, screen, threaded)

    def _setup(self, battle, cell_size, screen, threaded, hud_height=R.HUD_HEIGHT):
        """Tout ce qui ne dépend pas de la fenêtre (cf. video_export, qui
        dessine sur une surface hors écran)."""
        self.screen = screen
        self.screen_w, self.screen_h = screen.get_size()
        self.view_h = self.screen_h - hud_height
        self.clock = pygame.time.Clock()
        self.is_borderless = True   # False = plein écran exclusif (touche B)
        self.cell_size = cell_size
        self.threaded = threaded
        self.pipeline = None
        self.settings = settings_mod.get()
        prefs = self.settings.section("battle")
        self.world_bg = WORLD_BG        # fond hors de la carte

        self.small_font = T.font('ui', max(9, cell_size // 3) + 1)
        self.tiny_font = T.font('ui', max(7, cell_size // 4) + 1)
        self.banner_font = T.font('title', 20)
        self.pause_font = T.font('title', 34)
        self.card_font = T.font('ui', 14)
        self.hud_bold = T.font('ui_bold', 15)
        self.hud_font = T.font('ui', 13)
        self.top_bold = T.font('ui_bold', 13)
        self.top_small = T.font('ui', 11)

        # Moteur d'effets: particules, décalques, morts, sprites de combat
        self.fxr = FxRenderer(cell_size, R.load_token, self.tiny_font)
        self.minimap = ui.Minimap(battle, cell_size, self.screen_w, 38)

        self.paused = prefs["start_paused"]
        self.speed = prefs["speed"] if prefs["speed"] in SPEEDS else "normal"
        self.running = True
        self.return_action = None
        # Affichage: repris des réglages, et gardé pour la prochaine fois
        self.show_lines = prefs["show_lines"]
        self.show_intents = prefs["show_intents"]
        self.show_minimap = prefs["show_minimap"]
        self.show_terrain_legend = prefs["show_legend"]

        # Interface: zones cliquables de la dernière image, panneau ouvert
        # (None, "menu", "help", "options"), notifications, suivi d'unité
        self.clicks = hud.Clicks()
        self.overlay = None
        self._paused_before_menu = False
        self.toasts = hud.Toasts()
        self.tooltip = hud.Tooltip()
        self.follow_uid = None
        self._press = None              # clic gauche en cours sur le monde
        self._left_drag = False
        self.video_job = None

        # Zoom: le monde est dessiné à sa taille de case dans une surface de
        # vue (écran / zoom), puis mis à l'échelle — aucune coordonnée ne change.
        self.zoom = 1.0
        self.world_view = None
        self._scaled_view = None        # la vue mise à l'échelle du zoom
        self.dragging = False
        self.drag_start = (0, 0)
        self.drag_cam_start = (0, 0)
        self.minimap_drag = False

        # Relance (touche R): mêmes armées, même carte, mêmes options
        self._restart_args = (battle._restart_army1, battle._restart_army2,
                              battle.battlefield.width, battle.battlefield.height, 8)
        self._restart_kwargs = {'map_name': battle.map_name,
                                'map_options': getattr(battle, 'map_options', None)}
        self._load_battle(battle)

    # ─── État propre à une bataille (début et relance) ───

    def _load_battle(self, battle):
        cs = self.cell_size
        # Avant tout round: les effets se placent en pixels de cette taille
        battle.cell_size = cs
        if self.pipeline is not None:
            self.pipeline.close()
        self.pipeline = BP.RoundPipeline(battle, threaded=self.threaded)
        # L'écran ne touche plus la bataille jouée, seulement ses instantanés
        live = battle
        battle = self.battle = self.pipeline.initial_snapshot()
        # De quoi rejouer EXACTEMENT cette bataille ailleurs (vidéo): l'état
        # de départ et celui du hasard, avant que le premier round n'y tire
        self._replay_kit = BP.pack_battle(live, random.getstate())
        self._by_uid = {u.uid: u for u in battle.army1 + battle.army2}
        self.follow_uid = None
        bf = battle.battlefield
        self.grid_surface = R.build_grid_surface(battle, cs)
        self.fxr.reset(bf.width * cs, bf.height * cs)
        self.wfx = WeatherFx(getattr(bf, 'weather', None), snow=terrain_render.is_winter(bf))
        self.gate_state = R.gate_visual_state(bf)
        self.world_w = bf.width * cs
        self.world_h = bf.height * cs
        self.cam_x = max(0, (self.world_w - self.screen_w) / 2)
        self.cam_y = max(0, (self.world_h - self.view_h) / 2)
        self.clamp_camera()

        self.winner = None
        self.battle_report = None
        self.terrain_legend = None
        self.move_anim_progress = 1.0   # 0 = début du mouvement, 1 = arrivé
        self.round_frame = 10 ** 6      # force l'affichage du premier round
        self.screen_shake = 0.0         # secousse de caméra (impacts lourds)

        # Bannières d'événements dramatiques: [texte, couleur, images restantes]
        self.event_banners = []
        self.prev_gates_open = getattr(bf, 'gates_open', False)
        self.prev_intact_gates = sum(1 for h in bf.gate_hp.values() if h > 0)
        cmds = (battle.commander1, battle.commander2)
        self.prev_postures = [getattr(c, 'posture', 'balanced') for c in cmds]
        self.prev_maneuvers = [getattr(c, 'maneuver', None) for c in cmds]
        # Le premier round se calcule déjà (même en pause)
        self.pipeline.request(self._round_frames())

    # ─── Boucle ───

    def run(self):
        # Le fil de simulation calcule pendant que celui-ci dessine: un
        # passage de main plus fréquent (5 ms par défaut) évite qu'une image
        # attende trop longtemps le verrou global de Python.
        switch = sys.getswitchinterval()
        sys.setswitchinterval(0.001)
        try:
            while self.running:
                now = pygame.time.get_ticks()
                for event in pygame.event.get():
                    self.handle_event(event)
                self.scroll_camera()
                self.update()
                self.draw(now)
                pygame.display.flip()
                self.clock.tick(60)
        finally:
            sys.setswitchinterval(switch)
            self.pipeline.close()
            self.settings.save()
        return self.return_action

    # ─── Caméra ───

    def clamp_camera(self):
        self.cam_x, self.cam_y = ui.clamp_camera(self.cam_x, self.cam_y, self.world_w,
                                                 self.world_h, self.screen_w, self.view_h,
                                                 self.zoom)

    def set_zoom(self, new_zoom, anchor_x, anchor_y):
        """Change le zoom en gardant fixe le point écran (anchor_x, anchor_y)."""
        if new_zoom == self.zoom:
            return
        self.cam_x, self.cam_y = ui.zoom_around(self.cam_x, self.cam_y, anchor_x, anchor_y,
                                                self.zoom, new_zoom)
        self.zoom = new_zoom
        self.clamp_camera()

    def _minimap_jump(self, pos):
        """Centre la vue sur le point cliqué de la mini-carte (s'il y est)."""
        target = self.minimap.camera_for(self.battle, *pos, self.screen_w, self.view_h,
                                         self.zoom)
        if target is not None:
            self.cam_x, self.cam_y = target
            self.clamp_camera()
        return target is not None

    def fit_zoom(self):
        """Zoom où toute la carte tient dans la vue."""
        return min(self.screen_w / max(1, self.world_w), self.view_h / max(1, self.world_h))

    def _zoom_levels(self):
        levels = list(ui.ZOOM_LEVELS)
        fit = round(self.fit_zoom(), 3)
        if fit < levels[0]:
            levels.insert(0, fit)
        return levels

    def _next_zoom(self, direction):
        levels = self._zoom_levels()
        idx = min(range(len(levels)), key=lambda i: abs(levels[i] - self.zoom))
        return levels[max(0, min(len(levels) - 1, idx + direction))]

    def over_ui(self, pos):
        """La souris est-elle sur l'interface (bandeau, bouton, panneau) ?"""
        return (self.overlay is not None or pos[1] >= self.view_h
                or self.clicks.at(pos) is not None)

    def scroll_camera(self):
        """Défilement continu: touches maintenues et souris au bord (sauf
        sur l'interface: on ne fait pas défiler la carte en visant un
        bouton). Toute commande de caméra arrête le suivi d'une unité."""
        prefs = self.settings.section("battle")
        step = prefs["camera_speed"] / self.zoom
        keys = pygame.key.get_pressed()
        moved = False
        if self.overlay is None:
            for key_group, (dx, dy) in SCROLL_KEYS:
                if any(keys[k] for k in key_group):
                    self.cam_x += dx * step
                    self.cam_y += dy * step
                    moved = True
        mx, my = pygame.mouse.get_pos()
        if (prefs["edge_scroll"] and pygame.mouse.get_focused() and not self._left_drag
                and not self.over_ui((mx, my))):
            if mx < EDGE_SCROLL_MARGIN:
                self.cam_x -= step
                moved = True
            elif mx > self.screen_w - EDGE_SCROLL_MARGIN:
                self.cam_x += step
                moved = True
            if my < EDGE_SCROLL_MARGIN:
                self.cam_y -= step
                moved = True
            elif self.view_h - EDGE_SCROLL_MARGIN < my < self.view_h:
                self.cam_y += step
                moved = True
        if moved:
            self.follow_uid = None
        self._follow_camera()
        self.clamp_camera()

    def _follow_camera(self):
        """Caméra accrochée à l'unité suivie (glissement doux)."""
        if self.follow_uid is None:
            return
        u = self._by_uid.get(self.follow_uid)
        if u is None or not u.is_alive or u.position is None:
            self.follow_uid = None
            self.toasts.add("Unité suivie hors de combat", T.WARNING, 2.5)
            return
        uw, uh = _unit_dims(u)
        cx, cy = self._unit_center(u, uw, uh, 0, 0, pygame.time.get_ticks())
        vw, vh = self.screen_w / self.zoom, self.view_h / self.zoom
        self.cam_x += (cx - vw / 2 - self.cam_x) * 0.18
        self.cam_y += (cy - vh / 2 - self.cam_y) * 0.18

    # ─── Événements ───

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.quit()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self._left_down(event.pos)
            elif event.button == 2 and self.overlay is None:   # clic molette: glisser
                self.dragging = True
                self.drag_start = event.pos
                self.drag_cam_start = (self.cam_x, self.cam_y)
            elif event.button == 3 and self.overlay is not None:
                self.overlay = None          # clic droit: fermer le panneau
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self.dragging = False
            elif event.button == 1:
                self._left_up(event.pos)
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                self.cam_x = self.drag_cam_start[0] + (self.drag_start[0] - event.pos[0]) / self.zoom
                self.cam_y = self.drag_cam_start[1] + (self.drag_start[1] - event.pos[1]) / self.zoom
                self.follow_uid = None
                self.clamp_camera()
            elif self.minimap_drag:
                self._minimap_jump(event.pos)
            elif self._press is not None:
                self._left_motion(event.pos)
        elif event.type == pygame.MOUSEWHEEL and event.y and self.overlay is None:
            wmx, wmy = pygame.mouse.get_pos()
            self.set_zoom(self._next_zoom(1 if event.y > 0 else -1), wmx, wmy)
        elif event.type == pygame.KEYDOWN:
            action = KEY_ACTIONS.get(event.key)
            if action:
                getattr(self, action)()

    # ─── Souris: interface d'abord, puis mini-carte, puis le monde ───

    def _left_down(self, pos):
        zone = self.clicks.at(pos)
        if zone is not None:
            if zone[1] is not None:
                zone[1]()
            return
        if self.overlay is not None:
            self.overlay = None            # clic hors du panneau: le fermer
            return
        if self.show_minimap and self.minimap.rect.collidepoint(pos):
            self.minimap_drag = self._minimap_jump(pos)
            self.follow_uid = None
            return
        if pos[1] >= self.view_h:
            return
        if self.paused and self.winner is None and self.battle.round <= 1:
            self.paused = False            # premier clic sur la carte: on lance
        self._press = (pos, self.cam_x, self.cam_y)
        self._left_drag = False

    def _left_motion(self, pos):
        (sx, sy), cx, cy = self._press
        if not self._left_drag and abs(pos[0] - sx) + abs(pos[1] - sy) < DRAG_THRESHOLD:
            return
        self._left_drag = True
        self.follow_uid = None
        self.cam_x = cx + (sx - pos[0]) / self.zoom
        self.cam_y = cy + (sy - pos[1]) / self.zoom
        self.clamp_camera()

    def _left_up(self, pos):
        self.minimap_drag = False
        if self._press is not None and not self._left_drag:
            self._world_click(pos)
        self._press = None
        self._left_drag = False

    def _world_click(self, pos):
        """Clic (sans glisser) sur la carte: suivre l'unité cliquée, ou
        arrêter de suivre."""
        wx, wy = ui.screen_to_world(pos[0], pos[1], self.cam_x, self.cam_y, self.zoom)
        u = ui.unit_at(self.battle, wx, wy, self.cell_size)
        if u is None or u.uid == self.follow_uid:
            self.follow_uid = None
        else:
            self.follow_uid = u.uid

    # ─── Actions clavier (cf. KEY_ACTIONS) ───

    def toggle_pause(self):
        if self.overlay == "menu":
            self.close_overlay()
            return
        self.paused = not self.paused

    def _set_speed(self, speed):
        self.speed, self.paused = speed, False
        self.settings.set("battle", "speed", speed)

    def speed_normal(self):
        self._set_speed("normal")

    def speed_fast(self):
        self._set_speed("fast")

    def speed_faster(self):
        self._set_speed("faster")

    def pause_on(self):
        self.paused = True

    def quit(self):
        self.running = False
        self.return_action = None

    def to_menu(self):
        self.running = False
        self.return_action = "menu"

    def restart(self):
        from battle import Battle
        # Le fil finit son round AVANT la nouvelle bataille: la génération de
        # la carte ne doit pas tirer dans le même hasard que lui
        self.pipeline.close()
        self.overlay = None
        self._load_battle(Battle(*self._restart_args, **self._restart_kwargs))

    def _toggle_pref(self, attr, key):
        value = not getattr(self, attr)
        setattr(self, attr, value)
        self.settings.set("battle", key, value)

    def toggle_lines(self):
        self._toggle_pref("show_lines", "show_lines")

    def toggle_intents(self):
        self._toggle_pref("show_intents", "show_intents")

    def toggle_minimap(self):
        self._toggle_pref("show_minimap", "show_minimap")

    def _zoom_centered(self, new_zoom):
        self.set_zoom(new_zoom, self.screen_w / 2, self.view_h / 2)

    def zoom_in(self):
        self._zoom_centered(self._next_zoom(1))

    def zoom_out(self):
        self._zoom_centered(self._next_zoom(-1))

    def zoom_reset(self):
        self._zoom_centered(1.0)

    def view_all(self):
        """Vue globale: toute la carte à l'écran (G, Origine)."""
        self.follow_uid = None
        self.zoom = min(1.0, round(self.fit_zoom(), 3))
        self.clamp_camera()

    def toggle_legend(self):
        self._toggle_pref("show_terrain_legend", "show_legend")
        self.terrain_legend = None   # reconstruite au prochain affichage

    # ─── Panneaux (menu Échap, aide, options) ───

    def escape(self):
        """Échap: ferme le panneau ouvert, sinon ouvre le menu (pause)."""
        if self.overlay is not None:
            self.close_overlay()
        else:
            self.open_menu()

    def open_menu(self):
        self._paused_before_menu = self.paused
        self.paused = True
        self.overlay = "menu"

    def close_overlay(self):
        if self.overlay == "menu":
            self.paused = self._paused_before_menu
        self.overlay = None
        self.settings.save()

    def resume(self):
        self.overlay = None
        self.paused = False

    def toggle_help(self):
        self.overlay = None if self.overlay == "help" else "help"

    def toggle_options(self):
        if self.overlay == "options":
            self.close_overlay()
        else:
            self.overlay = "options"

    # ─── Vidéo ───

    def export_video(self):
        """Vidéo de TOUTE la bataille, en vue globale, rejouée dans un autre
        processus (le jeu continue pendant ce temps)."""
        import video_export
        if self.video_job is not None and self.video_job.running:
            self.toasts.add("Une vidéo est déjà en préparation", T.WARNING, 3)
            return
        expected = self.battle.round - 1 if self.winner else None
        self.video_job = video_export.ExportJob(
            self._replay_kit, dict(self.settings.section("video")),
            title=self._battle_title(), expected_rounds=expected)
        self.toasts.add("Vidéo en préparation…", T.GOLD, None, key="video",
                        sub="vue globale de toute la bataille", progress=0.0)

    def _battle_title(self):
        bf = self.battle.battlefield
        sky = getattr(bf, 'weather', None)
        parts = [self.battle.map_name]
        if sky is not None and sky.name != "Clair":
            parts.append(sky.label.lower())
        return " · ".join(parts)

    def _poll_video(self):
        job = self.video_job
        if job is None:
            return
        state = job.poll()
        if state['state'] == "running":
            total = state.get('total')
            done = state.get('round', 0)
            sub = (f"round {done} / {total}" if total else f"round {done}")
            self.toasts.add("Vidéo en préparation…", T.GOLD, None, key="video", sub=sub,
                            progress=(done / total) if total else None)
        elif state['state'] == "done":
            path = state['path']
            self.toasts.add("Vidéo enregistrée — cliquer pour ouvrir", T.SUCCESS, 12,
                            key="video", sub=os.path.basename(path),
                            action=lambda p=path: _open_folder(p))
            self.video_job = None
        elif state['state'] == "error":
            self.toasts.add("La vidéo a échoué", T.DANGER, 8, key="video",
                            sub=state.get('message', "")[:80])
            self.video_job = None

    def toggle_fullscreen(self):
        """Bascule entre fenêtre sans bord et plein écran exclusif."""
        self.is_borderless = not self.is_borderless
        flags = pygame.NOFRAME if self.is_borderless else pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), flags)
        R.clear_token_cache()
        self.fxr._snap_cache.clear()
        self.grid_surface = R.build_grid_surface(self.battle, self.cell_size)

    # ─── Simulation ───

    def _round_frames(self):
        return SPEEDS.get(self.speed, SPEEDS["normal"])[0]

    def update(self):
        self._poll_video()
        if not self.paused and self.winner is None:
            # ── Cadence CONTINUE ──
            # Le round n'est plus « simuler, animer, puis attendre »: sa
            # durée est fixée en frames, le moteur y répartit toutes les
            # actions (cf. battle.T_*), et le round suivant enchaîne sans
            # temps mort. C'est ce qui donne la sensation de temps réel.
            frames = self._round_frames()
            if self.round_frame >= frames:
                # Round fini: le suivant s'est calculé pendant son animation.
                # S'il n'est pas encore prêt, on garde l'image — l'écran, lui,
                # continue de répondre.
                snap = self.pipeline.take()
                if snap is not None:
                    self._show_round(snap, frames)
            else:
                self.round_frame += 1
            # Le déplacement occupe la première moitié du round et se
            # termine avant que l'échange général ne batte son plein.
            self.move_anim_progress = min(1.0, self.round_frame / max(1.0, frames * R.MOVE_WINDOW))

        battle = self.battle
        # Décompter les minuteries d'animation (une fois l'instant venu).
        # Les textes flottants vieillissent ICI, pour toutes les unités et
        # hors pause: vieillis au dessin, ceux d'une unité hors champ (ou
        # trop petite à l'écran) s'accumulaient et rejouaient tous d'un coup
        # quand la caméra y revenait — et ils filaient pendant la pause.
        for u in battle.army1 + battle.army2:
            if u._lunge_timer > 0 and self.round_frame >= getattr(u, '_lunge_delay', 0):
                u._lunge_timer -= 1
            if u._hit_flash > 0 and self.round_frame >= getattr(u, '_hit_flash_delay', 0):
                u._hit_flash -= 1
            fts = u.floating_texts
            if fts and not self.paused:
                expired = False
                for ft in fts:
                    ft.age += 1
                    expired = expired or not ft.is_alive()
                if expired:             # deque bornée: filtrée en place
                    keep = [ft for ft in fts if ft.is_alive()]
                    fts.clear()
                    fts.extend(keep)

        # Vieillir effets visuels — figés en pause (sinon les effets
        # horodatés se jouaient pendant que le round, lui, était arrêté)
        if not self.paused:
            for key in ('projectiles', 'attack_lines', 'aoe_explosions', 'heal_beams',
                        'armor_shimmers', 'wall_effects', 'impacts', 'shockwaves',
                        'slashes', 'thrusts', 'deaths'):
                lst = battle.visual_effects.get(key)
                if not lst:
                    continue
                for e in lst:
                    e.age += 1
                battle.visual_effects[key] = [e for e in lst if e.is_alive()]
        # Repeints et cratères horodatés: au moment de l'action, pas avant
        R.apply_destruction(self.grid_surface, battle, self.cell_size, self.round_frame)
        self.fxr.round_frame = self.round_frame
        self.fxr.update(battle, paused=self.paused)
        self.wfx.update(paused=self.paused)

        # Secousse de caméra: juste un frémissement sur les chocs les plus
        # lourds. Au-delà de 2 px ça devient illisible et laid.
        for fx in battle.visual_effects.get('shockwaves', []):
            if fx.age == fx.delay:
                self.screen_shake = min(R.SHAKE_MAX, self.screen_shake + 1.1)
        self.screen_shake *= 0.72
        if self.screen_shake < 0.25:
            self.screen_shake = 0.0

    def _show_round(self, snap, frames):
        """Passe à l'instantané du round suivant et demande celui d'après,
        qui se calculera pendant l'animation de celui-ci."""
        old = self.battle
        # Ce que la destruction a changé au round précédent est appliqué en
        # entier avant d'afficher le nouveau.
        R.apply_destruction(self.grid_surface, old, self.cell_size, 10 ** 6)
        BP.carry_over(old, snap)
        self.battle = battle = snap
        self._by_uid = {u.uid: u for u in battle.army1 + battle.army2}
        self.round_frame = 0
        # Rafraîchir la grille si siège (portes détruites)
        if battle.battlefield.gate_hp:
            self.gate_state = R.repaint_gates(self.grid_surface, battle, self.cell_size,
                                              self.gate_state)
        self._detect_events()
        result = battle.is_battle_over()
        if result:
            self.winner = result
            self.battle_report = battle.get_battle_report()
        else:
            self.pipeline.request(frames)

    def _banner(self, text, color, frames):
        self.event_banners.append([text, color, frames])

    def _detect_events(self):
        """Changements du round (portes, postures, manœuvres) → bannières."""
        battle = self.battle
        bf = battle.battlefield
        gates_open = getattr(bf, 'gates_open', False)
        if gates_open != self.prev_gates_open:
            if gates_open:
                self._banner("LES PORTES S'OUVRENT — SORTIE !", (255, 210, 70), 180)
            else:
                self._banner("LES PORTES SE REFERMENT", (150, 200, 255), 150)
            self.prev_gates_open = gates_open
        n_intact = sum(1 for h in bf.gate_hp.values() if h > 0)
        if n_intact < self.prev_intact_gates and not gates_open:
            if n_intact == 0:
                self._banner("LA PORTE EST ENFONCÉE !", (255, 120, 60), 180)
            self.prev_intact_gates = n_intact
        for ci, cmd in enumerate((battle.commander1, battle.commander2)):
            side = f"Armée {ci + 1}"
            posture = getattr(cmd, 'posture', 'balanced')
            if posture != self.prev_postures[ci]:
                self.prev_postures[ci] = posture
                label = R._POSTURE_BANNERS.get(posture)
                if label:
                    self._banner(f"{side} : {label[0]}", label[1], 150)
            maneuver = getattr(cmd, 'maneuver', None)
            if maneuver != self.prev_maneuvers[ci]:
                self.prev_maneuvers[ci] = maneuver
                if maneuver in _MANEUVER_BANNERS:
                    text, color, frames = _MANEUVER_BANNERS[maneuver]
                    self._banner(f"{side} {text}", color, frames)
        for txt, col, imp in getattr(battle, 'round_events', ()):
            if imp >= 2:
                self._banner(txt, col, 140)

    # ─── Dessin ───

    def draw(self, now):
        screen = self.screen
        mouse = pygame.mouse.get_pos()
        # Survol: décidé sur les zones de l'image précédente (un bouton
        # masque l'unité qui est dessous)
        if self.over_ui(mouse) or self._left_drag:
            hovered = None
        else:
            hovered = self._hovered_unit()[0]
        clicks = self.clicks = hud.Clicks()
        self._draw_world(now, hovered)
        self.wfx.draw(screen, self.screen_w, self.view_h)
        self.fxr.draw_screen(screen, self.screen_w, self.view_h)
        self._draw_top_bar()
        self._draw_banners()
        self._draw_terrain_legend()
        if self.show_minimap:
            self.minimap.refresh(self.battle)
            self.minimap.draw(screen, self.battle, self.cam_x, self.cam_y, self.screen_w,
                              self.view_h, self.zoom)
            clicks.add(self.minimap.rect.inflate(12, 12), self._minimap_click,
                       "Mini-carte : cliquer pour y aller")
        self._draw_bottom_hud()
        self._draw_follow_chip(mouse)
        if self.battle_report:
            panel = R.draw_battle_report(screen, self.battle_report, self.screen_w, self.view_h,
                                         self.small_font, self.tiny_font, footer=58)
            self._draw_report_buttons(panel, mouse)
        else:
            self._draw_toolbar(mouse)
            if self.paused and self.winner is None and self.overlay is None:
                self._draw_pause(mouse)
        self.toasts.draw(screen, clicks, self.screen_w - 14, self.view_h - 62, now,
                         (self.hud_bold, self.hud_font), mouse)
        if self.overlay == "menu":
            self._draw_menu_overlay(mouse)
        elif self.overlay == "help":
            self._draw_help_overlay(mouse)
        elif self.overlay == "options":
            self._draw_options_overlay(mouse)
        # Fiche de l'unité survolée (par-dessus tout)
        if hovered is not None and not self.battle_report and self.overlay is None:
            ui.draw_unit_card(screen, hovered, self.battle, mouse[0], mouse[1], self.card_font,
                              pygame.Rect(0, 30, self.screen_w, self.view_h - 30))
        self.tooltip.draw(screen, clicks.at(mouse), now, self.hud_font,
                          pygame.Rect(0, 0, self.screen_w, self.screen_h))

    def _minimap_click(self):
        self.minimap_drag = self._minimap_jump(pygame.mouse.get_pos())
        self.follow_uid = None

    # ─── Interface: barre d'outils, pause, suivi, rapport ───

    def _draw_toolbar(self, mouse):
        playing = not self.paused
        speed_keys = {"normal": "1", "fast": "2", "faster": "3"}
        exporting = self.video_job is not None and self.video_job.running
        groups = [
            [("pause" if playing else "play", self.toggle_pause,
              ("Pause" if playing else "Lecture") + "  —  Espace", False)],
            [(SPEEDS[s][2], getattr(self, f"speed_{s}"),
              f"Vitesse {SPEEDS[s][1]}  —  {speed_keys[s]}", self.speed == s)
             for s in ("normal", "fast", "faster")],
            [("zoom_out", self.zoom_out, "Éloigner  —  molette, −", False),
             ("fit", self.view_all, "Vue globale  —  G", self.zoom < 0.999
              and abs(self.zoom - min(1.0, self.fit_zoom())) < 0.01),
             ("zoom_in", self.zoom_in, "Rapprocher  —  molette, +", False)],
            [("lines", self.toggle_lines, "Lignes de ciblage  —  T", self.show_lines),
             ("intents", self.toggle_intents, "Intentions des généraux  —  I",
              self.show_intents),
             ("minimap", self.toggle_minimap, "Mini-carte  —  Tab", self.show_minimap),
             ("legend", self.toggle_legend, "Légende du terrain  —  L",
              self.show_terrain_legend)],
            [("record" if exporting else "video", self.export_video,
              "Vidéo de la bataille, vue globale  —  V", exporting)],
            [("restart", self.restart, "Relancer la même bataille  —  R", False),
             ("options", self.toggle_options, "Options  —  O", self.overlay == "options"),
             ("help", self.toggle_help, "Aide et raccourcis  —  H", self.overlay == "help"),
             ("menu", self.open_menu, "Menu  —  Échap", self.overlay == "menu")],
        ]
        hud.toolbar(self.screen, self.clicks, groups, self.screen_w // 2, self.view_h - 8, mouse)

    def _draw_pause(self, mouse):
        """Carton de pause (ou de lancement), cliquable: pas besoin de
        connaître la touche pour lancer la bataille."""
        screen = self.screen
        first = self.battle.round <= 1
        title = "Prêts au combat" if first else "Pause"
        pt = T.gold_text(title, self.pause_font)
        pw, ph = max(340, pt.get_width() + 90), pt.get_height() + 98
        prect = pygame.Rect((self.screen_w - pw) // 2, (self.view_h - ph) // 2 - 40, pw, ph)
        T.glass(screen, prect, 215, 10)
        T.corner_marks(screen, prect, T.GOLD_DIM, 9)
        screen.blit(pt, (prect.centerx - pt.get_width() // 2, prect.y + 8))
        T.divider(screen, prect.x + 30, prect.right - 30, prect.y + 12 + pt.get_height())
        brect = pygame.Rect(0, 0, 230, 40)
        brect.midbottom = (prect.centerx, prect.bottom - 26)
        hud.text_button(screen, self.clicks, brect,
                        "Lancer la bataille" if first else "Reprendre", self.hud_bold, mouse,
                        self.resume, icon_name="play", primary=True)
        T.text(screen, "ou Espace  ·  clic sur la carte" if first else "ou Espace",
               self.top_small, (prect.centerx, prect.bottom - 20), T.PARCHMENT_DIM,
               align="center")

    def _draw_follow_chip(self, mouse):
        """Puce « Suivi : unité » sous le bandeau, avec sa croix."""
        u = self._by_uid.get(self.follow_uid) if self.follow_uid is not None else None
        if u is None:
            return
        img = self.hud_font.render(f"Suivi : {u.name}", True, T.PARCHMENT)
        rect = pygame.Rect(0, 0, img.get_width() + 68, 28)
        rect.midtop = (self.screen_w // 2, 40 + (48 if self.event_banners else 0))
        T.glass(self.screen, rect, 225, 8)
        self.screen.blit(icons.icon("follow", 16, T.GOLD), (rect.x + 10, rect.y + 6))
        self.screen.blit(img, (rect.x + 32, rect.y + 5))
        hud.icon_button(self.screen, self.clicks, (rect.right - 26, rect.y + 4, 20, 20),
                        "close", mouse, self._stop_follow, "Arrêter de suivre")

    def _stop_follow(self):
        self.follow_uid = None

    def _draw_report_buttons(self, panel, mouse):
        """Actions de fin de bataille, sans avoir à connaître les touches."""
        labels = (("Rejouer", "restart", self.restart, True),
                  ("Vidéo", "video", self.export_video, False),
                  ("Menu", "menu", self.to_menu, False),
                  ("Quitter", "exit", self.quit, False))
        w, gap = 150, 12
        total = len(labels) * w + (len(labels) - 1) * gap
        x = panel.centerx - total // 2
        y = panel.bottom - 50
        for label, icon_name, action, primary in labels:
            hud.text_button(self.screen, self.clicks, (x, y, w, 38), label, self.hud_bold, mouse,
                            action, icon_name=icon_name, primary=primary)
            x += w + gap

    # ─── Panneaux ───

    def _modal_blocker(self):
        """Tout l'écran capte la souris; un clic hors du panneau le ferme."""
        self.clicks.add(pygame.Rect(0, 0, self.screen_w, self.screen_h), self.close_overlay)

    def _draw_menu_overlay(self, mouse):
        self._modal_blocker()
        panel, y = hud.modal(self.screen, pygame.Rect(0, 0, self.screen_w, self.screen_h),
                             380, 470, "Menu", "La bataille est en pause")
        self.clicks.add(panel)
        entries = (("Reprendre", "play", self.resume, True),
                   ("Options", "options", self.toggle_options, False),
                   ("Aide et raccourcis", "help", self.toggle_help, False),
                   ("Relancer la bataille", "restart", self.restart, False),
                   ("Retour au menu", "menu", self.to_menu, False),
                   ("Quitter le jeu", "exit", self.quit, False))
        for label, icon_name, action, primary in entries:
            hud.text_button(self.screen, self.clicks, (panel.x + 40, y, panel.w - 80, 40), label,
                            self.hud_bold, mouse, action, icon_name=icon_name, primary=primary,
                            danger=icon_name == "exit")
            y += 50

    def _draw_help_overlay(self, mouse):
        self._modal_blocker()
        panel, y = hud.modal(self.screen, pygame.Rect(0, 0, self.screen_w, self.screen_h),
                             900, 620, "Aide et raccourcis")
        self.clicks.add(panel)
        col_w = (panel.w - 80) // 2
        kx, mx_ = panel.x + 30, panel.x + 50 + col_w
        ky = T.section_header(self.screen, "Clavier", kx, y, col_w)
        for keys, what in KEY_HELP:
            x = kx
            for i, k in enumerate(keys):
                if i:
                    x += 2 + T.text(self.screen, "/", self.top_small, (x + 2, ky + 3),
                                    T.MUTED).w + 2
                x += hud.keycap(self.screen, k, self.top_small, x, ky) + 2
            T.text(self.screen, what, self.hud_font, (kx + 150, ky + 1), T.PARCHMENT)
            ky += 25
        my = T.section_header(self.screen, "Souris", mx_, y, col_w)
        for gesture, what in MOUSE_HELP:
            T.text(self.screen, gesture, self.hud_bold, (mx_, my), T.GOLD_BRIGHT)
            T.text(self.screen, what, self.hud_font, (mx_, my + 18), T.PARCHMENT)
            my += 44
        my = T.section_header(self.screen, "Astuces", mx_, my + 6, col_w)
        for tip in ("Survolez un bouton pour voir sa touche.",
                    "Vos choix (armées, carte, affichage) sont gardés",
                    "d'une partie à l'autre.",
                    "La vidéo rejoue toute la bataille en vue globale,",
                    "sans ralentir le jeu."):
            T.text(self.screen, tip, self.hud_font, (mx_, my), T.PARCHMENT_DIM)
            my += 19
        hud.text_button(self.screen, self.clicks, (panel.centerx - 80, panel.bottom - 54, 160, 38),
                        "Fermer", self.hud_bold, mouse, self.close_overlay, icon_name="close")

    def _draw_options_overlay(self, mouse):
        self._modal_blocker()
        prefs = self.settings.section("battle")
        video = self.settings.section("video")
        panel, y = hud.modal(self.screen, pygame.Rect(0, 0, self.screen_w, self.screen_h),
                             760, 600, "Options", "Enregistrées automatiquement")
        self.clicks.add(panel)
        s, f, fb = self.screen, self.hud_font, self.hud_bold
        x0, w = panel.x + 34, panel.w - 68
        label_w = 190

        def row(label, y):
            T.text(s, label, f, (x0, y + 3), T.PARCHMENT_DIM)
            return x0 + label_w

        y = T.section_header(s, "Affichage", x0, y, w)
        x = x0
        for label, attr, action in (("Lignes de ciblage", "show_lines", self.toggle_lines),
                                    ("Intentions", "show_intents", self.toggle_intents),
                                    ("Mini-carte", "show_minimap", self.toggle_minimap),
                                    ("Légende du terrain", "show_terrain_legend",
                                     self.toggle_legend)):
            x += hud.checkbox(s, self.clicks, x, y, label, getattr(self, attr), f, mouse,
                              action) + 22
        y += 40

        y = T.section_header(s, "Caméra", x0, y, w)
        hud.checkbox(s, self.clicks, x0, y, "Défilement quand la souris touche le bord",
                     prefs["edge_scroll"], f, mouse,
                     lambda: self.settings.set("battle", "edge_scroll", not prefs["edge_scroll"]))
        y += 32
        hud.choice(s, self.clicks, row("Vitesse de défilement", y), y, CAMERA_SPEEDS,
                   prefs["camera_speed"], f, mouse,
                   lambda v: self.settings.set("battle", "camera_speed", v))
        y += 42

        y = T.section_header(s, "Bataille", x0, y, w)
        hud.choice(s, self.clicks, row("Vitesse", y), y,
                   [(k, SPEEDS[k][1]) for k in ("normal", "fast", "faster")], self.speed, f,
                   mouse, self._set_speed)
        y += 32
        hud.checkbox(s, self.clicks, x0, y, "Attendre avant de lancer une nouvelle bataille",
                     prefs["start_paused"], f, mouse,
                     lambda: self.settings.set("battle", "start_paused", not prefs["start_paused"]))
        y += 42

        y = T.section_header(s, "Vidéo (vue globale)", x0, y, w)
        hud.choice(s, self.clicks, row("Définition", y), y,
                   (("720p", "720p"), ("1080p", "1080p")), video["resolution"], f, mouse,
                   lambda v: self.settings.set("video", "resolution", v))
        y += 32
        hud.choice(s, self.clicks, row("Images par seconde", y), y, ((24, "24"), (30, "30")),
                   video["fps"], f, mouse, lambda v: self.settings.set("video", "fps", v))
        y += 32
        hud.choice(s, self.clicks, row("Durée d'un round", y), y,
                   ((0.5, "0,5 s"), (1.0, "1 s"), (1.5, "1,5 s")), video["seconds_per_round"],
                   f, mouse, lambda v: self.settings.set("video", "seconds_per_round", v))
        y += 34
        import video_export
        folder = video_export.output_dir()
        T.text(s, f"Dossier : {folder}", self.top_small, (x0, y + 4), T.MUTED)
        hud.icon_button(s, self.clicks, (panel.right - 64, y, 28, 26), "folder", mouse,
                        lambda: _open_folder(os.path.join(folder, ".")), "Ouvrir le dossier")
        T.text(s, video_export.encoder_label(), self.top_small, (x0, y + 22), T.MUTED)
        hud.text_button(s, self.clicks, (panel.centerx - 80, panel.bottom - 54, 160, 38),
                        "Fermer", fb, mouse, self.close_overlay, icon_name="close")

    def _hovered_unit(self):
        """Unité sous la souris (hors HUD et mini-carte) et position souris."""
        hmx, hmy = pygame.mouse.get_pos()
        if hmy >= self.view_h or (self.show_minimap and self.minimap.rect.collidepoint(hmx, hmy)):
            return None, hmx, hmy
        wmx, wmy = ui.screen_to_world(hmx, hmy, self.cam_x, self.cam_y, self.zoom)
        return ui.unit_at(self.battle, wmx, wmy, self.cell_size), hmx, hmy

    def _draw_world(self, now, hovered):
        """Terrain, unités et effets, dans la surface de vue si zoomé."""
        real_screen = self.screen
        view_w = int(self.screen_w / self.zoom) + 1
        view_h = int(self.view_h / self.zoom) + 1

        # Décalage caméra (plus la secousse éventuelle)
        ox, oy = int(-self.cam_x), int(-self.cam_y)
        if self.screen_shake > 0.25:
            ox += int(round(math.sin(now * 0.07) * self.screen_shake))
            oy += int(round(math.cos(now * 0.11) * self.screen_shake * 0.6))

        # Le fond n'est utile que là où le décor ne couvre pas la vue: sur
        # une grande carte il la couvre entièrement, et remplir 8 millions de
        # pixels par image pour les réécrire aussitôt coûtait 2 ms.
        covered = (ox <= 0 and oy <= 0
                   and self.world_w + ox >= view_w and self.world_h + oy >= view_h)
        surf = real_screen
        if self.zoom != 1.0:
            size = (view_w, view_h)
            if self.world_view is None or self.world_view.get_size() != size:
                self.world_view = pygame.Surface(size)
            surf = self.world_view
        elif not covered:
            real_screen.fill(self.world_bg)
        if surf is not real_screen and not covered:
            # La surface de vue est entièrement repeinte à chaque image: seules
            # les bandes que la carte (opaque) ne couvre pas ont besoin du fond
            # — dézoomé, remplir toute la vue coûtait près de 2 ms par image.
            self._fill_outside_map(surf, ox, oy, view_w, view_h)

        # Clipper le rendu monde pour ne pas déborder sur le HUD
        surf.set_clip(pygame.Rect(0, 0, view_w, view_h))
        surf.blit(self.grid_surface, (ox, oy))
        if self.show_lines:
            self._draw_target_lines(surf, ox, oy)
        if self.show_intents:
            R.draw_intents(surf, self.battle, self.cell_size, ox, oy)
        if hovered is not None and hovered.is_alive:
            self._draw_move_overlay(surf, hovered, ox, oy)
        # Décalques au sol et animations de mort (sous les vivants)
        self.fxr.draw_ground(surf, self.battle, ox, oy, view_w, view_h, self.move_anim_progress)
        # Incendies: sous les unités, au-dessus du sol
        self.fxr.draw_fires(surf, self.battle, ox, oy, view_w, view_h, now)
        self._draw_units(surf, ox, oy, hovered, view_w, view_h)
        # Effets en surplomb: lames, projectiles, sorts, particules
        self.fxr.draw_overlay(surf, self.battle, ox, oy, view_w, view_h, now)
        surf.set_clip(None)

        if surf is not real_screen:
            size = (int(surf.get_width() * self.zoom), int(surf.get_height() * self.zoom))
            # Surface d'arrivée gardée d'une image à l'autre: une surface
            # plein écran allouée puis jetée à chaque image, c'est inutile
            if self._scaled_view is None or self._scaled_view.get_size() != size:
                self._scaled_view = pygame.Surface(size, 0, surf)
            scaled = pygame.transform.scale(surf, size, self._scaled_view)
            real_screen.set_clip(pygame.Rect(0, 0, self.screen_w, self.view_h))
            real_screen.blit(scaled, (0, 0))
            real_screen.set_clip(None)

    def _fill_outside_map(self, surf, ox, oy, view_w, view_h):
        """Fond du monde sur les bandes de la vue hors de la carte posée en
        (ox, oy)."""
        mw, mh = self.grid_surface.get_size()
        x0, y0, x1, y1 = ox, oy, ox + mw, oy + mh
        if y0 > 0:
            surf.fill(self.world_bg, (0, 0, view_w, y0))
        if y1 < view_h:
            surf.fill(self.world_bg, (0, y1, view_w, view_h - y1))
        top, bottom = max(0, y0), min(view_h, y1)
        if bottom > top:
            if x0 > 0:
                surf.fill(self.world_bg, (0, top, x0, bottom - top))
            if x1 < view_w:
                surf.fill(self.world_bg, (x1, top, view_w - x1, bottom - top))

    def _draw_move_overlay(self, surf, u, ox, oy):
        """Au survol: cases où l'unité peut s'arrêter au prochain round
        (mêmes règles que le moteur) et chemin réellement suivi ce round.
        Utile pour lire l'IA et repérer un déplacement aberrant."""
        cs = self.cell_size
        key = (id(u), self.battle.round, u.position, u.vitesse)
        if getattr(self, '_reach_key', None) != key:
            self._reach_key = key
            # Ancres atteignables → toutes les cases que l'empreinte couvrirait
            uw, uh = _unit_dims(u)
            cells = {(x + i, y + j)
                     for x, y in self.battle.battlefield.reachable_cells(u, self.battle)
                     for i in range(uw) for j in range(uh)}
            # Le calque ne dépend que des cases: construit une fois, pas à
            # chaque image tant que la souris reste sur l'unité
            self._reach_layer = None
            if cells:
                xs = [c[0] for c in cells]
                ys = [c[1] for c in cells]
                x0, y0 = min(xs), min(ys)
                layer = pygame.Surface(((max(xs) - x0 + 1) * cs, (max(ys) - y0 + 1) * cs),
                                       pygame.SRCALPHA)
                for (x, y) in cells:
                    r = pygame.Rect((x - x0) * cs, (y - y0) * cs, cs, cs)
                    layer.fill(_REACH_FILL, r)
                    pygame.draw.rect(layer, _REACH_EDGE, r, 1)
                self._reach_layer = (layer, x0 * cs, y0 * cs)
        if self._reach_layer is not None:
            layer, lx, ly = self._reach_layer
            surf.blit(layer, (lx + ox, ly + oy))
        path = getattr(u, '_move_path', None)
        if path and len(path) > 1:
            uw, uh = _unit_dims(u)
            pts = [(x * cs + (uw * cs) // 2 + ox, y * cs + (uh * cs) // 2 + oy)
                   for x, y in path]
            pygame.draw.lines(surf, _PATH_COLOR, False, pts, 2)
            for p in pts[:-1]:
                pygame.draw.circle(surf, _PATH_COLOR, p, max(2, cs // 10))

    def _draw_target_lines(self, surf, ox, oy):
        """Lignes de ciblage, couleur selon le type d'attaque."""
        cs = self.cell_size
        bf = self.battle.battlefield
        vx0, vy0, vx1, vy1 = self._world_view_rect(ox, oy, 0)
        for att, tgt in self.battle.visual_effects['target_indicators']:
            if not (att.is_alive and tgt.is_alive):
                continue
            # Trait entièrement hors champ: rien à tracer
            ax, ay = att.position
            tx, ty = tgt.position
            if (max(ax, tx) * cs < vx0 or min(ax, tx) * cs > vx1
                    or max(ay, ty) * cs < vy0 or min(ay, ty) * cs > vy1):
                continue
            if bf.manhattan_distance(att.position, tgt.position) > att._max_range:
                continue
            # Pas de ligne de visée à travers un mur/porte fermée
            if att.attack_type == "ranged" and not bf.has_line_of_fire(att, tgt):
                continue
            sp = (att.position[0] * cs + cs // 2 + ox, att.position[1] * cs + cs // 2 + oy)
            ep = (tgt.position[0] * cs + cs // 2 + ox, tgt.position[1] * cs + cs // 2 + oy)
            color = _TARGET_LINE_COLORS.get(att.attack_type, _TARGET_LINE_MELEE)
            pygame.draw.line(surf, color, sp, ep, 1)

    @property
    def apparent_cs(self):
        """Taille d'une case en pixels D'ÉCRAN (le monde est dessiné à la
        taille de case puis mis à l'échelle du zoom)."""
        return int(self.cell_size * self.zoom)

    def _world_view_rect(self, ox, oy, margin):
        """Rectangle du monde (en pixels) réellement visible, élargi de
        `margin`. Tout ce qui tombe dehors n'a pas à être dessiné: sur une
        grande carte, les neuf dixièmes de l'armée sont hors champ."""
        vx0, vy0 = -ox - margin, -oy - margin
        return (vx0, vy0,
                vx0 + int(self.screen_w / self.zoom) + 1 + 2 * margin,
                vy0 + int(self.view_h / self.zoom) + 1 + 2 * margin)

    def _group_colors(self):
        """Une armée articulée en plusieurs groupes: chacun reçoit une
        pastille de couleur. On ne se sert pas de la couleur de faction:
        deux groupes de la même faction doivent rester distinguables.

        Recalculé seulement quand la composition change: c'est un balayage
        des deux armées, et il tombait à chaque image."""
        key = (len(self.battle.army1), len(self.battle.army2), self.battle.round)
        if getattr(self, '_group_colors_key', None) == key:
            return self._group_colors_cache
        colors = [{}, {}]
        for side_i, army in enumerate((self.battle.army1, self.battle.army2)):
            seen = []
            for u in army:
                if u.contingent not in seen:
                    seen.append(u.contingent)
            for gi, name in enumerate(seen):
                colors[side_i][name] = R.GROUP_PIPS[gi % len(R.GROUP_PIPS)]
        self._group_colors_key, self._group_colors_cache = key, colors
        return colors

    # Marge de culling: une unité juste hors cadre peut encore faire dépasser
    # son nom, sa barre de PV ou un texte flottant dans le champ.
    CULL_MARGIN = 96

    def _draw_units(self, surf, ox, oy, hovered, view_w, view_h):
        battle = self.battle
        tick_time = pygame.time.get_ticks()
        army1_ids = battle.army_ids(battle.army1)
        group_colors = self._group_colors()
        multi_contingent = (len(group_colors[0]) > 1, len(group_colors[1]) > 1)
        cs = self.cell_size
        m = self.CULL_MARGIN
        vx0, vy0 = -ox - m, -oy - m
        vx1, vy1 = vx0 + view_w + 2 * m, vy0 + view_h + 2 * m
        drawn = set()   # éviter de dessiner deux fois les grosses unités
        for u in battle.army1 + battle.army2:
            if u.position is None or id(u) in drawn:
                continue
            drawn.add(id(u))
            # Hors champ: on ne dessine pas. Le test porte sur la position de
            # DÉPART comme sur celle d'arrivée — une unité qui entre dans le
            # cadre doit apparaître dès le début de son animation.
            # L'empreinte compte, pas seulement l'ancre: une unité 2×4 dont
            # l'ancre sort par le haut a encore son bas dans le cadre.
            px, py = u.position
            qx, qy = getattr(u, '_prev_position', None) or (px, py)
            uw, uh = _unit_dims(u)
            if ((max(px, qx) + uw) * cs < vx0 or min(px, qx) * cs > vx1
                    or (max(py, qy) + uh) * cs < vy0 or min(py, qy) * cs > vy1):
                continue
            side = 0 if id(u) in army1_ids else 1
            pips = group_colors[side] if multi_contingent[side] else None
            self._draw_unit(surf, u, side, pips, ox, oy, tick_time, u is hovered)

    def _unit_center(self, u, uw, uh, ox, oy, tick_time):
        """Centre écran de l'unité: interpolation du mouvement, pas de
        marche, secousse d'impact et fente de corps-à-corps."""
        cs = self.cell_size
        x, y = u.position
        # Chaque unité a un léger décalage de départ et une vitesse propre
        # (déterministes par unité) → l'armée ne bouge plus en bloc robotique
        prev_x, prev_y = getattr(u, '_prev_position', u.position)
        # uid, pas id(): l'unité est une nouvelle copie à chaque round
        seed_u = u.uid % 9973
        is_moving = (prev_x != x or prev_y != y)
        if is_moving:
            delay_u = (seed_u % 11) / 11.0 * 0.22               # 0 → 0.22 de retard
            speed_u = 1.0 + ((seed_u // 11) % 7) / 7.0 * 0.25   # 1.0 → 1.25x
            t_u = max(0.0, min(1.0, (self.move_anim_progress - delay_u) * speed_u
                               / max(0.05, 1.0 - delay_u)))
        else:
            t_u = 1.0
        # Ease-out pour un mouvement plus naturel (rapide au début, lent à la fin)
        t_ease = 1.0 - (1.0 - t_u) * (1.0 - t_u)
        path = getattr(u, '_move_path', None)
        if is_moving and path and len(path) > 2 and path[-1] == (x, y):
            # Case par case: on suit le chemin réellement parcouru (contour
            # d'un bois, d'un allié) au lieu d'un trait droit qui traversait
            # tout ce qui se trouvait entre le départ et l'arrivée
            fx, fy = _along_path(path, t_ease)
        else:
            path = None
            fx, fy = prev_x + (x - prev_x) * t_ease, prev_y + (y - prev_y) * t_ease
        cx = int(fx * cs + (uw * cs) // 2) + ox
        cy = int(fy * cs + (uh * cs) // 2) + oy

        # Balancement de marche: un "pas" par case parcourue, amorti en fin
        if is_moving and t_u < 1.0 and u.is_alive and not u.fleeing:
            steps = (len(path) - 1) if path else abs(x - prev_x) + abs(y - prev_y)
            steps = max(1, min(6, steps))
            cy -= int(abs(math.sin(t_u * math.pi * steps)) * cs * 0.07 * (1.0 - t_u * 0.5))

        # Secousse d'impact: l'unité tremble brièvement quand elle encaisse
        hit_flash = getattr(u, '_hit_flash', 0)
        if (hit_flash > 0 and u.is_alive
                and self.round_frame >= getattr(u, '_hit_flash_delay', 0)):
            amp = max(1.0, cs / 14.0) * (hit_flash / 12.0)
            cx += int(math.sin(tick_time * 0.09 + seed_u) * amp)
            cy += int(math.cos(tick_time * 0.11 + seed_u) * amp * 0.6)

        # Fente de corps-à-corps: aller-retour de 35 % vers la cible sur
        # 20 images (sin donne 0→1→0 sur [0, pi])
        lunge_target = getattr(u, '_lunge_target', None)
        lunge_timer = getattr(u, '_lunge_timer', 0)
        if lunge_target and lunge_timer > 0 and u.is_alive:
            amount = math.sin((1.0 - lunge_timer / 20) * math.pi) * 0.35
            tx = lunge_target[0] * cs + cs // 2 + ox
            ty = lunge_target[1] * cs + cs // 2 + oy
            cx = int(cx + (tx - cx) * amount)
            cy = int(cy + (ty - cy) * amount)
        return cx, cy

    def _draw_unit(self, surf, u, side, pip_colors, ox, oy, tick_time, is_hovered):
        cs = self.cell_size
        # Taille APPARENTE de la case à l'écran: c'est elle qui décide du
        # niveau de détail. Zoomé en arrière, un nom de cinq lettres et une
        # rangée de pastilles de moral ne sont plus lisibles une fois la vue
        # réduite — et il y a alors quatre fois plus d'unités à l'image.
        acs = self.apparent_cs
        uw, uh = _unit_dims(u)
        cx, cy = self._unit_center(u, uw, uh, ox, oy, tick_time)
        ur = max(3, min(uw, uh) * cs // 2 - 4)
        team_color = (60, 120, 220) if side == 0 else (220, 60, 60)

        if u.fear_aura > 0 and u.is_alive:
            self._draw_fear_aura(surf, u, cx, cy, ur, (tick_time // 200) % 4)
        if (acs >= 16 and u.is_alive and u.current_target
                and u.current_target.is_alive and not u.fleeing):
            self._draw_attack_symbol(surf, u.attack_type, cx, cy - ur - 10, max(3, cs // 8))
        if u.is_alive:
            self._draw_live_body(surf, u, cx, cy, ur, uw, uh, team_color, pip_colors,
                                 is_hovered, acs)
            self._draw_hp_bar(surf, u, cx, cy - ur - 5, max(4, uw * cs - 8))
            if acs >= 20:
                self._draw_name_and_morale(surf, u, cx, cy, ur)
        else:
            self._draw_corpse(surf, cx, cy, ur, team_color)
        if u.status_text and acs >= 16:
            st = R.label(self.small_font, u.status_text, (255, 80, 80))
            surf.blit(st, (cx - st.get_width() // 2, cy - ur - 18))
        if acs >= 16:
            self._draw_floating_texts(surf, u, cx, cy, ur)

    def _draw_fear_aura(self, surf, u, cx, cy, ur, pulse):
        color = ((220, 40, 40) if u.fear_aura == 1 else (240, 140, 0) if u.fear_aura == 2
                 else (255, 50, 150))
        for i in range(6):
            rad = math.radians(i * 60 + pulse * 20)
            pygame.draw.circle(surf, color, (cx + int((ur + 8) * math.cos(rad)),
                                             cy + int((ur + 8) * math.sin(rad))),
                               max(1, 3 * self.cell_size // 32))

    @staticmethod
    def _draw_attack_symbol(surf, attack_type, cx, sy, s):
        """Au-dessus de l'unité: ✦ violet = sort, → bleu = tir,
        | jaune = allonge, X rouge = corps-à-corps."""
        line = pygame.draw.line
        if attack_type == "spell":
            c = (180, 80, 255)
            line(surf, c, (cx, sy - s), (cx, sy + s), 2)
            line(surf, c, (cx - s, sy), (cx + s, sy), 2)
            line(surf, c, (cx - s + 1, sy - s + 1), (cx + s - 1, sy + s - 1), 1)
            line(surf, c, (cx + s - 1, sy - s + 1), (cx - s + 1, sy + s - 1), 1)
        elif attack_type == "ranged":
            c = (80, 160, 255)
            line(surf, c, (cx - s, sy), (cx + s, sy), 2)
            line(surf, c, (cx + s, sy), (cx + s - 3, sy - 3), 2)
            line(surf, c, (cx + s, sy), (cx + s - 3, sy + 3), 2)
        elif attack_type == "reach":
            c = (255, 200, 50)
            line(surf, c, (cx, sy + s), (cx, sy - s), 2)
            line(surf, c, (cx, sy - s), (cx - 2, sy - s + 3), 2)
            line(surf, c, (cx, sy - s), (cx + 2, sy - s + 3), 2)
        else:
            c = (220, 80, 80)
            line(surf, c, (cx - s, sy - s), (cx + s, sy + s), 2)
            line(surf, c, (cx + s, sy - s), (cx - s, sy + s), 2)

    def _draw_live_body(self, surf, u, cx, cy, ur, uw, uh, team_color, pip_colors,
                        is_hovered, acs):
        """Ombre, token (ou cercle), anneau d'équipe, orientation, survol,
        pastille de contingent et flash de dégâts.

        Les trois premiers ne dépendent que du type d'unité et du camp: ils
        sont assemblés une fois pour toutes (renderer.unit_body) et posés
        d'un seul blit."""
        cs = self.cell_size
        # Orientation de la figurine: celle de l'unité (toujours posée au
        # déploiement), à défaut l'est
        angle = ui.facing_angle(u)
        direction = unit_sprites.dir_index(angle) or 0
        body, half = R.unit_body((u.siege_engine, u.fleeing, u.token_name, u.color,
                                  R.unit_glyph(u), ur, uw, uh, cs, team_color, direction))
        surf.blit(body, (cx - half, cy - half))

        ring_r = ur + 2
        ring_w = max(2, cs // 8)
        # Chevron d'orientation: vers la cible, sinon vers la marche
        if acs >= 14 and not u.fleeing:
            ui.draw_facing(surf, cx, cy, ring_r, angle, team_color)
        if is_hovered:
            pygame.draw.circle(surf, (255, 240, 170), (cx, cy), ring_r + max(4, ring_w + 2), 2)

        # Pastille de contingent, seulement si l'équipe aligne plusieurs groupes
        if pip_colors is not None and acs >= 16:
            pip_c = pip_colors.get(u.contingent, (220, 220, 220))
            pip_r = max(2, cs // 9)
            ppx, ppy = cx + int(ring_r * 0.72), cy - int(ring_r * 0.72)
            pygame.draw.circle(surf, (15, 18, 22), (ppx, ppy), pip_r + 1)
            pygame.draw.circle(surf, pip_c, (ppx, ppy), pip_r)

        # Flash de dégâts (au moment PRÉCIS où le coup porte). Le décompte
        # se fait dans update(), avec les autres minuteries: sinon une unité
        # hors champ gardait son flash et le rejouait en entrant dans le cadre.
        hit_flash = getattr(u, '_hit_flash', 0)
        if hit_flash > 0 and self.round_frame >= getattr(u, '_hit_flash_delay', 0):
            fr = ur + 3
            surf.blit(R.hit_flash(fr, int(150 * (hit_flash / 12))), (cx - fr - 1, cy - fr - 1))

    @staticmethod
    def _draw_corpse(surf, cx, cy, ur, team_color):
        """Croix grise discrète au sol, cerclée de la couleur d'équipe éteinte."""
        gh = max(2, ur - 2)
        c = (70, 70, 70)
        pygame.draw.line(surf, c, (cx - gh, cy - gh), (cx + gh, cy + gh), 2)
        pygame.draw.line(surf, c, (cx + gh, cy - gh), (cx - gh, cy + gh), 2)
        dim = (team_color[0] // 3, team_color[1] // 3, team_color[2] // 3)
        pygame.draw.circle(surf, dim, (cx, cy), gh + 3, 1)

    @staticmethod
    def _draw_hp_bar(surf, u, cx, by, bw):
        """Barre de PV: vert → jaune → rouge."""
        hp_r = max(0, u.hp / u.max_hp) if u.max_hp > 0 else 0
        hp_c = (50, 190, 50) if hp_r > 0.6 else (220, 190, 40) if hp_r > 0.3 else (230, 70, 50)
        surf.blit(R.hp_bar(bw, int(bw * hp_r), hp_c), (cx - bw // 2 - 1, by - 1))

    def _draw_name_and_morale(self, surf, u, cx, cy, ur):
        cs = self.cell_size
        name = u.name[:5]
        name_txt = R.label(self.tiny_font, name, (220, 220, 220))
        # Ombre du texte pour la lisibilité sur tout terrain
        name_sh = R.label(self.tiny_font, name, (10, 10, 10))
        surf.blit(name_sh, (cx - name_txt.get_width() // 2 + 1, cy + ur + 3))
        surf.blit(name_txt, (cx - name_txt.get_width() // 2, cy + ur + 2))

        # Moral en pastilles (plus lisible que "M:3")
        morale = u.get_effective_morale()
        n_pips = max(0, min(6, morale))
        if not n_pips:
            return
        pip_r = max(1, cs // 14)
        color = ((100, 255, 100) if morale >= 3 else (255, 230, 90) if morale >= 2
                 else (255, 100, 100))
        pips = R.morale_pips(n_pips, pip_r, color)
        surf.blit(pips, (cx - pips.get_width() // 2, cy + ur + 13 - pip_r))

    def _draw_floating_texts(self, surf, u, cx, cy, ur):
        """Textes flottants de l'unité (vieillis dans update, pas ici)."""
        ft_oy = -ur - 6
        for ft in u.floating_texts:
            if not ft.is_visible():
                continue  # l'action n'a pas encore eu lieu
            prog = ft.get_progress()
            ts = R.label(self.tiny_font, ft.text, ft.color)
            R.blit_faded(surf, ts, (cx - ts.get_width() // 2,
                                    cy + ft_oy - int(prog * ft.duration / 4)),
                         255 - int(255 * prog))
            ft_oy -= 10

    def _draw_top_bar(self):
        """Bandeau supérieur: rapport de forces, round, postures et plans."""
        screen, sw, battle = self.screen, self.screen_w, self.battle
        screen.set_clip(None)
        a1c = sum(1 for u in battle.army1 if u.is_alive)
        a2c = sum(1 for u in battle.army2 if u.is_alive)

        top_h = 36
        screen.blit(T.vgradient(sw, top_h, (26, 28, 35), (12, 13, 17), 225), (0, 0))
        T.divider(screen, 0, sw, top_h - 1, T.GOLD_DIM, gem=False)

        # Barre "bras de fer" centrale (proportion des forces vivantes)
        bar_w = min(420, sw // 3)
        bar_x = (sw - bar_w) // 2
        bar_y, bar_h = 6, 12
        total = max(1, a1c + a2c)
        T.bar(screen, (bar_x, bar_y, bar_w, bar_h),
              [(a1c / total, T.TEAM[0]), (1 - a1c / total, T.TEAM[1])])
        mark_x = bar_x + int(bar_w * a1c / total)
        pygame.draw.line(screen, T.PARCHMENT, (mark_x, bar_y - 1), (mark_x, bar_y + bar_h), 2)
        T.diamond(screen, mark_x, bar_y - 2, 3, T.GOLD_BRIGHT)

        # Effectifs de part et d'autre de la barre
        T.text(screen, f"{a1c}", self.top_bold, (bar_x - 8, bar_y - 3),
               T.lighten(T.TEAM[0], 0.3), align="right")
        T.text(screen, f"{a2c}", self.top_bold, (bar_x + bar_w + 8, bar_y - 3),
               T.lighten(T.TEAM[1], 0.3))
        T.text(screen, ui.round_label(battle), T.font('serif', 12),
               (sw // 2, bar_y + bar_h + 1), T.GOLD, align="center")

        # Postures IA aux extrémités
        p1 = getattr(battle.commander1, 'posture', 'balanced')
        p2 = getattr(battle.commander2, 'posture', 'balanced')
        l1, pc1 = R.POSTURE_LABELS.get(p1, (p1, (180, 180, 180)))
        l2, pc2 = R.POSTURE_LABELS.get(p2, (p2, (180, 180, 180)))
        T.diamond(screen, 14, 11, 4, T.TEAM[0])
        T.text(screen, f"Armée 1 — {l1}", self.top_bold, (24, 3), pc1)
        T.diamond(screen, sw - 14, 11, 4, T.TEAM[1])
        T.text(screen, f"{l2} — Armée 2", self.top_bold, (sw - 24, 3), pc2, align="right")

        # Tempérament du général + manœuvre en cours: on comprend d'un coup
        # d'œil POURQUOI l'IA joue comme elle joue.
        for cmd, right in ((battle.commander1, False), (battle.commander2, True)):
            temper = getattr(cmd, 'temperament', None)
            if not temper:
                continue
            man = _MANEUVER_FR.get(getattr(cmd, 'maneuver', None))
            sub = temper if not man else f"{temper} · {man}"
            plan = getattr(cmd, 'plan', None)
            if plan is not None and plan.kind not in (None, "direct"):
                sub = f"{sub} · plan: {plan.label()}"
            if right:
                T.text(screen, sub, self.top_small, (sw - 24, 19), T.PARCHMENT_DIM, align="right")
            else:
                T.text(screen, sub, self.top_small, (24, 19), T.PARCHMENT_DIM)

    def _draw_banners(self):
        """Bannières d'événements (centre haut, fondu). Au plus 3, les plus
        récentes et sans doublon: au-delà, elles masquaient la bataille
        qu'elles commentent."""
        for eb in self.event_banners[:]:
            eb[2] -= 1
            if eb[2] <= 0:
                self.event_banners.remove(eb)
        shown, visible = set(), []
        for eb in reversed(self.event_banners):
            if eb[0] in shown:
                continue
            shown.add(eb[0])
            visible.append(eb)
            if len(visible) == 3:
                break
        y = 36 + 14   # sous le bandeau supérieur
        for eb in reversed(visible):
            fade = min(1.0, eb[2] / 40)
            bsurf = T.banner(eb[0], self.banner_font, tuple(eb[1]), int(255 * fade))
            self.screen.blit(bsurf, ((self.screen_w - bsurf.get_width()) // 2, y))
            y += bsurf.get_height() + 6

    def _draw_terrain_legend(self):
        """Légende du terrain (touche L), en bas à gauche: le haut de
        l'écran est aux bannières."""
        if not self.show_terrain_legend:
            return
        if self.terrain_legend is None:
            import terrain_render
            self.terrain_legend = terrain_render.legend_surface(self.battle.battlefield,
                                                                self.small_font)
        if self.terrain_legend is not None:
            self.screen.blit(self.terrain_legend,
                             (12, self.view_h - self.terrain_legend.get_height() - 12))

    def _draw_bottom_hud(self):
        if self.winner:
            status, color = "VICTOIRE : " + self.winner, (255, 215, 0)
        elif self.paused:
            status, color = "EN PAUSE", (255, 150, 110)
        else:
            status = f"LECTURE {SPEEDS.get(self.speed, SPEEDS['normal'])[1]}"
            color = (120, 220, 130) if self.speed == "normal" else (255, 220, 80)
        ui.draw_bottom_hud(self.screen, self.battle, self.screen_w, self.view_h, R.HUD_HEIGHT,
                           (self.hud_font, self.hud_bold), status, color, self.zoom,
                           None, HELP_TEXT, R.POSTURE_LABELS)
