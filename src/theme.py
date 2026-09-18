"""Thème visuel commun: palette, polices et éléments d'interface.

Style: ardoise sombre et or patiné — moderne par la sobriété (dégradés
doux, arrondis, ombres portées, espacements réguliers), dans l'esprit du
jeu par les titres à empattements dorés, les filets et losanges
d'ornement, les teintes de parchemin.

Aucune dépendance hors pygame. Les polices viennent du système (Palatino
Linotype / Garamond / Georgia pour les titres, Segoe UI / Calibri pour le
texte) avec repli sur la police de pygame: le jeu reste identique partout,
seulement moins élégant sans ces polices.

Tout ce qui est coûteux (dégradés, ombres, fonds, textes dorés) est mis en
cache par taille: dessiner un panneau coûte quelques blits.
"""
import math
import os
import random

import pygame

# ═══════════════════════════════════════════════════════════════
#                          PALETTE
# ═══════════════════════════════════════════════════════════════

INK = (12, 13, 17)              # fond le plus sombre
BG_TOP = (24, 27, 34)
BG_BOTTOM = (11, 12, 16)
PANEL_TOP = (31, 34, 42)
PANEL_BOTTOM = (22, 24, 30)
PANEL_EDGE = (74, 64, 44)       # bronze sombre
PANEL_EDGE_DARK = (6, 7, 9)

GOLD = (218, 180, 98)
GOLD_BRIGHT = (246, 214, 138)
GOLD_DIM = (148, 118, 64)
PARCHMENT = (234, 226, 206)     # texte principal
PARCHMENT_DIM = (160, 153, 138)  # texte secondaire
MUTED = (112, 108, 100)

TEAM = ((96, 152, 255), (238, 88, 76))
TEAM_DARK = ((40, 66, 120), (112, 38, 34))

SUCCESS = (116, 198, 124)
WARNING = (232, 170, 70)
DANGER = (222, 92, 80)

# Boutons (couleurs de base; relief et survol sont dérivés)
BTN = (48, 52, 63)
BTN_GOLD = (184, 142, 64)
BTN_RED = (126, 46, 42)
BTN_GREEN = (52, 104, 66)

ORNAMENT = GOLD_DIM


def lighten(c, k):
    return tuple(min(255, int(v + (255 - v) * k)) for v in c[:3])


def darken(c, k):
    return tuple(max(0, int(v * (1 - k))) for v in c[:3])


