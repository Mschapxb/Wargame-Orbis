"""Menu de composition d'armée — interface pygame.

Permet de sélectionner une faction et composer chaque armée
avant de lancer la bataille.
"""

import pygame
import sys

from unit_library import get_library, list_armies, build_army


# ═══════════════════════════════════════════════════════════════
#                       COULEURS & CONSTANTES
# ═══════════════════════════════════════════════════════════════

BG          = (20, 25, 30)
PANEL_BG    = (30, 38, 45)
PANEL_HOVER = (40, 50, 60)
BORDER      = (60, 70, 80)
HIGHLIGHT   = (80, 160, 255)
HIGHLIGHT2  = (255, 80, 80)
TEXT        = (210, 210, 210)
TEXT_DIM    = (130, 130, 140)
TEXT_BRIGHT = (255, 255, 255)
GOLD        = (255, 215, 0)
GREEN       = (80, 200, 80)
RED         = (200, 80, 80)
ORANGE      = (220, 160, 50)

BTN_NORMAL  = (50, 60, 75)
BTN_HOVER   = (65, 80, 100)
BTN_ACTIVE  = (80, 160, 255)
BTN_DANGER  = (180, 50, 50)

MIN_W, MIN_H = 1000, 600


# ═══════════════════════════════════════════════════════════════
#                         HELPERS
# ═══════════════════════════════════════════════════════════════

