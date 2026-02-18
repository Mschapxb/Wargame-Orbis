"""Éditeur d'unité personnalisée — interface Pygame.

Permet de créer/éditer des unités custom sauvegardées en JSON
dans le dossier custom_units/.
"""

import json
import os
import pygame
import sys

# ═══════════════════════════════════════════════════════════════
#                    CONSTANTES VISUELLES
# ═══════════════════════════════════════════════════════════════

BG          = (20, 25, 30)
PANEL_BG    = (30, 38, 45)
PANEL_HOVER = (40, 50, 60)
BORDER      = (60, 70, 80)
HIGHLIGHT   = (80, 160, 255)
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
INPUT_BG    = (25, 30, 38)
INPUT_ACTIVE = (35, 45, 60)
CURSOR_COLOR = (200, 200, 255)

CUSTOM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_units")

UNIT_TYPES = ["Infanterie", "Cavalerie", "Large", "Artillerie", "Monstre", "Héros"]
ROLES = ["front", "mid", "back"]
TRAITS = [
    "Encouragement", "Anti-Infanterie", "Anti-Large", "Phalange",
    "Charge montée", "Charge d'aïda", "Sort de bataille (1)",
    "Sort de bataille (2)",
]
SPELLS = [
    "Boule de feu", "Soin", "Armure magique",
    "Projectile magique", "Mur de force",
]


def ensure_custom_dir():
    os.makedirs(CUSTOM_DIR, exist_ok=True)


def list_custom_units():
    """Liste les fichiers JSON dans custom_units/."""
    ensure_custom_dir()
    result = []
    for f in sorted(os.listdir(CUSTOM_DIR)):
        if f.endswith(".json"):
            result.append(f[:-5])  # sans extension
    return result


