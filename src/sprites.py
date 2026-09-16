"""
Sprites procéduraux — générés en code, mis en cache.

Aucun fichier image n'est requis: chaque sprite (flèche, carreau, trait de
baliste, arc de lame, boule de feu, orbe, rune, halo...) est dessiné une
seule fois à la taille de cellule courante, puis réutilisé. Les rotations
sont quantifiées (pas de 6°) et mises en cache elles aussi: tourner une
surface à chaque frame coûterait bien plus cher que de la réutiliser.

Convention: les sprites « orientés » regardent vers +x (vers la droite);
l'appelant les fait pivoter selon la direction du tir ou du coup.
"""
import math
import random

import pygame

_cache = {}
_ROT_STEP = 6  # degrés


def clear():
    _cache.clear()


def _surf(w, h):
    return pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)


def _shade(c, d):
    return (max(0, min(255, c[0] + d)), max(0, min(255, c[1] + d)), max(0, min(255, c[2] + d)))


def rotated(key, base, angle_rad, flip_y=False):
    """Rotation mise en cache d'un sprite orienté vers +x."""
    deg = int(round(-math.degrees(angle_rad) / _ROT_STEP)) * _ROT_STEP % 360
    k = ('rot', key, deg, flip_y)
    s = _cache.get(k)
    if s is None:
        src = pygame.transform.flip(base, False, True) if flip_y else base
        s = pygame.transform.rotate(src, deg)
        _cache[k] = s
    return s


# ═══════════════════════════════════════════════════════════════
#   LUMIÈRE — halos additifs (à blitter en BLEND_RGB_ADD)
# ═══════════════════════════════════════════════════════════════

def glow(radius, color, level=8):
    """Halo radial sur fond noir, intensité quantifiée en 9 niveaux.

    Blitté en mode additif, le noir ne change rien et la couleur « allume »
    ce qui est dessous: c'est ce qui donne l'aspect lumineux des sorts,
    des braises et des éclats — impossible à obtenir avec un simple alpha.
    """
    radius = max(2, int(radius))
    level = max(0, min(8, int(level)))
    k = ('glow', radius, color, level)
    s = _cache.get(k)
    if s is not None:
        return s
    d = radius * 2 + 1
    s = pygame.Surface((d, d))
    s.fill((0, 0, 0))
    gain = level / 8.0
    for r in range(radius, 0, -1):
        t = 1.0 - r / radius
        f = (t * t) * gain
        pygame.draw.circle(s, (int(color[0] * f), int(color[1] * f), int(color[2] * f)),
                           (radius, radius), r)
    _cache[k] = s
    return s


