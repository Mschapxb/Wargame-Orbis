"""Écran de bataille: boucle d'affichage, caméra, commandes et HUD.

`BattleView(battle, cell_size).run()` joue la bataille à l'écran et renvoie
"menu" (touche M) ou None (quitter). renderer.py garde les primitives de
dessin (terrain, structures, rapport); ce module les orchestre.

Chaque image: événements → caméra → simulation → dessin. Les commandes
clavier passent par la table KEY_ACTIONS (touche → méthode).
"""
import math

import pygame

import renderer as R
import theme as T
import ui
from fx_render import FxRenderer
from weather_render import WeatherFx

CAM_SPEED = 12            # pixels écran par image
EDGE_SCROLL_MARGIN = 30   # bande de défilement au bord de l'écran
WORLD_BG = (25, 40, 30)

HELP_TEXT = ("ESPACE pause · F/N vitesse · molette/+/- zoom · Tab carte · I intentions · "
             "T lignes · L terrain · R relancer · M menu · ESC quitter")

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

KEY_ACTIONS = {
    pygame.K_SPACE: "toggle_pause",
    pygame.K_f: "speed_fast",
    pygame.K_n: "speed_normal",
    pygame.K_p: "pause_on",
    pygame.K_ESCAPE: "quit",
    pygame.K_m: "to_menu",
    pygame.K_r: "restart",
    pygame.K_t: "toggle_lines",
    pygame.K_i: "toggle_intents",
    pygame.K_TAB: "toggle_minimap",
    pygame.K_PLUS: "zoom_in", pygame.K_KP_PLUS: "zoom_in", pygame.K_EQUALS: "zoom_in",
    pygame.K_MINUS: "zoom_out", pygame.K_KP_MINUS: "zoom_out",
    pygame.K_0: "zoom_reset", pygame.K_KP0: "zoom_reset",
    pygame.K_l: "toggle_legend",
    pygame.K_b: "toggle_fullscreen",
}

# Défilement continu (touches maintenues, flèches et ZQSD): (dx, dy)
SCROLL_KEYS = (
    ((pygame.K_LEFT, pygame.K_q), (-1, 0)),
    ((pygame.K_RIGHT, pygame.K_d), (1, 0)),
    ((pygame.K_UP, pygame.K_z), (0, -1)),
    ((pygame.K_DOWN, pygame.K_s), (0, 1)),
)


def _unit_dims(u):
    """Empreinte en cases selon la taille de l'unité."""
    if u.size <= 1:
        return 1, 1
    if u.size == 2:
        return 2, 2
    return 2, 4