def draw_button(screen, rect, text, font, mouse_pos, color=BTN_NORMAL,
                hover_color=BTN_HOVER, text_color=TEXT):
    """Dessine un bouton et retourne True si survolé."""
    hovered = rect.collidepoint(mouse_pos)
    c = hover_color if hovered else color
    pygame.draw.rect(screen, c, rect, border_radius=4)
    pygame.draw.rect(screen, BORDER, rect, 1, border_radius=4)
    t = font.render(text, True, text_color)
    screen.blit(t, (rect.x + (rect.w - t.get_width()) // 2,
                     rect.y + (rect.h - t.get_height()) // 2))
    return hovered


def draw_text(screen, text, font, pos, color=TEXT):
    t = font.render(text, True, color)
    screen.blit(t, pos)
    return t.get_width(), t.get_height()


# ═══════════════════════════════════════════════════════════════
#                       MENU PRINCIPAL
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#                   ÉTAT D'UN CAMP (testable)
# ═══════════════════════════════════════════════════════════════

class ArmyState:
    """Composition d'un camp.

    Un camp est UNE armée, mais elle peut être articulée en plusieurs
    GROUPES (corps, divisions, contingents alliés…). Chaque groupe est
    déployé séparément sur le terrain, garde sa cohésion au combat et
    reçoit son propre bilan dans le rapport de bataille.
    """
    MAX_GROUPS = 4

    def __init__(self, side):
        self.side = side  # 0 = gauche, 1 = droite
        self.groups = [{}]   # [{(faction, unité): nombre}, ...]
        self.active = 0      # groupe en cours d'édition
        self.scroll_offset = 0
        self.show_bonuses = False  # Toggle affichage des bonus
        # Bonus globaux appliqués à toutes les unités de cette armée
        self.bonuses = {
            "mouvement": 0,
            "pv": 0,
            "moral": 0,
            "sauvegarde": 0,
            "toucher": 0,
            "blesser": 0,
            "perforation": 0,
            "degats": 0,
        }

    # ── Accès ──
    @property
    def current(self):
        return self.groups[self.active]

    @property
    def composition(self):
        """Vue fusionnée de tous les groupes (totaux, résumé tactique)."""
        merged = {}
        for g in self.groups:
            for k, v in g.items():
                if v > 0:
                    merged[k] = merged.get(k, 0) + v
        return merged

    @property
    def total_units(self):
        return sum(sum(g.values()) for g in self.groups)

    def group_size(self, i):
        return sum(self.groups[i].values())

    def group_factions(self, i):
        return sorted({an for (an, _), c in self.groups[i].items() if c > 0})

    def group_label(self, i):
        """Nom porté par le groupe dans le rapport de bataille."""
        facs = self.group_factions(i)
        single = len(self.groups) == 1
        if not facs:
            return f"Groupe {i + 1}"
        if len(facs) == 1:
            return facs[0] if single else f"G{i + 1} · {facs[0]}"
        return facs[0] + " +" if single else f"Groupe {i + 1}"

    # ── Édition ──
    def add_unit(self, army_name, unit_name, amount=1):
        key = (army_name, unit_name)
        g = self.current
        g[key] = g.get(key, 0) + amount

    def remove_unit(self, army_name, unit_name, amount=1):
        key = (army_name, unit_name)
        g = self.current
        if key in g:
            g[key] = max(0, g[key] - amount)
            if g[key] <= 0:
                del g[key]

    def clear(self):
        self.groups = [{}]
        self.active = 0

    def add_group(self):
        if len(self.groups) < self.MAX_GROUPS:
            self.groups.append({})
            self.active = len(self.groups) - 1

    def remove_group(self, i):
        if len(self.groups) > 1:
            del self.groups[i]
            self.active = min(self.active, len(self.groups) - 1)

    def copy_from(self, other):
        """Recopie la composition (tous groupes) et les bonus d'un autre camp."""
        self.groups = [dict(g) for g in other.groups] or [{}]
        self.active = 0
        self.bonuses = dict(other.bonuses)

    def get_all_units_flat(self):
        """Retourne [(army_name, unit_def), ...] pour toutes les factions."""
        result = []
        for army_name in list_armies():
            army_data = get_library().get(army_name, {})
            for unit_def in army_data.get("units", []):
                result.append((army_name, unit_def))
        return result

    def build(self):
        """Construit la liste d'unités, groupe par groupe.

        Chaque unité porte le nom de son groupe (`contingent`): c'est ce
        qui permet au moteur de déployer les groupes à part et au
        rapport de les compter séparément.
        """
        from unit_library import build_army as _build
        all_units = []
        for gi, comp in enumerate(self.groups):
            by_faction = {}
            for (army_name, unit_name), count in comp.items():
                if count <= 0:
                    continue
                by_faction.setdefault(army_name, []).append((unit_name, count))
            if not by_faction:
                continue
            label = self.group_label(gi)
            for army_name, pairs in by_faction.items():
                units = _build(army_name, pairs)
                for u in units:
                    u.contingent = label
                all_units.extend(units)

        # Appliquer les bonus globaux
        b = self.bonuses
        for u in all_units:
            if b["mouvement"] != 0:
                u.vitesse = max(0, u.vitesse + b["mouvement"])
                u.speed = u.vitesse
            if b["pv"] != 0:
                bonus_hp = b["pv"]
                u.pv = max(1, u.pv + bonus_hp)
                u.max_pv = u.pv
                u.hp = u.pv
                u.max_hp = u.pv
            if b["moral"] != 0:
                u.morale = max(1, min(6, u.morale + b["moral"]))
                u.base_morale = u.morale
            if b["sauvegarde"] != 0:
                u.sauvegarde = max(2, min(7, u.sauvegarde + b["sauvegarde"]))
            if b["toucher"] != 0 or b["blesser"] != 0 or b["perforation"] != 0 or b["degats"] != 0:
                for arme in u.armes:
                    if b["toucher"] != 0:
                        arme.toucher = max(2, arme.toucher + b["toucher"])
                    if b["blesser"] != 0:
                        arme.blesser = max(2, arme.blesser + b["blesser"])
                    if b["perforation"] != 0:
                        arme.perforation = arme.perforation + b["perforation"]
                    if b["degats"] != 0:
                        arme.dice = arme.dice.plus(b["degats"])

        return all_units


def run_army_menu(screen_w=None, screen_h=None):
    """Menu en deux écrans: composition des armées, puis champ de bataille
    (map_screen.py: carte, thème, relief, météo, avantage, aperçu).
    Retourne (army1_list, army2_list, map_name, map_options).
    map_options: {'biome', 'relief', 'weather', 'seed', 'advantage'…}
    (cf. maps.generate_map, weather.resolve, Battle)."""
    
    if screen_w is None or screen_h is None:
        info = pygame.display.Info()
        screen_w = max(MIN_W, info.current_w)
        screen_h = max(MIN_H, info.current_h)
    
    screen = pygame.display.set_mode((screen_w, screen_h), pygame.NOFRAME)
    pygame.display.set_caption("Composition des armées")
    clock = pygame.time.Clock()
    
    db = get_library()
    army_names = list_armies()
    
    # Polices
    title_font  = pygame.font.SysFont("arial", 24, bold=True)
    header_font = pygame.font.SysFont("arial", 17, bold=True)
    body_font   = pygame.font.SysFont("arial", 14)
    small_font  = pygame.font.SysFont("arial", 12)
    stat_font   = pygame.font.SysFont("arial", 11)
    
    states = [ArmyState(0), ArmyState(1)]
    # Choix de la carte: écran « Champ de bataille » (map_screen.py). Gardé
    # d'un aller-retour à l'autre entre les deux écrans.
    from map_screen import MapSetup, run_map_screen
    setup = MapSetup()

    def next_screen():
        """Écran 2. Retourne le résultat final du menu, ou None (retour)."""
        from renderer import compute_grid_from_screen
        a1 = states[0].build()
        a2 = states[1].build()
        grid_w, grid_h, _cell = compute_grid_from_screen()
        if run_map_screen(screen, screen_w, screen_h, a1, a2, setup,
                          (grid_w, grid_h)) == "launch":
            return a1, a2, setup.map_name, setup.options()
        pygame.display.set_caption("Composition des armées")
        return None
    
    # ─── Fond dégradé pré-rendu (une seule fois) ───
    bg_surface = pygame.Surface((screen_w, screen_h))
    for yy in range(screen_h):
        t = yy / max(1, screen_h)
        c = (int(BG[0] + 8 * (1 - t)), int(BG[1] + 10 * (1 - t)), int(BG[2] + 14 * (1 - t)))
        pygame.draw.line(bg_surface, c, (0, yy), (screen_w, yy))
    
    def army_summary(state):
        """Compte CaC / Tir / Cavalerie / Sorts de la composition."""
        melee = ranged = cav = mages = 0
        for (army_name, uname), count in state.composition.items():
            if count <= 0:
                continue
            army_data = db.get(army_name, {})
            udef = next((u for u in army_data.get("units", []) if u["nom"] == uname), None)
            if udef is None:
                continue
            is_ranged = any(a[1] >= 4 for a in udef.get("armes", []))
            has_spells = bool(udef.get("sorts"))
            if has_spells:
                mages += count
            elif is_ranged:
                ranged += count
            else:
                melee += count
            if udef.get("deplacement", 0) >= 6:
                cav += count
        return melee, ranged, mages, cav
    
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
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    clicked = True
                elif event.button == 3:
                    right_clicked = True
                elif event.button == 4:
                    scroll_delta = -1
                elif event.button == 5:
                    scroll_delta = 1
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                    if states[0].total_units > 0 and states[1].total_units > 0:
                        result = next_screen()
                        if result is not None:
                            return result
        
        screen.blit(bg_surface, (0, 0))
        
        # ─── TITRE ───
        title = title_font.render("— COMPOSITION DES ARMÉES —", True, GOLD)
        tx0 = (screen_w - title.get_width()) // 2
        screen.blit(title, (tx0, 10))
        pygame.draw.line(screen, (140, 120, 40),
                         (tx0, 40), (tx0 + title.get_width(), 40), 1)
        
        # ─── DEUX PANNEAUX CÔTE À CÔTE ───
        panel_margin = 15
        panel_top = 50
        panel_w = (screen_w - panel_margin * 3) // 2
        panel_h = screen_h - panel_top - 80
        
        for i, state in enumerate(states):
            px = panel_margin + i * (panel_w + panel_margin)
            py = panel_top
            
            panel_rect = pygame.Rect(px, py, panel_w, panel_h)
            # Ombre portée du panneau
            shadow_rect = pygame.Rect(px + 4, py + 4, panel_w, panel_h)
            sh = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            sh.fill((0, 0, 0, 70))
            screen.blit(sh, shadow_rect.topleft)
            pygame.draw.rect(screen, PANEL_BG, panel_rect, border_radius=6)
            team_border = HIGHLIGHT if i == 0 else HIGHLIGHT2
            pygame.draw.rect(screen, team_border, panel_rect, 2, border_radius=6)
            
            cx = px + 10
            cy = py + 10
            
            # ─── Titre armée ───
            label = f"Armée {i+1}"
            draw_text(screen, label, header_font, (cx, cy), team_border)
            n_units_hdr = state.total_units
            if n_units_hdr:
                draw_text(screen, f"{n_units_hdr} unités", small_font,
                          (cx + 90, cy + 4), TEXT_DIM)
            cy += 24

            # ─── Groupes: une armée peut être articulée en plusieurs corps ───
            # Les unités ajoutées vont dans le groupe SÉLECTIONNÉ; chaque
            # groupe est déployé à part sur le terrain.
            draw_text(screen, "Groupes:", small_font, (cx, cy + 3), TEXT_DIM)
            tab_x = cx + 56
            for gi in range(len(state.groups)):
                n_g = state.group_size(gi)
                tab_w = 46
                tab_rect = pygame.Rect(tab_x, cy, tab_w, 19)
                is_act = (gi == state.active)
                base_c = team_border if is_act else (58, 62, 72)
                if draw_button(screen, tab_rect, f"G{gi+1} ({n_g})", stat_font,
                               mouse_pos, base_c, (110, 120, 140)):
                    if clicked:
                        state.active = gi
                if is_act:
                    pygame.draw.rect(screen, GOLD, tab_rect, 1)
                tab_x += tab_w + 3
            if len(state.groups) < state.MAX_GROUPS:
                add_rect = pygame.Rect(tab_x, cy, 22, 19)
                if draw_button(screen, add_rect, "+", small_font, mouse_pos,
                               GREEN, (100, 220, 100)):
                    if clicked:
                        state.add_group()
                tab_x += 25
            if len(state.groups) > 1:
                del_rect = pygame.Rect(tab_x, cy, 22, 19)
                if draw_button(screen, del_rect, "x", small_font, mouse_pos,
                               BTN_DANGER, (220, 70, 70)):
                    if clicked:
                        state.remove_group(state.active)
            cy += 23

            pygame.draw.line(screen, BORDER, (cx, cy), (px + panel_w - 10, cy), 1)
            cy += 6
            
            # ─── Liste de toutes les factions + unités (scrollable) ───
            units_area_top = cy
            bonus_extra = 100 if state.show_bonuses else 0
            units_area_h = panel_h - (cy - py) - 120 - bonus_extra
            
            if panel_rect.collidepoint(mouse_pos) and scroll_delta != 0:
                state.scroll_offset = max(0, state.scroll_offset + scroll_delta * 3)
            
            clip_rect = pygame.Rect(px, units_area_top, panel_w, units_area_h)
            screen.set_clip(clip_rect)
            
            # Construire la liste : [(type, data), ...]
            # type="header" → faction header, type="unit" → unit row
            rows = []
            for army_name in army_names:
                army_data = db.get(army_name, {})
                rows.append(("header", army_name, army_data.get("color", (180, 180, 180))))
                for unit_def in army_data.get("units", []):
                    rows.append(("unit", army_name, unit_def))
            
            header_h = 24
            row_h = 38
            
            # Pixel offset scroll
            scroll_px = state.scroll_offset * 20
            
            draw_y = units_area_top - scroll_px
            total_content_h = 0
            
            for row in rows:
                if row[0] == "header":
                    rh = header_h
                    if draw_y + rh > units_area_top and draw_y < units_area_top + units_area_h:
                        fc = row[2]
                        pygame.draw.rect(screen, (fc[0]//4, fc[1]//4, fc[2]//4),
                                         (cx, draw_y, panel_w - 20, rh - 1), border_radius=2)
                        draw_text(screen, f"── {row[1]} ──", body_font, (cx + 4, draw_y + 3), fc)
                    draw_y += rh
                    total_content_h += rh
                else:
                    rh = row_h
                    if draw_y + rh > units_area_top and draw_y < units_area_top + units_area_h:
                        army_name = row[1]
                        unit_def = row[2]
                        uname = unit_def["nom"]
                        
                        # Fond hover
                        row_rect = pygame.Rect(cx, draw_y, panel_w - 20, rh - 2)
                        if row_rect.collidepoint(mouse_pos):
                            pygame.draw.rect(screen, PANEL_HOVER, row_rect, border_radius=3)
                        
                        # Nom
                        draw_text(screen, uname, body_font, (cx + 8, draw_y + 1), TEXT_BRIGHT)
                        
                        # Stats compactes
                        utype = unit_def.get("unit_type", "?")
                        traits_str = ", ".join(unit_def.get("traits", [])) or "-"
                        stat_line = f"Dép:{unit_def['deplacement']} Ble:{unit_def['blessure']} Brv:{unit_def['bravoure']} Svg:{unit_def['sauvegarde']} | {utype} | {traits_str}"
                        draw_text(screen, stat_line, stat_font, (cx + 8, draw_y + 17), TEXT_DIM)
                        
                        # Boutons
                        key = (army_name, uname)
                        count = state.current.get(key, 0)
                        count_all = state.composition.get(key, 0)
                        
                        btn_y = draw_y + 8
                        btn_h = 20
                        btn_set_x = cx + panel_w - 200
                        
                        # -5
                        b1 = pygame.Rect(btn_set_x, btn_y, 26, btn_h)
                        if draw_button(screen, b1, "-5", small_font, mouse_pos, BTN_DANGER, (220, 70, 70)):
                            if clicked:
                                state.remove_unit(army_name, uname, 5)
                        
                        # -1
                        b2 = pygame.Rect(btn_set_x + 28, btn_y, 26, btn_h)
                        if draw_button(screen, b2, "-1", small_font, mouse_pos, BTN_DANGER, (220, 70, 70)):
                            if clicked:
                                state.remove_unit(army_name, uname, 1)
                        
                        # Compteur du GROUPE actif (c'est lui que +/- modifie);
                        # le total tous groupes confondus est rappelé dessous.
                        count_text = body_font.render(str(count), True, GREEN if count > 0 else TEXT_DIM)
                        screen.blit(count_text, (btn_set_x + 60 - count_text.get_width() // 2, btn_y))
                        if count_all != count:
                            tot_t = stat_font.render(f"/{count_all}", True, TEXT_DIM)
                            screen.blit(tot_t, (btn_set_x + 60 - tot_t.get_width() // 2, btn_y + 15))
                        
                        # +1
                        b3 = pygame.Rect(btn_set_x + 82, btn_y, 26, btn_h)
                        if draw_button(screen, b3, "+1", small_font, mouse_pos, GREEN, (100, 220, 100)):
                            if clicked:
                                state.add_unit(army_name, uname, 1)
                        
                        # +5
                        b4 = pygame.Rect(btn_set_x + 110, btn_y, 26, btn_h)
                        if draw_button(screen, b4, "+5", small_font, mouse_pos, GREEN, (100, 220, 100)):
                            if clicked:
                                state.add_unit(army_name, uname, 5)
                        
                        # Clic direct sur la ligne (hors boutons):
                        # gauche = +1, droit = -1 — ajout/retrait rapide
                        buttons_zone = pygame.Rect(btn_set_x, btn_y, 140, btn_h)
                        if row_rect.collidepoint(mouse_pos):
                            if clicked and not buttons_zone.collidepoint(mouse_pos):
                                state.add_unit(army_name, uname, 1)
                            elif right_clicked:
                                state.remove_unit(army_name, uname, 1)
                        
                        # Surlignage des lignes avec unités sélectionnées
                        if count > 0:
                            pygame.draw.rect(screen, (GREEN[0] // 2, GREEN[1] // 2, GREEN[2] // 2),
                                             row_rect, 1, border_radius=3)
                    
                    draw_y += rh
                    total_content_h += rh
            
            screen.set_clip(None)
            
            # Max scroll
            max_scroll_px = max(0, total_content_h - units_area_h)
            max_scroll = max_scroll_px // 20
            state.scroll_offset = min(state.scroll_offset, max_scroll)
            
            # Scrollbar indicateur
            if total_content_h > units_area_h:
                sb_h = max(20, int(units_area_h * units_area_h / total_content_h))
                sb_y = units_area_top + int((units_area_h - sb_h) * scroll_px / max_scroll_px) if max_scroll_px > 0 else units_area_top
                pygame.draw.rect(screen, (80, 90, 100),
                                 (px + panel_w - 8, sb_y, 4, sb_h), border_radius=2)
            
            # ─── Composition actuelle (en bas) ───
            compo_y = units_area_top + units_area_h + 5
            pygame.draw.line(screen, BORDER, (cx, compo_y), (px + panel_w - 10, compo_y), 1)
            compo_y += 6
            
            n_groups = sum(1 for gi in range(len(state.groups)) if state.group_size(gi) > 0)
            total_txt = f"Composition: {state.total_units} unités"
            if n_groups > 1:
                total_txt += f"  —  {n_groups} groupes"
            draw_text(screen, total_txt, body_font, (cx, compo_y),
                      GREEN if state.total_units > 0 else TEXT_DIM)
            if n_groups > 1:
                draw_text(screen, "(chaque groupe est déployé et compté à part)",
                          stat_font, (cx, compo_y + 15), TEXT_DIM)
                compo_y += 14
            
            # Résumé tactique de l'armée (aide à équilibrer la compo)
            if state.total_units > 0:
                n_melee, n_ranged, n_mages, n_cav = army_summary(state)
                parts = []
                if n_melee: parts.append(f"{n_melee} CaC")
                if n_ranged: parts.append(f"{n_ranged} Tir")
                if n_mages: parts.append(f"{n_mages} Mage")
                if n_cav: parts.append(f"{n_cav} Cav")
                summary_txt = "  ·  ".join(parts)
                st = stat_font.render(summary_txt, True, (160, 180, 200))
                screen.blit(st, (cx + 170, compo_y + 3))
            
            clear_btn = pygame.Rect(px + panel_w - 70, compo_y - 2, 60, 22)
            if draw_button(screen, clear_btn, "Vider", small_font, mouse_pos,
                           BTN_DANGER, (220, 70, 70)):
                if clicked:
                    state.clear()
            
            # Bouton miroir: copier cette composition vers l'autre armée
            mirror_btn = pygame.Rect(px + panel_w - 212, compo_y - 2, 64, 22)
            mirror_label = "Copier →" if i == 0 else "← Copier"
            if draw_button(screen, mirror_btn, mirror_label, small_font, mouse_pos):
                if clicked and state.total_units > 0:
                    states[1 - i].copy_from(state)
            
            # Bouton toggle bonus
            bonus_toggle_btn = pygame.Rect(px + panel_w - 140, compo_y - 2, 64, 22)
            has_any_bonus = any(v != 0 for v in state.bonuses.values())
            toggle_color = ORANGE if has_any_bonus else BTN_NORMAL
            if draw_button(screen, bonus_toggle_btn, "Bonus", small_font, mouse_pos,
                           toggle_color, (240, 180, 70) if has_any_bonus else BTN_HOVER):
                if clicked:
                    state.show_bonuses = not state.show_bonuses
            
            compo_y += 22
            
            # ─── Section Bonus (collapsible) ───
            if state.show_bonuses:
                pygame.draw.line(screen, ORANGE, (cx, compo_y), (px + panel_w - 10, compo_y), 1)
                compo_y += 4
                
                # Disposition: 2 colonnes de 4 stats
                bonus_keys = list(state.bonuses.keys())
                # Noms courts pour l'affichage
                bonus_labels = {
                    "mouvement": "Mouv",
                    "pv": "PV",
                    "moral": "Moral",
                    "sauvegarde": "Svg",
                    "toucher": "Touch",
                    "blesser": "Bless",
                    "perforation": "Perf",
                    "degats": "Dégâts",
                }
                col_w = (panel_w - 30) // 2
                
                for idx, key in enumerate(bonus_keys):
                    col = idx % 2
                    row = idx // 2
                    bx = cx + col * col_w
                    by = compo_y + row * 22
                    
                    label = bonus_labels.get(key, key)
                    val = state.bonuses[key]
                    
                    # Label
                    draw_text(screen, f"{label}:", stat_font, (bx, by + 2), TEXT_DIM)
                    
                    # Bouton -
                    minus_btn = pygame.Rect(bx + 50, by, 20, 18)
                    if draw_button(screen, minus_btn, "-", small_font, mouse_pos, BTN_DANGER, (220, 70, 70)):
                        if clicked:
                            state.bonuses[key] = max(-5, val - 1)
                    
                    # Valeur
                    val_str = f"{val:+d}" if val != 0 else "0"
                    val_color = GREEN if val > 0 else RED if val < 0 else TEXT_DIM
                    vt = body_font.render(val_str, True, val_color)
                    screen.blit(vt, (bx + 76 - vt.get_width() // 2, by))
                    
                    # Bouton +
                    plus_btn = pygame.Rect(bx + 90, by, 20, 18)
                    if draw_button(screen, plus_btn, "+", small_font, mouse_pos, GREEN, (100, 220, 100)):
                        if clicked:
                            state.bonuses[key] = min(5, val + 1)
                
                compo_y += (len(bonus_keys) + 1) // 2 * 22 + 4
            
            # Liste compacte: groupe par groupe, puis faction
            stop = False
            for gi, comp_g in enumerate(state.groups):
                if stop:
                    break
                if not any(c > 0 for c in comp_g.values()):
                    continue
                if len(state.groups) > 1:
                    gc = GOLD if gi == state.active else TEXT_DIM
                    draw_text(screen, f"▸ {state.group_label(gi)}", small_font,
                              (cx, compo_y), gc)
                    compo_y += 13
                last_faction = None
                for (army_name, uname), count in sorted(comp_g.items()):
                    if count <= 0:
                        continue
                    if army_name != last_faction:
                        fc = db.get(army_name, {}).get("color", TEXT_DIM)
                        draw_text(screen, f" {army_name}:", small_font, (cx + 6, compo_y), fc)
                        compo_y += 13
                        last_faction = army_name
                    draw_text(screen, f"   {uname} x{count}", small_font,
                              (cx + 6, compo_y), TEXT)
                    compo_y += 13
                    if compo_y > py + panel_h - 10:
                        draw_text(screen, "  ...", small_font, (cx, compo_y), TEXT_DIM)
                        stop = True
                        break
        
        # ─── BOUTON ÉDITEUR D'UNITÉS ───
        custom_btn = pygame.Rect(screen_w - 180, screen_h - 52, 160, 36)
        from unit_editor import list_custom_units
        nb_custom = len(list_custom_units())
        custom_label = f"Unités custom ({nb_custom})" if nb_custom > 0 else "Créer unités"
        custom_color = ORANGE if nb_custom > 0 else BTN_NORMAL
        if draw_button(screen, custom_btn, custom_label, small_font, mouse_pos,
                       custom_color, (240, 180, 70) if nb_custom > 0 else BTN_HOVER):
            if clicked:
                from unit_editor import run_custom_units_screen
                run_custom_units_screen(screen, screen_w, screen_h)
                # Recharger la librairie après édition
                from unit_library import load_custom_units_into_db
                load_custom_units_into_db()
                # Refresh db reference
                db.update(get_library())
        
        # ─── BOUTON LANCER ───
        can_launch = states[0].total_units > 0 and states[1].total_units > 0
        
        launch_w = 420
        launch_h = 44
        launch_rect = pygame.Rect(
            (screen_w - launch_w) // 2,
            screen_h - 55,
            launch_w, launch_h
        )
        
        if can_launch:
            label = f"SUIVANT : CHAMP DE BATAILLE →  ({states[0].total_units} vs {states[1].total_units})"
            hovered = draw_button(screen, launch_rect, label,
                                  body_font, mouse_pos, BTN_ACTIVE, (100, 180, 255), TEXT_BRIGHT)
            if hovered and clicked:
                result = next_screen()
                if result is not None:
                    return result
        else:
            draw_button(screen, launch_rect,
                        "Ajoutez des unités aux deux armées",
                        body_font, mouse_pos, (40, 45, 50), (40, 45, 50), TEXT_DIM)
        
        # Aide
        help_txt = small_font.render("Clic gauche sur une ligne = +1  |  Clic droit = -1  |  Molette = défiler  |  ENTRÉE = choisir le champ de bataille  |  ÉCHAP = quitter", True, TEXT_DIM)
        screen.blit(help_txt, ((screen_w - help_txt.get_width()) // 2, screen_h - 16))
        
        pygame.display.flip()
        clock.tick(60)
    
    return None