def soft_blob(radius, color, alpha):
    """Tache douce à bords fondus (fumée, poussière, ombre de nuage)."""
    radius = max(2, int(radius))
    alpha = max(0, min(255, int(alpha)))
    k = ('blob', radius, color, alpha // 8)
    s = _cache.get(k)
    if s is not None:
        return s
    small = max(4, min(32, radius))
    base = _surf(small * 2, small * 2)
    for r in range(small, 0, -1):
        t = 1.0 - r / small
        a = int(alpha * (t ** 1.5))
        pygame.draw.circle(base, (*color, a), (small, small), r)
    s = pygame.transform.smoothscale(base, (radius * 2, radius * 2))
    _cache[k] = s
    return s


# ═══════════════════════════════════════════════════════════════
#   PROJECTILES
# ═══════════════════════════════════════════════════════════════

def missile(kind, cs):
    """Flèche, carreau d'arbalète ou trait de baliste, orienté vers +x."""
    k = ('missile', kind, cs)
    s = _cache.get(k)
    if s is not None:
        return s
    if kind == "ballista":
        L, H = cs * 1.45, max(7, cs * 0.34)
        shaft_c, shaft_w = (118, 86, 52), max(2, cs // 9)
        head_c, head_len, head_w = (190, 192, 200), cs * 0.36, H * 0.46
        fletch_c, fletch_len = (150, 60, 45), cs * 0.30
    elif kind == "bolt":
        L, H = cs * 0.88, max(6, cs * 0.28)
        shaft_c, shaft_w = (92, 70, 46), max(2, cs // 11)
        head_c, head_len, head_w = (170, 172, 182), cs * 0.20, H * 0.40
        fletch_c, fletch_len = (70, 56, 40), cs * 0.12
    else:  # arrow
        L, H = cs * 1.10, max(6, cs * 0.28)
        shaft_c, shaft_w = (182, 146, 96), max(2, cs // 14)
        head_c, head_len, head_w = (200, 202, 210), cs * 0.16, H * 0.32
        fletch_c, fletch_len = (236, 232, 224), cs * 0.20

    s = _surf(L + 2, H + 2)
    cy = (H + 2) / 2.0
    x0, x1 = 1, L + 1
    # Fût
    pygame.draw.line(s, _shade(shaft_c, -30), (x0, cy + 1), (x1 - head_len, cy + 1), shaft_w)
    pygame.draw.line(s, shaft_c, (x0, cy), (x1 - head_len, cy), shaft_w)
    # Empennage (deux ailettes)
    fx = x0 + fletch_len
    pygame.draw.polygon(s, fletch_c, [(x0, cy - H * 0.42), (fx, cy - 1), (x0 + fletch_len * 0.3, cy - 1)])
    pygame.draw.polygon(s, _shade(fletch_c, -40), [(x0, cy + H * 0.42), (fx, cy + 1), (x0 + fletch_len * 0.3, cy + 1)])
    if kind == "arrow":
        pygame.draw.line(s, (170, 40, 40), (x0 + fletch_len * 0.55, cy - H * 0.2), (x0 + fletch_len * 0.55, cy + H * 0.2), 1)
    # Pointe métallique
    tip = [(x1, cy), (x1 - head_len, cy - head_w), (x1 - head_len * 0.75, cy), (x1 - head_len, cy + head_w)]
    pygame.draw.polygon(s, head_c, tip)
    pygame.draw.polygon(s, _shade(head_c, -70), tip, 1)
    pygame.draw.line(s, (250, 250, 255), (x1 - 1, cy), (x1 - head_len * 0.7, cy - head_w * 0.4), 1)
    _cache[k] = s
    return s


def fireball_frames(cs, n=8):
    """Boule de feu animée: cœur blanc-jaune, langues de flamme mouvantes."""
    k = ('fireball', cs)
    frames = _cache.get(k)
    if frames is not None:
        return frames
    r = max(5, int(cs * 0.38))
    size = r * 3
    rng = random.Random(1234)
    frames = []
    for f in range(n):
        s = _surf(size, size)
        c = size // 2
        # Langues de flamme externes
        for i in range(14):
            ang = rng.uniform(0, math.tau)
            dist = rng.uniform(0.25, 0.75) * r
            rr = rng.uniform(0.35, 0.65) * r
            col = rng.choice([(255, 90, 20, 150), (240, 60, 10, 130), (255, 140, 30, 150)])
            pygame.draw.circle(s, col, (int(c + math.cos(ang) * dist), int(c + math.sin(ang) * dist)), int(rr))
        pygame.draw.circle(s, (255, 170, 50, 230), (c, c), int(r * 0.72))
        pygame.draw.circle(s, (255, 230, 120, 250), (c, c), int(r * 0.45))
        pygame.draw.circle(s, (255, 255, 235, 255), (c - r // 6, c - r // 6), max(1, int(r * 0.22)))
        frames.append(s)
    _cache[k] = frames
    return frames


def magic_orb_frames(cs, color=(190, 110, 255), n=6):
    """Orbe arcanique: noyau clair, halo coloré, quatre rais qui tournent."""
    k = ('orb', cs, color)
    frames = _cache.get(k)
    if frames is not None:
        return frames
    r = max(3, int(cs * 0.18))
    size = r * 5
    frames = []
    for f in range(n):
        s = _surf(size, size)
        c = size // 2
        pygame.draw.circle(s, (*color, 70), (c, c), int(r * 1.6))
        pygame.draw.circle(s, (*color, 150), (c, c), r)
        pygame.draw.circle(s, (245, 230, 255, 255), (c, c), max(1, int(r * 0.55)))
        base = f / n * (math.pi / 2)
        for i in range(4):
            a = base + i * math.pi / 2
            ex, ey = c + math.cos(a) * r * 2.2, c + math.sin(a) * r * 2.2
            pygame.draw.line(s, (*_shade(color, 60), 200), (c, c), (ex, ey), 1)
        frames.append(s)
    _cache[k] = frames
    return frames


# ═══════════════════════════════════════════════════════════════
#   CORPS À CORPS
# ═══════════════════════════════════════════════════════════════

def _crescent(c, R, a_from, a_to, thick_from, thick_to, steps=16):
    """Polygone en croissant: épaisseur variable du début à la fin de l'arc."""
    outer, inner = [], []
    for i in range(steps + 1):
        t = i / steps
        a = a_from + (a_to - a_from) * t
        th = thick_from + (thick_to - thick_from) * t
        outer.append((c + math.cos(a) * R, c + math.sin(a) * R))
        inner.append((c + math.cos(a) * R * (1 - th), c + math.sin(a) * R * (1 - th)))
    return outer + inner[::-1]


def slash_frames(cs, color=(255, 240, 220), n=7):
    """Arc de lame qui balaie (orienté vers +x, sens horaire).

    La traînée est faite de croissants CONTINUS empilés (et non de
    segments juxtaposés, qui laissaient des stries): chaque couche part
    d'un peu plus près du bord d'attaque, si bien que l'opacité s'accumule
    vers l'avant de la lame. Les dernières images s'effacent jusqu'à zéro.
    """
    k = ('slash', cs, color)
    frames = _cache.get(k)
    if frames is not None:
        return frames
    R = max(8, int(cs * 0.80))
    size = R * 2 + 8
    c = size // 2
    span = math.radians(150)
    a_start = -span / 2
    layers = 7
    frames = []
    for f in range(n):
        s = _surf(size, size)
        sweep_end = n * 0.55
        p = min(1.0, (f + 1) / sweep_end)
        fade = 1.0 if f + 1 <= sweep_end else max(0.0, 1.0 - (f + 1 - sweep_end) / (n - sweep_end))
        if fade <= 0.02:
            frames.append(s)
            continue
        lead = a_start + span * p
        trail = max(a_start, lead - span * 0.8)
        for L in range(layers):
            a_from = trail + (lead - trail) * (L / layers)
            if lead - a_from < 0.02:
                continue
            layer = _surf(size, size)
            poly = _crescent(c, R, a_from, lead, 0.05, 0.42 - 0.02 * L)
            alpha = int(min(255, 70 * fade))
            pygame.draw.polygon(layer, (*color, alpha), poly)
            s.blit(layer, (0, 0))
        # Fil de la lame: liseré blanc net sur le bord d'attaque
        ex, ey = c + math.cos(lead) * R, c + math.sin(lead) * R
        ix, iy = c + math.cos(lead) * R * 0.55, c + math.sin(lead) * R * 0.55
        pygame.draw.line(s, (255, 255, 255, int(255 * fade)), (ix, iy), (ex, ey), 3)
        frames.append(s)
    _cache[k] = frames
    return frames


def thrust_sprite(cs, color=(255, 230, 170)):
    """Estoc: traînée effilée terminée par une pointe brillante (vers +x)."""
    k = ('thrust', cs, color)
    s = _cache.get(k)
    if s is not None:
        return s
    L = max(14, int(cs * 1.6))
    H = max(6, int(cs * 0.34))
    s = _surf(L, H)
    cy = H / 2.0
    for i in range(L):
        t = i / L
        a = int(220 * t ** 2)
        hh = max(0.5, cy * t)
        pygame.draw.line(s, (*color, a), (i, cy - hh), (i, cy + hh))
    pygame.draw.polygon(s, (255, 255, 255, 255), [(L - 1, cy), (L - H, cy - H * 0.35), (L - H, cy + H * 0.35)])
    _cache[k] = s
    return s


# ═══════════════════════════════════════════════════════════════
#   SORTS DE SOUTIEN
# ═══════════════════════════════════════════════════════════════

def rune_shield_frames(radius, n=12):
    """Bouclier runique: hexagone lumineux, triangle intérieur qui tourne."""
    radius = max(6, int(radius))
    k = ('rune', radius)
    frames = _cache.get(k)
    if frames is not None:
        return frames
    size = radius * 2 + 6
    c = size // 2
    frames = []
    for f in range(n):
        s = _surf(size, size)
        rot = f / n * (math.pi / 3)
        hexa = [(c + math.cos(rot + i * math.pi / 3) * radius,
                 c + math.sin(rot + i * math.pi / 3) * radius) for i in range(6)]
        pygame.draw.polygon(s, (90, 170, 255, 45), hexa)
        pygame.draw.polygon(s, (150, 210, 255, 220), hexa, 2)
        tri = [(c + math.cos(-rot * 2 + i * math.tau / 3) * radius * 0.62,
                c + math.sin(-rot * 2 + i * math.tau / 3) * radius * 0.62) for i in range(3)]
        pygame.draw.polygon(s, (200, 235, 255, 160), tri, 1)
        for (hx, hy) in hexa:
            pygame.draw.circle(s, (230, 245, 255, 230), (int(hx), int(hy)), 2)
        frames.append(s)
    _cache[k] = frames
    return frames


def plus_sprite(size, color=(120, 255, 150)):
    """Petite croix de soin."""
    size = max(3, int(size))
    k = ('plus', size, color)
    s = _cache.get(k)
    if s is None:
        s = _surf(size, size)
        t = max(1, size // 3)
        pygame.draw.rect(s, color, (0, size // 2 - t // 2, size, t))
        pygame.draw.rect(s, color, (size // 2 - t // 2, 0, t, size))
        _cache[k] = s
    return s


# ═══════════════════════════════════════════════════════════════
#   DÉCALQUES AU SOL
# ═══════════════════════════════════════════════════════════════

def decal(kind, radius, seed):
    """Traces durables au sol: sang, brûlure, dépouille, gravats."""
    radius = max(3, int(radius))
    k = ('decal', kind, radius, seed % 6)
    s = _cache.get(k)
    if s is not None:
        return s
    rng = random.Random(seed % 6 * 7919 + len(kind))
    size = radius * 3
    s = _surf(size, size)
    c = size // 2
    if kind == "scorch":
        # Lobes doux superposés + projections: une trace calcinée, pas un disque
        for i in range(9):
            a = rng.uniform(0, math.tau)
            d = rng.uniform(0, radius * 0.55)
            rr = int(rng.uniform(radius * 0.3, radius * 0.6))
            blob = soft_blob(rr, (18, 14, 10), 90)
            s.blit(blob, (c + math.cos(a) * d - rr, c + math.sin(a) * d - rr))
        for i in range(10):
            a = rng.uniform(0, math.tau)
            d = rng.uniform(radius * 0.6, radius * 1.3)
            pygame.draw.circle(s, (25, 20, 16, 120), (int(c + math.cos(a) * d), int(c + math.sin(a) * d)),
                               max(1, int(rng.uniform(1, radius * 0.12))))
    elif kind == "blood":
        pygame.draw.ellipse(s, (95, 12, 12, 150), (c - radius * 0.6, c - radius * 0.4, radius * 1.2, radius * 0.8))
        for i in range(7):
            a = rng.uniform(0, math.tau)
            d = rng.uniform(radius * 0.5, radius * 1.2)
            pygame.draw.circle(s, (110, 16, 16, 140), (int(c + math.cos(a) * d), int(c + math.sin(a) * d)),
                               max(1, int(rng.uniform(1, radius * 0.22))))
    elif kind == "corpse":
        pygame.draw.ellipse(s, (30, 26, 22, 120), (c - radius, c - radius * 0.55, radius * 2, radius * 1.1))
        pygame.draw.ellipse(s, (80, 14, 14, 110), (c - radius * 0.5, c - radius * 0.2, radius, radius * 0.6))
        # Arme brisée abandonnée
        a = rng.uniform(0, math.pi)
        dx, dy = math.cos(a) * radius, math.sin(a) * radius
        pygame.draw.line(s, (120, 110, 100, 190), (c - dx, c - dy), (c + dx * 0.2, c + dy * 0.2), 2)
        pygame.draw.line(s, (120, 110, 100, 190), (c + dx * 0.45, c + dy * 0.45), (c + dx, c + dy), 2)
    else:  # rubble
        for i in range(8):
            a = rng.uniform(0, math.tau)
            d = rng.uniform(0, radius)
            w = rng.uniform(2, radius * 0.4)
            pygame.draw.rect(s, (90, 86, 80, 200), (c + math.cos(a) * d, c + math.sin(a) * d, w, w * 0.7))
    _cache[k] = s
    return s


# ═══════════════════════════════════════════════════════════════
#   CARTE — grain, vignettage
# ═══════════════════════════════════════════════════════════════

def ground_grain(size=128, seed=77):
    """Texture de grain répétable: mouchetures claires et sombres.

    Posée à faible opacité sur tout le terrain, elle casse l'aplat des
    couleurs unies sans coûter quoi que ce soit en jeu (elle est cuite
    dans la surface du terrain une fois pour toutes).
    """
    k = ('grain', size, seed)
    s = _cache.get(k)
    if s is not None:
        return s
    rng = random.Random(seed)
    s = _surf(size, size)
    for _ in range(size * size // 5):
        x, y = rng.randrange(size), rng.randrange(size)
        if rng.random() < 0.5:
            s.set_at((x, y), (0, 0, 0, rng.randint(14, 34)))
        else:
            s.set_at((x, y), (255, 255, 230, rng.randint(8, 20)))
    for _ in range(size // 3):
        # Traits courts SANS bouclage: un modulo sur les extrémités tirait un
        # trait d'un bord à l'autre de la tuile → lignes droites sur tout
        # le terrain.
        x, y = rng.randrange(1, size - 5), rng.randrange(2, size - 1)
        L = rng.randint(2, 4)
        pygame.draw.line(s, (0, 0, 0, 22), (x, y), (x + L, y - 1))
    _cache[k] = s
    return s


def vignette(w, h):
    """Assombrissement doux des bords de l'écran (focalise le regard)."""
    k = ('vignette', w, h)
    s = _cache.get(k)
    if s is not None:
        return s
    sw, sh = 96, 60
    steps = 24
    small = _surf(sw, sh)
    # Couches concentriques: bords sombres, centre transparent. Les primitives
    # de dessin REMPLACENT l'alpha (pas de mélange), d'où l'ordre extérieur →
    # intérieur avec une opacité décroissante.
    small.fill((0, 0, 0, 150))
    for i in range(steps):
        t = i / steps
        a = int(150 * (1.0 - t) ** 1.8)
        rw, rh = sw * (1.35 - 0.9 * t), sh * (1.35 - 0.9 * t)
        pygame.draw.ellipse(small, (0, 0, 0, a), ((sw - rw) / 2, (sh - rh) / 2, rw, rh))
    s = pygame.transform.smoothscale(small, (w, h))
    _cache[k] = s
    return s
