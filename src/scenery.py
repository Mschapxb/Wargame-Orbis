"""
Sprites de décor — arbres, buissons, rochers, végétation et objets.

Tout est dessiné en code, vu de dessus comme le reste de la carte, puis mis
en cache: aucun fichier image. Chaque sprite est tracé deux fois plus grand
puis réduit (suréchantillonnage), ce qui lisse les bords que les primitives
de pygame laissent crénelés.

Un sprite dépend de sa NATURE, d'une VARIANTE (forme, teinte: une forêt de
tampons identiques se lit comme du papier peint), de sa TAILLE et de la
PALETTE du lieu — biome et saison (cf. `palette`). Les ombres sont portées
vers le bas à droite (lumière du nord-ouest), comme celles des maisons et
des murs.

Convention: `sprite(...)` renvoie (surface, (ax, ay)); poser la surface en
(x - ax, y - ay) centre l'objet sur (x, y).
"""
import math
import random

import pygame

_cache = {}
SS = 2              # facteur de suréchantillonnage
N_VARIANTS = 6

SEASONS = ("Printemps", "Été", "Automne", "Hiver")
DEFAULT_SEASON = "Été"


def clear():
    _cache.clear()


def _clamp(v):
    return max(0, min(255, int(v)))


def shade(c, d):
    return (_clamp(c[0] + d), _clamp(c[1] + d), _clamp(c[2] + d))


def mix(a, b, t):
    return (_clamp(a[0] + (b[0] - a[0]) * t), _clamp(a[1] + (b[1] - a[1]) * t),
            _clamp(a[2] + (b[2] - a[2]) * t))


def tint(c, d):
    return (_clamp(c[0] + d[0]), _clamp(c[1] + d[1]), _clamp(c[2] + d[2]))


# ═══════════════════════════════════════════════════════════════
#   PALETTES — biome × saison
# ═══════════════════════════════════════════════════════════════
# Feuillages en triades (sombre, moyen, clair). Plusieurs triades par
# palette: chaque variante d'arbre en prend une, la forêt n'est jamais d'un
# seul vert.

_SUMMER_LEAVES = [((22, 58, 20), (38, 90, 32), (70, 128, 50)),
                  ((26, 62, 26), (46, 98, 38), (84, 140, 60)),
                  ((20, 52, 24), (34, 82, 36), (62, 118, 54)),
                  ((30, 64, 18), (56, 104, 30), (96, 146, 52))]
_SPRING_LEAVES = [((34, 80, 26), (62, 124, 42), (118, 176, 76)),
                  ((40, 86, 30), (74, 136, 50), (136, 190, 90)),
                  ((30, 72, 30), (56, 114, 48), (104, 164, 80)),
                  ((96, 60, 72), (190, 128, 150), (242, 196, 212))]   # arbre en fleurs
_AUTUMN_LEAVES = [((96, 42, 14), (168, 78, 24), (226, 138, 52)),
                  ((110, 70, 16), (184, 124, 30), (236, 184, 72)),
                  ((86, 28, 20), (150, 48, 30), (206, 92, 56)),
                  ((54, 60, 22), (104, 106, 36), (160, 150, 64))]
_CONIFER = ((14, 42, 24), (26, 66, 38), (52, 102, 60))
_PALM = ((40, 78, 30), (74, 124, 44), (132, 170, 70))

PALETTES = {
    # Prairie tempérée (Prairie, Village, sièges « prairie »)
    ("Prairie", "Été"): dict(
        leaves=_SUMMER_LEAVES, conifer=_CONIFER, bush=_SUMMER_LEAVES,
        grass=((58, 92, 38), (92, 132, 56)), flowers=[(236, 222, 120), (226, 132, 180),
                                                      (176, 196, 244), (244, 244, 236)],
        ground=(0, 0, 0), bare=False, snow=False, litter=None, moss=(64, 92, 44)),
    ("Prairie", "Printemps"): dict(
        leaves=_SPRING_LEAVES, conifer=_CONIFER, bush=_SPRING_LEAVES[:3],
        grass=((70, 112, 44), (118, 162, 70)),
        flowers=[(250, 236, 110), (240, 150, 196), (190, 206, 255), (255, 255, 250),
                 (250, 170, 90)],
        ground=(-6, 12, -4), bare=False, snow=False, litter=None, moss=(74, 110, 50)),
    ("Prairie", "Automne"): dict(
        leaves=_AUTUMN_LEAVES, conifer=_CONIFER, bush=_AUTUMN_LEAVES,
        grass=((96, 96, 44), (146, 136, 70)), flowers=[(200, 120, 60), (230, 200, 110)],
        ground=(16, 4, -8), bare=False, snow=False,
        litter=[(170, 82, 30), (200, 140, 50), (140, 50, 30)], moss=(88, 96, 46)),
    ("Prairie", "Hiver"): dict(
        leaves=_SUMMER_LEAVES, conifer=_CONIFER,
        bush=[((70, 60, 50), (104, 90, 72), (140, 126, 106))],
        grass=((150, 152, 130), (196, 198, 186)), flowers=[],
        ground=None, bare=True, snow=True, litter=None, moss=(120, 130, 120)),
    # Désert: palmiers, broussailles sèches; les saisons y changent peu
    ("Désert", "Été"): dict(
        leaves=[_PALM], conifer=_PALM, bush=[((92, 84, 44), (132, 118, 62), (176, 160, 92))],
        grass=((150, 128, 72), (190, 168, 104)), flowers=[(232, 176, 90)],
        ground=(0, 0, 0), bare=False, snow=False, litter=None, moss=None, stone=(156, 128, 94)),
    ("Désert", "Printemps"): dict(
        leaves=[_PALM], conifer=_PALM, bush=[((70, 92, 40), (108, 130, 56), (156, 176, 86))],
        grass=((128, 132, 64), (170, 170, 94)), flowers=[(240, 200, 90), (230, 120, 150)],
        ground=(-4, 4, -2), bare=False, snow=False, litter=None, moss=None, stone=(156, 128, 94)),
    ("Désert", "Hiver"): dict(
        leaves=[_PALM], conifer=_PALM, bush=[((88, 80, 56), (126, 114, 80), (164, 152, 118))],
        grass=((148, 136, 104), (184, 174, 146)), flowers=[],
        ground=(-14, -10, 2), bare=False, snow=False, litter=None, moss=None, stone=(146, 124, 98)),
}
PALETTES[("Désert", "Automne")] = PALETTES[("Désert", "Été")]
# La Forêt a la palette de la prairie (son sous-bois est plus sombre: cf.
# le fond de carte)
for _s in SEASONS:
    PALETTES[("Forêt", _s)] = PALETTES[("Prairie", _s)]

# Sol enneigé (remplace la couleur de fond du biome)
SNOW_GROUND = (206, 212, 220)