class BattleView:
    def __init__(self, battle, cell_size):
        info = pygame.display.Info()
        self.screen_w = info.current_w
        self.screen_h = info.current_h
        self.view_h = self.screen_h - R.HUD_HEIGHT
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.NOFRAME)
        pygame.display.set_caption("Battle Simulator")
        self.clock = pygame.time.Clock()
        self.is_borderless = True   # False = plein écran exclusif (touche B)
        self.cell_size = cell_size

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

        self.paused = True
        self.speed = "normal"
        self.running = True
        self.return_action = None
        self.show_lines = True
        self.show_intents = True
        self.show_minimap = True
        self.show_terrain_legend = False

        # Zoom: le monde est dessiné à sa taille de case dans une surface de
        # vue (écran / zoom), puis mis à l'échelle — aucune coordonnée ne change.
        self.zoom = 1.0
        self.world_view = None
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
        self.battle = battle
        bf = battle.battlefield
        battle.cell_size = cs
        self.grid_surface = R.build_grid_surface(battle, cs)
        self.fxr.reset(bf.width * cs, bf.height * cs)
        self.wfx = WeatherFx(getattr(bf, 'weather', None))
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
        self.round_frame = 10 ** 6      # force la simulation du premier round
        self.screen_shake = 0.0         # secousse de caméra (impacts lourds)

        # Bannières d'événements dramatiques: [texte, couleur, images restantes]
        self.event_banners = []
        self.prev_gates_open = getattr(bf, 'gates_open', False)
        self.prev_intact_gates = sum(1 for h in bf.gate_hp.values() if h > 0)
        cmds = (battle.commander1, battle.commander2)
        self.prev_postures = [getattr(c, 'posture', 'balanced') for c in cmds]
        self.prev_maneuvers = [getattr(c, 'maneuver', None) for c in cmds]

    # ─── Boucle ───

    def run(self):
        while self.running:
            now = pygame.time.get_ticks()
            for event in pygame.event.get():
                self.handle_event(event)
            self.scroll_camera()
            self.update()
            self.draw(now)
            pygame.display.flip()
            self.clock.tick(60)
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

    def scroll_camera(self):
        """Défilement continu: touches maintenues et souris au bord."""
        step = CAM_SPEED / self.zoom
        keys = pygame.key.get_pressed()
        for key_group, (dx, dy) in SCROLL_KEYS:
            if any(keys[k] for k in key_group):
                self.cam_x += dx * step
                self.cam_y += dy * step
        mx, my = pygame.mouse.get_pos()
        if mx < EDGE_SCROLL_MARGIN:
            self.cam_x -= step
        elif mx > self.screen_w - EDGE_SCROLL_MARGIN:
            self.cam_x += step
        if my < EDGE_SCROLL_MARGIN:
            self.cam_y -= step
        elif self.view_h - EDGE_SCROLL_MARGIN < my < self.view_h:
            self.cam_y += step
        self.clamp_camera()

    # ─── Événements ───

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.quit()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 2:   # clic molette: glisser la vue
                self.dragging = True
                self.drag_start = event.pos
                self.drag_cam_start = (self.cam_x, self.cam_y)
            elif event.button == 1 and self.show_minimap:
                self.minimap_drag = self._minimap_jump(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self.dragging = False
            elif event.button == 1:
                self.minimap_drag = False
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                self.cam_x = self.drag_cam_start[0] + (self.drag_start[0] - event.pos[0]) / self.zoom
                self.cam_y = self.drag_cam_start[1] + (self.drag_start[1] - event.pos[1]) / self.zoom
                self.clamp_camera()
            elif self.minimap_drag:
                self._minimap_jump(event.pos)
        elif event.type == pygame.MOUSEWHEEL and event.y:
            wmx, wmy = pygame.mouse.get_pos()
            self.set_zoom(ui.next_zoom(self.zoom, 1 if event.y > 0 else -1), wmx, wmy)
        elif event.type == pygame.KEYDOWN:
            action = KEY_ACTIONS.get(event.key)
            if action:
                getattr(self, action)()

    # ─── Actions clavier (cf. KEY_ACTIONS) ───

    def toggle_pause(self):
        self.paused = not self.paused

    def speed_fast(self):
        self.speed, self.paused = "fast", False

    def speed_normal(self):
        self.speed, self.paused = "normal", False

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
        self._load_battle(Battle(*self._restart_args, **self._restart_kwargs))

    def toggle_lines(self):
        self.show_lines = not self.show_lines

    def toggle_intents(self):
        self.show_intents = not self.show_intents

    def toggle_minimap(self):
        self.show_minimap = not self.show_minimap

    def _zoom_centered(self, new_zoom):
        self.set_zoom(new_zoom, self.screen_w / 2, self.view_h / 2)

    def zoom_in(self):
        self._zoom_centered(ui.next_zoom(self.zoom, 1))

    def zoom_out(self):
        self._zoom_centered(ui.next_zoom(self.zoom, -1))

    def zoom_reset(self):
        self._zoom_centered(1.0)

    def toggle_legend(self):
        self.show_terrain_legend = not self.show_terrain_legend
        self.terrain_legend = None   # reconstruite au prochain affichage

    def toggle_fullscreen(self):
        """Bascule entre fenêtre sans bord et plein écran exclusif."""
        self.is_borderless = not self.is_borderless
        flags = pygame.NOFRAME if self.is_borderless else pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), flags)
        R.clear_token_cache()
        self.fxr._snap_cache.clear()
        self.grid_surface = R.build_grid_surface(self.battle, self.cell_size)

    # ─── Simulation ───

    def update(self):
        battle = self.battle
        if not self.paused and self.winner is None:
            # ── Cadence CONTINUE ──
            # Le round n'est plus « simuler, animer, puis attendre »: sa
            # durée est fixée en frames, le moteur y répartit toutes les
            # actions (cf. battle.T_*), et le round suivant enchaîne sans
            # temps mort. C'est ce qui donne la sensation de temps réel.
            frames = R.ROUND_FRAMES_FAST if self.speed == "fast" else R.ROUND_FRAMES_NORMAL
            if self.round_frame >= frames:
                self._simulate_round(frames)
            else:
                self.round_frame += 1
            # Le déplacement occupe la première moitié du round et se
            # termine avant que l'échange général ne batte son plein.
            self.move_anim_progress = min(1.0, self.round_frame / max(1.0, frames * R.MOVE_WINDOW))

        # Décompter les timers de lunge (seulement une fois l'instant venu)
        for u in battle.army1 + battle.army2:
            if u._lunge_timer > 0 and self.round_frame >= getattr(u, '_lunge_delay', 0):
                u._lunge_timer -= 1

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

    def _simulate_round(self, frames):
        battle = self.battle
        # Ce que la destruction a changé au round précédent est appliqué en
        # entier avant d'en simuler un nouveau.
        R.apply_destruction(self.grid_surface, battle, self.cell_size, 10 ** 6)
        self.round_frame = 0
        battle.fx_frames_per_round = frames
        battle.simulate_round()
        # Rafraîchir la grille si siège (portes détruites)
        if battle.battlefield.gate_hp:
            self.gate_state = R.repaint_gates(self.grid_surface, battle, self.cell_size,
                                              self.gate_state)
        self._detect_events()
        result = battle.is_battle_over()
        if result:
            self.winner = result
            self.battle_report = battle.get_battle_report()

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
        hovered, hmx, hmy = self._hovered_unit()
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
        if self.paused and self.winner is None and not self.battle_report:
            self._draw_pause()
        self._draw_bottom_hud()
        if self.battle_report:
            R.draw_battle_report(screen, self.battle_report, self.screen_w, self.view_h,
                                 self.small_font, self.tiny_font)
        # Fiche de l'unité survolée (par-dessus tout)
        if hovered is not None and not self.battle_report:
            ui.draw_unit_card(screen, hovered, self.battle, hmx, hmy, self.card_font,
                              pygame.Rect(0, 30, self.screen_w, self.view_h - 30))

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
        real_screen.fill(WORLD_BG)
        surf = real_screen
        if self.zoom != 1.0:
            size = (int(self.screen_w / self.zoom) + 1, int(self.view_h / self.zoom) + 1)
            if self.world_view is None or self.world_view.get_size() != size:
                self.world_view = pygame.Surface(size)
            self.world_view.fill(WORLD_BG)
            surf = self.world_view
        view_w = int(self.screen_w / self.zoom) + 1
        view_h = int(self.view_h / self.zoom) + 1

        # Décalage caméra (plus la secousse éventuelle)
        ox, oy = int(-self.cam_x), int(-self.cam_y)
        if self.screen_shake > 0.25:
            ox += int(round(math.sin(now * 0.07) * self.screen_shake))
            oy += int(round(math.cos(now * 0.11) * self.screen_shake * 0.6))

        # Clipper le rendu monde pour ne pas déborder sur le HUD
        surf.set_clip(pygame.Rect(0, 0, view_w, view_h))
        surf.blit(self.grid_surface, (ox, oy))
        if self.show_lines:
            self._draw_target_lines(surf, ox, oy)
        if self.show_intents:
            R.draw_intents(surf, self.battle, self.cell_size, ox, oy)
        # Décalques au sol et animations de mort (sous les vivants)
        self.fxr.draw_ground(surf, self.battle, ox, oy, view_w, view_h, self.move_anim_progress)
        # Incendies: sous les unités, au-dessus du sol
        self.fxr.draw_fires(surf, self.battle, ox, oy, view_w, view_h, now)
        self._draw_units(surf, ox, oy, hovered)
        # Effets en surplomb: lames, projectiles, sorts, particules
        self.fxr.draw_overlay(surf, self.battle, ox, oy, view_w, view_h, now)
        surf.set_clip(None)

        if surf is not real_screen:
            scaled = pygame.transform.scale(surf, (int(surf.get_width() * self.zoom),
                                                   int(surf.get_height() * self.zoom)))
            real_screen.set_clip(pygame.Rect(0, 0, self.screen_w, self.view_h))
            real_screen.blit(scaled, (0, 0))
            real_screen.set_clip(None)

    def _draw_target_lines(self, surf, ox, oy):
        """Lignes de ciblage, couleur selon le type d'attaque."""
        cs = self.cell_size
        bf = self.battle.battlefield
        for att, tgt in self.battle.visual_effects['target_indicators']:
            if not (att.is_alive and tgt.is_alive):
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

    def _group_colors(self):
        """Une armée articulée en plusieurs groupes: chacun reçoit une
        pastille de couleur. On ne se sert pas de la couleur de faction:
        deux groupes de la même faction doivent rester distinguables."""
        colors = [{}, {}]
        for side_i, army in enumerate((self.battle.army1, self.battle.army2)):
            seen = []
            for u in army:
                if u.contingent not in seen:
                    seen.append(u.contingent)
            for gi, name in enumerate(seen):
                colors[side_i][name] = R.GROUP_PIPS[gi % len(R.GROUP_PIPS)]
        return colors

    def _draw_units(self, surf, ox, oy, hovered):
        battle = self.battle
        tick_time = pygame.time.get_ticks()
        army1_ids = set(id(u) for u in battle.army1)
        group_colors = self._group_colors()
        multi_contingent = (len(group_colors[0]) > 1, len(group_colors[1]) > 1)
        drawn = set()   # éviter de dessiner deux fois les grosses unités
        for u in battle.army1 + battle.army2:
            if u.position is None or id(u) in drawn:
                continue
            drawn.add(id(u))
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
        seed_u = id(u) % 9973
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
        cx = int((prev_x + (x - prev_x) * t_ease) * cs + (uw * cs) // 2) + ox
        cy = int((prev_y + (y - prev_y) * t_ease) * cs + (uh * cs) // 2) + oy

        # Balancement de marche: un "pas" par case parcourue, amorti en fin
        if is_moving and t_u < 1.0 and u.is_alive and not u.fleeing:
            steps = max(1, min(4, abs(x - prev_x) + abs(y - prev_y)))
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
        uw, uh = _unit_dims(u)
        cx, cy = self._unit_center(u, uw, uh, ox, oy, tick_time)
        ur = max(3, min(uw, uh) * cs // 2 - 4)
        team_color = (60, 120, 220) if side == 0 else (220, 60, 60)

        if u.fear_aura > 0 and u.is_alive:
            self._draw_fear_aura(surf, u, cx, cy, ur, (tick_time // 200) % 4)
        if u.is_alive and u.current_target and u.current_target.is_alive and not u.fleeing:
            self._draw_attack_symbol(surf, u.attack_type, cx, cy - ur - 10, max(3, cs // 8))
        if u.is_alive:
            self._draw_live_body(surf, u, cx, cy, ur, uw, uh, team_color, pip_colors, is_hovered)
            self._draw_hp_bar(surf, u, cx, cy - ur - 5, max(4, uw * cs - 8))
            if cs >= 20:
                self._draw_name_and_morale(surf, u, cx, cy, ur)
        else:
            self._draw_corpse(surf, cx, cy, ur, team_color)
        if u.status_text and cs >= 16:
            st = self.small_font.render(u.status_text, True, (255, 80, 80))
            surf.blit(st, (cx - st.get_width() // 2, cy - ur - 18))
        if cs >= 16:
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

    def _draw_live_body(self, surf, u, cx, cy, ur, uw, uh, team_color, pip_colors, is_hovered):
        """Ombre, token (ou cercle), anneau d'équipe, orientation, survol,
        pastille de contingent et flash de dégâts."""
        cs = self.cell_size
        sh_w, sh_h = max(4, ur * 2), max(2, ur // 2 + 2)
        surf.blit(R.get_shadow(sh_w, sh_h), (cx - sh_w // 2, cy + ur - sh_h // 2))

        if u.fleeing:
            pygame.draw.circle(surf, (255, 140, 0), (cx, cy), ur)
        else:
            token_size = min(uw, uh) * cs - 4
            token_img = R.load_token(u.token_name, token_size) if u.token_name else None
            if token_img:
                surf.blit(token_img, (cx - token_size // 2, cy - token_size // 2))
            else:
                pygame.draw.circle(surf, u.color, (cx, cy), ur)
                rc = ((255, 255, 255) if u.role == "front" else (128, 128, 128) if u.role == "mid"
                      else (0, 0, 0))
                pygame.draw.circle(surf, rc, (cx, cy), max(1, 3 * cs // 32))

        # Contour d'équipe PAR-DESSUS (outline épaisse)
        ring_r = ur + 2
        ring_w = max(2, cs // 8)
        pygame.draw.circle(surf, team_color, (cx, cy), ring_r, ring_w)
        # Chevron d'orientation: vers la cible, sinon vers la marche
        if cs >= 14 and not u.fleeing:
            ui.draw_facing(surf, cx, cy, ring_r, ui.facing_angle(u), team_color)
        if is_hovered:
            pygame.draw.circle(surf, (255, 240, 170), (cx, cy), ring_r + max(4, ring_w + 2), 2)

        # Pastille de contingent, seulement si l'équipe aligne plusieurs groupes
        if pip_colors is not None and cs >= 16:
            pip_c = pip_colors.get(u.contingent, (220, 220, 220))
            pip_r = max(2, cs // 9)
            ppx, ppy = cx + int(ring_r * 0.72), cy - int(ring_r * 0.72)
            pygame.draw.circle(surf, (15, 18, 22), (ppx, ppy), pip_r + 1)
            pygame.draw.circle(surf, pip_c, (ppx, ppy), pip_r)

        # Flash de dégâts (au moment PRÉCIS où le coup porte)
        hit_flash = getattr(u, '_hit_flash', 0)
        if hit_flash > 0 and self.round_frame >= getattr(u, '_hit_flash_delay', 0):
            u._hit_flash = hit_flash - 1
            fr = ur + 3
            fsurf = pygame.Surface((fr * 2 + 2, fr * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(fsurf, (255, 40, 40, int(150 * (hit_flash / 12))),
                               (fr + 1, fr + 1), fr)
            surf.blit(fsurf, (cx - fr - 1, cy - fr - 1))

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
        pygame.draw.rect(surf, (15, 15, 15), (cx - bw // 2 - 1, by - 1, bw + 2, 5))
        pygame.draw.rect(surf, (90, 25, 25), (cx - bw // 2, by, bw, 3))
        pygame.draw.rect(surf, hp_c, (cx - bw // 2, by, int(bw * hp_r), 3))

    def _draw_name_and_morale(self, surf, u, cx, cy, ur):
        cs = self.cell_size
        name_txt = self.tiny_font.render(u.name[:5], True, (220, 220, 220))
        # Ombre du texte pour la lisibilité sur tout terrain
        name_sh = self.tiny_font.render(u.name[:5], True, (10, 10, 10))
        surf.blit(name_sh, (cx - name_txt.get_width() // 2 + 1, cy + ur + 3))
        surf.blit(name_txt, (cx - name_txt.get_width() // 2, cy + ur + 2))

        # Moral en pastilles (plus lisible que "M:3")
        morale = u.get_effective_morale()
        n_pips = max(0, min(6, morale))
        pip_r = max(1, cs // 14)
        pip_gap = pip_r * 2 + 2
        total_w = n_pips * pip_gap - 2 if n_pips > 0 else 0
        color = ((100, 255, 100) if morale >= 3 else (255, 230, 90) if morale >= 2
                 else (255, 100, 100))
        for pi in range(n_pips):
            pygame.draw.circle(surf, color, (cx - total_w // 2 + pi * pip_gap + pip_r,
                                             cy + ur + 13), pip_r)

    def _draw_floating_texts(self, surf, u, cx, cy, ur):
        ft_oy = -ur - 6
        for ft in list(u.floating_texts):
            ft.age += 1
            if not ft.is_alive():
                u.floating_texts.remove(ft)
                continue
            if not ft.is_visible():
                continue  # l'action n'a pas encore eu lieu
            prog = ft.get_progress()
            ts = self.tiny_font.render(ft.text, True, ft.color)
            ts.set_alpha(255 - int(255 * prog))
            surf.blit(ts, (cx - ts.get_width() // 2, cy + ft_oy - int(prog * ft.duration / 4)))
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
        T.text(screen, f"Round {battle.round - 1}", T.font('serif', 12),
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

    def _draw_pause(self):
        screen = self.screen
        pt = T.gold_text("Pause", self.pause_font)
        pw, ph = max(260, pt.get_width() + 90), pt.get_height() + 48
        prect = pygame.Rect((self.screen_w - pw) // 2, (self.view_h - ph) // 2, pw, ph)
        T.glass(screen, prect, 215, 10)
        T.corner_marks(screen, prect, T.GOLD_DIM, 9)
        screen.blit(pt, (prect.centerx - pt.get_width() // 2, prect.y + 8))
        T.divider(screen, prect.x + 30, prect.right - 30, prect.y + 12 + pt.get_height())
        T.text(screen, "ESPACE pour reprendre", T.font('ui', 13),
               (prect.centerx, prect.bottom - 22), T.PARCHMENT_DIM, align="center")

    def _draw_bottom_hud(self):
        if self.winner:
            status, color = "VICTOIRE: " + self.winner, (255, 215, 0)
        elif self.paused:
            status, color = "PAUSE", (255, 130, 100)
        elif self.speed == "fast":
            status, color = ">> RAPIDE", (255, 220, 80)
        else:
            status, color = "> NORMAL", (110, 220, 110)
        ui.draw_bottom_hud(self.screen, self.battle, self.screen_w, self.view_h, R.HUD_HEIGHT,
                           (self.hud_font, self.hud_bold), status, color, self.zoom,
                           int(self.clock.get_fps()), HELP_TEXT, R.POSTURE_LABELS)
