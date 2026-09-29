"""Icônes vectorielles de l'interface (barre d'outils, menus, notifications).

Tracées à quatre fois leur taille puis réduites (lissage): des contours nets
et antialiasés sans image à livrer. Mises en cache par (nom, taille, couleur).

    icons.icon("play", 20, (240, 230, 210))  → Surface SRCALPHA 20×20
"""
import math

import pygame

_SS = 4                 # sur-échantillonnage
_cache = {}


def icon(name, size, color):
    key = (name, size, tuple(color))
    s = _cache.get(key)
    if s is None:
        big = pygame.Surface((size * _SS, size * _SS), pygame.SRCALPHA)
        _DRAW.get(name, _unknown)(big, size * _SS, tuple(color))
        s = pygame.transform.smoothscale(big, (size, size))
        if len(_cache) > 400:
            _cache.clear()
        _cache[key] = s
    return s


def names():
    return sorted(_DRAW)


# ─── Tracés (sur une toile carrée de côté S) ───

def _w(S, k=0.09):
    return max(2, int(S * k))


def _unknown(s, S, c):
    pygame.draw.circle(s, c, (S // 2, S // 2), S // 3, _w(S))


def _play(s, S, c):
    pygame.draw.polygon(s, c, [(S * 0.3, S * 0.2), (S * 0.3, S * 0.8), (S * 0.8, S * 0.5)])


def _pause(s, S, c):
    w = S * 0.18
    for x in (S * 0.28, S * 0.54):
        pygame.draw.rect(s, c, (x, S * 0.2, w, S * 0.6), border_radius=int(S * 0.04))


def _chevrons(n):
    def draw(s, S, c):
        w = S * 0.8 / (n + 0.6)
        x0 = S * 0.12
        for i in range(n):
            x = x0 + i * w * 0.85
            pygame.draw.polygon(s, c, [(x, S * 0.24), (x, S * 0.76), (x + w, S * 0.5)])
    return draw


def _magnifier(sign):
    def draw(s, S, c):
        w = _w(S)
        cx, cy, r = S * 0.42, S * 0.42, S * 0.26
        pygame.draw.circle(s, c, (cx, cy), r, w)
        pygame.draw.line(s, c, (cx + r * 0.7, cy + r * 0.7), (S * 0.86, S * 0.86), int(w * 1.4))
        if sign:
            pygame.draw.line(s, c, (cx - r * 0.5, cy), (cx + r * 0.5, cy), w)
        if sign == "+":
            pygame.draw.line(s, c, (cx, cy - r * 0.5), (cx, cy + r * 0.5), w)
    return draw


def _fit(s, S, c):
    w = _w(S)
    a, b, L = S * 0.14, S * 0.86, S * 0.26
    for (x, y, dx, dy) in ((a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)):
        pygame.draw.line(s, c, (x, y), (x + dx * L, y), w)
        pygame.draw.line(s, c, (x, y), (x, y + dy * L), w)
    pygame.draw.rect(s, c, (S * 0.36, S * 0.4, S * 0.28, S * 0.2), max(1, w // 2))


def _crosshair(s, S, c):
    w = _w(S)
    m = S / 2
    pygame.draw.circle(s, c, (m, m), S * 0.28, w)
    for (x1, y1, x2, y2) in ((m, S * 0.08, m, S * 0.3), (m, S * 0.7, m, S * 0.92),
                             (S * 0.08, m, S * 0.3, m), (S * 0.7, m, S * 0.92, m)):
        pygame.draw.line(s, c, (x1, y1), (x2, y2), w)
    pygame.draw.circle(s, c, (m, m), S * 0.05)


def _flag(s, S, c):
    w = _w(S)
    pygame.draw.line(s, c, (S * 0.26, S * 0.12), (S * 0.26, S * 0.9), w)
    pygame.draw.polygon(s, c, [(S * 0.3, S * 0.14), (S * 0.82, S * 0.28), (S * 0.3, S * 0.5)])


def _map(s, S, c):
    w = _w(S)
    pts = [(S * 0.1, S * 0.22), (S * 0.37, S * 0.12), (S * 0.63, S * 0.22), (S * 0.9, S * 0.12),
           (S * 0.9, S * 0.78), (S * 0.63, S * 0.88), (S * 0.37, S * 0.78), (S * 0.1, S * 0.88)]
    pygame.draw.polygon(s, c, pts, w)
    pygame.draw.line(s, c, (S * 0.37, S * 0.12), (S * 0.37, S * 0.78), w)
    pygame.draw.line(s, c, (S * 0.63, S * 0.22), (S * 0.63, S * 0.88), w)


def _layers(s, S, c):
    w = _w(S)
    for i, y in enumerate((S * 0.3, S * 0.48, S * 0.66)):
        pts = [(S * 0.5, y - S * 0.16), (S * 0.88, y), (S * 0.5, y + S * 0.16), (S * 0.12, y)]
        if i == 0:
            pygame.draw.polygon(s, c, pts)
        else:
            pygame.draw.lines(s, c, False, pts[1:] + pts[:1], w)


def _camera(s, S, c):
    pygame.draw.rect(s, c, (S * 0.08, S * 0.28, S * 0.58, S * 0.44), border_radius=int(S * 0.08))
    pygame.draw.polygon(s, c, [(S * 0.68, S * 0.5), (S * 0.92, S * 0.3), (S * 0.92, S * 0.7)])


def _record(s, S, c):
    pygame.draw.circle(s, c, (S / 2, S / 2), S * 0.3)


def _restart(s, S, c):
    w = _w(S)
    m, r = S / 2, S * 0.3
    rect = pygame.Rect(m - r, m - r, 2 * r, 2 * r)
    pygame.draw.arc(s, c, rect, math.radians(40), math.radians(330), w)
    ax, ay = m + r * math.cos(math.radians(40)), m - r * math.sin(math.radians(40))
    pygame.draw.polygon(s, c, [(ax + S * 0.14, ay - S * 0.02), (ax - S * 0.06, ay - S * 0.14),
                               (ax - S * 0.02, ay + S * 0.1)])


def _gear(s, S, c):
    m = S / 2
    for k in range(8):
        a = k * math.pi / 4
        pts = []
        for da, rr in ((-0.2, 0.3), (-0.14, 0.44), (0.14, 0.44), (0.2, 0.3)):
            pts.append((m + math.cos(a + da) * S * rr, m + math.sin(a + da) * S * rr))
        pygame.draw.polygon(s, c, pts)
    pygame.draw.circle(s, c, (m, m), S * 0.31)
    pygame.draw.circle(s, (0, 0, 0, 0), (m, m), S * 0.13)


def _help(s, S, c):
    w = _w(S)
    m = S / 2
    pygame.draw.circle(s, c, (m, m), S * 0.42, w)
    r = S * 0.13
    pygame.draw.arc(s, c, pygame.Rect(m - r, S * 0.24, 2 * r, 2 * r), math.radians(-60),
                    math.radians(190), w)
    pygame.draw.line(s, c, (m + r * 0.5, S * 0.47), (m, S * 0.56), w)
    pygame.draw.line(s, c, (m, S * 0.56), (m, S * 0.62), w)
    pygame.draw.circle(s, c, (m, S * 0.74), w * 0.8)


def _menu(s, S, c):
    w = int(S * 0.1)
    for y in (0.28, 0.5, 0.72):
        pygame.draw.line(s, c, (S * 0.18, S * y), (S * 0.82, S * y), w)


def _folder(s, S, c):
    pygame.draw.polygon(s, c, [(S * 0.08, S * 0.24), (S * 0.4, S * 0.24), (S * 0.48, S * 0.34),
                               (S * 0.92, S * 0.34), (S * 0.92, S * 0.8), (S * 0.08, S * 0.8)])


def _close(s, S, c):
    w = int(S * 0.11)
    pygame.draw.line(s, c, (S * 0.22, S * 0.22), (S * 0.78, S * 0.78), w)
    pygame.draw.line(s, c, (S * 0.78, S * 0.22), (S * 0.22, S * 0.78), w)


def _check(s, S, c):
    w = int(S * 0.12)
    pygame.draw.lines(s, c, False, [(S * 0.18, S * 0.52), (S * 0.42, S * 0.76),
                                    (S * 0.84, S * 0.26)], w)


def _eye(s, S, c):
    w = _w(S)
    m = S / 2
    pygame.draw.ellipse(s, c, (S * 0.08, S * 0.28, S * 0.84, S * 0.44), w)
    pygame.draw.circle(s, c, (m, m), S * 0.13)


def _exit(s, S, c):
    w = _w(S)
    pygame.draw.lines(s, c, False, [(S * 0.55, S * 0.18), (S * 0.18, S * 0.18),
                                    (S * 0.18, S * 0.82), (S * 0.55, S * 0.82)], w)
    pygame.draw.line(s, c, (S * 0.4, S * 0.5), (S * 0.88, S * 0.5), w)
    pygame.draw.polygon(s, c, [(S * 0.92, S * 0.5), (S * 0.74, S * 0.36), (S * 0.74, S * 0.64)])


def _lightning(s, S, c):
    pygame.draw.polygon(s, c, [(S * 0.58, S * 0.08), (S * 0.22, S * 0.56), (S * 0.46, S * 0.56),
                               (S * 0.38, S * 0.92), (S * 0.78, S * 0.4), (S * 0.54, S * 0.4)])


# ─── Insignes de classe d'unité (jetons sans image, cf. renderer.unit_body) ───

def _g_melee(s, S, c):
    """Deux épées croisées, gardes comprises."""
    w = int(S * 0.14)
    for (x1, y1), (x2, y2) in (((0.2, 0.2), (0.8, 0.8)), ((0.8, 0.2), (0.2, 0.8)),
                               ((0.2, 0.62), (0.4, 0.82)), ((0.8, 0.62), (0.6, 0.82))):
        pygame.draw.line(s, c, (S * x1, S * y1), (S * x2, S * y2), w)


def _g_ranged(s, S, c):
    w = int(S * 0.12)
    pygame.draw.arc(s, c, pygame.Rect(S * 0.1, S * 0.12, S * 0.55, S * 0.76), math.radians(-70),
                    math.radians(70), w)
    pygame.draw.line(s, c, (S * 0.48, S * 0.15), (S * 0.48, S * 0.85), max(1, w // 2))
    pygame.draw.line(s, c, (S * 0.2, S * 0.5), (S * 0.88, S * 0.5), w)
    pygame.draw.polygon(s, c, [(S * 0.94, S * 0.5), (S * 0.78, S * 0.4), (S * 0.78, S * 0.6)])


def _g_cavalry(s, S, c):
    w = int(S * 0.14)
    pygame.draw.arc(s, c, pygame.Rect(S * 0.18, S * 0.14, S * 0.64, S * 0.7), math.radians(-35),
                    math.radians(215), w)
    for x in (0.22, 0.78):
        pygame.draw.line(s, c, (S * x, S * 0.62), (S * x, S * 0.84), w)


def _g_mage(s, S, c):
    m = S / 2
    pts = []
    for k in range(8):
        r = S * (0.44 if k % 2 == 0 else 0.14)
        a = k * math.pi / 4 - math.pi / 2
        pts.append((m + math.cos(a) * r, m + math.sin(a) * r))
    pygame.draw.polygon(s, c, pts)


def _g_officer(s, S, c):
    w = int(S * 0.09)
    pygame.draw.line(s, c, (S * 0.28, S * 0.1), (S * 0.28, S * 0.9), w)
    pygame.draw.polygon(s, c, [(S * 0.32, S * 0.12), (S * 0.86, S * 0.12), (S * 0.72, S * 0.3),
                               (S * 0.86, S * 0.48), (S * 0.32, S * 0.48)])


def _g_artillery(s, S, c):
    w = int(S * 0.09)
    pygame.draw.arc(s, c, pygame.Rect(S * 0.1, S * 0.2, S * 0.8, S * 0.5), math.radians(15),
                    math.radians(165), w)
    pygame.draw.line(s, c, (S * 0.5, S * 0.18), (S * 0.5, S * 0.86), w)
    pygame.draw.line(s, c, (S * 0.3, S * 0.86), (S * 0.7, S * 0.86), w)


def _g_monster(s, S, c):
    w = int(S * 0.1)
    for dx in (-0.2, 0.0, 0.2):
        pygame.draw.arc(s, c, pygame.Rect(S * (0.3 + dx), S * 0.12, S * 0.4, S * 0.8),
                        math.radians(100), math.radians(250), w)


def _g_hero(s, S, c):
    pygame.draw.polygon(s, c, [(S * 0.12, S * 0.74), (S * 0.12, S * 0.3), (S * 0.32, S * 0.5),
                               (S * 0.5, S * 0.2), (S * 0.68, S * 0.5), (S * 0.88, S * 0.3),
                               (S * 0.88, S * 0.74)])


_DRAW = {
    "play": _play, "pause": _pause,
    "speed1": _chevrons(1), "speed2": _chevrons(2), "speed3": _chevrons(3),
    "zoom_in": _magnifier("+"), "zoom_out": _magnifier("-"), "search": _magnifier(""),
    "fit": _fit, "lines": _crosshair, "intents": _flag, "minimap": _map, "legend": _layers,
    "video": _camera, "record": _record, "restart": _restart, "options": _gear,
    "help": _help, "menu": _menu, "folder": _folder, "close": _close, "check": _check,
    "follow": _eye, "exit": _exit, "quick": _lightning,
    "glyph_melee": _g_melee, "glyph_ranged": _g_ranged, "glyph_cavalry": _g_cavalry,
    "glyph_mage": _g_mage, "glyph_officer": _g_officer, "glyph_artillery": _g_artillery,
    "glyph_monster": _g_monster, "glyph_hero": _g_hero,
}
