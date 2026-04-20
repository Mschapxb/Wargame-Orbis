"""Menu de composition d'armée WW1 — interface pygame.

Permet de sélectionner une faction WW1 et composer chaque armée
avant de lancer la bataille.
"""

import pygame
import sys

from unit_library import get_library, list_armies, build_army


# ═══════════════════════════════════════════════════════════════
#                       COULEURS & CONSTANTES
# ═══════════════════════════════════════════════════════════════

BG           = (18, 20, 22)           # Noir de guerre
PANEL_BG     = (28, 32, 36)
PANEL_HOVER  = (38, 44, 50)
BORDER       = (55, 62, 68)
HIGHLIGHT    = (180, 140, 60)         # Or feldgrau
HIGHLIGHT2   = (200, 80, 60)          # Rouge sang
TEXT         = (200, 195, 185)
TEXT_DIM     = (120, 115, 105)
TEXT_BRIGHT  = (240, 235, 225)
GOLD         = (200, 170, 80)
GREEN        = (70, 160, 70)
RED          = (180, 70, 60)
ORANGE       = (200, 140, 50)
BLUE_ALLIES  = (60, 100, 180)
BROWN_CENTRAL = (140, 100, 50)

BTN_NORMAL  = (45, 52, 58)
BTN_HOVER   = (60, 70, 80)
BTN_ACTIVE  = (100, 130, 60)          # Vert militaire
BTN_DANGER  = (160, 50, 45)

MIN_W, MIN_H = 1000, 600

# Descriptions courtes des types d'unités WW1
UNIT_TYPE_ICONS = {
    "Infanterie": "⬛",
    "Cavalerie":  "◆",
    "Artillerie": "▲",
    "Blindé":     "■",
    "Héros":      "★",
}

UNIT_TYPE_COLOR = {
    "Infanterie": (160, 160, 160),
    "Cavalerie":  (180, 140, 80),
    "Artillerie": (200, 100, 60),
    "Blindé":     (80, 160, 80),
    "Héros":      (220, 190, 60),
}


# ═══════════════════════════════════════════════════════════════
#                         HELPERS
# ═══════════════════════════════════════════════════════════════