def luminance(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


# ═══════════════════════════════════════════════════════════════
#                          POLICES
# ═══════════════════════════════════════════════════════════════

_FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_ROLES = {
    # (fichiers Windows, noms système de repli)
    'title': (("palab.ttf", "GARABD.TTF", "georgiab.ttf"),
              ("palatinolinotype", "georgia", "dejavuserif", "liberationserif", "serif")),
    'serif': (("pala.ttf", "GARA.TTF", "georgia.ttf"),
              ("palatinolinotype", "georgia", "dejavuserif", "liberationserif", "serif")),
    'ui': (("segoeui.ttf", "calibri.ttf"),
           ("segoeui", "calibri", "dejavusans", "liberationsans", "arial")),
    'ui_bold': (("seguisb.ttf", "segoeuib.ttf", "calibrib.ttf"),
                ("segoeuisemibold", "calibri", "dejavusans", "arial")),
}
_fonts = {}
_font_paths = {}


def _font_path(role):
    if role in _font_paths:
        return _font_paths[role]
    files, names = _ROLES[role]
    path = None
    for f in files:
        p = os.path.join(_FONT_DIR, f)
        if os.path.exists(p):
            path = p
            break
    if path is None:
        for n in names:
            p = pygame.font.match_font(n, bold=role in ('title', 'ui_bold'))
            if p:
                path = p
                break
    _font_paths[role] = path
    return path


def font(role, size):
    """Police d'un rôle ('title', 'serif', 'ui', 'ui_bold') à une taille."""
    k = (role, size)
    f = _fonts.get(k)
    if f is None:
        if not pygame.font.get_init():
            pygame.font.init()
        path = _font_path(role)
        try:
            f = pygame.font.Font(path, size) if path else None
        except (OSError, pygame.error):
            f = None
        if f is None:
            f = pygame.font.Font(None, int(size * 1.3))
            f.set_bold(role in ('title', 'ui_bold'))
        _fonts[k] = f
    return f


# ═══════════════════════════════════════════════════════════════
#                     PRIMITIVES MISES EN CACHE
# ═══════════════════════════════════════════════════════════════

_cache = {}


def _cached(key, build):
    s = _cache.get(key)
    if s is None:
        if len(_cache) > 600:
            _cache.clear()
        s = build()
        _cache[key] = s
    return s


def vgradient(w, h, top, bottom, alpha=255):
    """Surface w×h en dégradé vertical (mise en cache)."""
    w, h = max(1, int(w)), max(1, int(h))

    def build():
        s = pygame.Surface((1, h), pygame.SRCALPHA)
        for y in range(h):
            t = y / max(1, h - 1)
            c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            s.set_at((0, y), c + (alpha,))
        return pygame.transform.scale(s, (w, h))
    return _cached(('vg', w, h, top, bottom, alpha), build)


def _rounded_mask(w, h, radius):
    def build():
        m = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(m, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
        return m
    return _cached(('mask', w, h, radius), build)


def rounded_gradient(w, h, top, bottom, radius, alpha=255):
    """Dégradé vertical découpé en rectangle arrondi."""
    w, h = max(1, int(w)), max(1, int(h))

    def build():
        s = vgradient(w, h, top, bottom, alpha).copy()
        s.blit(_rounded_mask(w, h, radius), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return s
    return _cached(('rg', w, h, top, bottom, radius, alpha), build)


def soft_shadow(w, h, radius=10, spread=10, alpha=120):
    """Ombre portée floue d'un rectangle arrondi (réduction/agrandissement)."""
    w, h = max(1, int(w)), max(1, int(h))

    def build():
        W, H = w + spread * 2, h + spread * 2
        small = pygame.Surface((max(2, W // 4), max(2, H // 4)), pygame.SRCALPHA)
        pygame.draw.rect(small, (0, 0, 0, alpha),
                         (spread // 4, spread // 4, max(1, w // 4), max(1, h // 4)),
                         border_radius=max(1, radius // 4))
        s = pygame.transform.smoothscale(small, (W, H))
        s = pygame.transform.smoothscale(
            pygame.transform.smoothscale(s, (max(2, W // 2), max(2, H // 2))), (W, H))
        return s
    return _cached(('sh', w, h, radius, spread, alpha), build)


def background(w, h, seed=7):
    """Fond d'écran: dégradé ardoise, halo chaud en haut, grain et
    vignettage. Calculé une fois par taille."""
    def build():
        s = vgradient(w, h, BG_TOP, BG_BOTTOM).copy()
        glow = pygame.Surface((w // 4 + 1, h // 4 + 1), pygame.SRCALPHA)
        cx, cy = glow.get_width() // 2, 0
        R = max(glow.get_width(), glow.get_height())
        for r in range(R, 0, -2):
            a = int(26 * (1 - r / R) ** 2)
            pygame.draw.circle(glow, (120, 96, 52, a), (cx, cy), r)
        s.blit(pygame.transform.smoothscale(glow, (w, h)), (0, 0))
        rng = random.Random(seed)
        grain = pygame.Surface((w, h), pygame.SRCALPHA)
        for _ in range(w * h // 90):
            x, y = rng.randrange(w), rng.randrange(h)
            v = rng.choice((255, 0))
            grain.set_at((x, y), (v, v, v, rng.randint(6, 14)))
        s.blit(grain, (0, 0))
        s.blit(vignette(w, h, 150), (0, 0))
        return s
    return _cached(('bg', w, h, seed), build)


def vignette(w, h, strength=140):
    def build():
        small = pygame.Surface((64, 40), pygame.SRCALPHA)
        for y in range(40):
            for x in range(64):
                dx, dy = (x - 31.5) / 32, (y - 19.5) / 20
                d = min(1.0, math.hypot(dx, dy) / 1.25)
                small.set_at((x, y), (0, 0, 0, int(strength * d ** 2.4)))
        return pygame.transform.smoothscale(small, (w, h))
    return _cached(('vig', w, h, strength), build)


# ═══════════════════════════════════════════════════════════════
#                          TEXTE
# ═══════════════════════════════════════════════════════════════

def text(surf, s, fnt, pos, color=PARCHMENT, align="left", shadow=True, alpha=255):
    """Texte avec ombre douce. pos = (x, y) du coin gauche, du centre
    (align="center") ou du bord droit (align="right"). Retourne le rect."""
    img = fnt.render(s, True, color)
    x, y = pos
    if align == "center":
        x -= img.get_width() // 2
    elif align == "right":
        x -= img.get_width()
    if shadow:
        sh = fnt.render(s, True, INK)
        sh.set_alpha(int(170 * alpha / 255))
        surf.blit(sh, (x + 1, y + 1))
    if alpha < 255:
        img.set_alpha(alpha)
    surf.blit(img, (x, y))
    return pygame.Rect(x, y, img.get_width(), img.get_height())


def gold_text(s, fnt, top=GOLD_BRIGHT, bottom=GOLD_DIM):
    """Texte doré (dégradé vertical), mis en cache."""
    def build():
        base = fnt.render(s, True, (255, 255, 255))
        grad = vgradient(base.get_width(), base.get_height(), top, bottom)
        out = base.copy()
        out.blit(grad, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return out
    return _cached(('gt', s, id(fnt), top, bottom), build)


def diamond(surf, cx, cy, r, color, filled=True):
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    if filled:
        pygame.draw.polygon(surf, color, pts)
    else:
        pygame.draw.polygon(surf, color, pts, 1)


def divider(surf, x1, x2, y, color=ORNAMENT, gem=True, gem_bg=None):
    """Filet d'ornement: deux traits qui s'estompent vers les bords, un
    losange au centre."""
    w = max(2, x2 - x1)

    def build():
        s = pygame.Surface((w, 1), pygame.SRCALPHA)
        for x in range(w):
            t = 1 - abs(x - w / 2) / (w / 2)
            s.set_at((x, 0), color + (int(230 * t ** 0.7),))
        return s
    surf.blit(_cached(('div', w, color), build), (x1, y))
    if gem:
        cx = (x1 + x2) // 2
        if gem_bg is not None:
            pygame.draw.rect(surf, gem_bg, (cx - 13, y - 4, 26, 9))
        diamond(surf, cx, y, 4, color)
        diamond(surf, cx - 9, y, 2, color)
        diamond(surf, cx + 9, y, 2, color)


def title(surf, s, cx, y, size=30, subtitle=None):
    """Titre d'écran doré, avec ombre et filet d'ornement. Retourne le y
    sous le bloc."""
    fnt = font('title', size)
    img = gold_text(s, fnt)
    x = cx - img.get_width() // 2
    sh = fnt.render(s, True, INK)
    sh.set_alpha(200)
    surf.blit(sh, (x + 2, y + 2))
    surf.blit(img, (x, y))
    y2 = y + img.get_height() + 3
    half = max(160, img.get_width() // 2 + 60)
    divider(surf, cx - half, cx + half, y2)
    y2 += 8
    if subtitle:
        text(surf, subtitle, font('serif', 14), (cx, y2), PARCHMENT_DIM, align="center")
        y2 += 20
    return y2


# ═══════════════════════════════════════════════════════════════
#                       PANNEAUX ET CADRES
# ═══════════════════════════════════════════════════════════════

def corner_marks(surf, rect, color=ORNAMENT, size=8):
    """Équerres d'angle, à la manière d'un coin de reliure."""
    x0, y0, x1, y1 = rect.left + 3, rect.top + 3, rect.right - 4, rect.bottom - 4
    for (x, y, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        pygame.draw.line(surf, color, (x, y), (x + sx * size, y))
        pygame.draw.line(surf, color, (x, y), (x, y + sy * size))


def panel(surf, rect, accent=None, radius=10, shadow=True, alpha=255, ornate=True):
    """Panneau: ombre douce, fond en dégradé, liseré bronze, reflet en haut,
    bandeau de couleur (accent) et équerres d'angle."""
    rect = pygame.Rect(rect)
    if shadow:
        sh = soft_shadow(rect.w, rect.h, radius, 12, 150)
        surf.blit(sh, (rect.x - 12, rect.y - 12 + 5))
    surf.blit(rounded_gradient(rect.w, rect.h, PANEL_TOP, PANEL_BOTTOM, radius, alpha), rect.topleft)
    if accent is not None:
        glow = vgradient(max(1, rect.w - 2 * radius), 30, darken(accent, 0.35), PANEL_TOP, 90)
        surf.blit(glow, (rect.x + radius, rect.y + 3))
        band = rounded_gradient(rect.w, 4, lighten(accent, 0.15), darken(accent, 0.2), 2)
        surf.blit(band, (rect.x, rect.y))
    pygame.draw.rect(surf, PANEL_EDGE_DARK, rect.inflate(2, 2), 1, border_radius=radius + 1)
    pygame.draw.rect(surf, PANEL_EDGE, rect, 1, border_radius=radius)
    hy = rect.y + (5 if accent is not None else 1)
    pygame.draw.line(surf, lighten(PANEL_TOP, 0.12), (rect.x + radius, hy), (rect.right - radius, hy))
    if ornate:
        corner_marks(surf, rect.inflate(-6, -6))
    return rect


def glass(surf, rect, alpha=205, radius=8, edge=GOLD_DIM):
    """Cadre translucide (HUD en bataille): laisse deviner la carte."""
    rect = pygame.Rect(rect)
    surf.blit(rounded_gradient(rect.w, rect.h, (22, 24, 30), (12, 13, 17), radius, alpha),
              rect.topleft)
    pygame.draw.rect(surf, darken(edge, 0.25), rect, 1, border_radius=radius)
    pygame.draw.line(surf, lighten((22, 24, 30), 0.12), (rect.x + radius, rect.y + 1),
                     (rect.right - radius, rect.y + 1))
    return rect


def section_header(surf, s, x, y, w, color=GOLD, size=15):
    """Intitulé de section: texte à empattements, filet dessous."""
    fnt = font('title', size)
    r = text(surf, s, fnt, (x, y), color)
    pygame.draw.line(surf, darken(color, 0.55), (x, r.bottom + 2), (x + w, r.bottom + 2))
    return r.bottom + 6


# ═══════════════════════════════════════════════════════════════
#                          BOUTONS
# ═══════════════════════════════════════════════════════════════

def button(surf, rect, label, fnt, mouse_pos, base=BTN, text_color=None,
           selected=False, enabled=True, radius=6, hover_base=None):
    """Bouton en relief doux. Retourne True si survolé (et actif).

    base: couleur de fond (le relief et le survol en sont dérivés).
    text_color: None = choisi selon la clarté du fond.
    selected: liseré doré (bouton-bascule choisi)."""
    rect = pygame.Rect(rect)
    hovered = enabled and rect.collidepoint(mouse_pos)
    b = hover_base if (hovered and hover_base is not None) else base
    if not enabled:
        b = darken(base, 0.35)
    elif hovered and hover_base is None:
        b = lighten(base, 0.14)
    top, bottom = lighten(b, 0.16), darken(b, 0.18)
    if rect.h >= 26:
        sh = soft_shadow(rect.w, rect.h, radius, 4, 110)
        surf.blit(sh, (rect.x - 4, rect.y - 4 + 2))
    surf.blit(rounded_gradient(rect.w, rect.h, top, bottom, radius), rect.topleft)
    pygame.draw.line(surf, lighten(b, 0.35), (rect.x + radius, rect.y + 1),
                     (rect.right - radius - 1, rect.y + 1))
    edge = GOLD if selected else darken(b, 0.5)
    pygame.draw.rect(surf, edge, rect, 2 if selected else 1, border_radius=radius)
    if selected:
        pygame.draw.rect(surf, GOLD_DIM, rect.inflate(4, 4), 1, border_radius=radius + 2)
    if text_color is None:
        text_color = (30, 23, 12) if luminance(b) > 135 else PARCHMENT
    if not enabled:
        text_color = MUTED
    img = fnt.render(label, True, text_color)
    tx = rect.x + (rect.w - img.get_width()) // 2
    ty = rect.y + (rect.h - img.get_height()) // 2
    if luminance(b) <= 135:
        shd = fnt.render(label, True, INK)
        shd.set_alpha(160)
        surf.blit(shd, (tx + 1, ty + 1))
    surf.blit(img, (tx, ty))
    return hovered


def pill(surf, rect, label, fnt, color=GOLD, fill_alpha=40):
    """Pastille (compteur, étiquette)."""
    rect = pygame.Rect(rect)
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, fill_alpha), s.get_rect(), border_radius=rect.h // 2)
    pygame.draw.rect(s, (*color, 150), s.get_rect(), 1, border_radius=rect.h // 2)
    surf.blit(s, rect.topleft)
    img = fnt.render(label, True, lighten(color, 0.2))
    surf.blit(img, (rect.centerx - img.get_width() // 2, rect.centery - img.get_height() // 2))
    return rect


# ═══════════════════════════════════════════════════════════════
#                          JAUGES
# ═══════════════════════════════════════════════════════════════

def bar(surf, rect, segments, radius=None, back=(28, 30, 36)):
    """Jauge segmentée: segments = [(fraction, couleur), ...] de gauche à
    droite. Reflet en haut, liseré sombre."""
    rect = pygame.Rect(rect)
    if rect.w < 2 or rect.h < 2:
        return rect
    radius = rect.h // 2 if radius is None else radius
    surf.blit(rounded_gradient(rect.w, rect.h, darken(back, 0.3), back, radius), rect.topleft)
    x = rect.x
    total = 0.0
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    for frac, color in segments:
        w = int(round(rect.w * max(0.0, frac)))
        if total + frac >= 0.999:
            w = rect.right - x
        if w > 0:
            layer.blit(vgradient(w, rect.h, lighten(color, 0.22), darken(color, 0.2)),
                       (x - rect.x, 0))
        x += w
        total += frac
    layer.blit(_rounded_mask(rect.w, rect.h, radius), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(layer, rect.topleft)
    gloss = vgradient(max(1, rect.w - 2), max(1, rect.h // 2), (255, 255, 255), (255, 255, 255), 26)
    surf.blit(gloss, (rect.x + 1, rect.y + 1))
    pygame.draw.rect(surf, INK, rect, 1, border_radius=radius)
    return rect


# ═══════════════════════════════════════════════════════════════
#                       BANNIÈRE (cartouche)
# ═══════════════════════════════════════════════════════════════

def banner(label, fnt, color, alpha=255):
    """Cartouche d'annonce: fond sombre translucide, liserés de la couleur
    de l'événement, pointes latérales et losanges. Retourne une surface."""
    img = gold_text(label, fnt, lighten(color, 0.7), lighten(color, 0.2))
    pad_x, pad_y = 34, 7
    w, h = img.get_width() + pad_x * 2, img.get_height() + pad_y * 2

    def build():
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        body = [(12, 0), (w - 12, 0), (w, h // 2), (w - 12, h), (12, h), (0, h // 2)]
        pygame.draw.polygon(s, (14, 15, 19, 215), body)
        pygame.draw.polygon(s, (*darken(color, 0.2), 230), body, 1)
        inner = [(15, 3), (w - 15, 3), (w - 4, h // 2), (w - 15, h - 3), (15, h - 3), (4, h // 2)]
        pygame.draw.polygon(s, (*color, 70), inner, 1)
        for x in (18, w - 18):
            diamond(s, x, h // 2, 3, color)
        s.blit(img, (pad_x, pad_y))
        return s
    s = _cached(('ban', label, id(fnt), color), build)
    if alpha < 255:
        s = s.copy()
        s.set_alpha(alpha)
    return s
