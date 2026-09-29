"""Menu de composition d'armée — interface pygame.

Permet de sélectionner une faction et composer chaque armée
avant de lancer la bataille.
"""

import pygame
import sys
import unicodedata

import icons
import settings as settings_mod
import theme as T

from unit_library import get_library, list_armies


# ═══════════════════════════════════════════════════════════════
#                       COULEURS & CONSTANTES
# ═══════════════════════════════════════════════════════════════

# Palette: celle du thème commun (theme.py), sous les noms historiques
BG          = T.BG_BOTTOM
PANEL_BG    = T.PANEL_TOP
PANEL_HOVER = (44, 48, 58)
BORDER      = T.PANEL_EDGE
HIGHLIGHT   = T.TEAM[0]
HIGHLIGHT2  = T.TEAM[1]
TEXT        = T.PARCHMENT
TEXT_DIM    = T.PARCHMENT_DIM
TEXT_BRIGHT = (250, 244, 228)
GOLD        = T.GOLD
GREEN       = T.SUCCESS
RED         = T.DANGER
ORANGE      = T.WARNING

BTN_NORMAL  = T.BTN
BTN_HOVER   = T.lighten(T.BTN, 0.14)
BTN_ACTIVE  = T.BTN_GOLD
BTN_DANGER  = T.BTN_RED

MIN_W, MIN_H = 1000, 600


# ═══════════════════════════════════════════════════════════════
#                         HELPERS
# ═══════════════════════════════════════════════════════════════

def draw_button(screen, rect, text, font, mouse_pos, color=BTN_NORMAL,
                hover_color=BTN_HOVER, text_color=TEXT):
    """Dessine un bouton (thème commun) et retourne True si survolé.

    Le survol et le relief sont dérivés de `color`; un texte neutre (TEXT,
    TEXT_BRIGHT) prend la teinte lisible sur ce fond (sombre sur l'or)."""
    auto = text_color in (TEXT, TEXT_BRIGHT)
    return T.button(screen, rect, text, font, mouse_pos, base=color,
                    text_color=None if auto else text_color)


def draw_text(screen, text, font, pos, color=TEXT):
    r = T.text(screen, text, font, pos, color)
    return r.w, r.h


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

    # ── Mémoire d'une session à l'autre (cf. settings.py) ──
    def to_dict(self):
        return {'groups': [[[army, unit, n] for (army, unit), n in g.items() if n > 0]
                           for g in self.groups],
                'bonuses': dict(self.bonuses)}

    def load_dict(self, data, known):
        """Reprend une composition enregistrée; `known(faction, unité)` dit si
        l'unité existe encore (une unité supprimée depuis est ignorée)."""
        groups = []
        for g in data.get('groups') or []:
            comp = {}
            for entry in g:
                if (isinstance(entry, list) and len(entry) == 3 and isinstance(entry[2], int)
                        and entry[2] > 0 and known(entry[0], entry[1])):
                    comp[(entry[0], entry[1])] = entry[2]
            groups.append(comp)
        self.groups = groups[:self.MAX_GROUPS] or [{}]
        self.active = 0
        for k, v in (data.get('bonuses') or {}).items():
            if k in self.bonuses and isinstance(v, int):
                self.bonuses[k] = max(-5, min(5, v))

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

        # Appliquer les bonus globaux. Convention du menu: +1 est TOUJOURS
        # un avantage. Toucher, blesser et sauvegarde sont des seuils d6 (plus
        # bas = meilleur) et la perforation se soustrait à la sauvegarde
        # adverse (plus négative = meilleure): le bonus s'y retranche.
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
                # Plafond 6 (un d6), sauf pour un héros qui le dépasse déjà
                u.morale = max(1, min(max(6, u.morale), u.morale + b["moral"]))
                u.base_morale = u.morale
            if b["sauvegarde"] != 0:
                u.sauvegarde = max(2, min(7, u.sauvegarde - b["sauvegarde"]))
            if b["toucher"] != 0 or b["blesser"] != 0 or b["perforation"] != 0 or b["degats"] != 0:
                for arme in u.armes:
                    if b["toucher"] != 0:
                        arme.toucher = max(2, min(7, arme.toucher - b["toucher"]))
                    if b["blesser"] != 0:
                        arme.blesser = max(2, min(7, arme.blesser - b["blesser"]))
                    if b["perforation"] != 0:
                        arme.perforation = arme.perforation - b["perforation"]
                    if b["degats"] != 0:
                        arme.dice = arme.dice.plus(b["degats"])

        return all_units