def load_custom_unit(name):
    """Charge une unité custom depuis son fichier JSON."""
    path = os.path.join(CUSTOM_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_custom_unit(data):
    """Sauvegarde une unité custom en JSON."""
    ensure_custom_dir()
    name = data["nom"]
    path = os.path.join(CUSTOM_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def delete_custom_unit(name):
    path = os.path.join(CUSTOM_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)


# ═══════════════════════════════════════════════════════════════
#                     HELPERS UI
# ═══════════════════════════════════════════════════════════════

def draw_button(screen, rect, text, font, mouse_pos, color=BTN_NORMAL,
                hover_color=BTN_HOVER, text_color=TEXT):
    hovered = rect.collidepoint(mouse_pos)
    c = hover_color if hovered else color
    pygame.draw.rect(screen, c, rect, border_radius=4)
    pygame.draw.rect(screen, BORDER, rect, 1, border_radius=4)
    t = font.render(text, True, text_color)
    screen.blit(t, (rect.x + (rect.w - t.get_width()) // 2,
                     rect.y + (rect.h - t.get_height()) // 2))
    return hovered


def draw_text(screen, text, font, pos, color=TEXT):
    t = font.render(str(text), True, color)
    screen.blit(t, pos)
    return t.get_width(), t.get_height()


class TextInput:
    """Champ de saisie texte."""
    def __init__(self, x, y, w, h, label="", default="", numeric=False, max_len=30):
        self.rect = pygame.Rect(x, y, w, h)
        self.label = label
        self.text = str(default)
        self.active = False
        self.numeric = numeric
        self.max_len = max_len
        self.cursor_pos = len(self.text)
        self.cursor_blink = 0

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
            if self.active:
                self.cursor_pos = len(self.text)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos - 1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
            elif event.key == pygame.K_DELETE:
                self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos + 1:]
            elif event.key == pygame.K_LEFT:
                self.cursor_pos = max(0, self.cursor_pos - 1)
            elif event.key == pygame.K_RIGHT:
                self.cursor_pos = min(len(self.text), self.cursor_pos + 1)
            elif event.key == pygame.K_HOME:
                self.cursor_pos = 0
            elif event.key == pygame.K_END:
                self.cursor_pos = len(self.text)
            elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                self.active = False
            elif event.unicode and len(self.text) < self.max_len:
                ch = event.unicode
                if self.numeric:
                    if ch in "0123456789-+dD":
                        self.text = self.text[:self.cursor_pos] + ch + self.text[self.cursor_pos:]
                        self.cursor_pos += 1
                else:
                    if ch.isprintable():
                        self.text = self.text[:self.cursor_pos] + ch + self.text[self.cursor_pos:]
                        self.cursor_pos += 1

    def draw(self, screen, font, label_font, mouse_pos):
        # Label
        if self.label:
            lbl = label_font.render(self.label, True, TEXT_DIM)
            screen.blit(lbl, (self.rect.x, self.rect.y - 14))
        # Box
        bg = INPUT_ACTIVE if self.active else INPUT_BG
        pygame.draw.rect(screen, bg, self.rect, border_radius=3)
        border_c = HIGHLIGHT if self.active else BORDER
        pygame.draw.rect(screen, border_c, self.rect, 1, border_radius=3)
        # Text
        txt_surf = font.render(self.text, True, TEXT_BRIGHT)
        screen.blit(txt_surf, (self.rect.x + 4, self.rect.y + (self.rect.h - txt_surf.get_height()) // 2))
        # Cursor
        if self.active:
            self.cursor_blink = (self.cursor_blink + 1) % 60
            if self.cursor_blink < 40:
                cx = self.rect.x + 4 + font.size(self.text[:self.cursor_pos])[0]
                pygame.draw.line(screen, CURSOR_COLOR, (cx, self.rect.y + 3), (cx, self.rect.y + self.rect.h - 3), 1)

    @property
    def value(self):
        if self.numeric:
            txt = self.text.strip()
            if not txt or txt in ("-", "+"):
                return 0
            try:
                return int(txt)
            except ValueError:
                return txt  # Pour "1d6" etc.
        return self.text


# ═══════════════════════════════════════════════════════════════
#                   EXPLORATEUR DE FICHIERS
# ═══════════════════════════════════════════════════════════════

def run_file_browser(screen, screen_w, screen_h, start_dir=None):
    """Explorateur de fichiers pour sélectionner un PNG.
    Retourne le chemin du fichier sélectionné ou None."""
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 14)
    small = pygame.font.SysFont("arial", 12)
    title_font = pygame.font.SysFont("arial", 18, bold=True)

    if start_dir is None:
        # Commencer dans le dossier tokens ou le dossier courant
        tokens_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")
        start_dir = tokens_dir if os.path.isdir(tokens_dir) else os.path.expanduser("~")

    current_dir = start_dir
    scroll = 0
    selected = None
    preview_img = None

    while True:
        mouse_pos = pygame.mouse.get_pos()
        clicked = False
        scroll_delta = 0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    clicked = True
                elif event.button == 4:
                    scroll_delta = -1
                elif event.button == 5:
                    scroll_delta = 1
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                if event.key == pygame.K_RETURN and selected:
                    return selected
                if event.key == pygame.K_BACKSPACE:
                    parent = os.path.dirname(current_dir)
                    if parent != current_dir:
                        current_dir = parent
                        scroll = 0
                        selected = None
                        preview_img = None

        screen.fill(BG)

        # Titre
        title = title_font.render("Sélectionner un token (PNG)", True, GOLD)
        screen.blit(title, (20, 12))

        # Chemin actuel
        path_txt = small.render(current_dir, True, TEXT_DIM)
        screen.blit(path_txt, (20, 38))

        # Boutons navigation
        back_btn = pygame.Rect(screen_w - 220, 10, 90, 28)
        if draw_button(screen, back_btn, "← Retour", small, mouse_pos):
            if clicked:
                parent = os.path.dirname(current_dir)
                if parent != current_dir:
                    current_dir = parent
                    scroll = 0
                    selected = None
                    preview_img = None

        cancel_btn = pygame.Rect(screen_w - 120, 10, 100, 28)
        if draw_button(screen, cancel_btn, "Annuler", small, mouse_pos, BTN_DANGER, (220, 70, 70)):
            if clicked:
                return None

        # Lister fichiers
        try:
            entries = sorted(os.listdir(current_dir))
        except PermissionError:
            entries = []

        dirs = [e for e in entries if os.path.isdir(os.path.join(current_dir, e)) and not e.startswith(".")]
        files = [e for e in entries if os.path.isfile(os.path.join(current_dir, e))
                 and e.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))]

        items = [("dir", d) for d in dirs] + [("file", f) for f in files]

        scroll = max(0, scroll + scroll_delta)
        max_scroll = max(0, len(items) - 20)
        scroll = min(scroll, max_scroll)

        # Zone de liste
        list_x, list_y = 20, 60
        list_w = screen_w - 200 if selected else screen_w - 40
        row_h = 26

        for i, (etype, name) in enumerate(items[scroll:scroll + 25]):
            ry = list_y + i * row_h
            if ry > screen_h - 60:
                break

            row_rect = pygame.Rect(list_x, ry, list_w, row_h - 2)
            full_path = os.path.join(current_dir, name)
            is_sel = (selected == full_path)

            if row_rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, PANEL_HOVER, row_rect, border_radius=3)
            if is_sel:
                pygame.draw.rect(screen, (40, 60, 80), row_rect, border_radius=3)

            if etype == "dir":
                icon = "📁 "
                color = ORANGE
            else:
                icon = "🖼 "
                color = GREEN if is_sel else TEXT

            draw_text(screen, f"{icon}{name}", font, (list_x + 6, ry + 3), color)

            if row_rect.collidepoint(mouse_pos) and clicked:
                if etype == "dir":
                    current_dir = full_path
                    scroll = 0
                    selected = None
                    preview_img = None
                else:
                    selected = full_path
                    # Charger aperçu
                    try:
                        preview_img = pygame.image.load(full_path).convert_alpha()
                        # Resize pour aperçu
                        pw = min(150, preview_img.get_width())
                        ph = int(preview_img.get_height() * pw / preview_img.get_width())
                        preview_img = pygame.transform.smoothscale(preview_img, (pw, ph))
                    except Exception:
                        preview_img = None

        # Aperçu du token sélectionné
        if selected:
            prev_x = screen_w - 170
            prev_y = 70
            pygame.draw.rect(screen, PANEL_BG, (prev_x - 10, prev_y - 10, 160, 200), border_radius=6)
            pygame.draw.rect(screen, BORDER, (prev_x - 10, prev_y - 10, 160, 200), 1, border_radius=6)
            draw_text(screen, "Aperçu", small, (prev_x, prev_y - 8), TEXT_DIM)
            if preview_img:
                screen.blit(preview_img, (prev_x + (140 - preview_img.get_width()) // 2, prev_y + 20))
            fname = os.path.basename(selected)
            draw_text(screen, fname[:18], small, (prev_x, prev_y + 160), GREEN)

        # Bouton confirmer
        if selected:
            ok_btn = pygame.Rect((screen_w - 250) // 2, screen_h - 50, 250, 36)
            fname = os.path.basename(selected)
            if draw_button(screen, ok_btn, f"Choisir: {fname[:25]}", font, mouse_pos, BTN_ACTIVE, (100, 180, 255), TEXT_BRIGHT):
                if clicked:
                    return selected

        # Aide
        help_txt = small.render("Clic=Sélectionner  |  Backspace=Dossier parent  |  ENTRÉE=Confirmer  |  ÉCHAP=Annuler", True, TEXT_DIM)
        screen.blit(help_txt, ((screen_w - help_txt.get_width()) // 2, screen_h - 16))

        pygame.display.flip()
        clock.tick(60)


# ═══════════════════════════════════════════════════════════════
#                   ÉDITEUR D'UNITÉ
# ═══════════════════════════════════════════════════════════════

def _default_unit():
    return {
        "nom": "Nouvelle unité",
        "deplacement": 3,
        "blessure": 2,
        "bravoure": 2,
        "sauvegarde": 5,
        "role": "front",
        "size": 1,
        "unit_type": "Infanterie",
        "armes": [("Épée", 1, 2, 3, 3, 0, "1")],
        "traits": [],
        "sorts": [],
        "token_path": "",
        "color": [200, 200, 200],
    }


def run_unit_editor(screen, screen_w, screen_h, unit_data=None):
    """Lance l'éditeur d'unité. Retourne le dict sauvegardé ou None."""
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont("arial", 20, bold=True)
    header_font = pygame.font.SysFont("arial", 15, bold=True)
    font = pygame.font.SysFont("arial", 13)
    small = pygame.font.SysFont("arial", 11)
    label_font = pygame.font.SysFont("arial", 10)

    if unit_data is None:
        data = _default_unit()
    else:
        data = dict(unit_data)
        if "armes" not in data:
            data["armes"] = []
        if "traits" not in data:
            data["traits"] = []
        if "sorts" not in data:
            data["sorts"] = []

    # Champs de saisie
    col1_x = 20
    col2_x = screen_w // 2 + 10
    cy_start = 60
    fw = screen_w // 2 - 40  # field width
    fh = 24

    inp_nom = TextInput(col1_x, cy_start, fw, fh, "Nom", data["nom"], max_len=30)
    inp_dep = TextInput(col1_x, cy_start + 45, 60, fh, "Déplacement", str(data["deplacement"]), numeric=True, max_len=3)
    inp_pv = TextInput(col1_x + 80, cy_start + 45, 60, fh, "PV", str(data["blessure"]), numeric=True, max_len=4)
    inp_brv = TextInput(col1_x + 160, cy_start + 45, 60, fh, "Bravoure", str(data["bravoure"]), numeric=True, max_len=2)
    inp_svg = TextInput(col1_x + 240, cy_start + 45, 60, fh, "Sauvegarde", str(data["sauvegarde"]), numeric=True, max_len=2)
    inp_size = TextInput(col1_x + 320, cy_start + 45, 60, fh, "Taille", str(data["size"]), numeric=True, max_len=2)

    # Couleur
    color = list(data.get("color", [200, 200, 200]))

    # Armes (liste de champs)
    # Chaque arme: [nom, portée, nb_att, toucher, blesser, perf, dégâts]
    arme_inputs = []
    for a in data["armes"]:
        arme_inputs.append(_make_arme_inputs(a, col1_x, 0, fw))

    # État
    sel_type_idx = UNIT_TYPES.index(data["unit_type"]) if data["unit_type"] in UNIT_TYPES else 0
    sel_role_idx = ROLES.index(data["role"]) if data["role"] in ROLES else 0
    active_traits = set(data.get("traits", []))
    active_spells = set(data.get("sorts", []))
    token_path = data.get("token_path", "")
    token_preview = None
    if token_path and os.path.exists(token_path):
        try:
            token_preview = pygame.image.load(token_path).convert_alpha()
            token_preview = pygame.transform.smoothscale(token_preview, (48, 48))
        except Exception:
            token_preview = None

    scroll_y = 0
    error_msg = ""
    all_inputs = [inp_nom, inp_dep, inp_pv, inp_brv, inp_svg, inp_size]

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        clicked = False
        scroll_delta = 0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    clicked = True
                elif event.button == 4:
                    scroll_delta = -20
                elif event.button == 5:
                    scroll_delta = 20
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None

            for inp in all_inputs:
                inp.handle_event(event)
            for arme_row in arme_inputs:
                for inp in arme_row:
                    inp.handle_event(event)

        scroll_y = max(0, scroll_y + scroll_delta)

        screen.fill(BG)

        # Offset pour scroll
        oy = -scroll_y

        # Titre
        title = title_font.render("ÉDITEUR D'UNITÉ", True, GOLD)
        screen.blit(title, (20, 10 + oy))

        # === Champs principaux ===
        cy = cy_start + oy
        inp_nom.rect.y = cy
        inp_nom.draw(screen, font, label_font, mouse_pos)

        cy += 45
        for inp in [inp_dep, inp_pv, inp_brv, inp_svg, inp_size]:
            inp.rect.y = cy
            inp.draw(screen, font, label_font, mouse_pos)

        # === Type et Rôle ===
        cy += 50
        draw_text(screen, "Type:", label_font, (col1_x, cy), TEXT_DIM)
        bx = col1_x + 40
        for ti, tname in enumerate(UNIT_TYPES):
            btn = pygame.Rect(bx, cy, 80, 22)
            is_sel = (ti == sel_type_idx)
            bc = BTN_ACTIVE if is_sel else BTN_NORMAL
            if draw_button(screen, btn, tname, small, mouse_pos, bc, (100, 180, 255) if is_sel else BTN_HOVER):
                if clicked:
                    sel_type_idx = ti
            bx += 84

        cy += 28
        draw_text(screen, "Rôle:", label_font, (col1_x, cy), TEXT_DIM)
        bx = col1_x + 40
        for ri, rname in enumerate(ROLES):
            btn = pygame.Rect(bx, cy, 60, 22)
            is_sel = (ri == sel_role_idx)
            bc = BTN_ACTIVE if is_sel else BTN_NORMAL
            if draw_button(screen, btn, rname, small, mouse_pos, bc, (100, 180, 255) if is_sel else BTN_HOVER):
                if clicked:
                    sel_role_idx = ri
            bx += 64

        # === Couleur ===
        bx += 40
        draw_text(screen, "Couleur:", label_font, (bx, cy), TEXT_DIM)
        bx += 55
        for ci, cn in enumerate(["R", "G", "B"]):
            # Minus
            mb = pygame.Rect(bx, cy, 18, 22)
            if draw_button(screen, mb, "-", small, mouse_pos, BTN_DANGER, (220, 70, 70)):
                if clicked:
                    color[ci] = max(0, color[ci] - 20)
            bx += 20
            vt = small.render(f"{cn}:{color[ci]}", True, TEXT)
            screen.blit(vt, (bx, cy + 3))
            bx += 42
            pb = pygame.Rect(bx, cy, 18, 22)
            if draw_button(screen, pb, "+", small, mouse_pos, GREEN, (100, 220, 100)):
                if clicked:
                    color[ci] = min(255, color[ci] + 20)
            bx += 24
        # Preview color
        pygame.draw.circle(screen, tuple(color), (bx + 10, cy + 11), 10)
        pygame.draw.circle(screen, BORDER, (bx + 10, cy + 11), 10, 1)

        # === Token ===
        cy += 34
        draw_text(screen, "Token:", label_font, (col1_x, cy), TEXT_DIM)
        token_btn = pygame.Rect(col1_x + 50, cy, 160, 24)
        token_label = os.path.basename(token_path)[:20] if token_path else "Parcourir..."
        if draw_button(screen, token_btn, token_label, small, mouse_pos, BTN_NORMAL, BTN_HOVER, GREEN if token_path else TEXT):
            if clicked:
                result = run_file_browser(screen, screen_w, screen_h)
                if result:
                    token_path = result
                    try:
                        token_preview = pygame.image.load(token_path).convert_alpha()
                        token_preview = pygame.transform.smoothscale(token_preview, (48, 48))
                    except Exception:
                        token_preview = None
                # Reafficher
                screen.fill(BG)

        if token_preview:
            screen.blit(token_preview, (col1_x + 220, cy - 12))
        if token_path:
            clear_token = pygame.Rect(col1_x + 275, cy, 20, 24)
            if draw_button(screen, clear_token, "✕", small, mouse_pos, BTN_DANGER, (220, 70, 70)):
                if clicked:
                    token_path = ""
                    token_preview = None

        # === ARMES ===
        cy += 40
        pygame.draw.line(screen, BORDER, (col1_x, cy), (screen_w - 20, cy), 1)
        cy += 6
        draw_text(screen, "ARMES", header_font, (col1_x, cy), ORANGE)

        add_arme_btn = pygame.Rect(col1_x + 70, cy, 100, 22)
        if draw_button(screen, add_arme_btn, "+ Arme", small, mouse_pos, GREEN, (100, 220, 100)):
            if clicked and len(arme_inputs) < 5:
                arme_inputs.append(_make_arme_inputs(("Arme", 1, 1, 3, 3, 0, "1"), col1_x, 0, fw))
        cy += 28

        arme_to_remove = -1
        for ai, arme_row in enumerate(arme_inputs):
            # Labels
            labels = ["Nom", "Portée", "Att.", "Touch.", "Bless.", "Perf.", "Dégâts"]
            lx = col1_x
            for li, lbl in enumerate(labels):
                w = 120 if li == 0 else (45 if li < 6 else 60)
                draw_text(screen, lbl, label_font, (lx, cy), TEXT_DIM)
                arme_row[li].rect.y = cy + 12
                arme_row[li].rect.x = lx
                arme_row[li].draw(screen, font, label_font, mouse_pos)
                lx += w + 4

            # Bouton supprimer
            del_btn = pygame.Rect(lx + 4, cy + 12, 22, fh)
            if draw_button(screen, del_btn, "✕", small, mouse_pos, BTN_DANGER, (220, 70, 70)):
                if clicked:
                    arme_to_remove = ai

            cy += 42

        if arme_to_remove >= 0 and len(arme_inputs) > 0:
            arme_inputs.pop(arme_to_remove)

        # === TRAITS ===
        cy += 10
        pygame.draw.line(screen, BORDER, (col1_x, cy), (screen_w - 20, cy), 1)
        cy += 6
        draw_text(screen, "TRAITS", header_font, (col1_x, cy), ORANGE)
        cy += 22

        bx = col1_x
        for trait in TRAITS:
            is_on = trait in active_traits
            tw = font.size(trait)[0] + 16
            btn = pygame.Rect(bx, cy, tw, 22)
            bc = BTN_ACTIVE if is_on else BTN_NORMAL
            if draw_button(screen, btn, trait, small, mouse_pos, bc, (100, 180, 255) if is_on else BTN_HOVER):
                if clicked:
                    if is_on:
                        active_traits.discard(trait)
                    else:
                        active_traits.add(trait)
            bx += tw + 4
            if bx > screen_w - 100:
                bx = col1_x
                cy += 26
        cy += 28

        # === SORTS ===
        draw_text(screen, "SORTS", header_font, (col1_x, cy), ORANGE)
        cy += 22
        bx = col1_x
        for spell in SPELLS:
            is_on = spell in active_spells
            sw = font.size(spell)[0] + 16
            btn = pygame.Rect(bx, cy, sw, 22)
            bc = BTN_ACTIVE if is_on else BTN_NORMAL
            if draw_button(screen, btn, spell, small, mouse_pos, bc, (100, 180, 255) if is_on else BTN_HOVER):
                if clicked:
                    if is_on:
                        active_spells.discard(spell)
                    else:
                        active_spells.add(spell)
            bx += sw + 4

        # === Erreur ===
        cy += 40
        if error_msg:
            draw_text(screen, error_msg, font, (col1_x, cy), RED)

        # === Boutons bas ===
        btn_y = screen_h - 50
        save_btn = pygame.Rect((screen_w - 400) // 2, btn_y, 180, 36)
        if draw_button(screen, save_btn, "💾 Sauvegarder", font, mouse_pos, BTN_ACTIVE, (100, 180, 255), TEXT_BRIGHT):
            if clicked:
                result = _build_result(inp_nom, inp_dep, inp_pv, inp_brv, inp_svg, inp_size,
                                       sel_type_idx, sel_role_idx, arme_inputs, active_traits,
                                       active_spells, token_path, color)
                if isinstance(result, str):
                    error_msg = result
                else:
                    # Copier le token dans tokens/ si nécessaire
                    if token_path and os.path.exists(token_path):
                        tokens_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")
                        os.makedirs(tokens_dir, exist_ok=True)
                        dest = os.path.join(tokens_dir, f"{result['nom']}.png")
                        if os.path.abspath(token_path) != os.path.abspath(dest):
                            import shutil
                            try:
                                shutil.copy2(token_path, dest)
                            except Exception:
                                pass
                    save_custom_unit(result)
                    return result

        cancel_btn = pygame.Rect((screen_w - 400) // 2 + 200, btn_y, 180, 36)
        if draw_button(screen, cancel_btn, "Annuler", font, mouse_pos, BTN_DANGER, (220, 70, 70)):
            if clicked:
                return None

        # Aide
        help_txt = small.render("Tab=Champ suivant  |  Molette=Défiler  |  ÉCHAP=Annuler", True, TEXT_DIM)
        screen.blit(help_txt, ((screen_w - help_txt.get_width()) // 2, screen_h - 16))

        pygame.display.flip()
        clock.tick(60)

    return None


def _make_arme_inputs(arme_tuple, x, y, fw):
    """Crée les TextInputs pour une arme."""
    nom, portee, nb_att, toucher, blesser, perf, degats = arme_tuple
    return [
        TextInput(x, y, 120, 24, "", str(nom), max_len=20),
        TextInput(x, y, 45, 24, "", str(portee), numeric=True, max_len=3),
        TextInput(x, y, 45, 24, "", str(nb_att), numeric=True, max_len=3),
        TextInput(x, y, 45, 24, "", str(toucher), numeric=True, max_len=2),
        TextInput(x, y, 45, 24, "", str(blesser), numeric=True, max_len=2),
        TextInput(x, y, 45, 24, "", str(perf), numeric=True, max_len=3),
        TextInput(x, y, 60, 24, "", str(degats), numeric=True, max_len=6),
    ]


def _build_result(inp_nom, inp_dep, inp_pv, inp_brv, inp_svg, inp_size,
                  sel_type_idx, sel_role_idx, arme_inputs, active_traits,
                  active_spells, token_path, color):
    """Construit le dict résultat. Retourne un str si erreur."""
    nom = inp_nom.text.strip()
    if not nom:
        return "Le nom est obligatoire"

    try:
        dep = int(inp_dep.text) if inp_dep.text.strip() else 3
    except ValueError:
        return "Déplacement invalide"
    try:
        pv = int(inp_pv.text) if inp_pv.text.strip() else 2
    except ValueError:
        return "PV invalide"
    try:
        brv = int(inp_brv.text) if inp_brv.text.strip() else 2
    except ValueError:
        return "Bravoure invalide"
    try:
        svg = int(inp_svg.text) if inp_svg.text.strip() else 5
    except ValueError:
        return "Sauvegarde invalide"
    try:
        size = int(inp_size.text) if inp_size.text.strip() else 1
    except ValueError:
        return "Taille invalide"

    armes = []
    for ai, row in enumerate(arme_inputs):
        anom = row[0].text.strip()
        if not anom:
            continue
        try:
            aportee = int(row[1].text) if row[1].text.strip() else 1
            anb = int(row[2].text) if row[2].text.strip() else 1
            atouch = int(row[3].text) if row[3].text.strip() else 3
            abless = int(row[4].text) if row[4].text.strip() else 3
            aperf = int(row[5].text) if row[5].text.strip() else 0
        except ValueError:
            return f"Arme {ai+1}: valeur numérique invalide"
        adeg = row[6].text.strip() or "1"
        armes.append((anom, aportee, anb, atouch, abless, aperf, adeg))

    if not armes:
        return "Au moins une arme est requise"

    return {
        "nom": nom,
        "deplacement": dep,
        "blessure": pv,
        "bravoure": brv,
        "sauvegarde": svg,
        "role": ROLES[sel_role_idx],
        "size": size,
        "unit_type": UNIT_TYPES[sel_type_idx],
        "armes": armes,
        "traits": sorted(active_traits),
        "sorts": sorted(active_spells),
        "token_path": token_path,
        "color": color,
    }


# ═══════════════════════════════════════════════════════════════
#              ÉCRAN DE GESTION DES UNITÉS CUSTOM
# ═══════════════════════════════════════════════════════════════

def run_custom_units_screen(screen, screen_w, screen_h):
    """Écran de liste des unités custom avec créer/éditer/supprimer.
    Retourne quand l'utilisateur appuie sur Retour."""
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont("arial", 20, bold=True)
    font = pygame.font.SysFont("arial", 14)
    small = pygame.font.SysFont("arial", 12)
    stat_font = pygame.font.SysFont("arial", 11)

    scroll = 0

    while True:
        mouse_pos = pygame.mouse.get_pos()
        clicked = False
        scroll_delta = 0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    clicked = True
                elif event.button == 4:
                    scroll_delta = -1
                elif event.button == 5:
                    scroll_delta = 1
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return

        screen.fill(BG)

        # Titre
        title = title_font.render("UNITÉS PERSONNALISÉES", True, GOLD)
        screen.blit(title, (20, 12))

        # Boutons haut
        new_btn = pygame.Rect(screen_w - 280, 10, 130, 30)
        if draw_button(screen, new_btn, "+ Nouvelle unité", small, mouse_pos, GREEN, (100, 220, 100)):
            if clicked:
                result = run_unit_editor(screen, screen_w, screen_h)
                if result:
                    # Recharger dans la librairie
                    _reload_custom_in_library()

        back_btn = pygame.Rect(screen_w - 140, 10, 120, 30)
        if draw_button(screen, back_btn, "← Retour", small, mouse_pos):
            if clicked:
                return

        # Liste des unités custom
        customs = list_custom_units()
        scroll = max(0, min(scroll + scroll_delta, max(0, len(customs) - 15)))

        cy = 55
        if not customs:
            draw_text(screen, "Aucune unité personnalisée.", font, (20, cy), TEXT_DIM)
            draw_text(screen, "Cliquez '+ Nouvelle unité' pour en créer une.", small, (20, cy + 22), TEXT_DIM)
        else:
            for i, uname in enumerate(customs[scroll:scroll + 15]):
                data = load_custom_unit(uname)
                if data is None:
                    continue

                row_rect = pygame.Rect(20, cy, screen_w - 40, 50)
                if row_rect.collidepoint(mouse_pos):
                    pygame.draw.rect(screen, PANEL_HOVER, row_rect, border_radius=4)
                pygame.draw.rect(screen, BORDER, row_rect, 1, border_radius=4)

                # Token preview
                token_path = data.get("token_path", "")
                if token_path and os.path.exists(token_path):
                    try:
                        img = pygame.image.load(token_path).convert_alpha()
                        img = pygame.transform.smoothscale(img, (36, 36))
                        screen.blit(img, (30, cy + 7))
                    except Exception:
                        ucol = tuple(data.get("color", [200, 200, 200]))
                        pygame.draw.circle(screen, ucol, (48, cy + 25), 16)
                else:
                    ucol = tuple(data.get("color", [200, 200, 200]))
                    pygame.draw.circle(screen, ucol, (48, cy + 25), 16)

                # Info
                draw_text(screen, data["nom"], font, (75, cy + 4), TEXT_BRIGHT)
                stat_line = (f"Dép:{data['deplacement']} PV:{data['blessure']} Brv:{data['bravoure']} "
                             f"Svg:{data['sauvegarde']} | {data.get('unit_type', '?')} | {data.get('role', '?')}")
                draw_text(screen, stat_line, stat_font, (75, cy + 22), TEXT_DIM)

                armes_txt = ", ".join(a[0] for a in data.get("armes", []))
                draw_text(screen, armes_txt[:50], stat_font, (75, cy + 35), TEXT_DIM)

                # Boutons éditer / supprimer
                edit_btn = pygame.Rect(screen_w - 180, cy + 12, 70, 26)
                if draw_button(screen, edit_btn, "Éditer", small, mouse_pos):
                    if clicked:
                        result = run_unit_editor(screen, screen_w, screen_h, data)
                        if result:
                            # Si le nom a changé, supprimer l'ancien
                            if result["nom"] != uname:
                                delete_custom_unit(uname)
                            _reload_custom_in_library()

                del_btn = pygame.Rect(screen_w - 100, cy + 12, 70, 26)
                if draw_button(screen, del_btn, "Suppr.", small, mouse_pos, BTN_DANGER, (220, 70, 70)):
                    if clicked:
                        delete_custom_unit(uname)
                        _reload_custom_in_library()

                cy += 54

        pygame.display.flip()
        clock.tick(60)


def _reload_custom_in_library():
    """Recharge les unités custom dans UNIT_DATABASE."""
    from unit_library import load_custom_units_into_db
    load_custom_units_into_db()