def draw_button(screen, rect, text, font, mouse_pos, color=BTN_NORMAL,
                hover_color=BTN_HOVER, text_color=TEXT):
    hovered = rect.collidepoint(mouse_pos)
    c = hover_color if hovered else color
    pygame.draw.rect(screen, c, rect, border_radius=3)
    pygame.draw.rect(screen, BORDER, rect, 1, border_radius=3)
    t = font.render(text, True, text_color)
    screen.blit(t, (rect.x + (rect.w - t.get_width()) // 2,
                    rect.y + (rect.h - t.get_height()) // 2))
    return hovered


def draw_text(screen, text, font, pos, color=TEXT):
    t = font.render(text, True, color)
    screen.blit(t, pos)
    return t.get_width(), t.get_height()


def draw_separator(screen, y, x1, x2, color=BORDER):
    pygame.draw.line(screen, color, (x1, y), (x2, y), 1)


# ═══════════════════════════════════════════════════════════════
#                       MENU PRINCIPAL
# ═══════════════════════════════════════════════════════════════

def run_army_menu(screen_w=None, screen_h=None):
    """Lance le menu de composition WW1. Retourne (army1_list, army2_list, map_name) ou None."""

    if screen_w is None or screen_h is None:
        info = pygame.display.Info()
        screen_w = max(MIN_W, info.current_w)
        screen_h = max(MIN_H, info.current_h)

    screen = pygame.display.set_mode((screen_w, screen_h), pygame.NOFRAME)
    pygame.display.set_caption("Grande Guerre — Composition des forces")
    clock = pygame.time.Clock()

    db = get_library()
    army_names = list_armies()

    title_font  = pygame.font.SysFont("arial", 22, bold=True)
    header_font = pygame.font.SysFont("arial", 16, bold=True)
    body_font   = pygame.font.SysFont("arial", 14)
    small_font  = pygame.font.SysFont("arial", 12)
    stat_font   = pygame.font.SysFont("arial", 11)

    # ── État des deux armées ──
    class ArmyState:
        def __init__(self, side, default_faction=None):
            self.side = side
            self.composition = {}
            self.scroll_offset = 0
            self.show_bonuses = False
            self.selected_faction = default_faction or (army_names[side] if side < len(army_names) else army_names[0])
            self.bonuses = {
                "mouvement":   0,
                "pv":          0,
                "moral":       0,
                "sauvegarde":  0,
                "toucher":     0,
                "blesser":     0,
                "perforation": 0,
                "degats":      0,
            }

        @property
        def total_units(self):
            return sum(self.composition.values())

        def add_unit(self, army_name, unit_name, amount=1):
            key = (army_name, unit_name)
            self.composition[key] = self.composition.get(key, 0) + amount

        def remove_unit(self, army_name, unit_name, amount=1):
            key = (army_name, unit_name)
            if key in self.composition:
                self.composition[key] = max(0, self.composition[key] - amount)
                if self.composition[key] == 0:
                    del self.composition[key]

        def clear(self):
            self.composition.clear()

        def get_faction_units(self):
            army_data = db.get(self.selected_faction, {})
            return army_data.get("units", [])

        def build(self):
            from unit_library import build_army as _build
            all_units = []
            by_faction = {}
            for (army_name, unit_name), count in self.composition.items():
                if count <= 0:
                    continue
                by_faction.setdefault(army_name, []).append((unit_name, count))
            for army_name, comp in by_faction.items():
                all_units.extend(_build(army_name, comp))

            b = self.bonuses
            for u in all_units:
                if b["mouvement"]:
                    u.vitesse = max(0, u.vitesse + b["mouvement"])
                if b["pv"]:
                    u.pv = max(1, u.pv + b["pv"])
                    u.max_pv = u.pv
                if b["moral"]:
                    u.morale = max(1, min(6, u.morale + b["moral"]))
                    u.base_morale = u.morale
                if b["sauvegarde"]:
                    u.sauvegarde = max(2, min(7, u.sauvegarde + b["sauvegarde"]))
                for arme in u.armes:
                    if b["toucher"]:
                        arme.toucher = max(2, arme.toucher + b["toucher"])
                    if b["blesser"]:
                        arme.blesser = max(2, arme.blesser + b["blesser"])
                    if b["perforation"]:
                        arme.perforation += b["perforation"]
                    if b["degats"]:
                        arme._bonus = arme._bonus + b["degats"]
            return all_units

    # Defaults : Alliés vs Centraux
    faction_defaults = [
        next((n for n in army_names if "allié" in n.lower()), army_names[0]),
        next((n for n in army_names if "central" in n.lower()), army_names[min(1, len(army_names)-1)]),
    ]
    states = [ArmyState(0, faction_defaults[0]), ArmyState(1, faction_defaults[1])]
    selected_map = "No Man's Land"

    running = True

    while running:
        mouse_pos = pygame.mouse.get_pos()
        clicked = False
        right_clicked = False
        scroll_delta = 0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_RETURN:
                    if states[0].total_units > 0 and states[1].total_units > 0:
                        return states[0].build(), states[1].build(), selected_map
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    clicked = True
                elif event.button == 3:
                    right_clicked = True
                elif event.button == 4:
                    scroll_delta = -1
                elif event.button == 5:
                    scroll_delta = 1

        screen.fill(BG)

        # ── TITRE ──
        title_surf = title_font.render("★  GRANDE GUERRE — COMPOSITION DES FORCES  ★", True, GOLD)
        screen.blit(title_surf, ((screen_w - title_surf.get_width()) // 2, 8))
        draw_separator(screen, 34, 10, screen_w - 10, GOLD)

        # ── PANNEAUX ARMÉE (gauche + droite) ──
        panel_margin = 10
        panel_w = (screen_w - panel_margin * 3) // 2
        panel_h = screen_h - 160

        SIDE_LABELS = ["◀ FORCES ALLIÉES", "PUISSANCES CENTRALES ▶"]
        SIDE_COLORS = [BLUE_ALLIES, BROWN_CENTRAL]

        for side, state in enumerate(states):
            px = panel_margin + side * (panel_w + panel_margin)
            py = 40

            pygame.draw.rect(screen, PANEL_BG, (px, py, panel_w, panel_h), border_radius=4)
            pygame.draw.rect(screen, SIDE_COLORS[side], (px, py, panel_w, panel_h), 2, border_radius=4)

            # Titre panneau
            lbl = header_font.render(SIDE_LABELS[side], True, SIDE_COLORS[side])
            screen.blit(lbl, (px + (panel_w - lbl.get_width()) // 2, py + 6))

            # ── Sélecteur de faction ──
            faction_y = py + 30
            draw_text(screen, "Faction:", stat_font, (px + 8, faction_y + 4), TEXT_DIM)
            fbx = px + 65
            for fidx, fname in enumerate(army_names):
                fw = max(80, len(fname) * 7)
                fb = pygame.Rect(fbx, faction_y, fw, 22)
                is_sel = (fname == state.selected_faction)
                fc = SIDE_COLORS[side] if is_sel else BTN_NORMAL
                hc = (min(fc[0]+30, 255), min(fc[1]+30, 255), min(fc[2]+30, 255)) if is_sel else BTN_HOVER
                army_color = db.get(fname, {}).get("color", TEXT)
                tc = TEXT_BRIGHT if is_sel else army_color
                if draw_button(screen, fb, fname, stat_font, mouse_pos, fc, hc, tc):
                    if clicked:
                        state.selected_faction = fname
                fbx += fw + 4
                if fbx > px + panel_w - 10:
                    faction_y += 26
                    fbx = px + 65

            # ── Liste des unités de la faction sélectionnée ──
            cx = px + 8
            units_area_top = faction_y + 30
            units_area_h = panel_h - (units_area_top - py) - 160

            screen.set_clip(pygame.Rect(px, units_area_top, panel_w, units_area_h))

            faction_units = state.get_faction_units()
            army_color = db.get(state.selected_faction, {}).get("color", TEXT)

            scroll_px = state.scroll_offset * 20
            draw_y = units_area_top - scroll_px
            total_content_h = 0
            rh = 52

            for unit_def in faction_units:
                uname = unit_def["nom"]
                key = (state.selected_faction, uname)
                count = state.composition.get(key, 0)

                if draw_y + rh > units_area_top and draw_y < units_area_top + units_area_h:
                    row_rect = pygame.Rect(px + 4, draw_y + 1, panel_w - 8, rh - 2)
                    if count > 0:
                        pygame.draw.rect(screen, (35, 48, 35), row_rect, border_radius=3)
                    if row_rect.collidepoint(mouse_pos):
                        pygame.draw.rect(screen, PANEL_HOVER, row_rect, border_radius=3)
                    pygame.draw.rect(screen, BORDER, row_rect, 1, border_radius=3)

                    # Icône type
                    utype = unit_def.get("unit_type", "Infanterie")
                    icon = UNIT_TYPE_ICONS.get(utype, "?")
                    icon_col = UNIT_TYPE_COLOR.get(utype, TEXT_DIM)
                    draw_text(screen, icon, body_font, (cx + 2, draw_y + 4), icon_col)

                    # Nom + compteur
                    nc = GREEN if count > 0 else TEXT_BRIGHT
                    draw_text(screen, uname[:22], body_font, (cx + 20, draw_y + 4), nc)
                    if count > 0:
                        cnt_txt = body_font.render(f"×{count}", True, GREEN)
                        screen.blit(cnt_txt, (cx + panel_w - 60, draw_y + 4))

                    # Stats compactes
                    dep = unit_def.get("deplacement", 0)
                    pv  = unit_def.get("blessure", 1)
                    brv = unit_def.get("bravoure", 1)
                    svg = unit_def.get("sauvegarde", 7)
                    size= unit_def.get("size", 1)
                    traits = unit_def.get("traits", [])
                    trait_short = " · ".join(t[:10] for t in traits[:3])
                    stat_str = f"Dép:{dep}  PV:{pv}  Brv:{brv}  Svg:{svg}  Taille:{size}"
                    draw_text(screen, stat_str, stat_font, (cx + 20, draw_y + 22), TEXT_DIM)
                    if trait_short:
                        draw_text(screen, trait_short, stat_font, (cx + 20, draw_y + 35), ORANGE)

                    # Boutons +/-
                    btn_w = panel_w - 80
                    btn_set_x = cx + 4
                    btn_y = draw_y + rh - 20
                    btn_h = 16

                    # -1
                    b1 = pygame.Rect(btn_set_x, btn_y, 26, btn_h)
                    if draw_button(screen, b1, "-1", stat_font, mouse_pos, BTN_DANGER, (200, 70, 70)):
                        if clicked:
                            state.remove_unit(state.selected_faction, uname)

                    # +1
                    b2 = pygame.Rect(btn_set_x + 30, btn_y, 26, btn_h)
                    if draw_button(screen, b2, "+1", stat_font, mouse_pos, BTN_ACTIVE, (120, 160, 80)):
                        if clicked:
                            state.add_unit(state.selected_faction, uname)

                    # +5
                    b3 = pygame.Rect(btn_set_x + 60, btn_y, 30, btn_h)
                    if draw_button(screen, b3, "+5", stat_font, mouse_pos, BTN_ACTIVE, (120, 160, 80)):
                        if clicked:
                            state.add_unit(state.selected_faction, uname, 5)

                if scroll_delta and pygame.Rect(px, units_area_top, panel_w, units_area_h).collidepoint(mouse_pos):
                    state.scroll_offset = max(0, state.scroll_offset + scroll_delta)

                draw_y += rh
                total_content_h += rh

            screen.set_clip(None)

            max_scroll_px = max(0, total_content_h - units_area_h)
            max_scroll = max_scroll_px // 20
            state.scroll_offset = min(state.scroll_offset, max_scroll)

            if total_content_h > units_area_h:
                sb_h = max(16, int(units_area_h * units_area_h / total_content_h))
                sb_y = units_area_top + int((units_area_h - sb_h) * scroll_px / max_scroll_px) if max_scroll_px > 0 else units_area_top
                pygame.draw.rect(screen, (80, 90, 100),
                                 (px + panel_w - 8, sb_y, 4, sb_h), border_radius=2)

            # ── Composition actuelle ──
            compo_y = units_area_top + units_area_h + 5
            draw_separator(screen, compo_y, px + 4, px + panel_w - 4)
            compo_y += 6

            total_txt = f"Forces: {state.total_units} unités"
            draw_text(screen, total_txt, body_font, (px + 8, compo_y),
                      GREEN if state.total_units > 0 else TEXT_DIM)

            clear_btn = pygame.Rect(px + panel_w - 70, compo_y - 2, 60, 20)
            if draw_button(screen, clear_btn, "Vider", small_font, mouse_pos, BTN_DANGER, (200, 70, 70)):
                if clicked:
                    state.clear()

            bonus_btn = pygame.Rect(px + panel_w - 140, compo_y - 2, 64, 20)
            has_bonus = any(v != 0 for v in state.bonuses.values())
            bc = ORANGE if has_bonus else BTN_NORMAL
            if draw_button(screen, bonus_btn, "Bonus", small_font, mouse_pos, bc, (240, 180, 70) if has_bonus else BTN_HOVER):
                if clicked:
                    state.show_bonuses = not state.show_bonuses

            compo_y += 22

            # Bonus panel
            if state.show_bonuses:
                draw_separator(screen, compo_y, px + 4, px + panel_w - 4, ORANGE)
                compo_y += 4
                bonus_keys = list(state.bonuses.keys())
                bonus_labels = {
                    "mouvement": "Mvt", "pv": "PV", "moral": "Moral",
                    "sauvegarde": "Svg", "toucher": "Touch", "blesser": "Bless",
                    "perforation": "Perf", "degats": "Dégâts",
                }
                col_w = (panel_w - 30) // 2
                for idx, key in enumerate(bonus_keys):
                    col = idx % 2
                    row = idx // 2
                    bx = px + 8 + col * col_w
                    by = compo_y + row * 22
                    draw_text(screen, f"{bonus_labels.get(key, key)}:", stat_font, (bx, by + 2), TEXT_DIM)
                    minus_btn = pygame.Rect(bx + 50, by, 20, 18)
                    if draw_button(screen, minus_btn, "-", stat_font, mouse_pos, BTN_DANGER, (220, 70, 70)):
                        if clicked:
                            state.bonuses[key] = max(-5, state.bonuses[key] - 1)
                    val = state.bonuses[key]
                    val_str = f"{val:+d}" if val != 0 else "0"
                    val_color = GREEN if val > 0 else RED if val < 0 else TEXT_DIM
                    vt = body_font.render(val_str, True, val_color)
                    screen.blit(vt, (bx + 76 - vt.get_width() // 2, by))
                    plus_btn = pygame.Rect(bx + 90, by, 20, 18)
                    if draw_button(screen, plus_btn, "+", stat_font, mouse_pos, GREEN, (100, 220, 100)):
                        if clicked:
                            state.bonuses[key] = min(5, state.bonuses[key] + 1)
                compo_y += (len(bonus_keys) + 1) // 2 * 22 + 4

            # Résumé composition
            last_faction = None
            for (army_name, uname), count in sorted(state.composition.items()):
                if count <= 0:
                    continue
                if army_name != last_faction:
                    fc = db.get(army_name, {}).get("color", TEXT_DIM)
                    draw_text(screen, f" {army_name}:", stat_font, (px + 8, compo_y), fc)
                    compo_y += 13
                    last_faction = army_name
                draw_text(screen, f"   {uname[:20]} ×{count}", stat_font, (px + 8, compo_y), TEXT)
                compo_y += 13
                if compo_y > py + panel_h - 8:
                    draw_text(screen, "  ...", stat_font, (px + 8, compo_y), TEXT_DIM)
                    break

        # ── SÉLECTION DE MAP ──
        from maps import get_map_names, get_map_info
        map_names = get_map_names()

        map_y = screen_h - 112
        draw_separator(screen, map_y - 4, 10, screen_w - 10, GOLD)
        draw_text(screen, "TERRAIN:", small_font, (panel_margin, map_y + 6), TEXT_DIM)

        btn_x = panel_margin + 70
        for mname in map_names:
            is_sel = (mname == selected_map)
            minfo = get_map_info(mname)
            mbtn = pygame.Rect(btn_x, map_y, max(90, len(mname) * 8), 26)
            bc = (80, 100, 50) if is_sel else BTN_NORMAL
            hc = (100, 130, 60) if is_sel else BTN_HOVER
            tc = GOLD if is_sel else TEXT
            if draw_button(screen, mbtn, mname, small_font, mouse_pos, bc, hc, tc):
                if clicked:
                    selected_map = mname
            btn_x += mbtn.width + 6

        map_desc = get_map_info(selected_map).get("description", "")
        draw_text(screen, map_desc, stat_font, (btn_x + 10, map_y + 7), TEXT_DIM)

        # ── BOUTON ÉDITEUR ──
        custom_btn = pygame.Rect(screen_w - 185, map_y, 165, 26)
        from unit_editor import list_custom_units
        nb_custom = len(list_custom_units())
        custom_label = f"Unités custom ({nb_custom})" if nb_custom > 0 else "Créer unités custom"
        cc = ORANGE if nb_custom > 0 else BTN_NORMAL
        if draw_button(screen, custom_btn, custom_label, small_font, mouse_pos,
                       cc, (240, 180, 70) if nb_custom > 0 else BTN_HOVER):
            if clicked:
                from unit_editor import run_custom_units_screen
                run_custom_units_screen(screen, screen_w, screen_h)
                from unit_library import load_custom_units_into_db
                load_custom_units_into_db()
                db.update(get_library())

        # ── BOUTON LANCER ──
        can_launch = states[0].total_units > 0 and states[1].total_units > 0
        launch_w, launch_h = 340, 46
        launch_rect = pygame.Rect((screen_w - launch_w) // 2, screen_h - 60, launch_w, launch_h)

        if can_launch:
            label = f"⚔  EN AVANT — {selected_map}  ({states[0].total_units} vs {states[1].total_units})"
            hovered = draw_button(screen, launch_rect, label,
                                  body_font, mouse_pos, (80, 100, 50), (100, 130, 60), TEXT_BRIGHT)
            if hovered and clicked:
                return states[0].build(), states[1].build(), selected_map
        else:
            draw_button(screen, launch_rect,
                        "Constituez les deux forces avant de lancer",
                        body_font, mouse_pos, (35, 38, 42), (35, 38, 42), TEXT_DIM)

        help_txt = stat_font.render(
            "Clic gauche = +1  |  Molette = défiler  |  ENTRÉE = lancer  |  ÉCHAP = quitter",
            True, TEXT_DIM)
        screen.blit(help_txt, ((screen_w - help_txt.get_width()) // 2, screen_h - 16))

        pygame.display.flip()
        clock.tick(60)

    return None
