"""
Figurines des unités sans image de jeton — vues de dessus, orientées.

Une unité dont le jeton n'a pas d'image (la plupart des factions) était un
disque portant l'insigne de sa classe. Elle devient une petite figurine de
plateau: fantassin au bouclier et à la lance, tireur à l'arc et au carquois,
cavalier sur sa monture, mage au bâton lumineux, officier à l'étendard,
monstre cornu, héros à la cape… Tunique, bouclier et étoffes prennent la
couleur de l'unité; l'anneau d'équipe reste dessiné autour (renderer).

La figurine regarde là où l'unité fait face (facing.py): 16 orientations,
chacune mise en cache. Dessinée trois fois plus grande puis réduite (bords
lissés). Convention: tracée vers +x (l'est), tournée ensuite.
"""
import math

import pygame

_cache = {}
SS = 3
N_DIRS = 16


def _clamp(v):
    return max(0, min(255, int(v)))


def _shade(c, d):
    return (_clamp(c[0] + d), _clamp(c[1] + d), _clamp(c[2] + d))


def _mix(a, b, t):
    return tuple(_clamp(a[i] + (b[i] - a[i]) * t) for i in range(3))


STEEL = (150, 154, 164)
STEEL_HI = (214, 218, 226)
WOOD = (120, 84, 50)
LEATHER = (96, 66, 40)


def dir_index(angle):
    """Orientation (radians, 0 = est, y vers le bas) → indice 0..15."""
    if angle is None:
        return None
    return int(round(angle / (math.tau / N_DIRS))) % N_DIRS


def _ell(s, col, cx, cy, w, h, width=0):
    pygame.draw.ellipse(s, col, (cx - w / 2, cy - h / 2, w, h), width)


def _outlined_ell(s, col, cx, cy, w, h, dark):
    _ell(s, dark, cx, cy, w + SS * 2, h + SS * 2)
    _ell(s, col, cx, cy, w, h)


def _helmet(s, cx, cy, r, col=STEEL, plume=None):
    if plume:
        _ell(s, _shade(plume, -40), cx - r * 1.0, cy, r * 1.8, r * 0.8)
        _ell(s, plume, cx - r * 0.9, cy - SS * 0.5, r * 1.5, r * 0.55)
    pygame.draw.circle(s, _shade(col, -60), (cx, cy), r + SS)
    pygame.draw.circle(s, col, (cx, cy), r)
    pygame.draw.circle(s, _shade(col, 50), (cx - r * 0.3, cy - r * 0.35), r * 0.45)


def _shoulders(s, cx, cy, D, col):
    _outlined_ell(s, _shade(col, -10), cx, cy, D * 0.36, D * 0.62, _shade(col, -70))
    _ell(s, _shade(col, 22), cx - D * 0.03, cy - D * 0.08, D * 0.22, D * 0.28)


def _melee(s, D, c, col):
    # Lance tenue à droite (au sud quand on regarde l'est), bouclier à gauche
    y_sp = c + D * 0.17
    pygame.draw.line(s, WOOD, (c - D * 0.30, y_sp), (c + D * 0.42, y_sp), max(1, int(D * 0.06)))
    pygame.draw.polygon(s, STEEL_HI, [(c + D * 0.50, y_sp), (c + D * 0.40, y_sp - D * 0.035),
                                      (c + D * 0.40, y_sp + D * 0.035)])
    _shoulders(s, c - D * 0.04, c, D, col)
    sx, sy, sr = c + D * 0.12, c - D * 0.19, D * 0.19
    pygame.draw.circle(s, _shade(col, -80), (sx, sy), sr + SS)
    pygame.draw.circle(s, _shade(col, 18), (sx, sy), sr)
    pygame.draw.circle(s, _shade(col, -30), (sx, sy), sr, max(1, SS))
    pygame.draw.circle(s, STEEL, (sx, sy), sr * 0.32)
    pygame.draw.circle(s, STEEL_HI, (sx - sr * 0.1, sy - sr * 0.1), sr * 0.14)
    _helmet(s, c - D * 0.02, c, D * 0.13)