BONUS_LABELS = {
    "mouvement": "Mouv",
    "pv": "PV",
    "moral": "Moral",
    "sauvegarde": "Svg",
    "toucher": "Touch",
    "blesser": "Bless",
    "perforation": "Perf",
    "degats": "Dégâts",
}

HELP_TEXT = ("Clic = +1  ·  Maj+clic = +5  ·  clic droit = −1  ·  tapez pour chercher  ·  "
             "ENTRÉE = champ de bataille  ·  Maj+ENTRÉE = combat immédiat  ·  ÉCHAP = quitter")

PANEL_MARGIN = 15
FILTER_TOP = 54
PANEL_TOP = 94
FACTION_HEADER_H = 24
UNIT_ROW_H = 38
SCROLL_STEP_PX = 20   # pixels par cran de défilement


def _quit():
    pygame.quit()
    sys.exit()


def fold(text):
    """Minuscules sans accents: « Arbalétrier » se trouve en tapant « arbaletrier »."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")


class ArmyMenu:
    """Écran 1: composition des deux armées, côte à côte.

    Interface en mode immédiat: chaque image redessine tout, et un clic
    agit sur le bouton qu'il survole au moment où celui-ci est dessiné.
    """

    def __init__(self, screen_w, screen_h):
        self.screen_w, self.screen_h = screen_w, screen_h
        self.screen = pygame.display.set_mode((screen_w, screen_h), pygame.NOFRAME)
        pygame.display.set_caption("Composition des armées")
        self.clock = pygame.time.Clock()
        self.db = get_library()
        self.army_names = list_armies()

        self.title_font = T.font('title', 26)
        self.header_font = T.font('title', 20)
        self.faction_font = T.font('title', 14)
        self.name_font = T.font('ui_bold', 14)
        self.body_font = T.font('ui', 14)
        self.small_font = T.font('ui', 12)
        self.stat_font = T.font('ui', 11)

        self.states = [ArmyState(0), ArmyState(1)]
        # Choix de la carte: écran « Champ de bataille » (map_screen.py).
        # Gardé d'un aller-retour à l'autre entre les deux écrans.
        from map_screen import MapSetup
        self.setup = MapSetup()
        self.bg_surface = T.background(screen_w, screen_h)

        # Ce qui a été choisi la dernière fois revient tel quel: relancer
        # la même bataille, c'est ENTRÉE deux fois.
        self.settings = settings_mod.get()
        self._restore_session()
        # Liste des unités: filtre de faction, recherche, factions repliées
        self.faction_filter = None
        self.search = ""
        self.collapsed = set()
        self.shift = False

        # Entrées de l'image en cours
        self.mouse_pos = (0, 0)
        self.clicked = False
        self.right_clicked = False
        self.scroll_delta = 0

    # ─── Mémoire de session ───

    def _known_unit(self, army_name, unit_name):
        return any(u["nom"] == unit_name for u in self.db.get(army_name, {}).get("units", []))

    def _restore_session(self):
        session = self.settings.section("session")
        for state, data in zip(self.states, session.get("armies") or []):
            if isinstance(data, dict):
                state.load_dict(data, self._known_unit)
        if isinstance(session.get("map"), dict):
            self.setup.load_dict(session["map"])

    def remember(self):
        """Garde armées et champ de bataille pour la prochaine fois."""
        self.settings.set("session", "armies", [st.to_dict() for st in self.states])
        self.settings.set("session", "map", self.setup.to_dict())
        self.settings.save()

    def quit(self):
        self.remember()
        _quit()

    # ─── Boucle ───

    def run(self):
        while True:
            self.mouse_pos = pygame.mouse.get_pos()
            result = self._handle_events()
            if result is not None:
                return result
            result = self._draw()
            if result is not None:
                return result
            pygame.display.flip()
            self.clock.tick(60)

    @property
    def can_launch(self):
        return self.states[0].total_units > 0 and self.states[1].total_units > 0

    def _handle_events(self):
        self.clicked = self.right_clicked = False
        self.scroll_delta = 0
        self.shift = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.clicked = True
                elif event.button == 3:
                    self.right_clicked = True
                elif event.button == 4:
                    self.scroll_delta = -1
                elif event.button == 5:
                    self.scroll_delta = 1
            if event.type == pygame.KEYDOWN:
                result = self._key(event)
                if result is not None:
                    return result
        return None

    def _key(self, event):
        """Clavier: la recherche prend les lettres tapées; ENTRÉE avance,
        Maj+ENTRÉE lance le combat sur la dernière carte, ÉCHAP efface la
        recherche puis quitte."""
        shift = bool(event.mod & pygame.KMOD_SHIFT)
        if event.key == pygame.K_ESCAPE:
            if self.search:
                self.search = ""
                return None
            self.quit()
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.can_launch:
                return self.quick_launch() if shift else self.next_screen()
            return None
        if event.key == pygame.K_BACKSPACE:
            self.search = self.search[:-1]
            return None
        if event.key == pygame.K_SPACE and not self.search:
            return self.next_screen() if self.can_launch else None
        ch = event.unicode
        if ch and ch.isprintable() and not (event.mod & (pygame.KMOD_CTRL | pygame.KMOD_ALT)):
            if len(self.search) < 30:
                self.search += ch
                for st in self.states:
                    st.scroll_offset = 0
        return None

    def quick_launch(self):
        """Combat immédiat: les armées composées, sur la dernière carte."""
        self.remember()
        return (self.states[0].build(), self.states[1].build(), self.setup.map_name,
                self.setup.options())

    def next_screen(self):
        """Écran 2. Retourne le résultat final du menu, ou None (retour)."""
        from map_screen import run_map_screen
        from renderer import compute_grid_from_screen
        a1 = self.states[0].build()
        a2 = self.states[1].build()
        grid_w, grid_h, _cell = compute_grid_from_screen()
        if run_map_screen(self.screen, self.screen_w, self.screen_h, a1, a2, self.setup,
                          (grid_w, grid_h)) == "launch":
            self.remember()
            return a1, a2, self.setup.map_name, self.setup.options()
        pygame.display.set_caption("Composition des armées")
        return None

    def _button(self, rect, text, font, color=BTN_NORMAL, hover_color=BTN_HOVER,
                text_color=TEXT):
        """Dessine un bouton; True s'il vient d'être cliqué."""
        return (draw_button(self.screen, rect, text, font, self.mouse_pos, color, hover_color,
                            text_color)
                and self.clicked)

    # ─── Dessin ───

    def _draw(self):
        screen = self.screen
        screen.blit(self.bg_surface, (0, 0))
        T.title(screen, "Composition des armées", self.screen_w // 2, 8, 28)
        self._draw_filter_bar()
        panel_w = (self.screen_w - PANEL_MARGIN * 3) // 2
        panel_h = self.screen_h - PANEL_TOP - 80
        rows = self._unit_rows()
        for i, state in enumerate(self.states):
            px = PANEL_MARGIN + i * (panel_w + PANEL_MARGIN)
            self._draw_panel(i, state, pygame.Rect(px, PANEL_TOP, panel_w, panel_h), rows)
        self._draw_custom_units_button()
        result = self._draw_quick_button()
        if result is not None:
            return result
        result = self._draw_launch_button()
        help_txt = self.small_font.render(HELP_TEXT, True, TEXT_DIM)
        screen.blit(help_txt, ((self.screen_w - help_txt.get_width()) // 2, self.screen_h - 16))
        return result

    def _unit_rows(self):
        """[("header", faction, couleur, nb d'unités) | ("unit", faction,
        unit_def)] — après filtre de faction, recherche et factions repliées
        (une recherche montre tout ce qui correspond)."""
        rows = []
        query = fold(self.search.strip())
        for army_name in self.army_names:
            if self.faction_filter and army_name != self.faction_filter:
                continue
            army_data = self.db.get(army_name, {})
            units = [u for u in army_data.get("units", [])
                     if not query or query in fold(u["nom"])]
            if query and not units:
                continue
            rows.append(("header", army_name, army_data.get("color", (180, 180, 180)),
                         len(units)))
            if army_name in self.collapsed and not query:
                continue
            for unit_def in units:
                rows.append(("unit", army_name, unit_def))
        return rows

    def _draw_filter_bar(self):
        """Filtre de faction (puces) et recherche, communs aux deux armées."""
        screen = self.screen
        y, x = FILTER_TOP, PANEL_MARGIN
        search_w = min(320, self.screen_w // 4)
        chips_right = self.screen_w - PANEL_MARGIN - search_w - 16
        for name in [None] + self.army_names:
            label = "Toutes les factions" if name is None else name
            w = self.small_font.size(label)[0] + (34 if name else 22)
            if x + w > chips_right:
                break
            rect = pygame.Rect(x, y, w, 28)
            selected = self.faction_filter == name
            if self._button(rect, "", self.small_font, BTN_ACTIVE if selected else BTN_NORMAL):
                self.faction_filter = name
                for st in self.states:
                    st.scroll_offset = 0
            color = (30, 23, 12) if selected else TEXT
            tx = rect.x + 11
            if name:
                fc = self.db.get(name, {}).get("color", (180, 180, 180))
                pygame.draw.circle(screen, fc, (rect.x + 14, rect.centery), 5)
                pygame.draw.circle(screen, T.INK, (rect.x + 14, rect.centery), 5, 1)
                tx += 12
            img = self.small_font.render(label, True, color)
            screen.blit(img, (tx, rect.centery - img.get_height() // 2))
            x += w + 5
        box = pygame.Rect(self.screen_w - PANEL_MARGIN - search_w, y, search_w, 28)
        active = bool(self.search)
        screen.blit(T.rounded_gradient(box.w, box.h, (20, 22, 28), (30, 33, 41), 7), box)
        pygame.draw.rect(screen, T.GOLD if active else T.darken(T.GOLD_DIM, 0.2), box, 1,
                         border_radius=7)
        screen.blit(icons.icon("search", 16, T.GOLD if active else TEXT_DIM),
                    (box.x + 9, box.centery - 8))
        if active:
            txt = self.body_font.render(self.search, True, TEXT_BRIGHT)
            screen.blit(txt, (box.x + 32, box.centery - txt.get_height() // 2))
            caret_x = box.x + 33 + txt.get_width()
            if (pygame.time.get_ticks() // 500) % 2:
                pygame.draw.line(screen, T.GOLD, (caret_x, box.y + 7), (caret_x, box.bottom - 7))
            clear = pygame.Rect(box.right - 26, box.y + 4, 20, 20)
            if self._button(clear, "×", self.small_font):
                self.search = ""
        else:
            hint = self.small_font.render("Tapez pour chercher une unité…", True, TEXT_DIM)
            screen.blit(hint, (box.x + 32, box.centery - hint.get_height() // 2))

    def _draw_panel(self, i, state, panel, rows):
        team_color = HIGHLIGHT if i == 0 else HIGHLIGHT2
        T.panel(self.screen, panel, accent=team_color)
        cx, cy = panel.x + 12, panel.y + 12
        cy = self._draw_panel_header(i, state, cx, cy, team_color)
        cy = self._draw_group_tabs(i, state, cx, cy)
        T.divider(self.screen, cx, panel.right - 12, cy + 2, gem=False)
        cy += 8

        # Liste de toutes les factions et unités (défilante)
        bonus_extra = 100 if state.show_bonuses else 0
        list_area = pygame.Rect(panel.x, cy, panel.w, panel.h - (cy - panel.y) - 120 - bonus_extra)
        if panel.collidepoint(self.mouse_pos) and self.scroll_delta != 0:
            state.scroll_offset = max(0, state.scroll_offset + self.scroll_delta * 3)
        self._draw_unit_list(state, rows, list_area, cx)

        compo_y = self._draw_composition_bar(i, state, panel, cx, list_area.bottom + 5)
        if state.show_bonuses:
            compo_y = self._draw_bonus_editor(state, panel, cx, compo_y)
        self._draw_composition_list(state, panel, cx, compo_y)

    def _draw_panel_header(self, i, state, cx, cy, team_color):
        hdr = T.text(self.screen, f"Armée {i + 1}", self.header_font, (cx + 2, cy - 2),
                     T.lighten(team_color, 0.25))
        if state.total_units:
            T.pill(self.screen, (hdr.right + 12, cy + 2, 74, 20), f"{state.total_units} unités",
                   self.small_font, team_color)
        return cy + 28

    def _draw_group_tabs(self, i, state, cx, cy):
        """Onglets de groupes: une armée peut être articulée en plusieurs
        corps. Les unités ajoutées vont dans le groupe SÉLECTIONNÉ; chaque
        groupe est déployé à part sur le terrain."""
        draw_text(self.screen, "Groupes:", self.small_font, (cx, cy + 3), TEXT_DIM)
        tab_x = cx + 56
        for gi in range(len(state.groups)):
            tab_w = 46
            tab_rect = pygame.Rect(tab_x, cy, tab_w, 19)
            is_active = (gi == state.active)
            base = T.TEAM_DARK[i] if is_active else BTN_NORMAL
            if self._button(tab_rect, f"G{gi + 1} ({state.group_size(gi)})", self.stat_font,
                            base, (110, 120, 140)):
                state.active = gi
            if is_active:
                pygame.draw.rect(self.screen, GOLD, tab_rect, 1)
            tab_x += tab_w + 3
        if len(state.groups) < state.MAX_GROUPS:
            if self._button(pygame.Rect(tab_x, cy, 22, 19), "+", self.small_font, T.BTN_GREEN):
                state.add_group()
            tab_x += 25
        if len(state.groups) > 1:
            if self._button(pygame.Rect(tab_x, cy, 22, 19), "x", self.small_font,
                            BTN_DANGER, (220, 70, 70)):
                state.remove_group(state.active)
        return cy + 23

    def _draw_unit_list(self, state, rows, area, cx):
        screen = self.screen
        screen.set_clip(area)
        scroll_px = state.scroll_offset * SCROLL_STEP_PX
        draw_y = area.top - scroll_px
        total_h = 0
        for row in rows:
            rh = FACTION_HEADER_H if row[0] == "header" else UNIT_ROW_H
            if draw_y + rh > area.top and draw_y < area.bottom:
                if row[0] == "header":
                    self._draw_faction_header(row[1], row[2], cx, draw_y, area.w, row[3],
                                              area)
                else:
                    self._draw_unit_row(state, row[1], row[2], cx, draw_y, area.w)
            draw_y += rh
            total_h += rh
        screen.set_clip(None)

        max_scroll_px = max(0, total_h - area.h)
        state.scroll_offset = min(state.scroll_offset, max_scroll_px // SCROLL_STEP_PX)
        if total_h > area.h:   # indicateur de défilement
            sb_h = max(20, int(area.h * area.h / total_h))
            sb_y = (area.top + int((area.h - sb_h) * scroll_px / max_scroll_px)
                    if max_scroll_px > 0 else area.top)
            pygame.draw.rect(screen, (34, 36, 43), (area.right - 9, area.top, 5, area.h),
                             border_radius=3)
            pygame.draw.rect(screen, T.GOLD_DIM, (area.right - 9, sb_y, 5, sb_h), border_radius=3)

    def _draw_faction_header(self, army_name, fc, cx, y, panel_w, count=0, area=None):
        """Bandeau de faction; un clic le replie ou le déplie."""
        rh = FACTION_HEADER_H
        rect = pygame.Rect(cx, y + 1, panel_w - 24, rh - 3)
        hovered = rect.collidepoint(self.mouse_pos) and (area is None
                                                        or area.collidepoint(self.mouse_pos))
        top, bottom = T.darken(fc, 0.62), T.darken(fc, 0.78)
        if hovered:
            top, bottom = T.darken(fc, 0.5), T.darken(fc, 0.68)
        self.screen.blit(T.rounded_gradient(rect.w, rect.h, top, bottom, 4), rect)
        pygame.draw.rect(self.screen, T.lighten(fc, 0.1), (cx, y + 1, 3, rh - 3))
        folded = army_name in self.collapsed and not self.search
        # Chevron dessiné: la police de titre n'a pas les triangles Unicode
        mx, my = cx + 14, y + rh // 2
        pts = ([(mx - 3, my - 5), (mx + 4, my), (mx - 3, my + 5)] if folded
               else [(mx - 5, my - 3), (mx + 5, my - 3), (mx, my + 4)])
        pygame.draw.polygon(self.screen, T.lighten(fc, 0.3), pts)
        fnt = self.faction_font if T.has_glyphs(self.faction_font, army_name) else self.name_font
        T.text(self.screen, army_name, fnt, (cx + 24, y + 3), T.lighten(fc, 0.35))
        T.text(self.screen, f"{count} unité{'s' if count > 1 else ''}", self.stat_font,
               (rect.right - 10, y + 5), T.lighten(fc, 0.2), align="right")
        if hovered and self.clicked and not self.search:
            self.collapsed.symmetric_difference_update({army_name})
            self.clicked = False

    def _draw_unit_row(self, state, army_name, unit_def, cx, y, panel_w):
        """Une unité: nom, stats, boutons -5/-1/+1/+5 et compteur du groupe
        actif. Clic gauche sur la ligne (hors boutons) = +1, droit = -1."""
        screen = self.screen
        uname = unit_def["nom"]
        key = (army_name, uname)
        row_rect = pygame.Rect(cx, y, panel_w - 24, UNIT_ROW_H - 3)
        if state.current.get(key, 0) > 0:
            screen.blit(T.rounded_gradient(row_rect.w, row_rect.h, (52, 46, 32), (38, 35, 28), 5),
                        row_rect.topleft)
            pygame.draw.rect(screen, T.GOLD, (row_rect.x, row_rect.y + 3, 3, row_rect.h - 6))
        if row_rect.collidepoint(self.mouse_pos):
            screen.blit(T.rounded_gradient(row_rect.w, row_rect.h, (255, 255, 255),
                                           (255, 255, 255), 5, 16), row_rect.topleft)

        draw_text(screen, uname, self.name_font, (cx + 10, y + 1), TEXT_BRIGHT)
        traits = ", ".join(unit_def.get("traits", [])) or "-"
        stat_line = (f"Dép:{unit_def['deplacement']} Ble:{unit_def['blessure']} "
                     f"Brv:{unit_def['bravoure']} Svg:{unit_def['sauvegarde']} | "
                     f"{unit_def.get('unit_type', '?')} | {traits}")
        draw_text(screen, stat_line, self.stat_font, (cx + 10, y + 19), TEXT_DIM)

        count = state.current.get(key, 0)
        count_all = state.composition.get(key, 0)
        btn_y, btn_h = y + 8, 20
        bx = cx + panel_w - 200
        minus_hover, plus_hover = T.lighten(T.DANGER, 0.15), T.lighten(T.SUCCESS, 0.1)
        if self._button(pygame.Rect(bx, btn_y, 26, btn_h), "-5", self.small_font,
                        BTN_NORMAL, minus_hover):
            state.remove_unit(army_name, uname, 5)
        if self._button(pygame.Rect(bx + 28, btn_y, 26, btn_h), "-1", self.small_font,
                        BTN_NORMAL, minus_hover):
            state.remove_unit(army_name, uname, 1)
        # Compteur du GROUPE actif (c'est lui que +/- modifie); le total
        # tous groupes confondus est rappelé dessous.
        if count > 0:
            T.pill(screen, (bx + 57, btn_y, 23, btn_h), str(count), self.name_font, T.GOLD, 55)
        else:
            T.text(screen, "0", self.body_font, (bx + 68, btn_y + 1), T.MUTED, align="center")
        if count_all != count:
            tot = self.stat_font.render(f"/{count_all}", True, TEXT_DIM)
            screen.blit(tot, (bx + 68 - tot.get_width() // 2, btn_y + 20))
        if self._button(pygame.Rect(bx + 82, btn_y, 26, btn_h), "+1", self.small_font,
                        BTN_NORMAL, plus_hover):
            state.add_unit(army_name, uname, 1)
        if self._button(pygame.Rect(bx + 110, btn_y, 26, btn_h), "+5", self.small_font,
                        BTN_NORMAL, plus_hover):
            state.add_unit(army_name, uname, 5)

        buttons_zone = pygame.Rect(bx, btn_y, 140, btn_h)
        step = 5 if self.shift else 1          # Maj+clic: par cinq
        if row_rect.collidepoint(self.mouse_pos):
            if self.clicked and not buttons_zone.collidepoint(self.mouse_pos):
                state.add_unit(army_name, uname, step)
            elif self.right_clicked:
                state.remove_unit(army_name, uname, step)

    def army_summary(self, state):
        """Compte CaC / Tir / Sorts / Cavalerie de la composition."""
        melee = ranged = cav = mages = 0
        for (army_name, uname), count in state.composition.items():
            if count <= 0:
                continue
            udef = next((u for u in self.db.get(army_name, {}).get("units", [])
                         if u["nom"] == uname), None)
            if udef is None:
                continue
            if udef.get("sorts"):
                mages += count
            elif any(a[1] >= 4 for a in udef.get("armes", [])):
                ranged += count
            else:
                melee += count
            if udef.get("deplacement", 0) >= 6:
                cav += count
        return melee, ranged, mages, cav

    def _draw_composition_bar(self, i, state, panel, cx, compo_y):
        """Total, résumé tactique et boutons Vider / Copier / Bonus."""
        screen = self.screen
        T.divider(screen, cx, panel.right - 12, compo_y + 1)
        compo_y += 8
        n_groups = sum(1 for gi in range(len(state.groups)) if state.group_size(gi) > 0)
        total_txt = f"Composition: {state.total_units} unités"
        if n_groups > 1:
            total_txt += f"  —  {n_groups} groupes"
        draw_text(screen, total_txt, self.name_font, (cx, compo_y),
                  T.GOLD if state.total_units > 0 else TEXT_DIM)
        if n_groups > 1:
            draw_text(screen, "(chaque groupe est déployé et compté à part)",
                      self.stat_font, (cx, compo_y + 15), TEXT_DIM)
            compo_y += 14

        # Résumé tactique (aide à équilibrer la composition)
        if state.total_units > 0:
            counts = zip(self.army_summary(state), ("CaC", "Tir", "Mage", "Cav"))
            summary = "  ·  ".join(f"{n} {label}" for n, label in counts if n)
            T.text(screen, summary, self.stat_font, (cx + 175, compo_y + 3), (170, 186, 206))

        if self._button(pygame.Rect(panel.right - 70, compo_y - 2, 60, 22), "Vider",
                        self.small_font, BTN_DANGER, (220, 70, 70)):
            state.clear()
        # Miroir: copier cette composition vers l'autre armée
        mirror_label = "Copier →" if i == 0 else "← Copier"
        if (self._button(pygame.Rect(panel.right - 212, compo_y - 2, 64, 22), mirror_label,
                         self.small_font)
                and state.total_units > 0):
            self.states[1 - i].copy_from(state)
        has_bonus = any(v != 0 for v in state.bonuses.values())
        if self._button(pygame.Rect(panel.right - 140, compo_y - 2, 64, 22), "Bonus",
                        self.small_font, ORANGE if has_bonus else BTN_NORMAL,
                        (240, 180, 70) if has_bonus else BTN_HOVER):
            state.show_bonuses = not state.show_bonuses
        return compo_y + 22

    def _draw_bonus_editor(self, state, panel, cx, compo_y):
        """Bonus globaux de l'armée, deux colonnes de -/valeur/+ (±5)."""
        screen = self.screen
        pygame.draw.line(screen, ORANGE, (cx, compo_y), (panel.right - 10, compo_y), 1)
        compo_y += 4
        col_w = (panel.w - 30) // 2
        keys = list(state.bonuses.keys())
        for idx, key in enumerate(keys):
            bx = cx + (idx % 2) * col_w
            by = compo_y + (idx // 2) * 22
            val = state.bonuses[key]
            draw_text(screen, f"{BONUS_LABELS.get(key, key)}:", self.stat_font, (bx, by + 2),
                      TEXT_DIM)
            if self._button(pygame.Rect(bx + 50, by, 20, 18), "-", self.small_font,
                            BTN_NORMAL, T.lighten(T.DANGER, 0.15)):
                state.bonuses[key] = max(-5, val - 1)
            val_color = GREEN if val > 0 else RED if val < 0 else TEXT_DIM
            vt = self.body_font.render(f"{val:+d}" if val != 0 else "0", True, val_color)
            screen.blit(vt, (bx + 76 - vt.get_width() // 2, by))
            if self._button(pygame.Rect(bx + 90, by, 20, 18), "+", self.small_font,
                            BTN_NORMAL, T.lighten(T.SUCCESS, 0.1)):
                state.bonuses[key] = min(5, val + 1)
        return compo_y + (len(keys) + 1) // 2 * 22 + 4

    def _draw_composition_list(self, state, panel, cx, compo_y):
        """Liste compacte: groupe par groupe, puis faction; « ... » si elle
        déborde du panneau."""
        screen = self.screen
        for gi, comp in enumerate(state.groups):
            if not any(c > 0 for c in comp.values()):
                continue
            if len(state.groups) > 1:
                gc = GOLD if gi == state.active else TEXT_DIM
                draw_text(screen, f"▸ {state.group_label(gi)}", self.small_font, (cx, compo_y), gc)
                compo_y += 13
            last_faction = None
            for (army_name, uname), count in sorted(comp.items()):
                if count <= 0:
                    continue
                if army_name != last_faction:
                    fc = self.db.get(army_name, {}).get("color", TEXT_DIM)
                    draw_text(screen, f" {army_name}:", self.small_font, (cx + 6, compo_y), fc)
                    compo_y += 13
                    last_faction = army_name
                draw_text(screen, f"   {uname} x{count}", self.small_font, (cx + 6, compo_y), TEXT)
                compo_y += 13
                if compo_y > panel.bottom - 10:
                    draw_text(screen, "  ...", self.small_font, (cx, compo_y), TEXT_DIM)
                    return

    def _draw_custom_units_button(self):
        from unit_editor import list_custom_units
        nb_custom = len(list_custom_units())
        label = f"Unités custom ({nb_custom})" if nb_custom > 0 else "Créer unités"
        rect = pygame.Rect(self.screen_w - 180, self.screen_h - 52, 160, 36)
        if self._button(rect, label, self.small_font, BTN_NORMAL, BTN_HOVER,
                        T.GOLD_BRIGHT if nb_custom > 0 else TEXT):
            from unit_editor import run_custom_units_screen
            from unit_library import load_custom_units_into_db
            run_custom_units_screen(self.screen, self.screen_w, self.screen_h)
            # Recharger la bibliothèque après édition
            load_custom_units_into_db()
            self.db.update(get_library())

    def _draw_quick_button(self):
        """Combat immédiat: saute l'écran du champ de bataille et reprend la
        dernière carte (mêmes options, même graine)."""
        rect = pygame.Rect(PANEL_MARGIN, self.screen_h - 52, 250, 36)
        enabled = self.can_launch
        hovered = T.button(self.screen, rect, "", self.small_font, self.mouse_pos,
                           enabled=enabled)
        color = T.GOLD_BRIGHT if enabled else T.MUTED
        self.screen.blit(icons.icon("quick", 16, color), (rect.x + 12, rect.centery - 8))
        T.text(self.screen, "Combat immédiat", self.name_font, (rect.x + 34, rect.y + 2), color)
        T.text(self.screen, f"{self.setup.map_name} · Maj+Entrée", self.stat_font,
               (rect.x + 34, rect.y + 19), TEXT_DIM)
        if enabled and hovered and self.clicked:
            return self.quick_launch()
        return None

    def _draw_launch_button(self):
        launch_w, launch_h = 420, 44
        rect = pygame.Rect((self.screen_w - launch_w) // 2, self.screen_h - 55, launch_w, launch_h)
        if not self.can_launch:
            draw_button(self.screen, rect, "Ajoutez des unités aux deux armées", self.body_font,
                        self.mouse_pos, (40, 45, 50), (40, 45, 50), TEXT_DIM)
            return None
        n1, n2 = self.states[0].total_units, self.states[1].total_units
        label = f"SUIVANT : CHAMP DE BATAILLE →  ({n1} vs {n2})"
        if self._button(rect, label, self.body_font, BTN_ACTIVE, (100, 180, 255), TEXT_BRIGHT):
            return self.next_screen()
        return None


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
    return ArmyMenu(screen_w, screen_h).run()
