import math
import os
import pygame

import theme as T

import effects
import scenery
import sprites


HUD_HEIGHT = 80
# Taille de cellule cible (sera ajustée à l'écran)
TARGET_CELL_SIZE = 28
MIN_CELL_SIZE = 12
MAX_CELL_SIZE = 64

# ─── Cadence de la bataille ───
# Durée d'un round en frames (60 fps). Le moteur y répartit mouvement,
# charges et échanges: la partie défile sans temps mort entre les rounds.
ROUND_FRAMES_NORMAL = 66   # ~1,1 s par round
ROUND_FRAMES_FAST = 20     # ~0,33 s par round
# Part du round occupée par le déplacement (le reste = l'échange)
MOVE_WINDOW = 0.46
# Amplitude maximale de la secousse de caméra, en pixels
SHAKE_MAX = 2.0

# Couleurs de pastille des groupes (une armée peut être articulée en
# plusieurs corps déployés séparément). Volontairement éloignées du bleu
# et du rouge d'équipe.
GROUP_PIPS = [(255, 210, 90), (120, 235, 235), (200, 140, 255), (160, 235, 130)]

# Libellés FR des postures du commandant IA (affichés dans le HUD)
POSTURE_LABELS = {
    "balanced":   ("Équilibré",        (180, 180, 180)),
    "rush":       ("Charge générale",  (255, 150, 60)),
    "hold_line":  ("Ligne de tir",     (90, 180, 255)),
    "hold_walls": ("Défense des murs", (170, 170, 200)),
    "sortie":     ("SORTIE !",         (255, 210, 70)),
    "recall":     ("Repli",            (150, 200, 255)),
    "screen":     ("Écran protecteur", (120, 220, 200)),
    "exploit":    ("Exploitation !",   (255, 120, 90)),
    "regroup":    ("Regroupement",     (200, 170, 120)),
    "fall_back":  ("Repli sur le donjon", (230, 190, 120)),
}

# Bannières d'annonce lors d'un changement de posture
_POSTURE_BANNERS = {
    "rush":      ("CHARGE GÉNÉRALE !",            (255, 150, 60)),
    "hold_line": ("tient la ligne de tir",        (90, 180, 255)),
    "recall":    ("repli derrière les murs",      (150, 200, 255)),
    "screen":    ("couvre ses tireurs !",         (120, 220, 200)),
    "exploit":   ("EXPLOITE LA PERCÉE !",         (255, 120, 90)),
    "regroup":   ("se regroupe",                  (200, 170, 120)),
    "fall_back": ("se replie sur le donjon !",    (230, 190, 120)),
}

# Dossier des tokens (à côté des fichiers .py)
TOKENS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")

# Cache des images de tokens: {(token_name, size): Surface ou None}
_token_cache = {}

# Cache des ombres d'unités: {(w, h): Surface} — évite une allocation
# de Surface par unité et par frame
_shadow_cache = {}


# Cache des pastilles de moral: une rangée de 0 à 6 points, identique pour
# toutes les unités de même moral — une surface au lieu de six cercles.
_pips_cache = {}


def morale_pips(n, radius, color):
    key = (n, radius, color)
    s = _pips_cache.get(key)
    if s is None:
        gap = radius * 2 + 2
        w = max(1, n * gap - 2)
        s = pygame.Surface((w, radius * 2), pygame.SRCALPHA)
        for i in range(n):
            pygame.draw.circle(s, color, (i * gap + radius, radius), radius)
        _pips_cache[key] = s
    return s


def get_shadow(sh_w, sh_h):
    key = (sh_w, sh_h)
    s = _shadow_cache.get(key)
    if s is None:
        s = pygame.Surface((sh_w, sh_h), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 70), (0, 0, sh_w, sh_h))
        _shadow_cache[key] = s
    return s


# Corps d'unité pré-assemblé: ombre + jeton (ou pastille) + anneau d'équipe.
# Ces trois-là ne dépendent que du TYPE d'unité et de son camp, jamais de
# l'instant: à 300 unités à l'écran, c'était un millier d'appels de dessin
# par image, remplacés par un blit. Ce qui bouge (chevron d'orientation,
# survol, flash de dégâts, barre de PV) reste dessiné par-dessus.
_body_cache = {}


unit_glyph = effects.unit_glyph