def _ranged(s, D, c, col):
    # Carquois dans le dos, arc tendu devant
    pygame.draw.rect(s, LEATHER, (c - D * 0.36, c + D * 0.02, D * 0.20, D * 0.11), border_radius=SS)
    for k in range(3):
        pygame.draw.circle(s, (236, 230, 216), (c - D * 0.37, c + D * 0.04 + k * D * 0.035), max(1, SS))
    _shoulders(s, c - D * 0.06, c, D, col)
    R = D * 0.30
    rect = (c - R + D * 0.06, c - R, 2 * R, 2 * R)
    pygame.draw.arc(s, (70, 46, 24), rect, -1.25, 1.25, max(1, int(D * 0.06)))
    pygame.draw.arc(s, (150, 104, 60), rect, -1.25, 1.25, max(1, int(D * 0.03)))
    top = (c + D * 0.06 + math.cos(1.25) * R, c - math.sin(1.25) * R)
    bot = (c + D * 0.06 + math.cos(-1.25) * R, c - math.sin(-1.25) * R)
    pygame.draw.line(s, (230, 226, 210), top, bot, max(1, SS // 2))
    pygame.draw.line(s, (186, 150, 96), (c - D * 0.02, c), (c + D * 0.34, c), max(1, SS))
    hood = _mix(col, (70, 60, 50), 0.5)
    _helmet(s, c - D * 0.05, c, D * 0.13, hood)


def _cavalry(s, D, c, col):
    horse = (116, 80, 50)
    # Queue, corps, encolure et tête
    _ell(s, (54, 38, 26), c - D * 0.44, c, D * 0.14, D * 0.08)
    _outlined_ell(s, horse, c - D * 0.04, c, D * 0.74, D * 0.34, (50, 34, 22))
    _outlined_ell(s, horse, c + D * 0.34, c, D * 0.26, D * 0.15, (50, 34, 22))
    pygame.draw.line(s, (48, 34, 22), (c + D * 0.04, c), (c + D * 0.34, c), max(1, SS * 2))
    _ell(s, _shade(horse, 30), c - D * 0.10, c - D * 0.07, D * 0.36, D * 0.1)
    # Tapis de selle aux couleurs de l'unité
    _ell(s, _shade(col, -20), c - D * 0.06, c, D * 0.30, D * 0.40)
    # Lance
    y_l = c + D * 0.13
    pygame.draw.line(s, WOOD, (c - D * 0.20, y_l), (c + D * 0.50, y_l), max(1, int(D * 0.05)))
    pygame.draw.polygon(s, STEEL_HI, [(c + D * 0.56, y_l), (c + D * 0.48, y_l - D * 0.03),
                                      (c + D * 0.48, y_l + D * 0.03)])
    # Cavalier
    _outlined_ell(s, col, c - D * 0.06, c, D * 0.22, D * 0.36, _shade(col, -70))
    _helmet(s, c - D * 0.05, c, D * 0.10)


def _mage(s, D, c, col):
    robe = _shade(col, -10)
    pygame.draw.circle(s, _shade(col, -80), (c - D * 0.03, c), D * 0.31 + SS)
    pygame.draw.circle(s, robe, (c - D * 0.03, c), D * 0.31)
    pygame.draw.circle(s, _shade(col, 20), (c - D * 0.08, c - D * 0.08), D * 0.16)
    glow = _mix(col, (255, 255, 255), 0.55)
    tip = (c + D * 0.30, c - D * 0.26)
    pygame.draw.line(s, WOOD, (c - D * 0.10, c + D * 0.26), tip, max(1, int(D * 0.04)))
    halo = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    for r, a in ((D * 0.17, 60), (D * 0.11, 120)):
        pygame.draw.circle(halo, (*glow, a), tip, r)
    s.blit(halo, (0, 0))
    pygame.draw.circle(s, (255, 255, 255), tip, D * 0.05)
    hood = _shade(col, -40)
    pygame.draw.circle(s, _shade(hood, -40), (c - D * 0.06, c), D * 0.15 + SS)
    pygame.draw.circle(s, hood, (c - D * 0.06, c), D * 0.15)
    pygame.draw.circle(s, _shade(hood, 30), (c - D * 0.1, c - D * 0.05), D * 0.06)


def _officer(s, D, c, col):
    # Étendard planté derrière l'épaule, qui flotte vers l'arrière
    px, py = c - D * 0.10, c + D * 0.22
    flag = [(px, py), (px - D * 0.36, py - D * 0.05), (px - D * 0.30, py + D * 0.07),
            (px - D * 0.40, py + D * 0.18), (px, py + D * 0.14)]
    pygame.draw.polygon(s, _shade(col, 10), flag)
    pygame.draw.polygon(s, _shade(col, -60), flag, max(1, SS))
    pygame.draw.line(s, (236, 206, 110), (px - D * 0.04, py + D * 0.03), (px - D * 0.26, py + D * 0.02), SS)
    pygame.draw.circle(s, (70, 50, 30), (px, py), D * 0.035)
    # Cape, épaules et heaume à plumet
    _ell(s, _shade(col, -40), c - D * 0.16, c, D * 0.30, D * 0.62)
    _shoulders(s, c - D * 0.03, c, D, col)
    _helmet(s, c - D * 0.02, c, D * 0.13, (196, 170, 96), plume=(210, 50, 44))


def _artillery(s, D, c, col):
    frame = (118, 86, 52)
    pygame.draw.rect(s, (0, 0, 0, 70), (c - D * 0.24 + SS * 3, c - D * 0.12 + SS * 3, D * 0.5, D * 0.24))
    pygame.draw.rect(s, frame, (c - D * 0.26, c - D * 0.10, D * 0.52, D * 0.20), border_radius=SS)
    pygame.draw.rect(s, _shade(frame, -40), (c - D * 0.26, c - D * 0.10, D * 0.52, D * 0.20), max(1, SS),
                     border_radius=SS)
    rect = (c + D * 0.02, c - D * 0.40, D * 0.30, D * 0.80)
    pygame.draw.arc(s, (70, 50, 30), rect, -1.35, 1.35, max(1, int(D * 0.06)))
    pygame.draw.line(s, (220, 214, 200), (c + D * 0.21, c - D * 0.38), (c + D * 0.21, c + D * 0.38),
                     max(1, int(D * 0.03)))
    pygame.draw.line(s, STEEL_HI, (c - D * 0.10, c), (c + D * 0.46, c), max(1, int(D * 0.04)))
    for sy in (-1, 1):
        pygame.draw.circle(s, _shade(frame, -30), (c - D * 0.18, c + sy * D * 0.16), D * 0.06)
    pygame.draw.rect(s, col, (c - D * 0.20, c - D * 0.04, D * 0.14, D * 0.08))


def _monster(s, D, c, col):
    hide = _mix(col, (70, 60, 50), 0.45)
    # Queue, pattes griffues, dos hérissé, tête cornue
    pygame.draw.line(s, _shade(hide, -30), (c - D * 0.28, c), (c - D * 0.48, c + D * 0.08),
                     max(1, int(D * 0.07)))
    for sy in (-1, 1):
        for sx in (-0.18, 0.14):
            pygame.draw.line(s, _shade(hide, -50), (c + D * sx, c + sy * D * 0.2),
                             (c + D * (sx + 0.08), c + sy * D * 0.34), max(1, int(D * 0.06)))
    pygame.draw.circle(s, _shade(hide, -70), (c - D * 0.04, c), D * 0.33 + SS)
    pygame.draw.circle(s, hide, (c - D * 0.04, c), D * 0.33)
    for k in range(4):
        x = c - D * 0.22 + k * D * 0.1
        pygame.draw.polygon(s, _shade(hide, 40), [(x, c - D * 0.03), (x + D * 0.05, c), (x, c + D * 0.03),
                                                 (x - D * 0.05, c)])
    pygame.draw.circle(s, _shade(hide, 26), (c - D * 0.12, c - D * 0.12), D * 0.12)
    hx = c + D * 0.30
    pygame.draw.circle(s, _shade(hide, -60), (hx, c), D * 0.15 + SS)
    pygame.draw.circle(s, _shade(hide, 10), (hx, c), D * 0.15)
    for sy in (-1, 1):
        pygame.draw.polygon(s, (236, 226, 200), [(hx - D * 0.02, c + sy * D * 0.10),
                                                 (hx + D * 0.18, c + sy * D * 0.24),
                                                 (hx + D * 0.06, c + sy * D * 0.06)])
        pygame.draw.circle(s, (255, 70, 40), (hx + D * 0.08, c + sy * D * 0.05), max(1, D * 0.03))


def _hero(s, D, c, col):
    # Cape ample, armure à liserés d'or, épée lumineuse
    cape = [(c - D * 0.02, c - D * 0.26), (c - D * 0.44, c - D * 0.20), (c - D * 0.48, c + D * 0.20),
            (c - D * 0.02, c + D * 0.26)]
    pygame.draw.polygon(s, _shade(col, -30), cape)
    pygame.draw.polygon(s, _shade(col, -80), cape, max(1, SS))
    glow = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    pygame.draw.line(glow, (255, 250, 200, 90), (c + D * 0.04, c + D * 0.18), (c + D * 0.50, c + D * 0.18),
                     max(1, int(D * 0.10)))
    s.blit(glow, (0, 0))
    pygame.draw.line(s, (240, 244, 250), (c + D * 0.04, c + D * 0.18), (c + D * 0.48, c + D * 0.18),
                     max(1, int(D * 0.04)))
    pygame.draw.line(s, (210, 170, 70), (c + D * 0.06, c + D * 0.12), (c + D * 0.06, c + D * 0.24), SS)
    _shoulders(s, c - D * 0.04, c, D, (176, 180, 190))
    pygame.draw.ellipse(s, (212, 174, 80), (c - D * 0.22, c - D * 0.31, D * 0.36, D * 0.62), max(1, SS))
    _helmet(s, c - D * 0.03, c, D * 0.13, (214, 180, 90))


_DRAW = {
    "melee": _melee, "ranged": _ranged, "cavalry": _cavalry, "mage": _mage,
    "officer": _officer, "artillery": _artillery, "monster": _monster, "hero": _hero,
}


def _base(glyph, color, size):
    """Figurine tournée vers l'est, `size` pixels de côté (finaux)."""
    key = ('base', glyph, color, size)
    s = _cache.get(key)
    if s is not None:
        return s
    D = size * SS
    big = pygame.Surface((D, D), pygame.SRCALPHA)
    _DRAW.get(glyph, _melee)(big, D, D / 2, color)
    s = pygame.transform.smoothscale(big, (size, size))
    _cache[key] = s
    return s


def figure(glyph, color, size, direction=0):
    """Figurine (surface carrée de `size` px, centre = centre de l'unité),
    tournée vers l'orientation `direction` (0..15, 0 = est)."""
    direction = (direction or 0) % N_DIRS
    color = tuple(color[:3])
    key = ('fig', glyph, color, size, direction)
    s = _cache.get(key)
    if s is not None:
        return s
    base = _base(glyph, color, size)
    if direction:
        rot = pygame.transform.rotate(base, -direction * 360.0 / N_DIRS)
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        s.blit(rot, ((size - rot.get_width()) // 2, (size - rot.get_height()) // 2))
    else:
        s = base
    if len(_cache) > 3000:
        _cache.clear()
    _cache[key] = s
    return s
