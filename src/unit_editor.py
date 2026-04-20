"""Éditeur d'unité WW1 personnalisée — interface Pygame.

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

BG           = (20, 25, 30)
PANEL_BG     = (30, 38, 45)
PANEL_HOVER  = (40, 50, 60)
BORDER       = (60, 70, 80)
HIGHLIGHT    = (80, 160, 255)
TEXT         = (210, 210, 210)
TEXT_DIM     = (130, 130, 140)
TEXT_BRIGHT  = (255, 255, 255)
GOLD         = (255, 215, 0)
GREEN        = (80, 200, 80)
RED          = (200, 80, 80)
ORANGE       = (220, 160, 50)
BTN_NORMAL   = (50, 60, 75)
BTN_HOVER    = (65, 80, 100)
BTN_ACTIVE   = (80, 160, 255)
BTN_DANGER   = (180, 50, 50)
INPUT_BG     = (25, 30, 38)
INPUT_ACTIVE = (35, 45, 60)
CURSOR_COLOR = (200, 200, 255)

CUSTOM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_units")

UNIT_TYPES = ["Infanterie", "Cavalerie", "Artillerie", "Blindé", "Héros"]
ROLES = ["front", "mid", "back"]

# Traits WW1 disponibles dans l'éditeur
TRAITS = [
    "Encouragement",
    "Anti-Infanterie",
    "Anti-Blindé",
    "Planqué",
    "Embusqué",
    "Charge montée",
    "Tir rapide",
    "Tir de saturation",
    "Terreur",
    "Blindage",
    "Blindage lourd",
    "Assaut",
    "Infiltration",
    "Gaz de combat",
    "Lance-flammes",
    "Moral d'acier",
    "Tir indirect",
    "Position défensive",
    "Position haute",
    "Reconnaissance",
    "Sapeur",
    "Réparation blindé",
    "Ecrase barbelés",
    "Artillerie",
    "Artillerie legere",
    "Tactique d'assaut",
]

SPELLS = []  # Pas de sorts magiques en WW1


def ensure_custom_dir():
    os.makedirs(CUSTOM_DIR, exist_ok=True)


def list_custom_units():
    ensure_custom_dir()
    result = []
    for f in sorted(os.listdir(CUSTOM_DIR)):
        if f.endswith(".json"):
            result.append(f[:-5])
    return result


def load_custom_unit(name):
    path = os.path.join(CUSTOM_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_custom_unit(data):
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
        if self.label:
            lbl = label_font.render(self.label, True, TEXT_DIM)
            screen.blit(lbl, (self.rect.x, self.rect.y - 14))
        bg = INPUT_ACTIVE if self.active else INPUT_BG
        pygame.draw.rect(screen, bg, self.rect, border_radius=3)
        border_c = HIGHLIGHT if self.active else BORDER
        pygame.draw.rect(screen, border_c, self.rect, 1, border_radius=3)
        txt_surf = font.render(self.text, True, TEXT_BRIGHT)
        screen.blit(txt_surf, (self.rect.x + 4, self.rect.y + (self.rect.h - txt_surf.get_height()) // 2))
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
                return txt
        return self.text


# ═══════════════════════════════════════════════════════════════
#                   EXPLORATEUR DE FICHIERS
# ═══════════════════════════════════════════════════════════════

def run_file_browser(screen, screen_w, screen_h, start_dir=None):
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 14)
    small = pygame.font.SysFont("arial", 12)
    title_font = pygame.font.SysFont("arial", 18, bold=True)

    if start_dir is None:
        tokens_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")
        start_dir = tokens_dir if os.path.isdir(tokens_dir) else os.path.expanduser("~")

    current_dir = start_dir
    scroll = 0
    selected = None
    preview_img = None

    while True:
        mouse_pos = pygame.mouse.get_pos()
        clicked = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked = True
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None

        screen.fill(BG)
        draw_text(screen, "Sélectionner un token PNG", title_font, (20, 12), GOLD)

        back_btn = pygame.Rect(screen_w - 130, 10, 110, 28)
        if draw_button(screen, back_btn, "← Retour", small, mouse_pos):
            if clicked:
                return None

        confirm_btn = None
        if selected and selected.lower().endswith(".png"):
            confirm_btn = pygame.Rect(screen_w - 250, 10, 110, 28)
            if draw_button(screen, confirm_btn, "✓ Choisir", small, mouse_pos, GREEN, (100, 220, 100)):
                if clicked:
                    return selected

        # Dossier courant
        draw_text(screen, f"Dossier: {current_dir}", small, (20, 48), TEXT_DIM)

        # Bouton parent
        parent_btn = pygame.Rect(20, 68, 80, 22)
        if draw_button(screen, parent_btn, "↑ Parent", small, mouse_pos):
            if clicked:
                parent = os.path.dirname(current_dir)
                if parent != current_dir:
                    current_dir = parent
                    scroll = 0
                    selected = None
                    preview_img = None

        # Liste des fichiers
        try:
            entries = sorted(os.listdir(current_dir))
        except PermissionError:
            entries = []

        dirs = [e for e in entries if os.path.isdir(os.path.join(current_dir, e))]
        files = [e for e in entries if e.lower().endswith(".png")]
        all_entries = [("dir", d) for d in dirs] + [("file", f) for f in files]

        list_top = 98
        row_h = 22
        visible = (screen_h - list_top - 80) // row_h
        scroll = max(0, min(scroll, max(0, len(all_entries) - visible)))

        for i, (etype, name) in enumerate(all_entries[scroll:scroll + visible]):
            ry = list_top + i * row_h
            color = TEXT_DIM if etype == "dir" else TEXT
            prefix = "📁 " if etype == "dir" else "🖼 "
            full = os.path.join(current_dir, name)
            is_sel = (full == selected)
            if is_sel:
                pygame.draw.rect(screen, BTN_ACTIVE, (18, ry, screen_w // 2 - 40, row_h - 2), border_radius=3)
            txt = font.render(f"{prefix}{name}", True, TEXT_BRIGHT if is_sel else color)
            screen.blit(txt, (22, ry + 2))

            if clicked and pygame.Rect(18, ry, screen_w // 2 - 40, row_h).collidepoint(mouse_pos):
                if etype == "dir":
                    current_dir = full
                    scroll = 0
                    selected = None
                    preview_img = None
                else:
                    selected = full
                    try:
                        img = pygame.image.load(full).convert_alpha()
                        pw = min(200, screen_w // 3)
                        img = pygame.transform.smoothscale(img, (pw, pw))
                        preview_img = img
                    except Exception:
                        preview_img = None

        # Aperçu
        if preview_img:
            px = screen_w // 2 + 20
            screen.blit(preview_img, (px, list_top))
            draw_text(screen, os.path.basename(selected), small, (px, list_top + preview_img.get_height() + 4), TEXT_DIM)

        pygame.display.flip()
        clock.tick(60)

    return None


# ═══════════════════════════════════════════════════════════════
#                   ÉDITEUR D'UNITÉ PRINCIPAL
# ═══════════════════════════════════════════════════════════════

def _make_arme_inputs(arme_tuple, x, y, fw):
    nom, portee, nb_att, toucher, blesser, perf, degats = arme_tuple
    return [
        TextInput(x, y, 130, 24, "", str(nom), max_len=25),
        TextInput(x, y,  45, 24, "", str(portee),  numeric=True, max_len=3),
        TextInput(x, y,  40, 24, "", str(nb_att),  numeric=True, max_len=2),
        TextInput(x, y,  40, 24, "", str(toucher),  numeric=True, max_len=2),
        TextInput(x, y,  40, 24, "", str(blesser),  numeric=True, max_len=2),
        TextInput(x, y,  45, 24, "", str(perf),     numeric=True, max_len=3),
        TextInput(x, y,  60, 24, "", str(degats),   numeric=True, max_len=8),
    ]


def _build_result(inp_nom, inp_dep, inp_pv, inp_brv, inp_svg, inp_size,
                  sel_type_idx, sel_role_idx, arme_inputs, active_traits,
                  active_spells, token_path, color):
    nom = inp_nom.text.strip()
    if not nom:
        return "Le nom est obligatoire"
    try:
        dep = int(inp_dep.text) if inp_dep.text.strip() else 3
        pv  = int(inp_pv.text)  if inp_pv.text.strip()  else 2
        brv = int(inp_brv.text) if inp_brv.text.strip() else 2
        svg = int(inp_svg.text) if inp_svg.text.strip() else 7
        size= int(inp_size.text) if inp_size.text.strip() else 1
    except ValueError as e:
        return f"Valeur numérique invalide : {e}"

    armes = []
    for ai, row in enumerate(arme_inputs):
        anom = row[0].text.strip()
        if not anom:
            continue
        try:
            aportee = int(row[1].text) if row[1].text.strip() else 1
            anb     = int(row[2].text) if row[2].text.strip() else 1
            atouch  = int(row[3].text) if row[3].text.strip() else 3
            abless  = int(row[4].text) if row[4].text.strip() else 3
            aperf   = int(row[5].text) if row[5].text.strip() else 0
        except ValueError:
            return f"Arme {ai+1}: valeur numérique invalide"
        adeg = row[6].text.strip() or "1"
        armes.append((anom, aportee, anb, atouch, abless, aperf, adeg))

    if not armes:
        return "Au moins une arme est requise"

    return {
        "nom":        nom,
        "deplacement": dep,
        "blessure":   pv,
        "bravoure":   brv,
        "sauvegarde": svg,
        "role":       ROLES[sel_role_idx],
        "size":       size,
        "unit_type":  UNIT_TYPES[sel_type_idx],
        "armes":      armes,
        "traits":     sorted(active_traits),
        "sorts":      [],
        "token_path": os.path.relpath(token_path, CUSTOM_DIR) if token_path else "",
        "color":      color,
    }


def run_unit_editor(screen, screen_w, screen_h, existing_data=None):
    """Éditeur d'unité WW1. Retourne le dict sauvegardé ou None si annulé."""
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont("arial", 18, bold=True)
    font       = pygame.font.SysFont("arial", 14)
    small      = pygame.font.SysFont("arial", 12)
    label_font = pygame.font.SysFont("arial", 11)

    d = existing_data or {}

    # ── Champs principaux ──
    inp_nom  = TextInput(160, 50,  250, 26, "Nom", d.get("nom", ""), max_len=30)
    inp_dep  = TextInput(160, 88,   55, 26, "Déplacement", str(d.get("deplacement", 3)), numeric=True)
    inp_pv   = TextInput(260, 88,   55, 26, "PV",          str(d.get("blessure", 2)),    numeric=True)
    inp_brv  = TextInput(360, 88,   55, 26, "Bravoure",    str(d.get("bravoure", 2)),    numeric=True)
    inp_svg  = TextInput(460, 88,   55, 26, "Sauvegarde",  str(d.get("sauvegarde", 7)),  numeric=True)
    inp_size = TextInput(560, 88,   40, 26, "Taille",      str(d.get("size", 1)),         numeric=True)

    all_inputs_main = [inp_nom, inp_dep, inp_pv, inp_brv, inp_svg, inp_size]

    # Type et rôle
    sel_type_idx = UNIT_TYPES.index(d.get("unit_type", "Infanterie")) if d.get("unit_type") in UNIT_TYPES else 0
    sel_role_idx = ROLES.index(d.get("role", "front")) if d.get("role") in ROLES else 0

    # ── Armes (4 slots) ──
    DEFAULT_ARMES = [
        ("Fusil",  6, 1, 3, 3,  0, "1"),
        ("Baïonnette", 1, 1, 3, 3, 0, "1"),
        ("", 1, 1, 3, 3, 0, "1"),
        ("", 1, 1, 3, 3, 0, "1"),
    ]
    existing_armes = list(d.get("armes", []))
    while len(existing_armes) < 4:
        existing_armes.append(DEFAULT_ARMES[len(existing_armes)])

    ARME_Y0 = 180
    ARME_DY = 32
    arme_inputs = [_make_arme_inputs(existing_armes[i], 0, ARME_Y0 + i * ARME_DY, 0) for i in range(4)]

    # ── Traits ──
    active_traits = set(d.get("traits", []))

    # ── Token + couleur ──
    token_path = ""
    if d.get("token_path"):
        tp = d["token_path"]
        if not os.path.isabs(tp):
            tp = os.path.normpath(os.path.join(CUSTOM_DIR, tp))
        if os.path.exists(tp):
            token_path = tp

    color = list(d.get("color", [180, 140, 60]))
    color_inputs = [
        TextInput(0, 0, 48, 22, "R", str(color[0]), numeric=True, max_len=3),
        TextInput(0, 0, 48, 22, "G", str(color[1]), numeric=True, max_len=3),
        TextInput(0, 0, 48, 22, "B", str(color[2]), numeric=True, max_len=3),
    ]

    error_msg = ""
    preview_token = None
    if token_path:
        try:
            preview_token = pygame.image.load(token_path).convert_alpha()
            preview_token = pygame.transform.smoothscale(preview_token, (48, 48))
        except Exception:
            preview_token = None

    # ── Colonnes de traits (2 colonnes) ──
    TRAIT_X0 = 20
    TRAIT_Y0 = 400
    TRAIT_COL_W = (screen_w // 2 - 40) // 2
    TRAIT_DY = 20

    while True:
        mouse_pos = pygame.mouse.get_pos()
        clicked = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked = True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None
            for inp in all_inputs_main:
                inp.handle_event(event)
            for row in arme_inputs:
                for inp in row:
                    inp.handle_event(event)
            for ci in color_inputs:
                ci.handle_event(event)

        screen.fill(BG)
        draw_text(screen, "ÉDITEUR D'UNITÉ WW1", title_font, (20, 14), GOLD)

        # ── Section principale ──
        for inp in all_inputs_main:
            inp.draw(screen, font, label_font, mouse_pos)

        draw_text(screen, "Type:", label_font, (160, 122), TEXT_DIM)
        for i, ut in enumerate(UNIT_TYPES):
            br = pygame.Rect(220 + i * 90, 118, 84, 22)
            bc = BTN_ACTIVE if i == sel_type_idx else BTN_NORMAL
            if draw_button(screen, br, ut, label_font, mouse_pos, bc, BTN_HOVER):
                if clicked:
                    sel_type_idx = i

        draw_text(screen, "Rôle:", label_font, (160, 146), TEXT_DIM)
        for i, rl in enumerate(ROLES):
            br = pygame.Rect(220 + i * 90, 142, 84, 22)
            bc = BTN_ACTIVE if i == sel_role_idx else BTN_NORMAL
            if draw_button(screen, br, rl, label_font, mouse_pos, bc, BTN_HOVER):
                if clicked:
                    sel_role_idx = i

        # ── En-têtes armes ──
        draw_text(screen, "ARMES", font, (20, ARME_Y0 - 22), GOLD)
        headers = ["Nom", "Portée", "Att.", "Toucher", "Blesser", "Perf.", "Dégâts"]
        col_xs = [20, 160, 210, 255, 300, 345, 395]
        for hx, ht in zip(col_xs, headers):
            draw_text(screen, ht, label_font, (hx, ARME_Y0 - 12), TEXT_DIM)

        for i, row in enumerate(arme_inputs):
            y = ARME_Y0 + i * ARME_DY
            xs = col_xs
            for j, inp in enumerate(row):
                inp.rect.x = xs[j]
                inp.rect.y = y
                inp.draw(screen, font, label_font, mouse_pos)

        # ── Traits ──
        draw_text(screen, "TRAITS", font, (TRAIT_X0, TRAIT_Y0 - 18), GOLD)
        for i, trait in enumerate(TRAITS):
            col = i % 2
            row = i // 2
            tx = TRAIT_X0 + col * TRAIT_COL_W
            ty = TRAIT_Y0 + row * TRAIT_DY
            is_active = trait in active_traits
            cb_rect = pygame.Rect(tx, ty, 14, 14)
            pygame.draw.rect(screen, (80, 160, 80) if is_active else (50, 60, 70), cb_rect, border_radius=2)
            pygame.draw.rect(screen, BORDER, cb_rect, 1, border_radius=2)
            if is_active:
                pygame.draw.line(screen, TEXT_BRIGHT, (tx + 2, ty + 7), (tx + 5, ty + 11), 2)
                pygame.draw.line(screen, TEXT_BRIGHT, (tx + 5, ty + 11), (tx + 12, ty + 3), 2)
            draw_text(screen, trait, label_font, (tx + 18, ty), TEXT if is_active else TEXT_DIM)
            if clicked and pygame.Rect(tx, ty, TRAIT_COL_W - 5, TRAIT_DY).collidepoint(mouse_pos):
                if trait in active_traits:
                    active_traits.remove(trait)
                else:
                    active_traits.add(trait)

        # ── Token + couleur (côté droit) ──
        right_x = screen_w // 2 + 20
        draw_text(screen, "TOKEN PNG", font, (right_x, 50), GOLD)

        token_btn = pygame.Rect(right_x, 72, 160, 26)
        if draw_button(screen, token_btn, "Choisir token...", small, mouse_pos):
            if clicked:
                result = run_file_browser(screen, screen_w, screen_h)
                if result:
                    token_path = result
                    try:
                        preview_token = pygame.image.load(token_path).convert_alpha()
                        preview_token = pygame.transform.smoothscale(preview_token, (64, 64))
                    except Exception:
                        preview_token = None

        if preview_token:
            screen.blit(preview_token, (right_x + 170, 60))
            draw_text(screen, os.path.basename(token_path), label_font, (right_x + 170, 128), TEXT_DIM)
        elif token_path:
            draw_text(screen, "⚠ Token introuvable", label_font, (right_x, 105), RED)

        draw_text(screen, "COULEUR (RGB)", font, (right_x, 150), GOLD)
        for i, ci in enumerate(color_inputs):
            ci.rect.x = right_x + i * 58
            ci.rect.y = 170
            ci.draw(screen, font, label_font, mouse_pos)
        try:
            color = [max(0, min(255, int(ci.text or "0"))) for ci in color_inputs]
        except Exception:
            color = [180, 140, 60]
        pygame.draw.circle(screen, tuple(color), (right_x + 185, 180), 18)
        pygame.draw.circle(screen, BORDER, (right_x + 185, 180), 18, 1)

        # Description des traits WW1
        draw_text(screen, "RÉFÉRENCE TRAITS", font, (right_x, 215), GOLD)
        trait_desc = [
            ("Encouragement",    "+moral aux alliés proches"),
            ("Blindage/lourd",   "bonus sauvegarde (+1/+2)"),
            ("Terreur",          "cause peur (effroi lvl 2)"),
            ("Tir rapide",       "+1 attaque (Lee-Enfield style)"),
            ("Tir de saturation","= Anti-Infanterie"),
            ("Assaut/Infiltration", "bonus de charge / +1 vitesse"),
            ("Anti-Blindé",      "efficace vs tanks"),
            ("Gaz de combat",    "aura de peur lvl 1"),
            ("Lance-flammes",    "aura de peur lvl 2"),
            ("Moral d'acier",    "immunité peur"),
            ("Artillerie",       "immobile, longue portée"),
            ("Embusqué",         "+1 moral en position"),
            ("Reconnaissance",   "+1 vitesse"),
        ]
        for i, (tn, td) in enumerate(trait_desc):
            ty = 236 + i * 16
            draw_text(screen, f"• {tn}:", label_font, (right_x, ty), ORANGE)
            draw_text(screen, td, label_font, (right_x + 150, ty), TEXT_DIM)

        # ── Erreur ──
        if error_msg:
            draw_text(screen, f"⚠ {error_msg}", font, (20, screen_h - 70), RED)

        # ── Boutons bas ──
        save_btn = pygame.Rect(screen_w // 2 - 200, screen_h - 45, 180, 34)
        if draw_button(screen, save_btn, "💾 Sauvegarder", font, mouse_pos, GREEN, (100, 220, 100)):
            if clicked:
                result = _build_result(
                    inp_nom, inp_dep, inp_pv, inp_brv, inp_svg, inp_size,
                    sel_type_idx, sel_role_idx, arme_inputs,
                    active_traits, set(), token_path, color
                )
                if isinstance(result, str):
                    error_msg = result
                else:
                    save_custom_unit(result)
                    return result

        cancel_btn = pygame.Rect(screen_w // 2 + 20, screen_h - 45, 180, 34)
        if draw_button(screen, cancel_btn, "✗ Annuler", font, mouse_pos, BTN_DANGER, (220, 70, 70)):
            if clicked:
                return None

        pygame.display.flip()
        clock.tick(60)


# ═══════════════════════════════════════════════════════════════
#              ÉCRAN DE GESTION DES UNITÉS CUSTOM
# ═══════════════════════════════════════════════════════════════

def run_custom_units_screen(screen, screen_w, screen_h):
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont("arial", 20, bold=True)
    font  = pygame.font.SysFont("arial", 14)
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
        draw_text(screen, "UNITÉS WW1 PERSONNALISÉES", title_font, (20, 12), GOLD)

        new_btn = pygame.Rect(screen_w - 280, 10, 130, 30)
        if draw_button(screen, new_btn, "+ Nouvelle unité", small, mouse_pos, GREEN, (100, 220, 100)):
            if clicked:
                result = run_unit_editor(screen, screen_w, screen_h)
                if result:
                    _reload_custom_in_library()

        back_btn = pygame.Rect(screen_w - 140, 10, 120, 30)
        if draw_button(screen, back_btn, "← Retour", small, mouse_pos):
            if clicked:
                return

        customs = list_custom_units()
        scroll = max(0, min(scroll + scroll_delta, max(0, len(customs) - 15)))
        cy = 55

        if not customs:
            draw_text(screen, "Aucune unité WW1 personnalisée.", font, (20, cy), TEXT_DIM)
            draw_text(screen, "Cliquez '+ Nouvelle unité' pour en créer une.", small, (20, cy + 22), TEXT_DIM)
        else:
            for uname in customs[scroll:scroll + 15]:
                data = load_custom_unit(uname)
                if data is None:
                    continue
                row_rect = pygame.Rect(20, cy, screen_w - 40, 50)
                if row_rect.collidepoint(mouse_pos):
                    pygame.draw.rect(screen, PANEL_HOVER, row_rect, border_radius=4)
                pygame.draw.rect(screen, BORDER, row_rect, 1, border_radius=4)

                token_path = data.get("token_path", "")
                if token_path and not os.path.isabs(token_path):
                    token_path = os.path.normpath(os.path.join(CUSTOM_DIR, token_path))
                if token_path and os.path.exists(token_path):
                    try:
                        img = pygame.image.load(token_path).convert_alpha()
                        img = pygame.transform.smoothscale(img, (36, 36))
                        screen.blit(img, (30, cy + 7))
                    except Exception:
                        ucol = tuple(data.get("color", [180, 140, 60]))
                        pygame.draw.circle(screen, ucol, (48, cy + 25), 16)
                else:
                    ucol = tuple(data.get("color", [180, 140, 60]))
                    pygame.draw.circle(screen, ucol, (48, cy + 25), 16)

                draw_text(screen, data["nom"], font, (75, cy + 4), TEXT_BRIGHT)
                stat_line = (f"Dép:{data['deplacement']} PV:{data['blessure']} Brv:{data['bravoure']} "
                             f"Svg:{data['sauvegarde']} | {data.get('unit_type','?')} | {data.get('role','?')}")
                draw_text(screen, stat_line, stat_font, (75, cy + 22), TEXT_DIM)
                armes_txt = ", ".join(a[0] for a in data.get("armes", []))
                draw_text(screen, armes_txt[:60], stat_font, (75, cy + 35), TEXT_DIM)

                edit_btn = pygame.Rect(screen_w - 180, cy + 12, 70, 26)
                if draw_button(screen, edit_btn, "Éditer", small, mouse_pos):
                    if clicked:
                        result = run_unit_editor(screen, screen_w, screen_h, data)
                        if result:
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
    from unit_library import load_custom_units_into_db
    load_custom_units_into_db()
