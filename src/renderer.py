import math
import os
import pygame

import theme as T

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


def unit_body(spec):
    """Surface du corps et demi-côté, pour un blit centré en (cx, cy).

    `spec` = (engin, en fuite, jeton, couleur, rôle, ur, uw, uh, cs, couleur
    d'équipe) — tout ce dont le dessin dépend, et rien d'autre."""
    got = _body_cache.get(spec)
    if got is not None:
        return got
    engine, fleeing, token_name, color, role, ur, uw, uh, cs, team_color = spec
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
        pygame.draw.circle(surf, (255, 140, 0), (cx, cy), ur)
    else:
        token_img = load_token(token_name, token_size) if token_name else None
        if token_img:
            surf.blit(token_img, (cx - token_size // 2, cy - token_size // 2))
        else:
            pygame.draw.circle(surf, color, (cx, cy), ur)
            rc = ((255, 255, 255) if role == "front" else (128, 128, 128)
                  if role == "mid" else (0, 0, 0))
            pygame.draw.circle(surf, rc, (cx, cy), max(1, 3 * cs // 32))
    if not engine:      # l'engin porte déjà son liseré d'équipe
        pygame.draw.circle(surf, team_color, (cx, cy), ring_r, ring_w)
    if len(_body_cache) > 512:
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

    La surface est PARTAGÉE: qui joue sur son alpha (textes flottants) doit
    le refixer avant chaque blit, jamais après."""
    key = (id(fnt), text, color)
    s = _label_cache.get(key)
    if s is None:
        if len(_label_cache) > _LABEL_CACHE_MAX:
            _label_cache.clear()
        s = fnt.render(text, True, color)
        _label_cache[key] = s
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


# Objets de décor "volumineux": ils reçoivent une ombre portée
_BIG_PROPS = {"arbre_rond", "arbre_pin", "buisson", "buisson_sec", "souche",
              "tronc", "rocher", "caisse", "tonneau", "botte_foin",
              "charrette", "brasero", "gravats_tas", "pieux"}


def _prop_shade(color, d):
    return (max(0, color[0] + d), max(0, color[1] + d), max(0, color[2] + d))


def draw_prop(surf, kind, gx, gy, cs, seed, bg):
    """Dessine un objet de décor dans la case (gx, gy).

    Purement cosmétique: aucune incidence sur la grille, le pathfinding ou
    les lignes de vue. Chaque objet est légèrement décalé et teinté selon
    sa graine pour qu'aucun décor ne se répète à l'identique.
    """
    u = max(1, cs // 8)                    # unité de dessin proportionnelle
    jx = ((seed & 7) - 3) * cs // 16
    jy = (((seed >> 3) & 7) - 3) * cs // 16
    px = gx * cs + cs // 2 + jx
    py = gy * cs + cs // 2 + jy
    tint = ((seed >> 6) & 7) - 3           # -3..+3 variation de teinte

    # Ombre portée des gros objets: donne du volume au sol
    if kind in _BIG_PROPS and cs >= 14:
        sh_w = max(3, int(cs * 0.55))
        sh_h = max(2, sh_w // 3)
        sh = pygame.Surface((sh_w, sh_h), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 55), (0, 0, sh_w, sh_h))
        surf.blit(sh, (px - sh_w // 2, py + max(1, cs // 6)))

    if kind == "herbe":
        c = (min(255, bg[0] + 10 + tint), min(255, bg[1] + 26 + tint), min(255, bg[2] + 8))
        for k in range(3):
            bx = px + (k - 1) * max(1, u)
            pygame.draw.line(surf, c, (bx, py + u), (bx + (k - 1), py - u), 1)
    elif kind == "herbe_haute":
        c = (min(255, bg[0] + 6), min(255, bg[1] + 34 + tint), min(255, bg[2] + 6))
        for k in range(5):
            bx = px + (k - 2) * max(1, u // 2 + 1)
            pygame.draw.line(surf, c, (bx, py + u), (bx + (k - 2), py - 2 * u), 1)
    elif kind == "fleurs":
        stem = (min(255, bg[0] + 4), min(255, bg[1] + 28), min(255, bg[2] + 4))
        petals = [(230, 220, 120), (220, 130, 180), (170, 190, 240), (240, 160, 90)]
        pc = petals[(seed >> 9) % len(petals)]
        for k in range(3):
            bx = px + (k - 1) * max(2, u)
            by = py + u - (k % 2) * u
            pygame.draw.line(surf, stem, (bx, py + u), (bx, by - u), 1)
            pygame.draw.circle(surf, pc, (bx, by - u), max(1, u // 2))
    elif kind == "champignon":
        pygame.draw.line(surf, (215, 205, 180), (px, py + u), (px, py - u // 2), 1)
        pygame.draw.circle(surf, (150, 64, 52), (px, py - u), max(1, u // 2 + 1))
        pygame.draw.circle(surf, (196, 186, 170), (px + 1, py - u), 1)
    elif kind == "fougere":
        c = (30, 90 + tint * 3, 40)
        for k in range(5):
            ang = -1.9 + k * 0.45
            ex = px + int(math.cos(ang) * cs * 0.22)
            ey = py + u + int(math.sin(ang) * cs * 0.22)
            pygame.draw.line(surf, c, (px, py + u), (ex, ey), 1)
    elif kind == "caillou":
        c = _prop_shade((118, 114, 106), tint * 4)
        rr = max(1, u // 2 + 1)
        pygame.draw.ellipse(surf, c, (px - rr, py - rr // 2, rr * 2, max(2, rr)))
    elif kind == "paves":
        c = _prop_shade((105, 98, 88), tint * 3)
        for k in range(3):
            bx = px + (k - 1) * (u + 1)
            pygame.draw.rect(surf, c, (bx, py + (k % 2) - 1, max(2, u), max(1, u - 1)))
    elif kind == "gravats":
        c = _prop_shade((96, 92, 88), tint * 3)
        for k in range(3):
            pygame.draw.rect(surf, c, (px + (k - 1) * u, py + ((k * 3) % 3) - 1,
                                       max(1, u - 1), max(1, u - 1)))
    elif kind == "gravats_tas":
        base = _prop_shade((104, 100, 94), tint * 3)
        for k in range(4):
            rr = max(1, u - (k % 2))
            pygame.draw.circle(surf, _prop_shade(base, -6 * (k % 2)),
                               (px + (k - 2) * u, py + u - (k % 3)), rr)
    elif kind == "buisson":
        dark = (22, 62 + tint * 2, 22)
        mid = (34, 86 + tint * 3, 30)
        hi = (52, 108 + tint * 2, 42)
        rr = max(2, int(cs * 0.22))
        pygame.draw.circle(surf, dark, (px, py + 1), rr + 1)
        pygame.draw.circle(surf, mid, (px - rr // 2, py), rr)
        pygame.draw.circle(surf, mid, (px + rr // 2, py), rr)
        pygame.draw.circle(surf, mid, (px, py - rr // 2), rr)
        pygame.draw.circle(surf, hi, (px - rr // 3, py - rr // 2), max(1, rr // 2))
    elif kind == "buisson_sec":
        c = (96 + tint * 3, 82, 54)
        for k in range(5):
            ang = -2.3 + k * 0.55
            ex = px + int(math.cos(ang) * cs * 0.24)
            ey = py + u + int(math.sin(ang) * cs * 0.24)
            pygame.draw.line(surf, c, (px, py + u), (ex, ey), 1)
            pygame.draw.line(surf, c, (ex, ey), (ex + 2 - (k % 3), ey - 2), 1)
    elif kind == "arbre_rond":
        trunk = (74, 52, 32)
        rr = max(3, int(cs * 0.30))
        pygame.draw.rect(surf, trunk, (px - max(1, u // 2), py, max(2, u), max(2, rr)))
        pygame.draw.circle(surf, (16, 48 + tint, 14), (px + 1, py - rr // 2 + 1), rr)
        pygame.draw.circle(surf, (30, 84 + tint * 2, 26), (px, py - rr // 2), rr - 1)
        pygame.draw.circle(surf, (48, 106 + tint, 38),
                           (px - rr // 3, py - rr // 2 - rr // 3), max(1, rr // 2))
    elif kind == "arbre_pin":
        trunk = (66, 46, 28)
        h = max(4, int(cs * 0.62))
        pygame.draw.rect(surf, trunk, (px - max(1, u // 2), py + h // 4, max(2, u), h // 3))
        for k in range(3):
            w_t = max(3, int(cs * (0.34 - 0.07 * k)))
            top = py + h // 4 - int(h * (0.28 + 0.26 * k))
            base_y = top + max(3, int(h * 0.36))
            pygame.draw.polygon(surf, (18, 62 + tint * 2 + k * 6, 24),
                                [(px, top), (px - w_t, base_y), (px + w_t, base_y)])
    elif kind == "souche":
        rr = max(2, int(cs * 0.20))
        pygame.draw.ellipse(surf, (72, 50, 30), (px - rr, py - rr // 2, rr * 2, rr))
        pygame.draw.ellipse(surf, (104, 76, 46), (px - rr + 1, py - rr // 2, rr * 2 - 2, max(2, rr - 1)))
        pygame.draw.ellipse(surf, (78, 56, 34), (px - rr // 2, py - rr // 4, rr, max(1, rr // 2)), 1)
    elif kind == "tronc":
        w_l = max(4, int(cs * 0.62))
        h_l = max(2, int(cs * 0.22))
        pygame.draw.rect(surf, (86, 62, 38), (px - w_l // 2, py - h_l // 2, w_l, h_l),
                         border_radius=max(1, h_l // 2))
        pygame.draw.ellipse(surf, (118, 88, 54), (px + w_l // 2 - h_l, py - h_l // 2, h_l, h_l))
        pygame.draw.line(surf, (66, 46, 28), (px - w_l // 3, py), (px + w_l // 4, py), 1)
    elif kind == "rocher":
        base = _prop_shade((112, 106, 96), tint * 4)
        rr = max(2, int(cs * 0.26))
        pygame.draw.polygon(surf, _prop_shade(base, -18),
                            [(px - rr, py + rr // 2), (px - rr // 2, py - rr),
                             (px + rr, py - rr // 3), (px + rr // 2, py + rr // 2)])
        pygame.draw.polygon(surf, base,
                            [(px - rr + 1, py + rr // 2 - 1), (px - rr // 3, py - rr + 2),
                             (px + rr - 1, py - rr // 3), (px + rr // 3, py + rr // 2 - 1)])
        pygame.draw.line(surf, _prop_shade(base, 26),
                         (px - rr // 3, py - rr + 3), (px + rr // 3, py - rr // 4), 1)
    elif kind == "caisse":
        w_c = max(3, int(cs * 0.42))
        r_c = pygame.Rect(px - w_c // 2, py - w_c // 2, w_c, w_c)
        pygame.draw.rect(surf, (118, 88, 52), r_c)
        pygame.draw.rect(surf, (82, 60, 34), r_c, 1)
        pygame.draw.line(surf, (92, 68, 40), r_c.topleft, r_c.bottomright, 1)
        pygame.draw.line(surf, (92, 68, 40), r_c.topright, r_c.bottomleft, 1)
    elif kind == "tonneau":
        w_b = max(3, int(cs * 0.34))
        h_b = max(4, int(cs * 0.46))
        r_b = pygame.Rect(px - w_b // 2, py - h_b // 2, w_b, h_b)
        pygame.draw.ellipse(surf, (104, 72, 40), r_b)
        pygame.draw.ellipse(surf, (74, 52, 28), r_b, 1)
        pygame.draw.line(surf, (140, 130, 110),
                         (r_b.left, py - h_b // 6), (r_b.right, py - h_b // 6), 1)
        pygame.draw.line(surf, (140, 130, 110),
                         (r_b.left, py + h_b // 6), (r_b.right, py + h_b // 6), 1)
    elif kind == "botte_foin":
        w_h = max(4, int(cs * 0.46))
        h_h = max(3, int(cs * 0.34))
        r_h = pygame.Rect(px - w_h // 2, py - h_h // 2, w_h, h_h)
        pygame.draw.rect(surf, (196, 168, 78), r_h, border_radius=max(1, h_h // 3))
        pygame.draw.rect(surf, (150, 126, 56), r_h, 1, border_radius=max(1, h_h // 3))
        for k in range(2):
            ly = r_h.top + (k + 1) * h_h // 3
            pygame.draw.line(surf, (168, 142, 62), (r_h.left + 1, ly), (r_h.right - 1, ly), 1)
    elif kind == "charrette":
        w_w = max(5, int(cs * 0.58))
        pygame.draw.line(surf, (96, 70, 42), (px - w_w // 2, py), (px + w_w // 2, py),
                         max(2, cs // 12))
        wr = max(2, int(cs * 0.16))
        for sx in (px - w_w // 3, px + w_w // 3):
            pygame.draw.circle(surf, (70, 52, 32), (sx, py + wr), wr)
            pygame.draw.circle(surf, (120, 92, 56), (sx, py + wr), wr, 1)
    elif kind == "brasero":
        rr = max(2, int(cs * 0.20))
        pygame.draw.rect(surf, (70, 66, 62), (px - rr, py, rr * 2, max(2, rr)))
        pygame.draw.circle(surf, (255, 150, 40), (px, py - 1), max(1, rr // 2 + 1))
        pygame.draw.circle(surf, (255, 220, 120), (px, py - 2), max(1, rr // 3))
    elif kind == "pieux":
        h_p = max(4, int(cs * 0.55))
        pygame.draw.line(surf, (112, 84, 50), (px - u, py + h_p // 2), (px + u, py - h_p // 2), 2)
        pygame.draw.line(surf, (92, 68, 40), (px + u, py + h_p // 2), (px - u, py - h_p // 2), 2)
    elif kind == "seau":
        w_s = max(3, int(cs * 0.26))
        r_s = pygame.Rect(px - w_s // 2, py - w_s // 2, w_s, w_s)
        pygame.draw.rect(surf, (120, 116, 108), r_s)
        pygame.draw.arc(surf, (150, 146, 138), r_s.inflate(2, 2), 0.2, 2.9, 1)


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


def draw_hedge(surf, cells, cs, cset=None, burning=()):
    """Haie vive: touffes de feuillage reliées d'une case à l'autre."""
    cset = set(cells) if cset is None else cset
    dark, mid, light = (26, 58, 24), (40, 84, 34), (60, 108, 46)
    r = max(3, int(cs * 0.42))
    # Ombre et liaison entre cases voisines d'abord, touffes ensuite
    for (x, y) in cells:
        cxp, cyp = x * cs + cs // 2, y * cs + cs // 2
        pygame.draw.circle(surf, (18, 30, 16), (cxp + 2, cyp + 3), r)
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
        if (sd >> 4) % 5 == 0 and (x, y) not in burning:
            pygame.draw.circle(surf, (220, 210, 230), (cxp + r // 4, cyp - r // 4), max(1, cs // 16))


def _draw_house(surf, x0, y0, x1, y1, cs, level=0, burning=False):
    """Maison d'un seul tenant: mur, toit à faîtage, porte. `level` 1-2:
    toit percé puis éventré; `burning`: charpente noircie."""
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
    roof = (128 + v * 5, 72 + v * 2, 48)
    roof_dark = _prop_shade(roof, -26)
    roof_hi = _prop_shade(roof, 22)

    pygame.draw.rect(surf, wall, (px, py, w, h))
    pygame.draw.rect(surf, wall_dark, (px, py, w, h), 1)

    if w >= h:
        ridge_y = py + int(h * 0.42)
        pygame.draw.polygon(surf, roof, [(px, ridge_y), (px + w, ridge_y),
                                         (px + w, py), (px, py)])
        pygame.draw.polygon(surf, roof_dark,
                            [(px, ridge_y), (px + w, ridge_y),
                             (px + w - cs // 4, ridge_y + max(3, cs // 4)),
                             (px + cs // 4, ridge_y + max(3, cs // 4))])
        pygame.draw.line(surf, roof_hi, (px, ridge_y), (px + w, ridge_y), 2)
        step = max(4, cs // 2)
        for lx in range(px + step, px + w, step):
            pygame.draw.line(surf, roof_dark, (lx, py + 1), (lx, ridge_y - 1), 1)
    else:
        ridge_x = px + int(w * 0.42)
        pygame.draw.polygon(surf, roof, [(ridge_x, py), (ridge_x, py + h),
                                         (px, py + h), (px, py)])
        pygame.draw.polygon(surf, roof_dark,
                            [(ridge_x, py), (ridge_x, py + h),
                             (ridge_x + max(3, cs // 4), py + h - cs // 4),
                             (ridge_x + max(3, cs // 4), py + cs // 4)])
        pygame.draw.line(surf, roof_hi, (ridge_x, py), (ridge_x, py + h), 2)
        step = max(4, cs // 2)
        for ly in range(py + step, py + h, step):
            pygame.draw.line(surf, roof_dark, (px + 1, ly), (ridge_x - 1, ly), 1)

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
    fires = getattr(bf, 'fires', None) or {}
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
                            st.damage_level(bf, gid), any(c in fires for c in cells))
        hedges = [c for c in sorted(hedge_all) if _in_region(region, c[0], c[1], c[0], c[1])]
        draw_hedge(surf, hedges, cs, hedge_all, fires)
        return
    for (x0, y0, x1, y1, n_cells, cells) in _building_components(bf):
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if not _in_region(region, x0, y0, x1, y1):
            continue
        # Une maison est un bloc plein d'au moins 2×2. Tout le reste (arcs,
        # alignements d'une case) est une HAIE: la dessiner comme un toit
        # couvrirait son rectangle englobant, rues comprises.
        if n_cells != bw * bh or bw < 2 or bh < 2:
            draw_hedge(surf, cells, cs)
            continue
        _draw_house(surf, x0, y0, x1, y1, cs)


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


def draw_rock_masses(surf, bf, cs, region=None):
    """Dessine les masses rocheuses d'un seul tenant.

    Une falaise découpée en cases, chacune avec son propre contour, se lit
    comme un carrelage. Ici les cases connexes forment un bloc: remplissage
    continu, strates qui traversent, arêtes éclairées seulement en bordure
    de la masse. `region` borne les cases peintes (repeint incrémental).
    """
    seen = set()
    W, H = bf.width, bf.height
    for sx in range(W):
        for sy in range(H):
            if bf.grid[sx][sy] != 1 or (sx, sy) in seen:
                continue
            stack = [(sx, sy)]
            seen.add((sx, sy))
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

            cset = set(cells)
            sd = _detail_seed(sx, sy)
            v = ((sd >> 3) & 7) - 3
            base = (92 + v * 4, 86 + v * 4, 76 + v * 3)
            dark = _prop_shade(base, -26)
            light = _prop_shade(base, 30)

            for (cx, cy) in cells:
                if not _in_region(region, cx, cy, cx, cy):
                    continue
                px, py = cx * cs, cy * cs
                sdc = _detail_seed(cx, cy)
                tone = _prop_shade(base, ((sdc >> 2) & 3) - 1)
                pygame.draw.rect(surf, tone, (px, py, cs, cs))
                # Strates: continues d'une case à l'autre
                for k in (1, 2):
                    ly = py + k * cs // 3
                    pygame.draw.line(surf, _prop_shade(tone, -14 + ((sdc >> k) & 3) * 3),
                                     (px, ly), (px + cs, ly), 1)
                # Arêtes: uniquement sur le pourtour de la masse
                if (cx, cy - 1) not in cset:
                    pygame.draw.line(surf, light, (px, py), (px + cs, py), max(1, cs // 14))
                if (cx, cy + 1) not in cset:
                    pygame.draw.line(surf, dark, (px, py + cs - 1), (px + cs, py + cs - 1),
                                     max(1, cs // 14))
                if (cx - 1, cy) not in cset:
                    pygame.draw.line(surf, _prop_shade(base, 12), (px, py), (px, py + cs), 1)
                if (cx + 1, cy) not in cset:
                    pygame.draw.line(surf, dark, (px + cs - 1, py), (px + cs - 1, py + cs), 1)


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


def _draw_forest_tree(surf, x, y, cs, level=0, burning=False):
    """Arbre de cœur de bosquet. Chaque arbre diffère (taille, teinte,
    décalage, essence): une forêt de tampons identiques alignés sur la
    grille se lit comme du papier peint, pas comme un bois. Roussi par les
    dégâts, brun-noir quand il brûle."""
    sd = _detail_seed(x, y)
    cx = x * cs + cs // 2 + ((sd & 3) - 1) * cs // 10
    cy_tree = y * cs + cs // 2 + (((sd >> 2) & 3) - 1) * cs // 10
    rt = max(2, int(cs * (0.30 + ((sd >> 4) & 3) * 0.035)))
    hue = ((sd >> 6) & 7) - 3
    scorch = 44 if burning else 16 * level
    if sd % 5 == 0 and cs >= 16:
        pygame.draw.ellipse(surf, (14, 34, 12),
                            (cx - rt, cy_tree + rt - max(2, rt // 3), rt * 2, max(3, rt // 2)))
        pygame.draw.rect(surf, (58, 42, 26),
                         (cx - max(1, cs // 14), cy_tree, max(2, cs // 7), rt))
        for k in range(3):
            w_t = max(2, int(rt * (1.05 - 0.26 * k)))
            top = cy_tree - int(rt * (0.35 + 0.52 * k))
            pygame.draw.polygon(surf, (16 + scorch, max(20, 54 + hue + k * 7 - scorch), 22),
                                [(cx, top), (cx - w_t, top + int(rt * 0.62)),
                                 (cx + w_t, top + int(rt * 0.62))])
    else:
        pygame.draw.circle(surf, (12, 30, 10), (cx + 1, cy_tree + 3), rt + 1)
        pygame.draw.circle(surf, (26 + hue + scorch, max(20, 74 + hue * 3 - scorch), 22),
                           (cx, cy_tree), rt)
        pygame.draw.circle(surf, (42 + hue + scorch, max(24, 98 + hue * 3 - scorch), 34),
                           (cx - rt // 3, cy_tree - rt // 3), max(1, rt // 2))
        pygame.draw.circle(surf, (16, 52, 14), (cx, cy_tree), rt, 1)


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


def _draw_rock_outcrop(surf, x, y, cs, level=0):
    """Affleurement rocheux: facettes anguleuses et teinte minérale; fendu
    quand une machine l'a entamé."""
    sd = _detail_seed(x, y)
    cx = x * cs + cs // 2 + ((sd & 3) - 1) * cs // 12
    cyo = y * cs + cs // 2 + (((sd >> 2) & 3) - 1) * cs // 12
    rr = max(2, int(cs * (0.34 + ((sd >> 4) & 3) * 0.04)))
    v = ((sd >> 6) & 7) - 3
    stone = (max(0, min(255, 104 + v * 5)),
             max(0, min(255, 99 + v * 5)),
             max(0, min(255, 90 + v * 4)))
    dark = _prop_shade(stone, -26)
    light = _prop_shade(stone, 26)
    pts = []
    for k in range(6):
        ang = k * math.pi / 3 + ((sd >> k) & 3) * 0.12
        rad = rr * (0.74 + ((sd >> (k + 2)) & 3) * 0.09)
        pts.append((cx + rad * math.cos(ang), cyo + rad * math.sin(ang)))
    pygame.draw.polygon(surf, dark, [(p0 + 1, p1 + 2) for p0, p1 in pts])
    pygame.draw.polygon(surf, stone, pts)
    pygame.draw.line(surf, light, (cx - rr // 2, cyo - rr // 3),
                     (cx + rr // 4, cyo - rr // 2), max(1, cs // 16))
    pygame.draw.polygon(surf, dark, pts, 1)
    for k in range(level * 2):
        a = _hash3(x, y, k + 5) / 255.0 * math.tau
        pygame.draw.line(surf, _prop_shade(stone, -50), (cx, cyo),
                         (cx + math.cos(a) * rr * 0.9, cyo + math.sin(a) * rr * 0.9), 1)


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


def build_ground_layer(battle, cell_size):
    """Couche de SOL: fond, petits détails, repères, grain, taches organiques
    et traces permanentes (cratères). Construite une fois; le repeint d'une
    région y reprend le sol avant de redessiner ce qui repose dessus."""
    from maps import theme_info
    bf = battle.battlefield
    cs = cell_size
    W, H = bf.width * cs, bf.height * cs
    theme = theme_info(bf)
    bg = theme["bg_color"]
    ground = pygame.Surface((W, H))
    ground.fill(bg)
    # Couleur de grille très discrète (proche du fond) — l'ancienne grille
    # par case donnait un aspect "tableur"
    subtle_grid = (max(0, bg[0] - 3), max(0, bg[1] - 3), max(0, bg[2] - 3))
    if cs >= 14:
        grassy = theme["grassy"]
        gc = (min(255, bg[0] + 14), min(255, bg[1] + 22), min(255, bg[2] + 10))
        sc = (min(255, bg[0] + 16), min(255, bg[1] + 14), min(255, bg[2] + 12))
        for x in range(bf.width):
            for y in range(bf.height):
                if bf.grid[x][y] != 0:
                    continue
                seed = _detail_seed(x, y)
                if seed < 14:  # ~5% des cases: touffe d'herbe / caillou
                    px_d = x * cs + 2 + (seed % max(1, cs - 6))
                    py_d = y * cs + 2 + ((seed * 7) % max(1, cs - 6))
                    if grassy:
                        pygame.draw.line(ground, gc, (px_d, py_d + 3), (px_d, py_d), 1)
                        pygame.draw.line(ground, gc, (px_d + 2, py_d + 3), (px_d + 3, py_d + 1), 1)
                    else:
                        pygame.draw.circle(ground, sc, (px_d, py_d), 1)
                # Repères d'échelle: un point tous les 5 croisements, au lieu
                # d'un contour sur chaque case (qui faisait « tableur »)
                if x % 5 == 0 and y % 5 == 0:
                    pygame.draw.rect(ground, subtle_grid, (x * cs, y * cs, 1, 1))

    # ─── Grain de texture (mouchetures) ───
    grain = sprites.ground_grain(128, 77 + len(bf.map_name))
    for gx in range(0, W, 128):
        for gy in range(0, H, 128):
            ground.blit(grain, (gx, gy))

    # ─── Taches de sol organiques ───
    patches = getattr(bf, 'ground_patches', ())
    if patches and cs >= 12:
        draw_ground_patches(ground, patches, cs, bg)
    return ground


def paint_region(surf, battle, cell_size, ground, x0, y0, x1, y1):
    """Peint tout ce qui est statique sur les cases [x0..x1]×[y0..y1]: sol,
    fortifications, obstacles, terrain, bâtiments, décor. La carte entière
    et le repeint après destruction passent par ici: même résultat."""
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

    area = pygame.Rect(x0 * cs, y0 * cs, (x1 - x0 + 1) * cs, (y1 - y0 + 1) * cs)
    surf.blit(ground, area.topleft, area)

    structs = getattr(bf, 'structures', None) or {}
    fires = getattr(bf, 'fires', None) or {}
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
                    continue  # dessinés d'un seul tenant plus bas
                level = st.damage_level(bf, entry[1]) if entry is not None else 0
                if kind == st.PALISADE:
                    _draw_palisade_cell(surf, bf, x, y, cs, level, (x, y) in fires)
                elif kind == st.GROVE or bf.map_name == "Forêt":
                    _draw_forest_tree(surf, x, y, cs, level, (x, y) in fires)
                else:
                    _draw_rock_outcrop(surf, x, y, cs, level)

    if bf.walls or bf.gate_hp:
        draw_wall_shadows(surf, bf, cs, region)

    terrain_render.draw_terrain(surf, bf, cs, region)

    if bf.map_name == "Village" or getattr(bf, '_has_buildings', False):
        draw_village_buildings(surf, bf, cs, region)
    elif bf.map_name == "Défilé":
        draw_rock_masses(surf, bf, cs, region)

    # ─── Décor: végétation, cailloux, matériel abandonné ───
    # Posé par-dessus le sol, sous les unités. Aucune incidence de jeu. Le
    # feu et l'effondrement l'emportent: rien ne pousse sur des décombres.
    if cs >= 12:
        terr = bf.terrain
        gone = (tr_mod.RUBBLE, tr_mod.BURNT)
        for (dx_p, dy_p, kind, seed_p) in getattr(bf, 'decor', ()):
            if not (x0 <= dx_p <= x1 and y0 <= dy_p <= y1):
                continue
            if bf.grid[dx_p][dy_p] != 0:
                continue  # une case devenue mur/obstacle perd son décor
            if terr is not None and terr[dx_p][dy_p] in gone:
                continue
            draw_prop(surf, kind, dx_p, dy_p, cs, seed_p, bg)


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


def draw_battle_report(screen, report, screen_w, battlefield_h, small_font, tiny_font):
    """Rapport de bataille: panneau du thème sur la carte assombrie."""
    header_font = T.font('title', 18)
    body_font = T.font('ui_bold', 13)
    detail_font = T.font('ui', 13)
    small = T.font('ui', 11)

    veil = pygame.Surface((screen_w, battlefield_h), pygame.SRCALPHA)
    veil.fill((6, 7, 9, 150))
    screen.blit(veil, (0, 0))

    panel_w = min(780, screen_w - 20)
    panel_h = min(660, battlefield_h - 10)
    px = (screen_w - panel_w) // 2
    py = (battlefield_h - panel_h) // 2
    prect = T.panel(screen, (px, py, panel_w, panel_h))

    y = T.title(screen, "Rapport de bataille", prect.centerx, py + 14, 26)
    T.text(screen, f"Victoire : {report['winner']}   ·   {report['rounds']} rounds",
           T.font('serif', 16), (prect.centerx, y), T.PARCHMENT, align="center")
    y += 32

    col_w = (panel_w - 60) // 2
    clip = screen.get_clip()
    screen.set_clip(prect.inflate(-8, -8))

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
    pygame.draw.line(screen, T.darken(T.GOLD_DIM, 0.4), (prect.centerx, y), (prect.centerx, prect.bottom - 20))


def run_visual(battle, cell_size):
    """Joue la bataille à l'écran (cf. battle_view.BattleView). Renvoie
    "menu" pour revenir au menu, None pour quitter."""
    from battle_view import BattleView
    return BattleView(battle, cell_size).run()