def palette(biome="Prairie", season=DEFAULT_SEASON):
    return PALETTES.get((biome, season)) or PALETTES[("Prairie", DEFAULT_SEASON)]


def ground_color(bg, biome="Prairie", season=DEFAULT_SEASON):
    """Couleur de fond d'une carte dans la saison: l'hiver l'enneige (sauf
    au désert), les autres saisons la teintent."""
    pal = palette(biome, season)
    if pal['ground'] is None:
        # Neige, un peu plus chaude sur les sols de terre (sièges, village)
        return mix(SNOW_GROUND, bg, 0.12)
    return tint(bg, pal['ground'])


# ═══════════════════════════════════════════════════════════════
#   OUTILS DE DESSIN
# ═══════════════════════════════════════════════════════════════

def _surf(w, h):
    return pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)


def _finish(big, cx, cy):
    """Réduit la surface suréchantillonnée; (cx, cy) = centre de l'objet
    dans la grande surface. Renvoie (surface, ancre)."""
    w, h = max(1, big.get_width() // SS), max(1, big.get_height() // SS)
    small = pygame.transform.smoothscale(big, (w, h))
    return small, (int(cx / SS), int(cy / SS))


def _blurred(layer, k):
    """Flou bon marché: réduction puis agrandissement."""
    w, h = layer.get_size()
    k = max(2, int(k))
    small = pygame.transform.smoothscale(layer, (max(1, w // k), max(1, h // k)))
    return pygame.transform.smoothscale(small, (w, h))


def _shadow_circles(size, circles, alpha, blur):
    layer = _surf(*size)
    for (x, y, r) in circles:
        pygame.draw.circle(layer, (0, 0, 0, alpha), (x, y), r)
    return _blurred(layer, blur)


def _shadow_poly(size, pts, alpha, blur):
    layer = _surf(*size)
    pygame.draw.polygon(layer, (0, 0, 0, alpha), pts)
    return _blurred(layer, blur)


def _rng(kind, variant, extra=0):
    # hash() des chaînes change d'un lancement à l'autre: graine explicite
    seed = sum(ord(ch) * (i + 1) for i, ch in enumerate(kind)) * 7919 + variant * 104729 + extra * 31
    return random.Random(seed)


def _lobes(rng, cx, cy, R, n):
    """Lobes d'un houppier: un disque central et une couronne irrégulière."""
    lobes = [(cx, cy, R * 0.62)]
    off = rng.uniform(0, math.tau)
    for i in range(n):
        a = off + i * math.tau / n + rng.uniform(-0.25, 0.25)
        d = R * rng.uniform(0.40, 0.56)
        r = R * rng.uniform(0.38, 0.52)
        lobes.append((cx + math.cos(a) * d, cy + math.sin(a) * d, r))
    return lobes


def _canvas(size, pad=0.32):
    """Grande surface pour un objet de `size` pixels (finaux): marge pour
    l'ombre portée au sud-est. Renvoie (surface, D, cx, cy)."""
    D = size * SS
    W = int(D * (1 + pad))
    s = _surf(W, W)
    return s, D, D / 2, D / 2


# ═══════════════════════════════════════════════════════════════
#   ARBRES
# ═══════════════════════════════════════════════════════════════

_BURNT_TRIAD = ((30, 22, 16), (58, 40, 24), (88, 62, 36))


def _leaf_tree(size, variant, pal, scorch=0):
    """Feuillu vu de dessus: houppier en lobes, ombre propre au sud-est,
    reflets au nord-ouest, mouchetures de feuilles."""
    rng = _rng("feuillu", variant)
    triads = pal['leaves']
    dark, mid, light = triads[variant % len(triads)]
    if scorch:
        k = min(1.0, 0.34 * scorch)
        dark, mid, light = (mix(dark, _BURNT_TRIAD[0], k), mix(mid, _BURNT_TRIAD[1], k),
                            mix(light, _BURNT_TRIAD[2], k))
    s, D, cx, cy = _canvas(size)
    R = D * 0.42
    lobes = _lobes(rng, cx, cy, R, rng.randint(6, 8))
    s.blit(_shadow_circles(s.get_size(), [(x + R * 0.30, y + R * 0.42, r * 1.02) for x, y, r in lobes],
                           82, max(2, R / 5)), (0, 0))
    for x, y, r in lobes:
        pygame.draw.circle(s, dark, (x, y), r + SS)
    for x, y, r in lobes:
        pygame.draw.circle(s, mid, (x - r * 0.10, y - r * 0.12), r * 0.86)
    for x, y, r in lobes:
        pygame.draw.circle(s, light, (x - r * 0.30, y - r * 0.34), r * 0.42)
    # Mouchetures de feuilles: claires au nord-ouest, sombres au sud-est
    for _ in range(int(14 + R / 2)):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0, R * 0.95)
        px, py = cx + math.cos(a) * d, cy + math.sin(a) * d
        c = light if (px + py) < (cx + cy) else dark
        pygame.draw.circle(s, shade(c, rng.randint(-8, 10)), (px, py), max(1, R * 0.07))
    if triads is _SPRING_LEAVES and variant % 4 == 3 and not scorch:
        for _ in range(10):
            a = rng.uniform(0, math.tau)
            d = rng.uniform(0, R * 0.8)
            pygame.draw.circle(s, (252, 238, 244), (cx + math.cos(a) * d, cy + math.sin(a) * d),
                               max(1, R * 0.06))
    return _finish(s, cx, cy)


def _bare_tree(size, variant, pal, snow=True):
    """Arbre d'hiver: branches nues en étoile, un peu de neige."""
    rng = _rng("nu", variant)
    s, D, cx, cy = _canvas(size, 0.25)
    R = D * 0.44
    bark = (66, 56, 48)
    branches = []
    n = rng.randint(5, 7)
    off = rng.uniform(0, math.tau)
    for i in range(n):
        a = off + i * math.tau / n + rng.uniform(-0.3, 0.3)
        branches.append((a, R * rng.uniform(0.7, 1.0), rng.uniform(0.35, 0.7), rng.uniform(0.35, 0.7)))

    def draw(target, dx, dy, col):
        for a, L, b1, b2 in branches:
            x0, y0 = cx + dx, cy + dy
            pygame.draw.line(target, col, (x0, y0), (x0 + math.cos(a) * L, y0 + math.sin(a) * L),
                             max(1, int(D * 0.045)))
            mx_, my_ = x0 + math.cos(a) * L * 0.55, y0 + math.sin(a) * L * 0.55
            for b in (a - b1, a + b2):
                pygame.draw.line(target, col, (mx_, my_),
                                 (mx_ + math.cos(b) * L * 0.4, my_ + math.sin(b) * L * 0.4),
                                 max(1, int(D * 0.025)))

    shadow = _surf(*s.get_size())
    draw(shadow, R * 0.25, R * 0.35, (0, 0, 0, 70))
    s.blit(_blurred(shadow, 3), (0, 0))
    draw(s, 0, 0, bark)
    pygame.draw.circle(s, shade(bark, 12), (cx, cy), max(2, D * 0.07))
    if snow:
        for a, L, _b1, _b2 in branches:
            for t in (0.3, 0.62):
                pygame.draw.circle(s, (236, 240, 246), (cx + math.cos(a) * L * t - SS,
                                                       cy + math.sin(a) * L * t - SS), max(1, D * 0.03))
    return _finish(s, cx, cy)


def _conifer(size, variant, pal, snow=False, scorch=0):
    """Résineux vu de dessus: étoiles de branches superposées, de plus en
    plus claires vers la cime."""
    rng = _rng("pin", variant)
    dark, mid, light = pal['conifer']
    if scorch:
        k = min(1.0, 0.34 * scorch)
        dark, mid, light = (mix(dark, _BURNT_TRIAD[0], k), mix(mid, _BURNT_TRIAD[1], k),
                            mix(light, _BURNT_TRIAD[2], k))
    s, D, cx, cy = _canvas(size)
    R = D * 0.42
    n = rng.choice((8, 9, 10))
    rot = rng.uniform(0, math.tau)

    def star(r, a0, k=0.55, ox=0.0, oy=0.0):
        pts = []
        for i in range(n * 2):
            rr = r if i % 2 == 0 else r * k
            a = a0 + i * math.pi / n
            pts.append((cx + ox + math.cos(a) * rr, cy + oy + math.sin(a) * rr))
        return pts

    s.blit(_shadow_poly(s.get_size(), star(R * 1.02, rot, 0.55, R * 0.32, R * 0.44), 86, 4), (0, 0))
    layers = ((1.0, dark), (0.78, mid), (0.52, mix(mid, light, 0.5)), (0.28, light))
    for i, (k, col) in enumerate(layers):
        pygame.draw.polygon(s, col, star(R * k, rot + i * 0.35, 0.5 + 0.05 * i))
    for i in range(n):
        a = rot + i * math.tau / n
        if math.cos(a - 3.9) > 0.2:      # branches éclairées au nord-ouest
            pygame.draw.line(s, shade(light, 12), (cx, cy),
                             (cx + math.cos(a) * R * 0.8, cy + math.sin(a) * R * 0.8), max(1, SS))
    if snow:
        for i in range(n):
            a = rot + i * math.tau / n
            if math.cos(a - 3.9) > -0.3:
                for t in (0.45, 0.75):
                    pygame.draw.circle(s, (238, 242, 248),
                                       (cx + math.cos(a) * R * t, cy + math.sin(a) * R * t),
                                       max(1, R * 0.10))
        pygame.draw.circle(s, (244, 246, 250), (cx - R * 0.05, cy - R * 0.05), R * 0.14)
    return _finish(s, cx, cy)


def _palm(size, variant, pal, scorch=0):
    """Palmier vu de dessus: palmes arquées rayonnant du stipe."""
    rng = _rng("palmier", variant)
    dark, mid, light = _PALM
    if scorch:
        k = min(1.0, 0.34 * scorch)
        dark, mid, light = (mix(dark, _BURNT_TRIAD[0], k), mix(mid, _BURNT_TRIAD[1], k),
                            mix(light, _BURNT_TRIAD[2], k))
    s, D, cx, cy = _canvas(size)
    R = D * 0.46
    n = rng.randint(7, 9)
    off = rng.uniform(0, math.tau)
    fronds = [(off + i * math.tau / n + rng.uniform(-0.2, 0.2), R * rng.uniform(0.8, 1.05))
              for i in range(n)]

    def frond(a, L, dx=0.0, dy=0.0):
        left, right = [], []
        x = y = 0.0
        for j in range(7):
            t = j / 6
            b = a + 0.35 * t * t
            x = cx + dx + math.cos(b) * L * t
            y = cy + dy + math.sin(b) * L * t
            wdt = R * 0.16 * math.sin(math.pi * min(1.0, t * 1.1))
            nx, ny = -math.sin(b), math.cos(b)
            left.append((x + nx * wdt, y + ny * wdt))
            right.append((x - nx * wdt, y - ny * wdt))
        return left + right[::-1], (cx + dx, cy + dy), (x, y)

    shadow = _surf(*s.get_size())
    for a, L in fronds:
        pygame.draw.polygon(shadow, (0, 0, 0, 80), frond(a, L, R * 0.3, R * 0.4)[0])
    s.blit(_blurred(shadow, 3), (0, 0))
    for k, (a, L) in enumerate(sorted(fronds, key=lambda f: -math.sin(f[0]))):
        poly, p0, p1 = frond(a, L)
        pygame.draw.polygon(s, dark, poly)
        pygame.draw.polygon(s, mid if k % 2 else mix(mid, light, 0.35),
                            [(x - SS * 0.6, y - SS * 0.6) for x, y in poly])
        pygame.draw.line(s, shade(light, 10), p0, p1, max(1, SS))
    pygame.draw.circle(s, (104, 78, 44), (cx, cy), R * 0.14)
    pygame.draw.circle(s, (140, 108, 64), (cx - SS, cy - SS), R * 0.08)
    return _finish(s, cx, cy)


def _bush(size, variant, pal, snow=False):
    """Buisson: petit houppier bas et touffu; en fleurs au printemps."""
    rng = _rng("buisson", variant)
    triads = pal['bush']
    dark, mid, light = triads[variant % len(triads)]
    s, D, cx, cy = _canvas(size, 0.28)
    R = D * 0.40
    lobes = _lobes(rng, cx, cy, R, rng.randint(4, 6))
    s.blit(_shadow_circles(s.get_size(), [(x + R * 0.25, y + R * 0.35, r) for x, y, r in lobes],
                           74, max(2, R / 4)), (0, 0))
    for x, y, r in lobes:
        pygame.draw.circle(s, dark, (x, y), r + SS * 0.5)
    for x, y, r in lobes:
        pygame.draw.circle(s, mid, (x - r * 0.12, y - r * 0.14), r * 0.8)
    for x, y, r in lobes:
        pygame.draw.circle(s, light, (x - r * 0.32, y - r * 0.34), r * 0.36)
    flowers = pal.get('flowers') or []
    if flowers and variant % 2 == 0 and not snow:
        c = flowers[variant % len(flowers)]
        for _ in range(6):
            a = rng.uniform(0, math.tau)
            d = rng.uniform(0, R * 0.8)
            pygame.draw.circle(s, c, (cx + math.cos(a) * d, cy + math.sin(a) * d), max(1, R * 0.10))
    if snow:
        for x, y, r in lobes:
            pygame.draw.circle(s, (236, 240, 246), (x - r * 0.3, y - r * 0.35), r * 0.45)
    return _finish(s, cx, cy)


def _dry_bush(size, variant, pal, snow=False):
    """Broussaille sèche: rameaux en étoile, quelques feuilles grises."""
    rng = _rng("buisson_sec", variant)
    _dark, mid, _light = pal['bush'][0]
    twig = mix(mid, (120, 96, 60), 0.5)
    s, D, cx, cy = _canvas(size, 0.2)
    R = D * 0.44
    s.blit(_shadow_circles(s.get_size(), [(cx + R * 0.2, cy + R * 0.3, R * 0.6)], 46, 4), (0, 0))
    for _ in range(rng.randint(9, 13)):
        a = rng.uniform(0, math.tau)
        L = R * rng.uniform(0.5, 1.0)
        x1, y1 = cx + math.cos(a) * L, cy + math.sin(a) * L
        pygame.draw.line(s, twig, (cx, cy), (x1, y1), max(1, SS))
        b = a + rng.choice((-1, 1)) * 0.6
        pygame.draw.line(s, twig, (x1, y1), (x1 + math.cos(b) * L * 0.3, y1 + math.sin(b) * L * 0.3),
                         max(1, SS // 2))
        if rng.random() < 0.5:
            pygame.draw.circle(s, mid, (x1, y1), max(1, R * 0.09))
    pygame.draw.circle(s, shade(twig, -20), (cx, cy), max(1, R * 0.12))
    if snow:
        pygame.draw.circle(s, (236, 240, 246), (cx - SS, cy - SS), max(1, R * 0.16))
    return _finish(s, cx, cy)


# ═══════════════════════════════════════════════════════════════
#   MINÉRAL
# ═══════════════════════════════════════════════════════════════

def _rock(size, variant, pal, snow=False, level=0):
    """Rocher: bloc facetté, face supérieure claire, flancs sud-est dans
    l'ombre; mousse ou neige selon le lieu, lézardes s'il est entamé."""
    rng = _rng("rocher", variant)
    s, D, cx, cy = _canvas(size)
    R = D * 0.42
    base = shade(pal.get('stone', (112, 107, 99)), rng.randint(-12, 12))
    n = rng.randint(7, 9)
    off = rng.uniform(0, math.tau)
    outer = []
    for i in range(n):
        a = off + i * math.tau / n + rng.uniform(-0.18, 0.18)
        r = R * rng.uniform(0.75, 1.0)
        outer.append((cx + math.cos(a) * r, cy + math.sin(a) * r * 0.86))
    s.blit(_shadow_poly(s.get_size(), [(x + R * 0.28, y + R * 0.36) for x, y in outer], 96, 4), (0, 0))
    pygame.draw.polygon(s, shade(base, -40), outer)
    # Face supérieure: le contour rétréci et décalé vers le nord-ouest;
    # flancs: facettes entre les deux, éclairées selon leur orientation
    top = [(cx + (x - cx) * 0.66 - R * 0.10, cy + (y - cy) * 0.66 - R * 0.14) for x, y in outer]
    for i in range(n):
        a, b = outer[i], outer[(i + 1) % n]
        ta, tb = top[i], top[(i + 1) % n]
        mx_, my_ = (a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2 - cy
        lit = -(mx_ + my_) / (R * 1.4)
        pygame.draw.polygon(s, shade(base, int(lit * 36) - 8), [a, b, tb, ta])
    pygame.draw.polygon(s, shade(base, 18), top)
    pygame.draw.lines(s, shade(base, 44), False, top[len(top) // 2:] + top[:1], max(1, SS))
    moss = pal.get('moss')
    if moss and not snow:
        for _ in range(3):
            x, y = outer[rng.randrange(n)]
            pygame.draw.circle(s, moss, (x + (cx - x) * 0.25, y + (cy - y) * 0.25), max(1, R * 0.13))
    if snow:
        cap = [(cx + (x - cx) * 0.8, cy + (y - cy) * 0.8 - R * 0.05) for x, y in top]
        pygame.draw.polygon(s, (236, 240, 246), cap)
        pygame.draw.polygon(s, (204, 212, 224), cap, max(1, SS))
    for _ in range(level * 2):
        a = rng.uniform(0, math.tau)
        pygame.draw.line(s, shade(base, -70), (cx, cy),
                         (cx + math.cos(a) * R * 0.9, cy + math.sin(a) * R * 0.8), max(1, SS))
    pygame.draw.polygon(s, shade(base, -62), outer, max(1, SS))
    return _finish(s, cx, cy)


def _pebbles(size, variant, pal, snow=False):
    rng = _rng("caillou", variant)
    s, D, cx, cy = _canvas(size, 0.1)
    for _ in range(rng.randint(2, 4)):
        x = rng.uniform(D * 0.25, D * 0.75)
        y = rng.uniform(D * 0.3, D * 0.7)
        r = D * rng.uniform(0.07, 0.14)
        c = shade(pal.get('stone', (118, 113, 104)), rng.randint(-14, 14))
        pygame.draw.ellipse(s, (0, 0, 0, 64), (x - r + SS, y - r * 0.6 + SS * 1.5, r * 2, r * 1.3))
        pygame.draw.ellipse(s, c, (x - r, y - r * 0.6, r * 2, r * 1.3))
        pygame.draw.ellipse(s, shade(c, 30), (x - r * 0.6, y - r * 0.55, r * 0.9, r * 0.6))
        if snow:
            pygame.draw.ellipse(s, (236, 240, 246), (x - r * 0.7, y - r * 0.6, r * 1.2, r * 0.6))
    return _finish(s, cx, cy)


def _rubble(size, variant, pal, heap=False):
    rng = _rng("gravats", variant, int(heap))
    s, D, cx, cy = _canvas(size, 0.1)
    n = rng.randint(6, 9) if heap else rng.randint(3, 5)
    spread = 0.30 if heap else 0.34
    for _ in range(n):
        x = cx + rng.uniform(-spread, spread) * D
        y = cy + rng.uniform(-spread, spread) * D * 0.8
        w = D * rng.uniform(0.08, 0.18 if heap else 0.13)
        c = (104 + rng.randint(-16, 16), 98 + rng.randint(-14, 14), 90 + rng.randint(-12, 12))
        pts = [(x - w, y + w * 0.3), (x - w * 0.3, y - w * 0.8), (x + w, y - w * 0.3),
               (x + w * 0.5, y + w * 0.8)]
        pygame.draw.polygon(s, (0, 0, 0, 74), [(px + SS * 1.5, py + SS * 2) for px, py in pts])
        pygame.draw.polygon(s, c, pts)
        pygame.draw.line(s, shade(c, 28), pts[0], pts[1], max(1, SS))
    return _finish(s, cx, cy)


# ═══════════════════════════════════════════════════════════════
#   PETITE VÉGÉTATION
# ═══════════════════════════════════════════════════════════════

def _grass(size, variant, pal, tall=False, snow=False):
    rng = _rng("herbe", variant, int(tall))
    lo, hi = pal['grass']
    s, D, cx, cy = _canvas(size, 0.0)
    n = rng.randint(6, 9) if tall else rng.randint(4, 6)
    by = D * 0.62
    for _ in range(n):
        a = -math.pi / 2 + rng.uniform(-0.9, 0.9)
        L = D * (rng.uniform(0.30, 0.46) if tall else rng.uniform(0.18, 0.30))
        x0 = cx + rng.uniform(-D * 0.12, D * 0.12)
        x1, y1 = x0 + math.cos(a) * L, by + math.sin(a) * L
        pygame.draw.line(s, mix(lo, hi, rng.random()), (x0, by), (x1, y1), max(1, SS))
        if snow and rng.random() < 0.4:
            pygame.draw.circle(s, (236, 240, 246), (x1, y1), max(1, SS))
    return _finish(s, cx, cy)


def _flowers(size, variant, pal):
    rng = _rng("fleurs", variant)
    lo, _hi = pal['grass']
    cols = pal.get('flowers') or [(230, 220, 120)]
    s, D, cx, cy = _canvas(size, 0.0)
    c = cols[variant % len(cols)]
    for _ in range(rng.randint(4, 7)):
        x = cx + rng.uniform(-D * 0.28, D * 0.28)
        y = cy + rng.uniform(-D * 0.24, D * 0.24)
        pygame.draw.line(s, lo, (x, y + D * 0.1), (x + rng.uniform(-2, 2), y), max(1, SS))
        r = max(1, D * 0.06)
        for k in range(4):
            a = k * math.pi / 2 + 0.4
            pygame.draw.circle(s, c, (x + math.cos(a) * r, y + math.sin(a) * r), r)
        pygame.draw.circle(s, (250, 220, 90), (x, y), max(1, r * 0.6))
    return _finish(s, cx, cy)


def _fern(size, variant, pal):
    rng = _rng("fougere", variant)
    dark, mid, light = pal['bush'][variant % len(pal['bush'])]
    s, D, cx, cy = _canvas(size, 0.0)
    for _ in range(rng.randint(5, 7)):
        a = rng.uniform(0, math.tau)
        L = D * rng.uniform(0.28, 0.42)
        for j in range(1, 6):
            t = j / 6
            x, y = cx + math.cos(a) * L * t, cy + math.sin(a) * L * t
            for sgn in (-1, 1):
                b = a + sgn * 1.1
                ll = L * 0.22 * (1 - t * 0.6)
                pygame.draw.line(s, mid if sgn < 0 else dark, (x, y),
                                 (x + math.cos(b) * ll, y + math.sin(b) * ll), max(1, SS))
        pygame.draw.line(s, light, (cx, cy), (cx + math.cos(a) * L, cy + math.sin(a) * L), max(1, SS))
    return _finish(s, cx, cy)


def _reeds(size, variant, pal, snow=False):
    """Roseaux de marais: touffe de tiges et de massettes brunes."""
    rng = _rng("roseaux", variant)
    s, D, cx, cy = _canvas(size, 0.0)
    by = D * 0.58
    stem = (150, 146, 110) if snow else (96, 124, 60)
    for _ in range(rng.randint(7, 11)):
        a = -math.pi / 2 + rng.uniform(-0.8, 0.8)
        L = D * rng.uniform(0.3, 0.48)
        x0 = cx + rng.uniform(-D * 0.12, D * 0.12)
        x1, y1 = x0 + math.cos(a) * L, by + math.sin(a) * L
        pygame.draw.line(s, shade(stem, rng.randint(-14, 16)), (x0, by), (x1, y1), max(1, SS))
        if rng.random() < 0.35:
            pygame.draw.ellipse(s, (92, 60, 34), (x1 - SS, y1 - SS * 2.5, SS * 2.2, SS * 5))
    return _finish(s, cx, cy)


def _mushrooms(size, variant, pal):
    rng = _rng("champignon", variant)
    s, D, cx, cy = _canvas(size, 0.1)
    for _ in range(rng.randint(2, 4)):
        x = cx + rng.uniform(-D * 0.2, D * 0.2)
        y = cy + rng.uniform(-D * 0.18, D * 0.18)
        r = D * rng.uniform(0.07, 0.11)
        pygame.draw.circle(s, (0, 0, 0, 64), (x + SS, y + SS * 1.5), r)
        pygame.draw.circle(s, (170, 58, 44), (x, y), r)
        pygame.draw.circle(s, (206, 96, 70), (x - r * 0.3, y - r * 0.3), r * 0.5)
        pygame.draw.circle(s, (240, 232, 220), (x + r * 0.2, y - r * 0.1), max(1, r * 0.22))
    return _finish(s, cx, cy)


def _stump(size, variant, pal, snow=False):
    rng = _rng("souche", variant)
    s, D, cx, cy = _canvas(size, 0.3)
    r = D * 0.26
    s.blit(_shadow_circles(s.get_size(), [(cx + r * 0.3, cy + r * 0.4, r * 1.05)], 76, 3), (0, 0))
    for _ in range(5):
        a = rng.uniform(0, math.tau)
        pygame.draw.line(s, (70, 50, 32), (cx, cy), (cx + math.cos(a) * r * 1.5, cy + math.sin(a) * r * 1.5),
                         max(1, int(SS * 1.5)))
    pygame.draw.circle(s, (78, 56, 34), (cx, cy), r)
    pygame.draw.circle(s, (150, 118, 76), (cx - SS, cy - SS), r * 0.8)
    for k in (0.55, 0.3):
        pygame.draw.circle(s, (118, 90, 56), (cx - SS, cy - SS), r * k, max(1, SS // 2))
    if snow:
        pygame.draw.circle(s, (236, 240, 246), (cx - SS, cy - SS), r * 0.7)
    return _finish(s, cx, cy)


def _log(size, variant, pal, snow=False):
    rng = _rng("tronc", variant)
    s, D, cx, cy = _canvas(size, 0.3)
    a = rng.uniform(-0.6, 0.6)
    L, w = D * 0.40, D * 0.11
    dx, dy = math.cos(a) * L, math.sin(a) * L
    pygame.draw.line(s, (0, 0, 0, 74), (cx - dx + w * 0.5, cy - dy + w), (cx + dx + w * 0.5, cy + dy + w),
                     int(w * 2))
    pygame.draw.line(s, (82, 60, 38), (cx - dx, cy - dy), (cx + dx, cy + dy), int(w * 2))
    pygame.draw.line(s, (112, 84, 52), (cx - dx, cy - dy - w * 0.5), (cx + dx, cy + dy - w * 0.5),
                     max(1, int(w * 0.6)))
    pygame.draw.circle(s, (150, 118, 76), (cx + dx, cy + dy), w)
    pygame.draw.circle(s, (118, 90, 56), (cx + dx, cy + dy), w * 0.5, max(1, SS // 2))
    if snow:
        pygame.draw.line(s, (236, 240, 246), (cx - dx, cy - dy - w * 0.6), (cx + dx, cy + dy - w * 0.6),
                         max(1, int(w * 0.8)))
    return _finish(s, cx, cy)


# ═══════════════════════════════════════════════════════════════
#   OBJETS (village, camp, siège)
# ═══════════════════════════════════════════════════════════════

_SNOW = (236, 240, 246)


def _crate(size, variant, pal, snow=False):
    s, D, cx, cy = _canvas(size, 0.2)
    w = D * 0.5
    r = pygame.Rect(0, 0, w, w)
    r.center = (cx, cy)
    pygame.draw.rect(s, (0, 0, 0, 84), r.move(D * 0.08, D * 0.10), border_radius=SS)
    wood = (132, 98, 58) if variant % 2 else (118, 88, 52)
    pygame.draw.rect(s, wood, r)
    for k in range(1, 4):
        y = r.top + k * w / 4
        pygame.draw.line(s, shade(wood, -26), (r.left, y), (r.right, y), max(1, SS // 2))
    pygame.draw.rect(s, shade(wood, -40), r, max(1, SS))
    pygame.draw.line(s, shade(wood, -34), r.topleft, r.bottomright, max(1, SS))
    pygame.draw.line(s, shade(wood, 18), (r.left + SS, r.top + SS), (r.right - SS, r.top + SS), max(1, SS))
    if snow:
        pygame.draw.rect(s, _SNOW, r.inflate(-SS * 3, -SS * 3).move(-SS, -SS), border_radius=SS)
    return _finish(s, cx, cy)


def _barrel(size, variant, pal, snow=False):
    s, D, cx, cy = _canvas(size, 0.2)
    r = D * 0.26
    pygame.draw.circle(s, (0, 0, 0, 84), (cx + r * 0.3, cy + r * 0.45), r)
    pygame.draw.circle(s, (78, 54, 30), (cx, cy), r)
    pygame.draw.circle(s, (128, 92, 54), (cx, cy), r * 0.86)
    for k in range(-2, 3):
        x = cx + k * r * 0.32
        h = math.sqrt(max(0.0, (r * 0.86) ** 2 - (x - cx) ** 2))
        pygame.draw.line(s, (100, 70, 40), (x, cy - h), (x, cy + h), max(1, SS // 2))
    pygame.draw.circle(s, (150, 146, 136), (cx, cy), r * 0.98, max(1, SS))
    pygame.draw.circle(s, (160, 124, 80), (cx - r * 0.25, cy - r * 0.3), r * 0.28)
    if snow:
        pygame.draw.circle(s, _SNOW, (cx - SS, cy - SS), r * 0.7)
    return _finish(s, cx, cy)


def _hay(size, variant, pal, snow=False):
    rng = _rng("foin", variant)
    s, D, cx, cy = _canvas(size, 0.2)
    r = D * 0.30
    pygame.draw.circle(s, (0, 0, 0, 76), (cx + r * 0.3, cy + r * 0.4), r)
    pygame.draw.circle(s, (170, 140, 60), (cx, cy), r)
    pygame.draw.circle(s, (206, 176, 86), (cx - SS, cy - SS), r * 0.88)
    for k in (0.7, 0.45, 0.2):
        pygame.draw.circle(s, (178, 148, 66), (cx - SS, cy - SS), r * k, max(1, SS // 2))
    for _ in range(10):
        a = rng.uniform(0, math.tau)
        pygame.draw.line(s, (226, 200, 110), (cx + math.cos(a) * r * 0.9, cy + math.sin(a) * r * 0.9),
                         (cx + math.cos(a) * r * 1.1, cy + math.sin(a) * r * 1.1), max(1, SS // 2))
    if snow:
        pygame.draw.circle(s, _SNOW, (cx - SS * 2, cy - SS * 2), r * 0.72)
    return _finish(s, cx, cy)


def _cart(size, variant, pal, snow=False):
    s, D, cx, cy = _canvas(size, 0.2)
    bed = _surf(D, D)
    w, h = D * 0.56, D * 0.32
    r = pygame.Rect(0, 0, w, h)
    r.center = (D / 2, D / 2)
    for sy in (r.top - SS, r.bottom - SS * 2):
        pygame.draw.rect(bed, (54, 40, 26), (r.left + w * 0.2, sy, w * 0.18, SS * 3))
        pygame.draw.rect(bed, (54, 40, 26), (r.right - w * 0.38, sy, w * 0.18, SS * 3))
    pygame.draw.rect(bed, (112, 82, 48), r)
    for k in range(1, 4):
        x = r.left + k * w / 4
        pygame.draw.line(bed, (86, 62, 36), (x, r.top), (x, r.bottom), max(1, SS // 2))
    pygame.draw.rect(bed, (70, 50, 30), r, max(1, SS))
    for sgn in (1, -1):
        y = r.centery - sgn * h * 0.2
        pygame.draw.line(bed, (96, 70, 42), (r.right, y), (r.right + w * 0.3, y - sgn * h * 0.05), SS)
    if snow:
        pygame.draw.rect(bed, _SNOW, r.inflate(-SS * 4, -SS * 4))
    rot = pygame.transform.rotate(bed, (variant % 4) * 90 + 17)
    shadow = rot.copy()
    shadow.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MIN)
    shadow.fill((255, 255, 255, 90), special_flags=pygame.BLEND_RGBA_MULT)
    s.blit(shadow, (cx - rot.get_width() / 2 + SS * 3, cy - rot.get_height() / 2 + SS * 4))
    s.blit(rot, (cx - rot.get_width() / 2, cy - rot.get_height() / 2))
    return _finish(s, cx, cy)


def _brazier(size, variant, pal, snow=False):
    s, D, cx, cy = _canvas(size, 0.2)
    r = D * 0.22
    pygame.draw.circle(s, (0, 0, 0, 84), (cx + r * 0.3, cy + r * 0.4), r * 1.1)
    pygame.draw.circle(s, (60, 56, 52), (cx, cy), r)
    pygame.draw.circle(s, (34, 30, 28), (cx, cy), r * 0.78)
    for k in range(6):
        a = k * 1.1
        pygame.draw.circle(s, (255, 120 + 20 * (k % 3), 30),
                           (cx + math.cos(a) * r * 0.4, cy + math.sin(a) * r * 0.4), r * 0.22)
    pygame.draw.circle(s, (255, 226, 130), (cx, cy), r * 0.26)
    return _finish(s, cx, cy)


def _stakes(size, variant, pal, snow=False):
    """Chevaux de frise: pieux croisés, pointes durcies au feu."""
    s, D, cx, cy = _canvas(size, 0.2)
    a0 = (variant % 3) * 0.4 - 0.4
    L = D * 0.42
    for dx, dy, col in ((SS * 2, SS * 3, (0, 0, 0, 74)), (0, 0, None)):
        pygame.draw.line(s, col or (92, 68, 40), (cx - L + dx, cy + dy), (cx + L + dx, cy + dy),
                         max(1, SS * 2))
        for k in (-0.6, 0, 0.6):
            x = cx + k * L
            for sgn in (-1, 1):
                b = a0 + sgn * 0.8 + math.pi / 2
                ex, ey = x + math.cos(b) * L * 0.55, cy + math.sin(b) * L * 0.55
                pygame.draw.line(s, col or (122, 90, 54), (x + dx, cy + dy), (ex + dx, ey + dy),
                                 max(1, int(SS * 1.5)))
                if col is None:
                    pygame.draw.circle(s, (60, 42, 26), (ex, ey), max(1, SS))
    return _finish(s, cx, cy)


def _bucket(size, variant, pal, snow=False):
    s, D, cx, cy = _canvas(size, 0.2)
    r = D * 0.18
    pygame.draw.circle(s, (0, 0, 0, 74), (cx + SS * 2, cy + SS * 3), r)
    pygame.draw.circle(s, (120, 116, 108), (cx, cy), r)
    pygame.draw.circle(s, (60, 84, 110) if not snow else (200, 214, 228), (cx, cy), r * 0.72)
    pygame.draw.arc(s, (160, 156, 148), (cx - r * 1.2, cy - r * 1.2, r * 2.4, r * 2.4), 0.3, 2.8, max(1, SS))
    return _finish(s, cx, cy)


def _cobbles(size, variant, pal, snow=False):
    rng = _rng("paves", variant)
    s, D, cx, cy = _canvas(size, 0.1)
    for _ in range(rng.randint(4, 7)):
        x = cx + rng.uniform(-D * 0.3, D * 0.3)
        y = cy + rng.uniform(-D * 0.3, D * 0.3)
        w = D * rng.uniform(0.10, 0.16)
        c = (108 + rng.randint(-12, 12), 100 + rng.randint(-10, 10), 90 + rng.randint(-10, 10))
        pygame.draw.rect(s, shade(c, -30), (x - w / 2 + SS, y - w / 2 + SS, w, w * 0.8), border_radius=SS * 2)
        pygame.draw.rect(s, c, (x - w / 2, y - w / 2, w, w * 0.8), border_radius=SS * 2)
    return _finish(s, cx, cy)


def _tent(size, variant, pal, snow=False):
    """Tente de camp vue de dessus: deux pans de toile et un faîtage."""
    s, D, cx, cy = _canvas(size, 0.2)
    canvas = [(214, 200, 170), (196, 176, 140), (182, 170, 150)][variant % 3]
    w, h = D * 0.78, D * 0.56
    r = pygame.Rect(0, 0, w, h)
    r.center = (cx, cy)
    pygame.draw.rect(s, (0, 0, 0, 84), r.move(SS * 4, SS * 5), border_radius=SS * 2)
    top = pygame.Rect(r.left, r.top, w, h / 2)
    bottom = pygame.Rect(r.left, r.centery, w, h / 2)
    pygame.draw.rect(s, shade(canvas, 16), top, border_radius=SS)
    pygame.draw.rect(s, shade(canvas, -30), bottom, border_radius=SS)
    for k in range(1, 5):
        x = r.left + k * w / 5
        pygame.draw.line(s, shade(canvas, -14), (x, r.top), (x, r.bottom), max(1, SS // 2))
    pygame.draw.line(s, shade(canvas, -60), (r.left, r.centery), (r.right, r.centery), max(1, SS))
    pygame.draw.rect(s, shade(canvas, -50), r, max(1, SS), border_radius=SS)
    for px_ in (r.left, r.right):
        for py_ in (r.top, r.bottom):
            ex = px_ + (-1 if px_ == r.left else 1) * D * 0.08
            ey = py_ + (-1 if py_ == r.top else 1) * D * 0.08
            pygame.draw.line(s, (90, 80, 64), (px_, py_), (ex, ey), max(1, SS // 2))
    if snow:
        pygame.draw.rect(s, _SNOW, top.inflate(-SS * 4, -SS * 4))
    return _finish(s, cx, cy)


def _campfire(size, variant, pal, snow=False):
    s, D, cx, cy = _canvas(size, 0.1)
    r = D * 0.26
    for k in range(9):
        a = k * math.tau / 9
        pygame.draw.circle(s, (104, 100, 94), (cx + math.cos(a) * r, cy + math.sin(a) * r), r * 0.22)
        pygame.draw.circle(s, (140, 136, 128), (cx + math.cos(a) * r - SS, cy + math.sin(a) * r - SS), r * 0.12)
    for k in range(3):
        a = k * math.pi / 3 + 0.3
        pygame.draw.line(s, (70, 48, 28), (cx - math.cos(a) * r * 0.7, cy - math.sin(a) * r * 0.7),
                         (cx + math.cos(a) * r * 0.7, cy + math.sin(a) * r * 0.7), max(1, SS * 2))
    pygame.draw.circle(s, (255, 140, 40), (cx, cy), r * 0.42)
    pygame.draw.circle(s, (255, 214, 110), (cx, cy), r * 0.22)
    return _finish(s, cx, cy)


def _woodpile(size, variant, pal, snow=False):
    s, D, cx, cy = _canvas(size, 0.2)
    rows, cols = 2, 4
    r = D * 0.08
    x0, y0 = cx - cols * r, cy - rows * r
    pygame.draw.rect(s, (0, 0, 0, 74), (x0 + SS * 3, y0 + SS * 4, cols * r * 2, rows * r * 2),
                     border_radius=SS * 2)
    for j in range(rows):
        for i in range(cols):
            x, y = x0 + r + i * r * 2, y0 + r + j * r * 2
            pygame.draw.circle(s, (86, 60, 36), (x, y), r)
            pygame.draw.circle(s, (160, 124, 80), (x - SS * 0.5, y - SS * 0.5), r * 0.7)
    if snow:
        pygame.draw.rect(s, _SNOW, (x0, y0 - SS, cols * r * 2, r))
    return _finish(s, cx, cy)


def _sacks(size, variant, pal, snow=False):
    rng = _rng("sacs", variant)
    s, D, cx, cy = _canvas(size, 0.2)
    for _ in range(3):
        x = cx + rng.uniform(-D * 0.15, D * 0.15)
        y = cy + rng.uniform(-D * 0.12, D * 0.12)
        w, h = D * 0.24, D * 0.18
        pygame.draw.ellipse(s, (0, 0, 0, 74), (x - w / 2 + SS * 2, y - h / 2 + SS * 3, w, h))
        pygame.draw.ellipse(s, (170, 150, 108), (x - w / 2, y - h / 2, w, h))
        pygame.draw.ellipse(s, (196, 178, 136), (x - w / 3, y - h / 2 + SS, w / 2, h / 2))
    return _finish(s, cx, cy)


def _well(size, variant, pal, snow=False):
    s, D, cx, cy = _canvas(size, 0.25)
    r = D * 0.32
    pygame.draw.circle(s, (0, 0, 0, 84), (cx + r * 0.25, cy + r * 0.35), r * 1.05)
    pygame.draw.circle(s, (110, 106, 98), (cx, cy), r)
    for k in range(12):
        a = k * math.tau / 12
        pygame.draw.line(s, (80, 76, 70), (cx + math.cos(a) * r * 0.7, cy + math.sin(a) * r * 0.7),
                         (cx + math.cos(a) * r, cy + math.sin(a) * r), max(1, SS // 2))
    pygame.draw.circle(s, (30, 44, 56), (cx, cy), r * 0.66)
    pygame.draw.circle(s, (60, 90, 110), (cx - SS * 2, cy - SS * 2), r * 0.3)
    pygame.draw.line(s, (96, 70, 42), (cx - r * 1.1, cy), (cx + r * 1.1, cy), max(1, SS * 2))
    return _finish(s, cx, cy)


def _banner(size, variant, pal, snow=False):
    """Oriflamme plantée (camp): mât, pied et étoffe au vent."""
    s, D, cx, cy = _canvas(size, 0.2)
    cloth = [(150, 40, 36), (40, 70, 140), (180, 150, 60)][variant % 3]
    pygame.draw.ellipse(s, (0, 0, 0, 74), (cx - D * 0.08, cy + D * 0.02, D * 0.3, D * 0.1))
    pygame.draw.circle(s, (70, 52, 34), (cx, cy), D * 0.05)
    pts = [(cx, cy - D * 0.02), (cx + D * 0.36, cy - D * 0.12), (cx + D * 0.30, cy + D * 0.02),
           (cx + D * 0.38, cy + D * 0.12), (cx, cy + D * 0.08)]
    pygame.draw.polygon(s, cloth, pts)
    pygame.draw.polygon(s, shade(cloth, -40), pts, max(1, SS))
    pygame.draw.line(s, (236, 210, 120), (cx + D * 0.06, cy - D * 0.02), (cx + D * 0.26, cy - D * 0.08), SS)
    return _finish(s, cx, cy)


# ═══════════════════════════════════════════════════════════════
#   CATALOGUE
# ═══════════════════════════════════════════════════════════════
# nature → (dessin, taille en cases, famille). Famille « tall »: dépasse les
# unités qui passent dessous (dessiné en dernier, trié de haut en bas);
# « big »: objet volumineux; « small »: végétation rase et menus objets.

KINDS = {
    "arbre_rond": (_leaf_tree, 1.3, "tall"),
    "arbre_pin":  (_conifer, 1.2, "tall"),
    "palmier":    (_palm, 1.35, "tall"),
    "arbre_nu":   (_bare_tree, 1.25, "tall"),
    "buisson":    (_bush, 0.74, "big"),
    "buisson_sec": (_dry_bush, 0.72, "big"),
    "rocher":     (_rock, 0.74, "big"),
    "souche":     (_stump, 0.6, "big"),
    "tronc":      (_log, 0.95, "big"),
    "caillou":    (_pebbles, 0.75, "small"),
    "gravats":    (_rubble, 0.8, "small"),
    "gravats_tas": (lambda sz, v, p, **k: _rubble(sz, v, p, heap=True), 0.85, "big"),
    "herbe":      (_grass, 0.75, "small"),
    "herbe_haute": (lambda sz, v, p, **k: _grass(sz, v, p, tall=True, **k), 0.9, "small"),
    "fleurs":     (_flowers, 0.8, "small"),
    "fougere":    (_fern, 0.9, "small"),
    "champignon": (_mushrooms, 0.65, "small"),
    "roseaux":    (_reeds, 0.85, "small"),
    "paves":      (_cobbles, 0.85, "small"),
    "seau":       (_bucket, 0.6, "small"),
    "caisse":     (_crate, 0.62, "big"),
    "tonneau":    (_barrel, 0.6, "big"),
    "botte_foin": (_hay, 0.7, "big"),
    "charrette":  (_cart, 1.1, "big"),
    "brasero":    (_brazier, 0.6, "big"),
    "pieux":      (_stakes, 0.9, "big"),
    "tente":      (_tent, 1.5, "big"),
    "feu_camp":   (_campfire, 0.8, "big"),
    "bois_pile":  (_woodpile, 0.72, "big"),
    "sacs":       (_sacks, 0.62, "big"),
    "puits":      (_well, 0.95, "big"),
    "banniere":   (_banner, 0.8, "big"),
}
# Dessins qui savent se couvrir de neige
_SNOWY = {"buisson_sec", "caillou", "herbe", "herbe_haute", "roseaux", "souche", "tronc", "caisse",
          "tonneau", "botte_foin", "charrette", "tente", "bois_pile", "seau", "paves", "brasero",
          "pieux", "feu_camp", "sacs", "puits", "banniere"}


def family(kind):
    return KINDS.get(kind, (None, 0.6, "small"))[2]


def sprite(kind, variant, cs, biome="Prairie", season=DEFAULT_SEASON, state=0):
    """Sprite d'un objet de décor pour des cases de `cs` pixels.

    state: dégâts (1-2) d'un bosquet ou d'un rocher; 3 = en feu (roussi)."""
    variant %= N_VARIANTS
    key = (kind, variant, cs, biome, season, state)
    got = _cache.get(key)
    if got is not None:
        return got
    pal = palette(biome, season)
    snow = pal['snow']
    fn, rel, _fam = KINDS.get(kind, KINDS["caillou"])
    size = max(4, int(round(cs * rel)))
    if kind == "arbre_rond":
        # Désert: le feuillu devient palmier; l'hiver dénude les feuillus
        if biome == "Désert":
            got = _palm(size, variant, pal, scorch=state)
        elif pal['bare'] and state == 0:
            got = _bare_tree(size, variant, pal, snow=snow)
        else:
            got = _leaf_tree(size, variant, pal, scorch=state)
    elif kind == "arbre_pin":
        got = _conifer(size, variant, pal, snow=snow, scorch=state)
    elif kind == "palmier":
        got = _palm(size, variant, pal, scorch=state)
    elif kind == "arbre_nu":
        got = _bare_tree(size, variant, pal, snow=snow)
    elif kind == "rocher":
        got = _rock(size, variant, pal, snow=snow, level=min(2, state))
    elif kind == "buisson":
        got = _bush(size, variant, pal, snow=snow)
    elif kind in _SNOWY:
        got = fn(size, variant, pal, snow=snow)
    else:
        got = fn(size, variant, pal)
    if len(_cache) > 4000:
        _cache.clear()
    _cache[key] = got
    return got


def blit(surf, kind, variant, x, y, cs, biome="Prairie", season=DEFAULT_SEASON, state=0):
    """Pose l'objet centré en (x, y) (pixels)."""
    img, (ax, ay) = sprite(kind, variant, cs, biome, season, state)
    surf.blit(img, (int(x - ax), int(y - ay)))