def _draw_badge(surf, cx, cy, ur, color, glyph):
    """Jeton sans image: disque éclairé par le haut à la couleur de l'unité,
    liseré sombre, et l'insigne de sa classe (lisible sur toute couleur)."""
    import icons
    pygame.draw.circle(surf, T.darken(color, 0.55), (cx, cy), ur)
    pygame.draw.circle(surf, T.darken(color, 0.12), (cx, cy), max(1, ur - 1))
    pygame.draw.circle(surf, T.lighten(color, 0.12), (cx, cy - max(1, ur // 6)),
                       max(1, int(ur * 0.72)))
    size = max(8, int(ur * 1.4))
    light = T.luminance(color) < 150
    ink = (250, 244, 228) if light else (26, 22, 16)
    halo = (16, 14, 12) if light else (255, 250, 236)
    back = icons.icon("glyph_" + glyph, size, halo)
    back.set_alpha(150)
    surf.blit(back, (cx - size // 2 + 1, cy - size // 2 + 1))
    surf.blit(icons.icon("glyph_" + glyph, size, ink), (cx - size // 2, cy - size // 2))


def _draw_figure(surf, cx, cy, ur, color, glyph, team_color, direction):
    """Socle de figurine (disque clair teinté de l'équipe: la silhouette s'en
    détache à toute taille) et figurine vue de dessus, orientée."""
    import unit_sprites
    pygame.draw.circle(surf, T.lighten(T.darken(team_color, 0.25), 0.42), (cx, cy), ur)
    pygame.draw.circle(surf, T.lighten(team_color, 0.62), (cx - max(1, ur // 6), cy - max(1, ur // 6)),
                       max(1, int(ur * 0.78)))
    size = ur * 2 + 2
    fig = unit_sprites.figure(glyph, color, size, direction)
    surf.blit(fig, (cx - size // 2, cy - size // 2))


def unit_body(spec):
    """Surface du corps et demi-côté, pour un blit centré en (cx, cy).

    `spec` = (engin, en fuite, jeton, couleur, insigne, ur, uw, uh, cs,
    couleur d'équipe[, orientation 0..15]) — tout ce dont le dessin
    dépend, et rien d'autre. Sans image de jeton, l'unité est une figurine
    (unit_sprites) tournée selon l'orientation."""
    got = _body_cache.get(spec)
    if got is not None:
        return got
    engine, fleeing, token_name, color, glyph, ur, uw, uh, cs, team_color = spec[:10]
    direction = spec[10] if len(spec) > 10 else 0
    sh_w, sh_h = max(4, ur * 2), max(2, ur // 2 + 2)
    ring_r, ring_w = ur + 2, max(2, cs // 8)
    token_size = min(uw, uh) * cs - 4
    half = max(sh_w // 2, ring_r, ur + sh_h, token_size // 2,
               (uw * cs) // 2, (uh * cs) // 2) + 2
    surf = pygame.Surface((half * 2, half * 2), pygame.SRCALPHA)
    cx = cy = half
    surf.blit(get_shadow(sh_w, sh_h), (cx - sh_w // 2, cy + ur - sh_h // 2))
    if engine:
        draw_siege_engine(surf, engine,
                          pygame.Rect(cx - uw * cs // 2, cy - uh * cs // 2,
                                      uw * cs, uh * cs), team_color)
    elif fleeing:
        _draw_badge(surf, cx, cy, ur, (255, 140, 0), glyph)
    else:
        token_img = load_token(token_name, token_size) if token_name else None
        if token_img:
            surf.blit(token_img, (cx - token_size // 2, cy - token_size // 2))
        elif ur >= 7:
            _draw_figure(surf, cx, cy, ur, color, glyph, team_color, direction)
        else:   # trop petit pour une figurine: l'insigne reste lisible
            _draw_badge(surf, cx, cy, ur, color, glyph)
    if not engine:      # l'engin porte déjà son liseré d'équipe
        pygame.draw.circle(surf, team_color, (cx, cy), ring_r, ring_w)
    if len(_body_cache) > 2048:
        _body_cache.clear()
    _body_cache[spec] = got = (surf, half)
    return got


# Cache des petits textes du champ de bataille (noms, statuts, textes
# flottants). La même chaîne revient à chaque image pour des centaines
# d'unités, et rendre une police coûte bien plus cher que reblitter une
# surface déjà prête: c'était près d'un millier d'appels par image.
_label_cache = {}
_LABEL_CACHE_MAX = 4000


def label(fnt, text, color):
    """Texte rendu, mémorisé par (police, chaîne, couleur).

    La surface est PARTAGÉE: qui veut la poser en fondu passe par
    blit_faded, qui lui rend ensuite sa pleine opacité."""
    key = (id(fnt), text, color)
    s = _label_cache.get(key)
    if s is None:
        if len(_label_cache) > _LABEL_CACHE_MAX:
            _label_cache.clear()
        s = fnt.render(text, True, color)
        _label_cache[key] = s
    return s


def blit_faded(dest, surf, pos, alpha):
    """Blit d'une surface PARTAGÉE (cf. label) à l'opacité `alpha`, rendue
    ensuite à sa pleine opacité: les autres utilisateurs du cache (noms,
    statuts) ne doivent pas hériter du fondu d'un texte flottant."""
    surf.set_alpha(alpha)
    dest.blit(surf, pos)
    surf.set_alpha(None)


# Barres de PV: cadre sombre, fond rouge sombre, jauge — trois rectangles
# par unité et par image, remplacés par un blit. La largeur de jauge est un
# entier (0 → bw): le nombre de variantes reste petit.
_bar_cache = {}


def hp_bar(bw, fill_w, color):
    """Surface (bw + 2) × 5 de la barre, à poser en (x - 1, y - 1) — mêmes
    pixels que les trois draw.rect qu'elle remplace (couleurs opaques)."""
    key = (bw, fill_w, color)
    s = _bar_cache.get(key)
    if s is None:
        s = pygame.Surface((bw + 2, 5))
        s.fill((15, 15, 15))
        s.fill((90, 25, 25), (1, 1, bw, 3))
        if fill_w > 0:
            s.fill(color, (1, 1, fill_w, 3))
        if len(_bar_cache) > 2048:
            _bar_cache.clear()
        _bar_cache[key] = s
    return s


# Halo rouge du flash de dégâts: un disque par (rayon, opacité), et les
# opacités sont en nombre fini — inutile d'allouer une Surface par unité et
# par image.
_flash_cache = {}


def hit_flash(radius, alpha):
    key = (radius, alpha)
    s = _flash_cache.get(key)
    if s is None:
        s = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 40, 40, alpha), (radius + 1, radius + 1), radius)
        if len(_flash_cache) > 512:
            _flash_cache.clear()
        _flash_cache[key] = s
    return s


def load_token(token_name, size):
    """Charge et redimensionne un token. Retourne None si pas trouvé."""
    key = (token_name, size)
    if key in _token_cache:
        return _token_cache[key]

    filepath = os.path.join(TOKENS_DIR, f"{token_name}.png")
    if os.path.exists(filepath):
        try:
            img = pygame.image.load(filepath).convert_alpha()
            img = pygame.transform.smoothscale(img, (size, size))
            _token_cache[key] = img
            return img
        except (pygame.error, OSError):
            _token_cache[key] = None
            return None

    _token_cache[key] = None
    return None


def clear_token_cache():
    """Vide le cache (utile après resize)."""
    _token_cache.clear()
    _shadow_cache.clear()
    _label_cache.clear()
    _pips_cache.clear()
    _body_cache.clear()
    _flash_cache.clear()
    _bar_cache.clear()



def compute_grid_from_screen(target_cell=TARGET_CELL_SIZE):
    """Calcule une grille large avec hauteur fixe de 64 cases.

    Retourne (grid_width, grid_height, cell_size).
    """
    info = pygame.display.Info()
    screen_w = info.current_w

    cell_size = max(MIN_CELL_SIZE, min(target_cell, MAX_CELL_SIZE))

    # Champ de bataille large: ~2,6 écrans de large, 64 cases de haut.
    # Les armées doivent manœuvrer un moment avant de se rencontrer.
    grid_w = int(screen_w * 2.6) // cell_size
    grid_h = 64

    grid_w = max(120, grid_w)

    return grid_w, grid_h, cell_size


def _ground_color(bg, x, y):
    """Variation de sol déterministe (pseudo-bruit, pas de random pour ne
    pas perturber la RNG de la bataille).

    Seulement un grain très fin: toute variation à l'échelle de plusieurs
    cases dessinerait des carrés alignés sur la grille. Les variations
    larges sont confiées aux taches organiques (draw_ground_patches).
    """
    # Aplat: la moindre variation par case se lit comme un carrelage dès
    # que les cases font 30 px. Le relief visuel du sol vient du grain de
    # texture et des taches organiques, qui ignorent la grille.
    return bg


def _detail_seed(x, y):
    """Valeur déterministe 0..255 pour décider des petits détails de sol."""
    n = (x * 2654435761 + y * 40503) & 0xFFFFFFFF
    return (n >> 16) & 0xFF


def _prop_shade(color, d):
    return (max(0, color[0] + d), max(0, color[1] + d), max(0, color[2] + d))


# Décor: sprites de scenery.py. Les « petits » objets (herbes, cailloux)
# se posent au sol; les gros et les arbres sont triés de haut en bas pour
# que celui du dessous passe devant.


def _prop_pos(gx, gy, cs, seed):
    """Position (pixels) d'un objet de décor: décalé dans sa case selon sa
    graine, pour qu'aucun décor ne s'aligne sur la grille."""
    jx = ((seed & 7) - 3) * cs // 14
    jy = (((seed >> 3) & 7) - 3) * cs // 14
    return gx * cs + cs // 2 + jx, gy * cs + cs // 2 + jy


def draw_prop(surf, kind, gx, gy, cs, seed, bg=None, look=("Prairie", scenery.DEFAULT_SEASON)):
    """Dessine un objet de décor dans la case (gx, gy).

    Purement cosmétique: aucune incidence sur la grille, le pathfinding ou
    les lignes de vue. La graine choisit la variante et le décalage."""
    px, py = _prop_pos(gx, gy, cs, seed)
    scenery.blit(surf, kind, seed >> 6, px, py, cs, look[0], look[1])


def _building_components(bf):
    """Regroupe les cases de bâtiment (1) en structures connexes.

    Dessiner chaque case séparément donnait un damier de petits toits
    identiques; en réunissant les cases on obtient de vraies maisons avec
    un faîtage, des murs et une porte.
    """
    seen = set()
    comps = []
    W, H = bf.width, bf.height
    for x in range(W):
        for y in range(H):
            if bf.grid[x][y] != 1 or (x, y) in seen:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            cells = []
            while stack:
                cx, cy = stack.pop()
                cells.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if (0 <= nx < W and 0 <= ny < H and (nx, ny) not in seen
                            and bf.grid[nx][ny] == 1):
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            comps.append((min(xs), min(ys), max(xs), max(ys), len(cells), cells))
    return comps


def _in_region(region, x0, y0, x1, y1):
    """Le rectangle de cases (x0..x1, y0..y1) touche-t-il la région ?"""
    if region is None:
        return True
    rx0, ry0, rx1, ry1 = region
    return not (x1 < rx0 or x0 > rx1 or y1 < ry0 or y0 > ry1)


def _burnt_tint(surf, rect, strength):
    """Assombrit une zone déjà peinte (structure qui brûle)."""
    k = max(0, min(255, int(255 * (1.0 - strength))))
    shade = pygame.Surface((max(1, rect[2]), max(1, rect[3])))
    shade.fill((k, int(k * 0.92), int(k * 0.85)))
    surf.blit(shade, rect[:2], special_flags=pygame.BLEND_RGB_MULT)


def draw_hedge(surf, cells, cs, cset=None, burning=(), look=None):
    """Haie vive: touffes de feuillage reliées d'une case à l'autre, aux
    couleurs de la saison (enneigée l'hiver)."""
    cset = set(cells) if cset is None else cset
    pal = scenery.palette(*(look or ("Prairie", scenery.DEFAULT_SEASON)))
    snow = pal['snow']
    if snow:
        dark, mid, light = (28, 54, 34), (42, 76, 48), (60, 98, 64)
    else:
        dark, mid, light = pal['bush'][0]
    r = max(3, int(cs * 0.42))
    # Ombre et liaison entre cases voisines d'abord, touffes ensuite
    for (x, y) in cells:
        cxp, cyp = x * cs + cs // 2, y * cs + cs // 2
        pygame.draw.circle(surf, scenery.shade(dark, -14), (cxp + 2, cyp + 3), r)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (dx or dy) and (x + dx, y + dy) in cset:
                    pygame.draw.line(surf, dark, (cxp, cyp),
                                     (cxp + dx * cs // 2, cyp + dy * cs // 2), max(3, int(cs * 0.6)))
    for (x, y) in cells:
        cxp, cyp = x * cs + cs // 2, y * cs + cs // 2
        sd = _detail_seed(x, y)
        if (x, y) in burning:
            m, l = (58, 46, 26), (80, 60, 30)
        else:
            m, l = mid, light
        pygame.draw.circle(surf, m, (cxp, cyp), r)
        pygame.draw.circle(surf, l, (cxp - r // 3 + (sd & 3) - 1, cyp - r // 3), max(2, r // 2))
        pygame.draw.circle(surf, m, (cxp + r // 3, cyp + r // 4 - ((sd >> 2) & 3)), max(2, r // 2))
        if (x, y) in burning:
            continue
        if snow:
            pygame.draw.circle(surf, (236, 240, 246), (cxp - r // 3, cyp - r // 3), max(2, r // 2))
            pygame.draw.circle(surf, (214, 222, 234), (cxp + r // 4, cyp - r // 5), max(1, r // 3))
        elif (sd >> 4) % 5 == 0 and pal.get('flowers'):
            fl = pal['flowers'][(sd >> 7) % len(pal['flowers'])]
            pygame.draw.circle(surf, fl, (cxp + r // 4, cyp - r // 4), max(1, cs // 16))


# Couvertures: (couleur de base, motif). Tirées par maison (graine de case)
_ROOFS = (((128, 72, 48), "tuiles"), ((136, 78, 50), "tuiles"),
          ((86, 92, 104), "ardoise"), ((170, 140, 80), "chaume"))


def _roof_texture(surf, rect, roof, kind, cs, along_x):
    """Motif de la couverture dans `rect`: rangs de tuiles, écailles
    d'ardoise ou brins de chaume."""
    dark = _prop_shade(roof, -26)
    x0, y0, w, h = rect
    step = max(4, cs // 2)
    if kind == "tuiles":
        if along_x:
            for lx in range(x0 + step, x0 + w, step):
                pygame.draw.line(surf, dark, (lx, y0 + 1), (lx, y0 + h - 1), 1)
        else:
            for ly in range(y0 + step, y0 + h, step):
                pygame.draw.line(surf, dark, (x0 + 1, ly), (x0 + w - 1, ly), 1)
    elif kind == "ardoise":
        row = max(3, cs // 5)
        for k, ly in enumerate(range(y0 + row, y0 + h, row)):
            pygame.draw.line(surf, dark, (x0 + 1, ly), (x0 + w - 2, ly), 1)
            off = (k % 2) * row
            for lx in range(x0 + off + row, x0 + w - 1, row * 2):
                pygame.draw.line(surf, dark, (lx, ly - row + 1), (lx, ly), 1)
    else:   # chaume: brins courts
        for k in range(max(4, w * h // max(1, cs * 3))):
            sx = x0 + 1 + (_hash3(x0 + k, y0, 3) * max(1, w - 3)) // 255
            sy = y0 + 1 + (_hash3(x0, y0 + k, 4) * max(1, h - 4)) // 255
            pygame.draw.line(surf, dark if k % 2 else _prop_shade(roof, 18), (sx, sy), (sx + 1, sy + 3), 1)


def _draw_house(surf, x0, y0, x1, y1, cs, level=0, burning=False, snow=False):
    """Maison d'un seul tenant: mur, toit à faîtage (tuiles, ardoise ou
    chaume), cheminée, porte. `level` 1-2: toit percé puis éventré;
    `burning`: charpente noircie; `snow`: toit enneigé."""
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    w = bw * cs
    h = bh * cs
    px, py = x0 * cs, y0 * cs
    sd = _detail_seed(x0, y0)
    v = ((sd >> 3) & 7) - 3

    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 70), (0, 0, w, h), border_radius=2)
    surf.blit(sh, (px + max(2, cs // 5), py + max(2, cs // 5)))

    wall = (118 + v * 4, 104 + v * 3, 84 + v * 2)
    wall_dark = _prop_shade(wall, -24)
    base, kind = _ROOFS[_hash3(x0, y0, 5) % len(_ROOFS)]
    roof = _prop_shade(base, v * 4)
    roof_dark = _prop_shade(roof, -26)
    roof_hi = _prop_shade(roof, 22)

    pygame.draw.rect(surf, wall, (px, py, w, h))
    pygame.draw.rect(surf, wall_dark, (px, py, w, h), 1)
    if cs >= 14 and h > cs:
        # Colombages de la façade
        beam = _prop_shade(wall, -46)
        for k in range(1, bw):
            bx = px + k * cs
            pygame.draw.line(surf, beam, (bx, py + h // 2), (bx, py + h - 1), max(1, cs // 14))

    if w >= h:
        ridge_y = py + int(h * 0.42)
        slope = pygame.Rect(px, py, w, ridge_y - py)
        pygame.draw.rect(surf, roof, slope)
        eave = [(px, ridge_y), (px + w, ridge_y),
                (px + w - cs // 4, ridge_y + max(3, cs // 4)), (px + cs // 4, ridge_y + max(3, cs // 4))]
        pygame.draw.polygon(surf, roof_dark, eave)
        _roof_texture(surf, slope, roof, kind, cs, True)
        pygame.draw.line(surf, roof_hi, (px, ridge_y), (px + w, ridge_y), 2)
        chimney = (px + w - cs // 2 - max(3, cs // 5) if sd & 1 else px + cs // 3, py + max(1, cs // 8))
    else:
        ridge_x = px + int(w * 0.42)
        slope = pygame.Rect(px, py, ridge_x - px, h)
        pygame.draw.rect(surf, roof, slope)
        eave = [(ridge_x, py), (ridge_x, py + h),
                (ridge_x + max(3, cs // 4), py + h - cs // 4), (ridge_x + max(3, cs // 4), py + cs // 4)]
        pygame.draw.polygon(surf, roof_dark, eave)
        _roof_texture(surf, slope, roof, kind, cs, False)
        pygame.draw.line(surf, roof_hi, (ridge_x, py), (ridge_x, py + h), 2)
        chimney = (px + max(1, cs // 8), py + h - cs // 2 - max(3, cs // 5) if sd & 1 else py + cs // 3)
    if snow:
        pygame.draw.rect(surf, (230, 236, 244), slope.inflate(-2, -2))
        pygame.draw.polygon(surf, (196, 206, 222), eave)
        pygame.draw.rect(surf, roof_dark, slope, 1)
    if cs >= 12 and level == 0 and kind != "chaume":
        cw = max(3, cs // 5)
        pygame.draw.rect(surf, (0, 0, 0), (chimney[0] + 2, chimney[1] + 2, cw, cw))
        pygame.draw.rect(surf, (96, 88, 82), (chimney[0], chimney[1], cw, cw))
        pygame.draw.rect(surf, (40, 34, 30), (chimney[0] + 1, chimney[1] + 1, max(1, cw - 2), max(1, cw - 2)))

    if cs >= 16 and h > cs:
        door_w = max(3, cs // 3)
        door_h = max(4, int(cs * 0.55))
        dx = px + w // 2 - door_w // 2
        dy = py + h - door_h
        pygame.draw.rect(surf, (62, 44, 28), (dx, dy, door_w, door_h))
        pygame.draw.rect(surf, (40, 28, 18), (dx, dy, door_w, door_h), 1)
        if w > 2 * cs:
            win = max(3, cs // 4)
            for wx in (px + cs // 2, px + w - cs // 2 - win):
                pygame.draw.rect(surf, (72, 84, 92),
                                 (wx, py + h - door_h - win - 2, win, win))
                pygame.draw.rect(surf, (46, 34, 22),
                                 (wx, py + h - door_h - win - 2, win, win), 1)

    # ── Dégâts: le toit se perce, puis s'éventre sur la charpente ──
    if level >= 1:
        n_holes = max(1, 2 * bw * bh // 3 + (level - 1) * bw * bh)
        for k in range(n_holes):
            hx = px + int(w * (0.15 + 0.7 * (_hash3(x0, y0, k + 11) / 255)))
            hy = py + int(h * (0.12 + 0.6 * (_hash3(x0, y0, k + 29) / 255)))
            rw = max(3, int(cs * (0.22 + 0.18 * level)))
            pygame.draw.ellipse(surf, (34, 24, 18), (hx - rw // 2, hy - rw // 3, rw, max(2, rw * 2 // 3)))
            # tuiles tombées au pied du mur
            pygame.draw.rect(surf, roof_dark, (hx - 4 + (k % 5), py + h + 1 + (k % 3),
                                               max(2, cs // 8), max(2, cs // 10)))
    if level >= 2:
        beam = (58, 40, 24)
        for k in range(bw + 1):
            bx = px + k * w // max(1, bw)
            pygame.draw.line(surf, beam, (bx, py + 2), (bx + cs // 4, py + h - 2), max(2, cs // 10))
    if burning:
        _burnt_tint(surf, (px, py, w, h), 0.45)


def draw_village_buildings(surf, bf, cs, region=None):
    """Maisons (d'un seul tenant) et haies du village.

    Source: les structures du champ de bataille — une maison effondrée
    disparaît, une maison entamée montre ses dégâts. Sans structures
    (anciennes cartes, tests), la forme se déduit de la grille."""
    import terrain_render
    fires = getattr(bf, 'fires', None) or {}
    look = terrain_render.look(bf)
    snow = scenery.palette(*look)['snow']
    if getattr(bf, 'structures', None):
        import structures as st
        hedge_all = set()
        for gid, cells in bf.structure_members.items():
            if bf.structure_hp.get(gid, 0) <= 0:
                continue
            kind = bf.structure_kind[gid]
            if kind == st.HEDGE:
                hedge_all.update(cells)
            elif kind == st.HOUSE:
                xs = [c[0] for c in cells]
                ys = [c[1] for c in cells]
                if not _in_region(region, min(xs), min(ys), max(xs), max(ys)):
                    continue
                _draw_house(surf, min(xs), min(ys), max(xs), max(ys), cs,
                            st.damage_level(bf, gid), any(c in fires for c in cells), snow)
        hedges = [c for c in sorted(hedge_all) if _in_region(region, c[0], c[1], c[0], c[1])]
        draw_hedge(surf, hedges, cs, hedge_all, fires, look)
        return
    for (x0, y0, x1, y1, n_cells, cells) in _building_components(bf):
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if not _in_region(region, x0, y0, x1, y1):
            continue
        # Une maison est un bloc plein d'au moins 2×2. Tout le reste (arcs,
        # alignements d'une case) est une HAIE: la dessiner comme un toit
        # couvrirait son rectangle englobant, rues comprises.
        if n_cells != bw * bh or bw < 2 or bh < 2:
            draw_hedge(surf, cells, cs, look=look)
            continue
        _draw_house(surf, x0, y0, x1, y1, cs, snow=snow)


def draw_ground_patches(surf, patches, cs, bg):
    """Grandes taches de sol organiques (terre nue, herbe rase, gravier).

    Le bruit par case dessinait fatalement des carrés; ces ellipses,
    indépendantes de la grille, cassent la régularité du damier.
    """
    for (fx, fy, rw, rh, tint, alpha) in patches:
        w = max(6, int(rw * cs))
        h = max(4, int(rh * cs))
        col = (max(0, min(255, bg[0] + tint[0])),
               max(0, min(255, bg[1] + tint[1])),
               max(0, min(255, bg[2] + tint[2])))
        # Un ovale net se verrait comme un autocollant: on empile
        # plusieurs lobes translucides décalés → contour irrégulier et
        # bords fondus.
        pad = max(w, h) // 2
        s_p = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        sd = int(fx * 131 + fy * 71) & 0xFFFF
        a_lobe = max(8, alpha // 3)
        for k in range(5):
            sc = 0.55 + ((sd >> (k * 2)) & 3) * 0.16
            lw = max(4, int(w * sc))
            lh = max(3, int(h * sc))
            ox_l = pad + (w - lw) // 2 + (((sd >> (k * 3)) & 7) - 3) * w // 12
            oy_l = pad + (h - lh) // 2 + (((sd >> (k * 3 + 1)) & 7) - 3) * h // 10
            pygame.draw.ellipse(s_p, (*col, a_lobe), (ox_l, oy_l, lw, lh))
        surf.blit(s_p, (int(fx * cs) - w // 2 - pad, int(fy * cs) - h // 2 - pad))


def _hash3(x, y, k=0):
    n = (x * 73856093 ^ y * 19349663 ^ k * 83492791) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return (n >> 8) & 0xFF


def draw_wall_cell(surf, bf, x, y, cs, wall_color):
    """Mur de pierre: appareil de moellons irréguliers, parapet crénelé côté
    assaillant, arêtes éclairées. Chaque pierre a sa propre teinte — un mur
    uni se lisait comme une bande de carrelage."""
    px, py = x * cs, y * cs
    base = (108, 104, 98)
    pygame.draw.rect(surf, _prop_shade(base, -28), (px, py, cs, cs))  # mortier
    row_h = max(3, cs // 3)
    for r_i in range(0, cs, row_h):
        wy = y * cs + r_i
        row_idx = (py + r_i) // row_h
        off = (cs // 4) if (row_idx % 2) else 0
        bw = max(4, cs // 2)
        bx = px - off
        c_i = 0
        while bx < px + cs:
            v = _hash3(x * 4 + c_i, row_idx, 1) % 23 - 11
            stone = _prop_shade(base, v)
            x0 = max(px, bx + 1)
            x1 = min(px + cs, bx + bw - 1)
            if x1 > x0:
                pygame.draw.rect(surf, stone, (x0, wy + 1, x1 - x0, min(row_h, py + cs - wy) - 1))
                pygame.draw.line(surf, _prop_shade(stone, 18), (x0, wy + 1), (x1 - 1, wy + 1))
            bx += bw
            c_i += 1
    # Parapet crénelé sur la face exposée (côté où il n'y a pas de mur)
    outer_left = not (x > 0 and bf.grid[x - 1][y] in (2, 3))
    outer_right = not (x < bf.width - 1 and bf.grid[x + 1][y] in (2, 3))
    merlon_w = max(3, cs // 4)
    for side_out, sx in ((outer_left, px), (outer_right, px + cs - merlon_w)):
        if not side_out:
            continue
        pygame.draw.rect(surf, _prop_shade(base, -10), (sx, py, merlon_w, cs))
        seg = max(4, cs // 2)
        for k in range(0, cs, seg):
            if ((py + k) // seg) % 2 == 0:
                m_h = seg - 1
                pygame.draw.rect(surf, _prop_shade(base, 14), (sx, py + k, merlon_w, m_h))
                pygame.draw.line(surf, _prop_shade(base, 40), (sx, py + k), (sx + merlon_w - 1, py + k))
                pygame.draw.rect(surf, _prop_shade(base, -45), (sx, py + k, merlon_w, m_h), 1)
    if y == 0 or bf.grid[x][y - 1] not in (2, 3):
        pygame.draw.line(surf, _prop_shade(base, 45), (px, py), (px + cs - 1, py), 2)
    if y == bf.height - 1 or bf.grid[x][y + 1] not in (2, 3):
        pygame.draw.line(surf, _prop_shade(base, -55), (px, py + cs - 1), (px + cs - 1, py + cs - 1), 2)


def draw_gate_cell(surf, bf, x, y, cs, gate_color, bg):
    """Porte fortifiée: battants de planches continues, bandes de fer qui
    courent sur toute la hauteur, jambages de pierre aux extrémités."""
    px, py = x * cs, y * cs
    hp = bf.gate_hp.get((x, y), 0)
    # Ouverture par case: le donjon peut être ouvert quand l'extérieur ne l'est pas
    gates_open = (x, y) in getattr(bf, 'open_gate_cells', ())
    top_end = y == 0 or bf.grid[x][y - 1] != 3
    bot_end = y == bf.height - 1 or bf.grid[x][y + 1] != 3
    if hp > 0 and not gates_open:
        wood = (132, 92, 52)
        pygame.draw.rect(surf, wood, (px, py, cs, cs))
        n_pl = max(3, cs // 8)
        for i in range(n_pl):
            v = _hash3(x, i, 7) % 17 - 8
            plx = px + i * cs // n_pl
            pygame.draw.rect(surf, _prop_shade(wood, v), (plx + 1, py, cs // n_pl - 1, cs))
            pygame.draw.line(surf, _prop_shade(wood, -45), (plx, py), (plx, py + cs))
        # Portes renforcées (fortification 2-3): bandes de fer plus serrées
        band_step = max(6, int(cs * {2: 1.0, 3: 0.6}.get(getattr(bf, 'fortification', 1), 1.5)))
        for wy in range(py - (py % band_step), py + cs, band_step):
            by = wy + band_step // 3
            if py <= by < py + cs:
                pygame.draw.rect(surf, (58, 58, 64), (px, by, cs, max(2, cs // 8)))
                for sx_ in (px + cs // 5, px + cs // 2, px + cs - cs // 5):
                    pygame.draw.circle(surf, (170, 170, 178), (sx_, by + max(1, cs // 16)), max(1, cs // 16))
        if top_end:
            pygame.draw.rect(surf, (96, 92, 88), (px - 2, py, cs + 4, max(3, cs // 6)))
        if bot_end:
            pygame.draw.rect(surf, (96, 92, 88), (px - 2, py + cs - max(3, cs // 6), cs + 4, max(3, cs // 6)))
        # Dégâts: fissures qui apparaissent quand la porte s'affaiblit
        # (plutôt qu'une jauge par case, qui dessinait des barreaux)
        pct = max(0.0, min(1.0, hp / max(1, bf.gate_max_hp.get((x, y), 10))))
        if pct < 0.75:
            n_cracks = 1 if pct >= 0.5 else (2 if pct >= 0.25 else 3)
            for i in range(n_cracks):
                sx_ = px + cs * (0.2 + 0.3 * i)
                sy_ = py + cs * (0.15 + 0.25 * ((x + y + i) % 3))
                pygame.draw.lines(surf, (40, 26, 14), False,
                                  [(sx_, sy_), (sx_ + cs * 0.12, sy_ + cs * 0.18),
                                   (sx_ + cs * 0.05, sy_ + cs * 0.34), (sx_ + cs * 0.16, sy_ + cs * 0.5)], 2)
    elif hp > 0 and gates_open:
        pygame.draw.rect(surf, _ground_color(bg, x, y), (px, py, cs, cs))
        pygame.draw.rect(surf, (112, 78, 44), (px, py, max(3, cs // 6), cs))
        pygame.draw.rect(surf, (112, 78, 44), (px + cs - max(3, cs // 6), py, max(3, cs // 6), cs))
    else:
        pygame.draw.rect(surf, _ground_color(bg, x, y), (px, py, cs, cs))
        for i in range(4):
            a = _hash3(x, y, i) / 255.0 * math.pi
            cx_, cy_ = px + cs * (0.2 + 0.2 * i), py + cs * (0.3 + 0.15 * (i % 3))
            dx, dy = math.cos(a) * cs * 0.22, math.sin(a) * cs * 0.22
            pygame.draw.line(surf, (98, 70, 42), (cx_ - dx, cy_ - dy), (cx_ + dx, cy_ + dy), max(2, cs // 10))


def draw_rampart_cell(surf, bf, x, y, cs):
    """Chemin de ronde: longues dalles décalées, sans quadrillage."""
    px, py = x * cs, y * cs
    base = (116, 110, 100)
    pygame.draw.rect(surf, base, (px, py, cs, cs))
    slab = max(4, int(cs * 0.75))
    for wy in range(py - (py % slab), py + cs, slab):
        row = wy // slab
        off = (slab // 2) if row % 2 else 0
        for wx in range(px - (px % slab) - off, px + cs, slab):
            v = _hash3(wx // slab, row, 3) % 15 - 7
            x0, y0 = max(px, wx + 1), max(py, wy + 1)
            x1, y1 = min(px + cs, wx + slab - 1), min(py + cs, wy + slab - 1)
            if x1 > x0 and y1 > y0:
                pygame.draw.rect(surf, _prop_shade(base, v), (x0, y0, x1 - x0, y1 - y0))


def draw_tower_cell(surf, bf, x, y, cs):
    """Plateforme de tour (fortification 2-3): dalles plus sombres et
    merlons sur le pourtour du carré 2×2."""
    px, py = x * cs, y * cs
    base = (92, 88, 84)
    pygame.draw.rect(surf, base, (px, py, cs, cs))
    half = cs // 2
    for i, (ox, oy) in enumerate(((0, 0), (half, 0), (0, half), (half, half))):
        v = _hash3(x * 2 + i, y, 5) % 13 - 6
        pygame.draw.rect(surf, _prop_shade(base, v), (px + ox + 1, py + oy + 1, half - 2, half - 2))
    cells = bf.tower_cells
    merlon = max(2, cs // 5)
    edge = (70, 66, 62)
    for (dx, dy, rect) in ((0, -1, (px, py, cs, merlon)),
                           (0, 1, (px, py + cs - merlon, cs, merlon)),
                           (-1, 0, (px, py, merlon, cs)),
                           (1, 0, (px + cs - merlon, py, merlon, cs))):
        if (x + dx, y + dy) in cells:
            continue
        pygame.draw.rect(surf, edge, rect)
        # Créneaux: encoches claires le long du parapet
        horizontal = dy != 0
        step = max(4, cs // 3)
        for k in range(step // 2, cs, step):
            notch = ((rect[0] + k, rect[1], max(1, step // 3), merlon) if horizontal
                     else (rect[0], rect[1] + k, merlon, max(1, step // 3)))
            pygame.draw.rect(surf, (128, 122, 114), notch)


_WOOD = (122, 86, 50)
_WOOD_DARK = (74, 50, 28)
_HIDE = (150, 118, 84)


def draw_siege_engine(surf, kind, rect, team_color):
    """Silhouette d'un engin de siège vu de dessus, dans `rect` (son
    empreinte): bélier sous son toit de peaux, beffroi à étages."""
    x, y, w, h = rect
    m = max(2, w // 12)
    if kind == "ram":
        # Toit de peaux à deux pans, poutre ferrée qui dépasse vers l'avant
        roof = pygame.Rect(x + m, y + m, w - 2 * m, h - 2 * m)
        pygame.draw.rect(surf, _HIDE, roof, border_radius=max(2, w // 10))
        pygame.draw.line(surf, _WOOD_DARK, (roof.left, roof.centery), (roof.right, roof.centery),
                         max(1, w // 16))
        for i in range(1, 4):
            lx = roof.left + roof.w * i // 4
            pygame.draw.line(surf, _prop_shade(_HIDE, -30), (lx, roof.top + 2), (lx, roof.bottom - 2), 1)
        beam_h = max(3, h // 7)
        pygame.draw.rect(surf, _WOOD_DARK, (roof.centerx, roof.centery - beam_h // 2,
                                            roof.w // 2 + m + 1, beam_h))
        pygame.draw.rect(surf, (150, 150, 158), (roof.right - 1, roof.centery - beam_h // 2 - 1,
                                                 m + 2, beam_h + 2))
        # Roues
        r = max(2, w // 9)
        for (wx_, wy_) in ((roof.left + r, roof.top), (roof.right - r, roof.top),
                           (roof.left + r, roof.bottom), (roof.right - r, roof.bottom)):
            pygame.draw.circle(surf, _WOOD_DARK, (wx_, wy_), r)
        border = roof
    else:
        # Beffroi: plate-forme crénelée, étages en retrait, pont-levis à l'avant
        body = pygame.Rect(x + m, y + m, w - 2 * m, h - 2 * m)
        pygame.draw.rect(surf, _WOOD, body)
        inner = body.inflate(-body.w // 3, -body.h // 5)
        pygame.draw.rect(surf, _prop_shade(_WOOD, 18), inner)
        for i in range(1, 6):
            ly = body.top + body.h * i // 6
            pygame.draw.line(surf, _WOOD_DARK, (body.left, ly), (body.right, ly), 1)
        merlon = max(2, w // 8)
        for k in range(body.left, body.right, merlon * 2):
            pygame.draw.rect(surf, _WOOD_DARK, (k, body.top, merlon, merlon))
            pygame.draw.rect(surf, _WOOD_DARK, (k, body.bottom - merlon, merlon, merlon))
        pygame.draw.rect(surf, _HIDE, (body.right - merlon, body.top + body.h // 4,
                                       merlon, body.h // 2))
        border = body
    pygame.draw.rect(surf, (20, 16, 12), border, 1)
    pygame.draw.rect(surf, team_color, border.inflate(4, 4), max(2, w // 16),
                     border_radius=max(2, w // 10))


def draw_siege_ramp_cell(surf, x, y, cs):
    """Tour de siège accolée: charpente et planchers, praticable."""
    px, py = x * cs, y * cs
    pygame.draw.rect(surf, _WOOD, (px, py, cs, cs))
    step = max(3, cs // 4)
    for k in range(py, py + cs, step):
        pygame.draw.line(surf, _WOOD_DARK, (px, k), (px + cs, k), 1)
    pygame.draw.line(surf, _WOOD_DARK, (px, py), (px + cs, py + cs), max(1, cs // 12))
    pygame.draw.rect(surf, _WOOD_DARK, (px, py, cs, cs), 1)


def draw_bridge_cell(surf, x, y, cs):
    """Passerelle d'une tour de siège posée sur le mur."""
    px, py = x * cs, y * cs
    pygame.draw.rect(surf, _prop_shade(_WOOD, 12), (px, py, cs, cs))
    step = max(3, cs // 5)
    for k in range(px, px + cs, step):
        pygame.draw.line(surf, _WOOD_DARK, (k, py), (k, py + cs), 1)
    pygame.draw.line(surf, (60, 58, 56), (px, py), (px + cs, py), max(1, cs // 10))
    pygame.draw.line(surf, (60, 58, 56), (px, py + cs - 1), (px + cs, py + cs - 1), max(1, cs // 10))


def draw_wall_shadows(surf, bf, cs, region=None):
    """Ombre portée des murs sur le sol côté assaillant: donne de la hauteur."""
    shade = pygame.Surface((max(2, int(cs * 0.6)), cs), pygame.SRCALPHA)
    w = shade.get_width()
    for i in range(w):
        a = int(90 * (1 - i / w) ** 1.5)
        pygame.draw.line(shade, (0, 0, 0, a), (w - 1 - i, 0), (w - 1 - i, cs))
    x0, y0, x1, y1 = region if region is not None else (0, 0, bf.width - 1, bf.height - 1)
    for x in range(max(1, x0), min(bf.width, x1 + 2)):
        for y in range(max(0, y0), min(bf.height, y1 + 1)):
            if bf.grid[x][y] in (2, 3) and bf.grid[x - 1][y] in (0, 5):
                surf.blit(shade, (x * cs - w, y * cs))


def gate_visual_state(bf):
    """État VISIBLE des portes: ouverte, ou niveau de fissures par case.
    Tant qu'il ne change pas, inutile de repeindre quoi que ce soit."""
    def level(pos, hp):
        if hp <= 0:
            return -1
        pct = hp / max(1, bf.gate_max_hp.get(pos, 10))
        return 0 if pct >= 0.75 else (1 if pct >= 0.5 else (2 if pct >= 0.25 else 3))
    return (tuple(sorted(getattr(bf, 'open_gate_cells', ()))),
            tuple(sorted((pos, level(pos, hp)) for pos, hp in bf.gate_hp.items())))


def repaint_gates(surface, battle, cell_size, previous_state):
    """Repeint UNIQUEMENT les cases de porte dont l'aspect a changé.

    Reconstruire tout le terrain à chaque round coûtait ~90 ms sur une
    grande carte: un à-coup visible une fois par seconde pendant un siège.
    """
    from maps import theme_info
    bf = battle.battlefield
    theme = theme_info(bf)
    bg = theme["bg_color"]
    gate_color = theme.get("gate_color", (140, 100, 50))
    new_state = gate_visual_state(bf)
    if new_state == previous_state:
        return new_state
    old = dict(previous_state[1]) if previous_state else {}
    reopened = previous_state is None or previous_state[0] != new_state[0]
    for pos, lvl in new_state[1]:
        if reopened or old.get(pos) != lvl:
            draw_gate_cell(surface, bf, pos[0], pos[1], cell_size, gate_color, bg)
    return new_state


def _draw_palisade_cell(surf, bf, x, y, cs, level=0, burning=False):
    """Pan de palissade: pieux taillés en pointe, liés par une traverse aux
    pieux voisins; fendu puis éventré selon les dégâts, noirci s'il brûle."""
    px, py = x * cs, y * cs
    wood = (122, 88, 52) if not burning else (70, 50, 34)
    dark = _prop_shade(wood, -34)
    n = 3
    pw = max(2, cs // 5)
    sh = pygame.Surface((cs, max(2, cs // 5)), pygame.SRCALPHA)
    sh.fill((0, 0, 0, 60))
    surf.blit(sh, (px + cs // 6, py + cs - cs // 6))
    for k in range(n):
        if level >= 2 and k == 1:
            continue  # pieu arraché
        sx = px + (k + 1) * cs // (n + 1) - pw // 2
        top = py + cs // 6 + (_hash3(x, y, k) % 3) + (cs // 5 if level >= 1 and k == 2 else 0)
        pygame.draw.rect(surf, wood, (sx, top, pw, py + cs - 2 - top))
        pygame.draw.polygon(surf, wood, [(sx, top), (sx + pw // 2, top - cs // 6), (sx + pw, top)])
        pygame.draw.line(surf, dark, (sx + pw - 1, top), (sx + pw - 1, py + cs - 2), 1)
    bar_y = py + cs // 2
    pygame.draw.line(surf, dark, (px + 2, bar_y), (px + cs - 2, bar_y), max(1, cs // 12))
    structs = getattr(bf, 'structures', {})
    for dy in (-1, 1):
        entry = structs.get((x, y + dy))
        if entry is not None and entry[0] == "palissade":
            pygame.draw.line(surf, dark, (px + cs // 2, py + cs // 2),
                             (px + cs // 2, py + cs // 2 + dy * cs // 2), max(1, cs // 10))


def _draw_wall_damage(surf, x, y, cs, level):
    """Mur entamé par les machines: lézardes, puis moellons arrachés et
    crénelage éboulé au pied du mur."""
    if level <= 0:
        return
    px, py = x * cs, y * cs
    crack = (40, 36, 34)
    for k in range(1 + level):
        sx = px + cs * (0.2 + 0.6 * (_hash3(x, y, k + 40) / 255))
        sy = py + cs * 0.1
        pts = [(sx, sy)]
        for j in range(3):
            sx += (_hash3(x, y, k * 7 + j) % 7 - 3) * cs / 14
            sy += cs * 0.28
            pts.append((sx, min(py + cs - 1, sy)))
        pygame.draw.lines(surf, crack, False, pts, max(1, cs // 14))
    if level >= 2:
        for k in range(3):
            hx = px + int(cs * (0.15 + 0.6 * (_hash3(x, y, k + 60) / 255)))
            hy = py + int(cs * (0.15 + 0.6 * (_hash3(x, y, k + 80) / 255)))
            w = max(3, cs // 4)
            pygame.draw.rect(surf, (52, 48, 46), (hx, hy, w, max(2, w * 2 // 3)))
        # moellons tombés côté assaillant
        for k in range(3):
            pygame.draw.rect(surf, (118, 112, 104),
                             (px - cs // 3 + (k * cs) // 5, py + (k * 11) % max(1, cs - 4),
                              max(2, cs // 7), max(2, cs // 8)))


def _mottle(w, h, cs, seed, color, alpha_max, cells=3.0):
    """Marbrure à grande échelle: un bruit de basse résolution agrandi en
    douceur. Casse l'aplat du sol sans jamais dessiner la grille."""
    step = max(4, int(cs * cells))
    sw, sh = w // step + 2, h // step + 2
    small = pygame.Surface((sw, sh), pygame.SRCALPHA)
    for x in range(sw):
        for y in range(sh):
            v = _hash3(x + seed * 17, y - seed * 29, seed)
            small.set_at((x, y), (color[0], color[1], color[2], v * alpha_max // 255))
    return pygame.transform.smoothscale(small, (sw * step, sh * step))


def _grass_tile(size, pal, winter, seed=5):
    """Tuile de brins et de grains fins, répétée sur tout le sol."""
    import random
    rng = random.Random(seed)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    lo, hi = pal['grass']
    for _ in range(size * size // 90):
        x, y = rng.randrange(1, size - 4), rng.randrange(4, size - 1)
        if winter:
            s.set_at((x, y), (255, 255, 255, rng.randint(40, 90)))
            continue
        c = scenery.mix(lo, hi, rng.random())
        L = rng.randint(2, 4)
        pygame.draw.line(s, (*c, rng.randint(40, 90)), (x, y), (x + rng.randint(-1, 1), y - L))
    return s


def build_ground_layer(battle, cell_size):
    """Couche de SOL: fond, marbrures, taches organiques, grain, brins,
    chemins, puis le terrain immuable (eau, marais, collines, falaises) et
    les traces permanentes (cratères). Construite une fois; le repeint d'une
    région y reprend le sol avant de redessiner ce qui repose dessus.

    Le terrain immuable est celui du DÉBUT de bataille (gardé sur la
    bataille, `_static_terrain`): une colline sous un rocher pulvérisé reste
    dessinée — ses décombres se posent dessus — et une reconstruction de la
    carte donne exactement l'image entretenue par les repeints."""
    from maps import theme_info
    import terrain_render
    bf = battle.battlefield
    cs = cell_size
    W, H = bf.width * cs, bf.height * cs
    theme = theme_info(bf)
    bg = theme["bg_color"]
    biome, season = terrain_render.look(bf)
    pal = scenery.palette(biome, season)
    ground = pygame.Surface((W, H))
    ground.fill(bg)
    if cs >= 6:
        seed = len(bf.map_name)
        # Sur la neige, des ombres bleutées et discrètes (le noir la salit)
        dark = (60, 80, 120) if pal['snow'] else (0, 0, 0)
        ground.blit(_mottle(W, H, cs, seed, dark, 22 if pal['snow'] else 46, 3.5), (0, 0))
        light = (255, 255, 255) if pal['snow'] else scenery.tint(bg, (60, 60, 20))
        ground.blit(_mottle(W, H, cs, seed + 1, light, 34, 2.3), (0, 0))
        if not pal['snow'] and biome != "Désert":
            ground.blit(_mottle(W, H, cs, seed + 2, pal['grass'][1], 40, 5.0), (0, 0))

    # ─── Taches de sol organiques ───
    patches = getattr(bf, 'ground_patches', ())
    if patches and cs >= 12:
        draw_ground_patches(ground, patches, cs, bg)

    # ─── Grain de texture (mouchetures) et brins ───
    grain = sprites.ground_grain(128, 77 + len(bf.map_name))
    for gx in range(0, W, 128):
        for gy in range(0, H, 128):
            ground.blit(grain, (gx, gy))
    if cs >= 12 and (theme["grassy"] or pal['snow']):
        tile = _grass_tile(256, pal, pal['snow'])
        for gx in range(0, W, 256):
            for gy in range(0, H, 256):
                ground.blit(tile, (gx, gy))

    # ─── Champs cultivés et chemins (purement visuels) ───
    for field in getattr(bf, 'fields', ()) or ():
        draw_field(ground, field, cs, season)
    for path in getattr(bf, 'paths', ()) or ():
        draw_path(ground, path, cs, bg, pal['snow'], biome)

    # ─── Terrain immuable ───
    static = getattr(battle, '_static_terrain', None)
    if static is None and bf.terrain is not None:
        static = battle._static_terrain = [col[:] for col in bf.terrain]
    terrain_render.draw_static(ground, bf, cs, static, bg)
    return ground


# Couleur d'une parcelle selon la culture et la saison, et celle des sillons
_CROP_COLORS = {
    "blé": {"Printemps": (104, 150, 70), "Été": (206, 180, 96), "Automne": (170, 146, 92),
            "Hiver": (226, 230, 236)},
    "labour": {"Printemps": (104, 108, 62), "Été": (118, 92, 64), "Automne": (112, 86, 60),
               "Hiver": (222, 224, 228)},
    "pré": {"Printemps": (118, 168, 78), "Été": (136, 156, 78), "Automne": (146, 138, 80),
            "Hiver": (228, 232, 238)},
}


def draw_field(surf, field, cs, season=scenery.DEFAULT_SEASON):
    """Parcelle cultivée (cx, cy, w, h, angle, culture) en cases: aplat de
    la culture, sillons parallèles, bordure d'herbe. Aucun effet de jeu."""
    fx, fy, w, h, ang, crop = field
    if cs < 6:
        return
    base = _CROP_COLORS.get(crop, _CROP_COLORS["pré"]).get(season, (136, 156, 78))
    pw, ph = max(4, int(w * cs)), max(4, int(h * cs))
    s = pygame.Surface((pw, ph), pygame.SRCALPHA)
    s.fill((*base, 150))
    furrow = (*_prop_shade(base, -34 if season != "Hiver" else -70), 110)
    step = max(3, cs // 4 if crop != "pré" else cs // 2)
    for k in range(step // 2, ph, step):
        pygame.draw.line(s, furrow, (2, k), (pw - 3, k), 1)
    pygame.draw.rect(s, (*_prop_shade(base, -46), 120), s.get_rect(), max(1, cs // 10))
    rot = pygame.transform.rotate(s, -math.degrees(ang))
    surf.blit(rot, (int(fx * cs - rot.get_width() / 2), int(fy * cs - rot.get_height() / 2)))


def draw_path(surf, path, cs, bg, winter=False, biome="Prairie"):
    """Chemin de terre battue le long d'une polyligne (en cases): bande
    douce, bas-côtés, deux ornières. Aucun effet de jeu."""
    if len(path) < 2 or cs < 6:
        return
    if biome == "Désert":
        dirt = (150, 130, 96)
    elif winter:
        dirt = (168, 164, 158)
    else:
        dirt = scenery.mix(bg, (120, 98, 64), 0.6)
    pts = []
    for (a, b) in zip(path, path[1:]):
        n = max(1, int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 3))
        for k in range(n):
            t = k / n
            pts.append(((a[0] + (b[0] - a[0]) * t) * cs, (a[1] + (b[1] - a[1]) * t) * cs))
    pts.append((path[-1][0] * cs, path[-1][1] * cs))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = cs * 2
    x0, y0 = int(min(xs)) - pad, int(min(ys)) - pad
    layer = pygame.Surface((int(max(xs)) - x0 + pad, int(max(ys)) - y0 + pad), pygame.SRCALPHA)
    r = max(2, int(cs * 0.55))
    edge = (*scenery.shade(dirt, -14), 70)
    for (x, y) in pts:
        pygame.draw.circle(layer, edge, (x - x0, y - y0), r + max(1, cs // 8))
    for (x, y) in pts:
        pygame.draw.circle(layer, (*dirt, 150), (x - x0, y - y0), r)
    rut = (*scenery.shade(dirt, -34), 120)
    for off in (-0.22, 0.22):
        line = []
        for i, (x, y) in enumerate(pts):
            j, k = min(len(pts) - 1, i + 1), max(0, i - 1)
            dx, dy = pts[j][0] - pts[k][0], pts[j][1] - pts[k][1]
            d = math.hypot(dx, dy) or 1.0
            line.append((x - x0 - dy / d * off * cs, y - y0 + dx / d * off * cs))
        if len(line) >= 2:
            pygame.draw.lines(layer, rut, False, line, max(1, cs // 12))
    surf.blit(layer, (x0, y0))


def _obstacle_sprite(bf, x, y, cs, kind, level, burning, look):
    """Sprite d'un obstacle `1` destructible: arbre de bosquet (plus grand
    qu'un arbre de sous-bois) ou affleurement rocheux. Renvoie (y de tri,
    nature, variante, x, y, taille de case, état)."""
    import structures as st
    sd = _hash3(x, y, 7)
    px = x * cs + cs // 2 + ((sd & 7) - 3) * cs // 24
    py = y * cs + cs // 2 + (((sd >> 3) & 7) - 3) * cs // 24
    if kind == st.GROVE or (kind is None and bf.map_name == "Forêt"):
        if look[0] == "Désert":
            tree = "palmier"
        else:
            pine = 110 if bf.map_name == "Forêt" else 60
            tree = "arbre_pin" if _hash3(x, y, 8) < pine else "arbre_rond"
        return (py, tree, _hash3(x, y, 9), px, py, int(cs * 1.2), 3 if burning else level)
    # Rochers: assez gros pour que les amas se lisent comme des blocs
    return (py, "rocher", _hash3(x, y, 9), px, py, int(cs * 1.65), level)


def paint_region(surf, battle, cell_size, ground, x0, y0, x1, y1):
    """Peint tout ce qui est statique sur les cases [x0..x1]×[y0..y1]: sol,
    terrain vivant, fortifications, obstacles, bâtiments, décor, arbres. La
    carte entière et le repeint après destruction passent par ici: même
    résultat."""
    from maps import theme_info
    import structures as st
    import terrain as tr_mod
    import terrain_render
    bf = battle.battlefield
    cs = cell_size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(bf.width - 1, x1), min(bf.height - 1, y1)
    if x1 < x0 or y1 < y0:
        return
    region = (x0, y0, x1, y1)
    theme = theme_info(bf)
    bg = theme["bg_color"]
    wall_color = theme.get("wall_color", (100, 100, 110))
    gate_color = theme.get("gate_color", (140, 100, 50))
    look = terrain_render.look(bf)

    area = pygame.Rect(x0 * cs, y0 * cs, (x1 - x0 + 1) * cs, (y1 - y0 + 1) * cs)
    surf.blit(ground, area.topleft, area)

    # ─── Terrain vivant, au ras du sol ───
    clip = surf.get_clip()
    surf.set_clip(area.clip(clip))
    terrain_render.draw_dynamic(surf, bf, cs, region)
    surf.set_clip(clip)

    structs = getattr(bf, 'structures', None) or {}
    fires = getattr(bf, 'fires', None) or {}
    upright = []          # (y, nature, variante, x, y, taille de case, état)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            cell = bf.grid[x][y]
            if cell == 0:
                continue
            if cell == 2:
                draw_wall_cell(surf, bf, x, y, cs, wall_color)
                entry = structs.get((x, y))
                if entry is not None:
                    _draw_wall_damage(surf, x, y, cs, st.damage_level(bf, entry[1]))
            elif cell == 3:
                draw_gate_cell(surf, bf, x, y, cs, gate_color, bg)
            elif cell == 4 and (x, y) in getattr(bf, 'bridge_cells', ()):
                draw_bridge_cell(surf, x, y, cs)
            elif cell == 5 and (x, y) in getattr(bf, 'siege_ramp_cells', ()):
                draw_siege_ramp_cell(surf, x, y, cs)
            elif cell == 4:
                if (x, y) in getattr(bf, 'tower_cells', ()):
                    draw_tower_cell(surf, bf, x, y, cs)
                else:
                    draw_rampart_cell(surf, bf, x, y, cs)
            elif cell == 5:
                pygame.draw.rect(surf, (104, 98, 88), (x * cs, y * cs, cs, cs))
                step_h = max(2, cs // 4)
                for sy in range(y * cs + 2, (y + 1) * cs - 1, step_h):
                    pygame.draw.line(surf, (95, 85, 70), (x * cs + 2, sy), (x * cs + cs - 2, sy), 1)
                    pygame.draw.line(surf, (55, 50, 42), (x * cs + 2, sy + 1), (x * cs + cs - 2, sy + 1), 1)
            else:
                entry = structs.get((x, y))
                kind = entry[0] if entry is not None else None
                if kind in (st.HOUSE, st.HEDGE) or bf.map_name in ("Village", "Défilé"):
                    continue  # maisons et haies plus bas; falaises cuites dans le sol
                level = st.damage_level(bf, entry[1]) if entry is not None else 0
                if kind == st.PALISADE:
                    _draw_palisade_cell(surf, bf, x, y, cs, level, (x, y) in fires)
                else:
                    upright.append(_obstacle_sprite(bf, x, y, cs, kind, level, (x, y) in fires, look))

    if bf.walls or bf.gate_hp:
        draw_wall_shadows(surf, bf, cs, region)

    if bf.map_name == "Village" or getattr(bf, '_has_buildings', False):
        draw_village_buildings(surf, bf, cs, region)

    # ─── Décor: végétation, cailloux, matériel abandonné ───
    # Posé par-dessus le sol, sous les unités. Aucune incidence de jeu. Le
    # feu et l'effondrement l'emportent: rien ne pousse sur des décombres.
    if cs >= 8:
        terr = bf.terrain
        gone = (tr_mod.RUBBLE, tr_mod.BURNT)
        for (dx_p, dy_p, kind, seed_p) in getattr(bf, 'decor', ()):
            if not (x0 - 1 <= dx_p <= x1 + 1 and y0 - 1 <= dy_p <= y1 + 1):
                continue
            if bf.grid[dx_p][dy_p] != 0:
                continue  # une case devenue mur/obstacle perd son décor
            if terr is not None and terr[dx_p][dy_p] in gone:
                continue
            if scenery.family(kind) == "small":
                draw_prop(surf, kind, dx_p, dy_p, cs, seed_p, bg, look)
            else:
                px, py = _prop_pos(dx_p, dy_p, cs, seed_p)
                upright.append((py, kind, seed_p >> 6, px, py, cs, 0))

    # ─── Arbres et gros objets, de haut en bas ───
    upright += [(yy, k, v, px, py, cs, s)
                for (yy, k, v, px, py, s) in terrain_render.tall_sprites(bf, cs, region)]
    upright.sort()
    for (_yy, kind, v, px, py, size, state) in upright:
        scenery.blit(surf, kind, v, px, py, size, look[0], look[1], state)


def build_grid_surface(battle, cell_size):
    """Pré-rend la surface statique de la carte. La couche de sol est gardée
    sur la bataille (`_ground_layer`) pour les repeints de région."""
    bf = battle.battlefield
    import structures as st
    # Maisons et haies se dessinent d'un seul tenant sur toute carte qui en a
    bf._has_buildings = any(k in (st.HOUSE, st.HEDGE)
                            for k in getattr(bf, 'structure_kind', {}).values())
    ground = build_ground_layer(battle, cell_size)
    battle._ground_layer = ground
    surf = pygame.Surface(ground.get_size())
    paint_region(surf, battle, cell_size, ground, 0, 0, bf.width - 1, bf.height - 1)
    return surf


def repaint_region(surface, battle, cell_size, cells):
    """Repeint UNIQUEMENT le voisinage des cases dont l'aspect a changé
    (effondrement, feu, dégâts). Reconstruire toute la carte coûtait ~90 ms.

    Le clip couvre les cases + 1 de marge (ombres, débordements); le contenu
    est redessiné sur + 2 pour que ce qui déborde des voisines revienne."""
    ground = getattr(battle, '_ground_layer', None)
    if ground is None or not cells:
        return
    cs = cell_size
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
    clip = pygame.Rect((bx0 - 1) * cs, (by0 - 1) * cs,
                       (bx1 - bx0 + 3) * cs, (by1 - by0 + 3) * cs)
    clip = clip.clip(surface.get_rect())
    previous = surface.get_clip()
    surface.set_clip(clip)
    paint_region(surface, battle, cs, ground, bx0 - 2, by0 - 2, bx1 + 2, by1 + 2)
    surface.set_clip(previous)


def bake_crater(surface, battle, x, y, radius, seed):
    """Trace permanente (boule de feu): cuite dans le sol ET dans la surface
    affichée, elle survit aux repeints et ne s'efface jamais."""
    decal = sprites.decal("scorch", max(3, radius * 0.8), seed)
    pos = (int(x - decal.get_width() / 2), int(y - decal.get_height() / 2))
    ground = getattr(battle, '_ground_layer', None)
    if ground is not None:
        ground.blit(decal, pos)
    surface.blit(decal, pos)


def apply_destruction(surface, battle, cell_size, round_frame):
    """Applique les repeints et cratères dont l'instant est venu (listes
    horodatées remplies par le moteur, cf. Battle._flush_structure_changes)."""
    pending = getattr(battle, 'pending_repaints', None)
    if pending:
        due = [cells for d, cells in pending if d <= round_frame]
        if due:
            battle.pending_repaints = [(d, c) for d, c in pending if d > round_frame]
            for cells in due:
                repaint_region(surface, battle, cell_size, cells)
    craters = getattr(battle, 'pending_craters', None)
    if craters:
        due = [c for c in craters if c[0] <= round_frame]
        if due:
            battle.pending_craters = [c for c in craters if c[0] > round_frame]
            for (d, x, y, r) in due:
                bake_crater(surface, battle, x, y, r, int(x * 3 + y * 7))


def draw_intents(screen, battle, cell_size, ox, oy):
    """Intentions des plans de bataille: flèches (marteau, feinte, aile forte),
    zone (aile refusée), drapeau (colline).
    Translucides, dans la couleur du camp, sous les unités."""
    cs = cell_size
    font = _intent_font()
    for cmd, color in ((battle.commander1, (110, 160, 255)), (battle.commander2, (255, 120, 110))):
        plan = getattr(cmd, 'plan', None)
        if plan is None:
            continue
        for it in plan.intents(cmd):
            if it['type'] == 'arrow':
                pts = [(p[0] * cs + cs / 2 + ox, p[1] * cs + cs / 2 + oy) for p in it['points']]
                _draw_soft_arrow(screen, pts, color, max(3, cs // 6))
                lx, ly = pts[-1]
            elif it['type'] == 'zone':
                cx = it['center'][0] * cs + cs / 2 + ox
                cy = it['center'][1] * cs + cs / 2 + oy
                r = int(it['radius'] * cs)
                _draw_dashed_circle(screen, (cx, cy), r, color)
                lx, ly = cx, cy - r
            else:
                lx = it['pos'][0] * cs + cs / 2 + ox
                ly = it['pos'][1] * cs + cs / 2 + oy
                pole_h = int(cs * 1.4)
                pygame.draw.line(screen, (60, 50, 40), (lx, ly), (lx, ly - pole_h), 2)
                pygame.draw.polygon(screen, color, [(lx, ly - pole_h),
                                                    (lx + cs * 0.8, ly - pole_h + cs * 0.25),
                                                    (lx, ly - pole_h + cs * 0.5)])
                ly -= pole_h
            if it.get('label') and cs >= 14:
                t = font.render(it['label'], True, color)
                sh = font.render(it['label'], True, (10, 10, 10))
                screen.blit(sh, (lx - t.get_width() / 2 + 1, ly - t.get_height() - 3))
                screen.blit(t, (lx - t.get_width() / 2, ly - t.get_height() - 4))


_INTENT_FONT = []


def _intent_font():
    if not _INTENT_FONT:
        _INTENT_FONT.append(pygame.font.SysFont("arial", 13, bold=True))
    return _INTENT_FONT[0]


def _draw_soft_arrow(screen, pts, color, width):
    """Flèche translucide (polyligne + pointe), dessinée sur une surface
    limitée à sa boîte englobante."""
    if len(pts) < 2:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = width * 4
    x0, y0 = int(min(xs)) - pad, int(min(ys)) - pad
    w, h = int(max(xs)) - x0 + pad, int(max(ys)) - y0 + pad
    if w <= 0 or h <= 0 or w > 6000 or h > 6000:
        return
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    local = [(p[0] - x0, p[1] - y0) for p in pts]
    pygame.draw.lines(surf, (*color, 120), False, local, width)
    (xa, ya), (xb, yb) = local[-2], local[-1]
    ang = math.atan2(yb - ya, xb - xa)
    head = width * 3.2
    left = (xb - head * math.cos(ang - 0.45), yb - head * math.sin(ang - 0.45))
    right = (xb - head * math.cos(ang + 0.45), yb - head * math.sin(ang + 0.45))
    pygame.draw.polygon(surf, (*color, 170), [(xb, yb), left, right])
    screen.blit(surf, (x0, y0))


def _draw_dashed_circle(screen, center, radius, color):
    cx, cy = center
    n = max(12, int(radius / 3))
    for k in range(0, n, 2):
        a0 = k / n * math.tau
        a1 = (k + 1) / n * math.tau
        pygame.draw.line(screen, color, (cx + math.cos(a0) * radius, cy + math.sin(a0) * radius),
                         (cx + math.cos(a1) * radius, cy + math.sin(a1) * radius), 2)


def draw_battle_report(screen, report, screen_w, battlefield_h, small_font, tiny_font, footer=0):
    """Rapport de bataille: panneau du thème sur la carte assombrie.
    `footer`: hauteur réservée en bas du panneau (boutons d'action).
    Retourne le rect du panneau."""
    header_font = T.font('title', 18)
    body_font = T.font('ui_bold', 13)
    detail_font = T.font('ui', 13)
    small = T.font('ui', 11)

    veil = pygame.Surface((screen_w, battlefield_h), pygame.SRCALPHA)
    veil.fill((6, 7, 9, 150))
    screen.blit(veil, (0, 0))

    panel_w = min(780, screen_w - 20)
    panel_h = min(660 + footer, battlefield_h - 10)
    px = (screen_w - panel_w) // 2
    py = (battlefield_h - panel_h) // 2
    prect = T.panel(screen, (px, py, panel_w, panel_h))
    content = prect.inflate(-8, -8)
    content.h -= footer

    y = T.title(screen, "Rapport de bataille", prect.centerx, py + 14, 26)
    T.text(screen, f"Victoire : {report['winner']}   ·   {report['rounds']} rounds",
           T.font('serif', 16), (prect.centerx, y), T.PARCHMENT, align="center")
    y += 32

    col_w = (panel_w - 60) // 2
    clip = screen.get_clip()
    screen.set_clip(content)

    def listing(label, items, color, item_color, col_x, cy):
        cy = T.section_header(screen, label, col_x, cy, col_w, color, 14)
        for name, count in items[:8]:
            txt = f"{name}  ×{count}" if count > 1 else name
            T.diamond(screen, col_x + 5, cy + 8, 2, color)
            T.text(screen, txt, detail_font, (col_x + 14, cy), item_color)
            cy += 17
        if len(items) > 8:
            rest = sum(c for _, c in items[8:])
            T.text(screen, f"… et {rest} autres", small, (col_x + 14, cy), T.MUTED)
            cy += 16
        return cy + 6

    for i, army_key in enumerate(['army1', 'army2']):
        army = report[army_key]
        col_x = px + 22 + i * (col_w + 16)
        cy = y
        team = T.TEAM[i]

        T.diamond(screen, col_x + 5, cy + 11, 5, team)
        T.text(screen, army['name'], header_font, (col_x + 16, cy), T.lighten(team, 0.3))
        cy += 28

        total = army['total']
        n_alive, n_dead, n_fled = army['alive_count'], army['dead_count'], army['fled_count']
        if total > 0:
            T.bar(screen, (col_x, cy, col_w, 14),
                  [(n_alive / total, (70, 170, 90)), (n_fled / total, T.WARNING),
                   (n_dead / total, (130, 42, 40))])
        cy += 22
        chip_w = (col_w - 12) // 3
        for k, (lbl, n, c) in enumerate((("vivants", n_alive, T.SUCCESS),
                                         ("en fuite", n_fled, T.WARNING),
                                         ("morts", n_dead, T.DANGER))):
            T.pill(screen, (col_x + k * (chip_w + 6), cy, chip_w, 22),
                   f"{n}/{total} {lbl}", small, c, 36)
        cy += 32

        # ── Détail par contingent (équipe composée de plusieurs armées) ──
        contingents = army.get('contingents') or []
        if len(contingents) > 1:
            cy = T.section_header(screen, "Contingents", col_x, cy, col_w, T.GOLD, 14)
            for c in contingents[:4]:
                T.text(screen, c['name'][:28], body_font, (col_x, cy), T.PARCHMENT)
                T.text(screen, f"{c['alive_count']} / {c['fled_count']} / {c['dead_count']}"
                       f"  (sur {c['total']})", small, (col_x + col_w, cy + 2),
                       T.PARCHMENT_DIM, align="right")
                cy += 17
                if c['total'] > 0:
                    T.bar(screen, (col_x, cy, col_w, 5),
                          [(c['alive_count'] / c['total'], (70, 170, 90)),
                           (c['fled_count'] / c['total'], T.WARNING),
                           (c['dead_count'] / c['total'], (130, 42, 40))])
                cy += 11
            cy += 6

        if army['alive']:
            cy = listing("Survivants", army['alive'], T.SUCCESS, (190, 225, 190), col_x, cy)
        if army['fled']:
            cy = listing("En fuite", army['fled'], T.WARNING, (230, 200, 140), col_x, cy)
        if army['dead']:
            cy = listing("Tombés", army['dead'], T.DANGER, (215, 160, 150), col_x, cy)

    screen.set_clip(clip)
    pygame.draw.line(screen, T.darken(T.GOLD_DIM, 0.4), (prect.centerx, y),
                     (prect.centerx, content.bottom - 12))
    if footer:
        T.divider(screen, prect.x + 30, prect.right - 30, content.bottom + 2)
    return prect


def run_visual(battle, cell_size):
    """Joue la bataille à l'écran (cf. battle_view.BattleView). Renvoie
    "menu" pour revenir au menu, None pour quitter."""
    from battle_view import BattleView
    return BattleView(battle, cell_size).run()
