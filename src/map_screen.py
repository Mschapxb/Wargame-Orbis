"""Écran « Champ de bataille »: le second écran du menu, après la
composition des armées.

On y choisit la carte, son thème, son relief, la météo et l'éventuel
avantage de terrain d'un camp, avec un APERÇU de la vraie carte — celle
qui sera jouée, déploiement des deux armées compris. « Nouvelle carte »
tire une autre graine; tout changement d'option régénère l'aperçu sur la
même graine.

L'aperçu et la bataille sont identiques parce que la graine voyage dans
`map_options['seed']` (cf. Battle.__init__): génération, météo tirée au
sort et déploiement se jouent sur cette graine.
"""
import random
import sys

import pygame

import maps as maps_mod
import siege_engines
import weather as weather_mod
import theme as T
from menu import (BTN_ACTIVE, BTN_HOVER, BTN_NORMAL, GOLD, TEXT, TEXT_BRIGHT, TEXT_DIM, draw_button, draw_text)

TEAM_COLORS = T.TEAM
_SEEDS = random.Random()          # jamais le random du moteur


# ═══════════════════════════════════════════════════════════════
#                   ÉTAT DE L'ÉCRAN (testable)
# ═══════════════════════════════════════════════════════════════

class MapSetup:
    """Choix de l'écran « Champ de bataille »; survit aux allers-retours
    avec l'écran des armées."""

    def __init__(self, map_name="Prairie"):
        self.map_name = map_name
        self.biome = "Prairie"
        self.relief = maps_mod.natural_relief_name(map_name)
        self.weather = weather_mod.CLEAR
        self.advantage = maps_mod.ADVANTAGE_NONE
        self.level = maps_mod.ADVANTAGE_LEVELS[0]
        self.fortification = maps_mod.FORTIFICATION_LEVELS[0]
        self.seed = _SEEDS.randrange(1, 1_000_000)

    def set_map(self, name):
        """Une nouvelle carte repart de son relief naturel."""
        if name != self.map_name:
            self.map_name = name
            if name in maps_mod.THEMED_MAPS:
                self.relief = maps_mod.natural_relief_name(name)

    def new_seed(self):
        old = self.seed
        while self.seed == old:
            self.seed = _SEEDS.randrange(1, 1_000_000)

    @property
    def advantage_allowed(self):
        return self.map_name not in maps_mod.SIEGE_MAPS

    def options(self):
        """map_options pour Battle (et pour le redémarrage R)."""
        opts = {'biome': self.biome, 'relief': self.relief,
                'weather': self.weather, 'seed': self.seed}
        if self.advantage_allowed and self.advantage != maps_mod.ADVANTAGE_NONE:
            opts['advantage'] = self.advantage
            opts['advantage_level'] = self.level
        if not self.advantage_allowed and self.fortification != maps_mod.FORTIFICATION_LEVELS[0]:
            opts['fortification'] = maps_mod.fortification_of({'fortification': self.fortification})
        return opts

    def key(self):
        """Ce qui change la carte: sert à ne régénérer l'aperçu qu'au besoin."""
        return (self.map_name, tuple(sorted(self.options().items())))


# ═══════════════════════════════════════════════════════════════
#                          APERÇU
# ═══════════════════════════════════════════════════════════════

def build_preview(army1, army2, setup, grid_w, grid_h, fit_w, fit_h):
    """(surface de l'aperçu, bataille générée). La bataille est construite
    exactement comme celle qui sera jouée (mêmes armées, même graine)."""
    from battle import Battle
    import renderer
    from weather_render import WeatherFx

    b = Battle(army1, army2, grid_w, grid_h, 8, map_name=setup.map_name,
               map_options=setup.options())
    cell = max(3, min(12, fit_w // grid_w, fit_h // grid_h))
    surf = renderer.build_grid_surface(b, cell)
    bf = b.battlefield
    for side, army in enumerate((b.army1, b.army2)):
        col = TEAM_COLORS[side]
        for u in army:
            w, h = bf.get_unit_dims(u)
            cx = u.position[0] * cell + w * cell / 2
            cy = u.position[1] * cell + h * cell / 2
            r = max(2, int(cell * 0.42 * max(w, h)))
            pygame.draw.circle(surf, (15, 15, 20), (int(cx), int(cy)), r + 1)
            pygame.draw.circle(surf, col, (int(cx), int(cy)), r)
    WeatherFx(bf.weather).draw(surf, surf.get_width(), surf.get_height())
    scale = min(fit_w / surf.get_width(), fit_h / surf.get_height(), 1.0)
    if scale < 1.0:
        surf = pygame.transform.smoothscale(
            surf, (max(1, int(surf.get_width() * scale)), max(1, int(surf.get_height() * scale))))
    return surf, b


def describe_setup(setup, battle):
    """Ligne de résumé sous l'aperçu (valeurs RÉSOLUES: relief et météo
    tirés au sort compris)."""
    theme = battle.battlefield.theme or {}
    parts = [f"Carte n° {setup.seed}", maps_mod.describe_options(setup.map_name, theme)]
    sky = battle.battlefield.weather
    parts.append(f"météo: {sky.label.lower()}")
    level = getattr(battle.battlefield, 'fortification', 1)
    if battle.battlefield.is_siege and level > 1:
        parts.append(f"défenses: niveau {level}")
    side, level = maps_mod.advantage_of(setup.options())
    if side:
        parts.append(f"avantage: armée {side} ({maps_mod.ADVANTAGE_LEVELS[level - 1].lower()})")
    return "   ·   ".join(parts)


# ═══════════════════════════════════════════════════════════════
#                          ÉCRAN
# ═══════════════════════════════════════════════════════════════

def run_map_screen(screen, screen_w, screen_h, army1, army2, setup, grid_size):
    """Boucle de l'écran. Retourne "launch" (COMBAT !) ou "back" (retour aux
    armées); `setup` est modifié en place. Quitter ferme le programme."""
    clock = pygame.time.Clock()
    body_font = T.font('ui', 14)
    small_font = T.font('ui', 12)
    label_font = T.font('title', 14)
    background = T.background(screen_w, screen_h)
    grid_w, grid_h = grid_size

    margin = 15
    rows_top = 62
    row_h = 32
    preview_top = rows_top + 4 * row_h + 8
    preview_rect = pygame.Rect(margin, preview_top, screen_w - 2 * margin,
                               max(80, screen_h - preview_top - 96))

    preview, preview_battle, preview_key = None, None, None

    while True:
        mouse_pos = pygame.mouse.get_pos()
        clicked = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked = True
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    return "back"
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return "launch"
                if event.key in (pygame.K_n, pygame.K_F5):
                    setup.new_seed()

        screen.blit(background, (0, 0))
        T.title(screen, "Champ de bataille", screen_w // 2, 8, 28)

        # Redéfinie à chaque image: elle lit mouse_pos/clicked de l'image en cours
        def choice_row(options, selected, x, y, min_w=70):
            for opt in options:
                is_sel = (opt == selected)
                rect = pygame.Rect(x, y, max(min_w, small_font.size(opt)[0] + 20), 26)
                if draw_button(screen, rect, opt, small_font, mouse_pos,  # noqa: B023
                               BTN_ACTIVE if is_sel else BTN_NORMAL,
                               (100, 180, 255) if is_sel else BTN_HOVER,
                               TEXT_BRIGHT if is_sel else TEXT) and clicked:  # noqa: B023
                    selected = opt
                if is_sel:
                    pygame.draw.rect(screen, GOLD, rect, 2, border_radius=4)
                x += rect.w + 6
            return selected, x

        def clipped_note(text, x, y):
            screen.set_clip(pygame.Rect(x, y, max(0, screen_w - x - margin), 26))
            draw_text(screen, text, small_font, (x, y + 6), TEXT_DIM)
            screen.set_clip(None)

        label_w = 84
        # ─── Carte ───
        y = rows_top
        T.text(screen, "Carte", label_font, (margin, y + 4), T.GOLD)
        new_map, x = choice_row(maps_mod.get_map_names(), setup.map_name, margin + label_w, y)
        setup.set_map(new_map)
        clipped_note(maps_mod.get_map_info(setup.map_name).get("description", ""), x + 10, y)

        # ─── Thème et relief ───
        y += row_h
        if setup.map_name in maps_mod.THEMED_MAPS:
            x = margin
            if setup.map_name not in maps_mod.OPEN_MAPS:
                T.text(screen, "Thème", label_font, (x, y + 4), T.GOLD)
                setup.biome, x = choice_row(maps_mod.BIOMES, setup.biome, x + label_w, y)
                x += 18
            T.text(screen, "Relief", label_font, (x, y + 4), T.GOLD)
            reliefs = list(maps_mod.RELIEFS) + [maps_mod.RANDOM_RELIEF]
            setup.relief, x = choice_row(reliefs, setup.relief, x + label_w, y)
        else:
            clipped_note("Relief fixe: le goulet et son torrent sont la carte.", margin, y)

        # ─── Météo ───
        y += row_h
        T.text(screen, "Météo", label_font, (margin, y + 4), T.GOLD)
        skies = list(weather_mod.WEATHERS) + [weather_mod.RANDOM_WEATHER]
        setup.weather, x = choice_row(skies, setup.weather, margin + label_w, y)
        sky_desc = weather_mod.DESCRIPTIONS.get(setup.weather, "Tirée au sort selon le biome.")
        if (setup.map_name in maps_mod.SIEGE_MAPS
                and setup.weather in (weather_mod.FOG, weather_mod.DUSK)):
            sky_desc += " Très dur pour l'assaillant d'un siège."
        clipped_note(sky_desc, x + 10, y)

        # ─── Avantage du terrain (bataille rangée) / Défenses (siège) ───
        y += row_h
        if setup.advantage_allowed:
            T.text(screen, "Avantage", label_font, (margin, y + 4), T.GOLD)
            setup.advantage, x = choice_row(list(maps_mod.ADVANTAGE_SIDES), setup.advantage,
                                            margin + label_w, y)
            if setup.advantage != maps_mod.ADVANTAGE_NONE:
                x += 18
                T.text(screen, "Intensité", label_font, (x, y + 4), T.GOLD)
                setup.level, x = choice_row(maps_mod.ADVANTAGE_LEVELS, setup.level,
                                            x + label_w, y)
                note = ("Hauteurs sous le front du camp favorisé."
                        if setup.level == maps_mod.ADVANTAGE_LEVELS[0] else
                        "Hauteurs plus étendues et bosquets de couverture aux ailes.")
            else:
                note = "Carte en miroir: aucun camp n'a meilleur terrain."
            clipped_note(note, x + 10, y)
        else:
            # Siège: la forteresse est déjà l'avantage du défenseur; la rangée
            # sert à choisir son niveau de fortification.
            T.text(screen, "Défenses", label_font, (margin, y + 4), T.GOLD)
            setup.fortification, x = choice_row(list(maps_mod.FORTIFICATION_LEVELS),
                                                setup.fortification, margin + label_w, y)
            lvl = maps_mod.fortification_of({'fortification': setup.fortification})
            clipped_note(maps_mod.FORTIFICATION_DESCRIPTIONS[lvl], x + 10, y)

        # ─── Aperçu (régénéré seulement quand la carte change) ───
        if setup.key() != preview_key:
            preview, preview_battle = build_preview(army1, army2, setup, grid_w, grid_h,
                                                    preview_rect.w - 8, preview_rect.h - 8)
            preview_key = setup.key()
        T.panel(screen, preview_rect)
        map_rect = preview.get_rect(center=preview_rect.center)
        screen.blit(preview, map_rect.topleft)
        pygame.draw.rect(screen, T.INK, map_rect.inflate(2, 2), 1)
        pygame.draw.rect(screen, T.GOLD_DIM, map_rect.inflate(6, 6), 1)
        summary = describe_setup(setup, preview_battle)
        T.text(screen, summary, T.font('serif', 15), (screen_w // 2, preview_rect.bottom + 6),
               T.PARCHMENT, align="center")
        for side, col in enumerate(TEAM_COLORS):
            n = len(army1 if side == 0 else army2)
            lx = margin + side * 150
            pygame.draw.circle(screen, col, (lx + 6, preview_rect.bottom + 16), 5)
            draw_text(screen, f"Armée {side + 1} ({n})", small_font,
                      (lx + 16, preview_rect.bottom + 9), TEXT_DIM)
        # Machines sans servants: elles ne tireront ni n'avanceront
        warnings = [(i + 1, siege_engines.staffing_warning(a))
                    for i, a in enumerate((army1, army2))]
        wy = preview_rect.bottom + 22   # sous le résumé, à droite des légendes
        for side, text in warnings:
            if text:
                draw_text(screen, f"Attention, armée {side}: {text}", small_font,
                          (margin + 310, wy), (235, 170, 90))
                wy += 15

        # ─── Boutons ───
        by = screen_h - 58
        back_rect = pygame.Rect(margin, by, 160, 40)
        if draw_button(screen, back_rect, "← Armées", body_font, mouse_pos) and clicked:
            return "back"
        reroll_rect = pygame.Rect(screen_w - margin - 200, by, 200, 40)
        if draw_button(screen, reroll_rect, "Nouvelle carte (N)", body_font, mouse_pos,
                       BTN_NORMAL, BTN_HOVER, T.GOLD_BRIGHT) and clicked:
            setup.new_seed()
        launch_rect = pygame.Rect((screen_w - 300) // 2, by - 2, 300, 44)
        if draw_button(screen, launch_rect, f"COMBAT ! — {setup.map_name}", body_font,
                       mouse_pos, BTN_ACTIVE, (100, 180, 255), TEXT_BRIGHT) and clicked:
            return "launch"

        help_txt = small_font.render(
            "ENTRÉE = combat  |  N = nouvelle carte  |  ÉCHAP = retour aux armées",
            True, TEXT_DIM)
        screen.blit(help_txt, ((screen_w - help_txt.get_width()) // 2, screen_h - 14))

        pygame.display.flip()
        clock.tick(60)
