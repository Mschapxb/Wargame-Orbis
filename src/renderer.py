import math
import os
import pygame
import sys


simulation_speed = "normal"
pause = True

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
}

# Bannières d'annonce lors d'un changement de posture
_POSTURE_BANNERS = {
    "rush":      ("CHARGE GÉNÉRALE !",            (255, 150, 60)),
    "hold_line": ("tient la ligne de tir",        (90, 180, 255)),
    "recall":    ("repli derrière les murs",      (150, 200, 255)),
    "screen":    ("couvre ses tireurs !",         (120, 220, 200)),
    "exploit":   ("EXPLOITE LA PERCÉE !",         (255, 120, 90)),
    "regroup":   ("se regroupe",                  (200, 170, 120)),
}

# Dossier des tokens (à côté des fichiers .py)
TOKENS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")

# Cache des images de tokens: {(token_name, size): Surface ou None}
_token_cache = {}

# Cache des ombres d'unités: {(w, h): Surface} — évite une allocation
# de Surface par unité et par frame
_shadow_cache = {}


def get_shadow(sh_w, sh_h):
    key = (sh_w, sh_h)
    s = _shadow_cache.get(key)
    if s is None:
        s = pygame.Surface((sh_w, sh_h), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 70), (0, 0, sh_w, sh_h))
        _shadow_cache[key] = s
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
        except Exception:
            _token_cache[key] = None
            return None
    
    _token_cache[key] = None
    return None


def clear_token_cache():
    """Vide le cache (utile après resize)."""
    _token_cache.clear()
    _shadow_cache.clear()



def compute_grid_from_screen(target_cell=TARGET_CELL_SIZE):
    """Calcule une grille large avec hauteur fixe de 50 cases.
    
    Retourne (grid_width, grid_height, cell_size).
    """
    info = pygame.display.Info()
    screen_w = info.current_w
    screen_h = info.current_h
    
    cell_size = max(MIN_CELL_SIZE, min(target_cell, MAX_CELL_SIZE))
    
    # Largeur: ~2x l'écran, hauteur: fixe 50 cases
    grid_w = (screen_w * 2) // cell_size
    grid_h = 50
    
    grid_w = max(80, grid_w)
    
    return grid_w, grid_h, cell_size


def _ground_color(bg, x, y):
    """Variation de sol déterministe (pseudo-bruit, pas de random pour ne
    pas perturber la RNG de la bataille).

    Seulement un grain très fin: toute variation à l'échelle de plusieurs
    cases dessinerait des carrés alignés sur la grille. Les variations
    larges sont confiées aux taches organiques (draw_ground_patches).
    """
    n = ((x * 0x27D4EB2D) ^ (y * 0x165667B1)) & 0xFFFFFFFF
    n = ((n ^ (n >> 15)) * 0x2545F491) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) & 0xFFFFFFFF
    v = (n >> 9) % 5 - 2  # -2..+2, juste un grain
    return (max(0, min(255, bg[0] + v)),
            max(0, min(255, bg[1] + v + (1 if v > 0 else 0))),
            max(0, min(255, bg[2] + v)))


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
        pygame.draw.circle(surf, (190, 70, 60), (px, py - u), max(1, u // 2 + 1))
        pygame.draw.circle(surf, (235, 225, 210), (px + 1, py - u), 1)
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
            comps.append((min(xs), min(ys), max(xs), max(ys), len(cells)))
    return comps


def draw_village_buildings(surf, bf, cs):
    """Dessine les bâtiments d'un village comme des maisons entières."""
    for (x0, y0, x1, y1, n_cells) in _building_components(bf):
        w = (x1 - x0 + 1) * cs
        h = (y1 - y0 + 1) * cs
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


def draw_rock_masses(surf, bf, cs):
    """Dessine les masses rocheuses d'un seul tenant.

    Une falaise découpée en cases, chacune avec son propre contour, se lit
    comme un carrelage. Ici les cases connexes forment un bloc: remplissage
    continu, strates qui traversent, arêtes éclairées seulement en bordure
    de la masse.
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


def build_grid_surface(battle, cell_size):
    """Pré-rend la surface de la grille avec le thème de la map."""
    from maps import get_map_info
    
    bf = battle.battlefield
    W = bf.width * cell_size
    grid_h = bf.height * cell_size
    grid_surface = pygame.Surface((W, grid_h))
    
    theme = get_map_info(bf.map_name)
    bg = theme["bg_color"]
    obs_color = theme["obstacle_color"]
    grid_color = theme["grid_color"]
    wall_color = theme.get("wall_color", (100, 100, 110))
    gate_color = theme.get("gate_color", (140, 100, 50))
    
    # Couleur de grille très discrète (proche du fond) — l'ancienne grille
    # par case donnait un aspect "tableur"
    subtle_grid = (max(0, bg[0] - 3), max(0, bg[1] - 3), max(0, bg[2] - 3))
    
    for x in range(bf.width):
        for y in range(bf.height):
            r = pygame.Rect(x * cell_size, y * cell_size, cell_size, cell_size)
            cell = bf.grid[x][y]
            
            if cell == 2:  # Mur
                pygame.draw.rect(grid_surface, wall_color, r)
                # Pierres: joints horizontaux décalés une rangée sur deux
                stone_c = (max(0, wall_color[0] - 18), max(0, wall_color[1] - 18), max(0, wall_color[2] - 14))
                hi_c = (min(255, wall_color[0] + 20), min(255, wall_color[1] + 20), min(255, wall_color[2] + 22))
                mid_y = y * cell_size + cell_size // 2
                pygame.draw.line(grid_surface, stone_c,
                                 (x * cell_size, mid_y), (x * cell_size + cell_size, mid_y), 1)
                off = (cell_size // 2) if (y % 2 == 0) else 0
                pygame.draw.line(grid_surface, stone_c,
                                 (x * cell_size + off, y * cell_size),
                                 (x * cell_size + off, mid_y), 1)
                off2 = 0 if (y % 2 == 0) else (cell_size // 2)
                pygame.draw.line(grid_surface, stone_c,
                                 (x * cell_size + off2, mid_y),
                                 (x * cell_size + off2, y * cell_size + cell_size), 1)
                # Liseré clair en haut (lumière)
                pygame.draw.line(grid_surface, hi_c,
                                 (x * cell_size, y * cell_size),
                                 (x * cell_size + cell_size, y * cell_size), 1)
            elif cell == 3:  # Porte
                hp = bf.gate_hp.get((x, y), 0)
                gates_open = getattr(bf, 'gates_open', False)
                if hp > 0 and not gates_open:
                    # Porte fermée: planches verticales + clous
                    pygame.draw.rect(grid_surface, gate_color, r)
                    plank_c = (max(0, gate_color[0] - 25), max(0, gate_color[1] - 20), max(0, gate_color[2] - 12))
                    n_planks = max(2, cell_size // 8)
                    for p in range(1, n_planks):
                        px_line = x * cell_size + p * cell_size // n_planks
                        pygame.draw.line(grid_surface, plank_c,
                                         (px_line, y * cell_size), (px_line, y * cell_size + cell_size), 1)
                    # Renfort horizontal + clous
                    band_y = y * cell_size + cell_size // 2
                    pygame.draw.line(grid_surface, (90, 90, 100),
                                     (x * cell_size + 1, band_y), (x * cell_size + cell_size - 1, band_y), 2)
                    if cell_size >= 16:
                        pygame.draw.circle(grid_surface, (180, 180, 190),
                                           (x * cell_size + 4, band_y), 1)
                        pygame.draw.circle(grid_surface, (180, 180, 190),
                                           (x * cell_size + cell_size - 4, band_y), 1)
                    # Barre de PV de porte
                    bar_w = cell_size - 4
                    pct = hp / 10
                    pygame.draw.rect(grid_surface, (60, 40, 20),
                                     (x * cell_size + 2, y * cell_size + cell_size - 5, bar_w, 3))
                    pygame.draw.rect(grid_surface, (200, 150, 50),
                                     (x * cell_size + 2, y * cell_size + cell_size - 5, int(bar_w * pct), 3))
                elif hp > 0 and gates_open:
                    # Porte OUVERTE (intacte): sol de passage + battants repliés
                    pygame.draw.rect(grid_surface, _ground_color(bg, x, y), r)
                    pygame.draw.rect(grid_surface, gate_color,
                                     (x * cell_size, y * cell_size, 3, cell_size))
                    pygame.draw.rect(grid_surface, gate_color,
                                     (x * cell_size + cell_size - 3, y * cell_size, 3, cell_size))
                else:
                    # Porte détruite — sol + débris
                    pygame.draw.rect(grid_surface, _ground_color(bg, x, y), r)
                    pygame.draw.line(grid_surface, (90, 70, 40),
                                     (x * cell_size + 2, y * cell_size + 2),
                                     (x * cell_size + cell_size - 2, y * cell_size + cell_size - 2), 1)
                    pygame.draw.line(grid_surface, (70, 55, 30),
                                     (x * cell_size + cell_size - 3, y * cell_size + 3),
                                     (x * cell_size + 3, y * cell_size + cell_size - 3), 1)
            elif cell == 1:  # Obstacle
                if bf.map_name == "Forêt":
                    # Chaque arbre diffère (taille, teinte, décalage, essence):
                    # une forêt de tampons identiques alignés sur la grille
                    # se lit comme du papier peint, pas comme un bois.
                    pygame.draw.rect(grid_surface, _ground_color(bg, x, y), r)
                    sd = _detail_seed(x, y)
                    cx = x * cell_size + cell_size // 2 + ((sd & 3) - 1) * cell_size // 10
                    cy_tree = (y * cell_size + cell_size // 2
                               + (((sd >> 2) & 3) - 1) * cell_size // 10)
                    tr = max(2, int(cell_size * (0.30 + ((sd >> 4) & 3) * 0.035)))
                    hue = ((sd >> 6) & 7) - 3
                    if sd % 5 == 0 and cell_size >= 16:
                        pygame.draw.ellipse(grid_surface, (14, 34, 12),
                                            (cx - tr, cy_tree + tr - max(2, tr // 3),
                                             tr * 2, max(3, tr // 2)))
                    else:
                        pygame.draw.circle(grid_surface, (12, 30, 10),
                                           (cx + 1, cy_tree + 3), tr + 1)
                    if sd % 5 == 0 and cell_size >= 16:
                        # Conifère: étages triangulaires
                        pygame.draw.rect(grid_surface, (58, 42, 26),
                                         (cx - max(1, cell_size // 14), cy_tree,
                                          max(2, cell_size // 7), tr))
                        for k in range(3):
                            w_t = max(2, int(tr * (1.05 - 0.26 * k)))
                            top = cy_tree - int(tr * (0.35 + 0.52 * k))
                            pygame.draw.polygon(
                                grid_surface, (16, 54 + hue + k * 7, 22),
                                [(cx, top), (cx - w_t, top + int(tr * 0.62)),
                                 (cx + w_t, top + int(tr * 0.62))])
                    else:
                        pygame.draw.circle(grid_surface, (26 + hue, 74 + hue * 3, 22),
                                           (cx, cy_tree), tr)
                        pygame.draw.circle(grid_surface, (42 + hue, 98 + hue * 3, 34),
                                           (cx - tr // 3, cy_tree - tr // 3), max(1, tr // 2))
                        pygame.draw.circle(grid_surface, (16, 52, 14), (cx, cy_tree), tr, 1)
                elif bf.map_name == "Village":
                    # Le sol passe dessous: les maisons sont dessinées
                    # ensuite, d'un seul tenant (cf. draw_village_buildings)
                    pygame.draw.rect(grid_surface, _ground_color(bg, x, y), r)
                elif bf.map_name == "Défilé":
                    # Le sol passe dessous: les masses rocheuses sont
                    # dessinées ensuite d'un seul tenant
                    pygame.draw.rect(grid_surface, _ground_color(bg, x, y), r)
                else:
                    # Affleurement rocheux: facettes anguleuses, pas une
                    # bulle uniforme — et une teinte minérale, pas la
                    # couleur du pré.
                    pygame.draw.rect(grid_surface, _ground_color(bg, x, y), r)
                    sd = _detail_seed(x, y)
                    cx = x * cell_size + cell_size // 2 + ((sd & 3) - 1) * cell_size // 12
                    cyo = y * cell_size + cell_size // 2 + (((sd >> 2) & 3) - 1) * cell_size // 12
                    rr = max(2, int(cell_size * (0.34 + ((sd >> 4) & 3) * 0.04)))
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
                    pygame.draw.polygon(grid_surface, dark,
                                        [(p0 + 1, p1 + 2) for p0, p1 in pts])
                    pygame.draw.polygon(grid_surface, stone, pts)
                    pygame.draw.line(grid_surface, light,
                                     (cx - rr // 2, cyo - rr // 3),
                                     (cx + rr // 4, cyo - rr // 2), max(1, cell_size // 16))
                    pygame.draw.polygon(grid_surface, dark, pts, 1)
            elif cell == 4:  # Rempart marchable
                ramp_color = (88, 88, 98)
                pygame.draw.rect(grid_surface, ramp_color, r)
                # Dallage en damier discret
                if (x + y) % 2 == 0:
                    pygame.draw.rect(grid_surface, (94, 94, 104),
                                     (x * cell_size + 1, y * cell_size + 1, cell_size - 2, cell_size - 2))
                pygame.draw.rect(grid_surface, (104, 104, 116), r, 1)
            elif cell == 5:  # Escalier
                stair_color = (75, 70, 60)
                pygame.draw.rect(grid_surface, stair_color, r)
                step_h = max(2, cell_size // 4)
                for sy in range(y * cell_size + 2, (y + 1) * cell_size - 1, step_h):
                    pygame.draw.line(grid_surface, (95, 85, 70),
                                     (x * cell_size + 2, sy),
                                     (x * cell_size + cell_size - 2, sy), 1)
                    pygame.draw.line(grid_surface, (55, 50, 42),
                                     (x * cell_size + 2, sy + 1),
                                     (x * cell_size + cell_size - 2, sy + 1), 1)
            else:
                # Sol avec pseudo-bruit + petits détails épars
                pygame.draw.rect(grid_surface, _ground_color(bg, x, y), r)
                if cell_size >= 14:
                    seed = _detail_seed(x, y)
                    if seed < 14:  # ~5% des cases: touffe d'herbe / caillou
                        dx = 2 + (seed % max(1, cell_size - 6))
                        dy = 2 + ((seed * 7) % max(1, cell_size - 6))
                        px_d = x * cell_size + dx
                        py_d = y * cell_size + dy
                        if bf.map_name in ("Prairie", "Forêt"):
                            gc = (min(255, bg[0] + 14), min(255, bg[1] + 22), min(255, bg[2] + 10))
                            pygame.draw.line(grid_surface, gc, (px_d, py_d + 3), (px_d, py_d), 1)
                            pygame.draw.line(grid_surface, gc, (px_d + 2, py_d + 3), (px_d + 3, py_d + 1), 1)
                        else:
                            sc = (min(255, bg[0] + 16), min(255, bg[1] + 14), min(255, bg[2] + 12))
                            pygame.draw.circle(grid_surface, sc, (px_d, py_d), 1)
            
            # Repères d'échelle: un point tous les 5 croisements, au lieu
            # d'un contour sur chaque case (qui faisait « tableur »)
            if cell == 0 and x % 5 == 0 and y % 5 == 0 and cell_size >= 14:
                pygame.draw.rect(grid_surface, subtle_grid,
                                 (x * cell_size, y * cell_size, 1, 1))

    # ─── Taches de sol organiques (sous tout le reste) ───
    patches = getattr(bf, 'ground_patches', ())
    if patches and cell_size >= 12:
        draw_ground_patches(grid_surface, patches, cell_size, bg)

    # ─── Reliefs d'un seul tenant ───
    if bf.map_name == "Village":
        draw_village_buildings(grid_surface, bf, cell_size)
    elif bf.map_name == "Défilé":
        draw_rock_masses(grid_surface, bf, cell_size)

    # ─── Décor: végétation, cailloux, matériel abandonné ───
    # Posé par-dessus le sol, sous les unités. Aucune incidence de jeu.
    if cell_size >= 12:
        for (dx_p, dy_p, kind, seed_p) in getattr(bf, 'decor', ()):
            if bf.grid[dx_p][dy_p] != 0:
                continue  # une case devenue mur/obstacle perd son décor
            draw_prop(grid_surface, kind, dx_p, dy_p, cell_size, seed_p, bg)

    return grid_surface


def draw_projectile(screen, proj, ox=0, oy=0):
    pos = proj.get_current_pos()
    px, py = pos[0] + ox, pos[1] + oy
    angle = proj.get_angle()
    
    if proj.projectile_type == "arrow":
        length = 12
        ex = px + length * math.cos(angle)
        ey = py + length * math.sin(angle)
        sx = px - length * math.cos(angle)
        sy = py - length * math.sin(angle)
        pygame.draw.line(screen, proj.color, (sx, sy), (ex, ey), 2)
        a = math.pi / 6
        p1 = (ex - 6 * math.cos(angle - a), ey - 6 * math.sin(angle - a))
        p2 = (ex - 6 * math.cos(angle + a), ey - 6 * math.sin(angle + a))
        pygame.draw.polygon(screen, (255, 200, 100), [(ex, ey), p1, p2])
    elif proj.projectile_type == "fireball":
        r = 6
        pygame.draw.circle(screen, (255, 200, 0), (int(px), int(py)), r + 2)
        pygame.draw.circle(screen, (255, 100, 0), (int(px), int(py)), r)
        pygame.draw.circle(screen, (255, 255, 100), (int(px), int(py)), r // 2)
    elif proj.projectile_type == "magic":
        r = 5
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        for i in range(4):
            tx = px - i * 4 * cos_a
            ty = py - i * 4 * sin_a
            pygame.draw.circle(screen, (150, 100, min(255, 200 + i * 10)), (int(tx), int(ty)), max(1, r - i))
        pygame.draw.circle(screen, (200, 150, 255), (int(px), int(py)), r)


def draw_battle_report(screen, report, screen_w, battlefield_h, small_font, tiny_font):
    """Dessine le rapport de bataille en overlay semi-transparent."""
    title_font = pygame.font.SysFont("arial", 22, bold=True)
    header_font = pygame.font.SysFont("arial", 17, bold=True)
    body_font = pygame.font.SysFont("arial", 14)
    detail_font = pygame.font.SysFont("arial", 13)
    
    panel_w = min(750, screen_w - 20)
    panel_h = min(640, battlefield_h - 10)
    px = (screen_w - panel_w) // 2
    py = (battlefield_h - panel_h) // 2
    
    overlay = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    overlay.fill((15, 20, 25, 230))
    screen.blit(overlay, (px, py))
    pygame.draw.rect(screen, (200, 180, 80), (px, py, panel_w, panel_h), 2)
    
    y = py + 14
    
    title = title_font.render("RAPPORT DE BATAILLE", True, (255, 215, 0))
    screen.blit(title, (px + (panel_w - title.get_width()) // 2, y))
    y += 28
    
    winner_txt = header_font.render(f"Victoire: {report['winner']}  —  {report['rounds']} rounds", True, (220, 200, 120))
    screen.blit(winner_txt, (px + (panel_w - winner_txt.get_width()) // 2, y))
    y += 26
    
    pygame.draw.line(screen, (120, 120, 80), (px + 15, y), (px + panel_w - 15, y), 1)
    y += 10
    
    col_w = (panel_w - 40) // 2
    
    for i, army_key in enumerate(['army1', 'army2']):
        army = report[army_key]
        col_x = px + 15 + i * (col_w + 10)
        cy = y
        
        team_color = (80, 160, 255) if i == 0 else (255, 80, 80)
        
        header = header_font.render(army['name'], True, team_color)
        screen.blit(header, (col_x, cy))
        cy += 24
        
        total = army['total']
        n_alive = army['alive_count']
        n_dead = army['dead_count']
        n_fled = army['fled_count']
        
        bar_w = col_w - 5
        bar_h = 16
        
        if total > 0:
            alive_pct = n_alive / total
            dead_pct = n_dead / total
            fled_pct = n_fled / total
            
            pygame.draw.rect(screen, (40, 40, 40), (col_x, cy, bar_w, bar_h))
            if alive_pct > 0:
                pygame.draw.rect(screen, (50, 180, 50), (col_x, cy, int(bar_w * alive_pct), bar_h))
            if fled_pct > 0:
                fx = col_x + int(bar_w * alive_pct)
                pygame.draw.rect(screen, (220, 150, 30), (fx, cy, int(bar_w * fled_pct), bar_h))
            if dead_pct > 0:
                dx = col_x + int(bar_w * (alive_pct + fled_pct))
                pygame.draw.rect(screen, (180, 40, 40), (dx, cy, int(bar_w * dead_pct), bar_h))
            pygame.draw.rect(screen, (100, 100, 100), (col_x, cy, bar_w, bar_h), 1)
        cy += bar_h + 8
        
        txt_alive = body_font.render(f"Vivants: {n_alive}/{total}", True, (80, 220, 80))
        screen.blit(txt_alive, (col_x, cy))
        cy += 20
        
        txt_dead = body_font.render(f"Morts: {n_dead}/{total}", True, (220, 80, 80))
        screen.blit(txt_dead, (col_x, cy))
        cy += 20
        
        txt_fled = body_font.render(f"Fuyants: {n_fled}/{total}", True, (220, 170, 50))
        screen.blit(txt_fled, (col_x, cy))
        cy += 24

        # ── Détail par contingent (équipe composée de plusieurs armées) ──
        contingents = army.get('contingents') or []
        if len(contingents) > 1:
            lbl = body_font.render("Contingents:", True, (200, 190, 150))
            screen.blit(lbl, (col_x, cy))
            cy += 19
            for c in contingents[:4]:
                nm = detail_font.render(f"  {c['name'][:22]}", True, (215, 205, 175))
                screen.blit(nm, (col_x, cy))
                cy += 15
                stats = (f"     {c['alive_count']} vivants · "
                         f"{c['fled_count']} fuyants · {c['dead_count']} morts"
                         f"  ({c['total']})")
                st = tiny_font.render(stats, True, (150, 160, 150))
                screen.blit(st, (col_x, cy))
                # Petite barre de pertes du contingent
                cw = col_w - 20
                if c['total'] > 0 and cw > 20:
                    bx, by2, bh2 = col_x + 6, cy + 13, 4
                    ap = c['alive_count'] / c['total']
                    fp = c['fled_count'] / c['total']
                    pygame.draw.rect(screen, (40, 40, 40), (bx, by2, cw, bh2))
                    pygame.draw.rect(screen, (50, 180, 50), (bx, by2, int(cw * ap), bh2))
                    pygame.draw.rect(screen, (220, 150, 30),
                                     (bx + int(cw * ap), by2, int(cw * fp), bh2))
                    pygame.draw.rect(screen, (180, 40, 40),
                                     (bx + int(cw * (ap + fp)), by2,
                                      cw - int(cw * (ap + fp)), bh2))
                cy += 22
            cy += 4

        pygame.draw.line(screen, (60, 60, 60), (col_x, cy), (col_x + col_w - 5, cy), 1)
        cy += 6
        
        # Survivants (groupés: nom x quantité)
        if army['alive']:
            label = body_font.render("Survivants:", True, (80, 220, 80))
            screen.blit(label, (col_x, cy))
            cy += 18
            for name, count in army['alive'][:8]:
                txt = f"  {name} x{count}" if count > 1 else f"  {name}"
                t = detail_font.render(txt, True, (160, 220, 160))
                screen.blit(t, (col_x, cy))
                cy += 16
            if len(army['alive']) > 8:
                rest = sum(c for _, c in army['alive'][8:])
                more = detail_font.render(f"  ...et {rest} autres", True, (120, 160, 120))
                screen.blit(more, (col_x, cy))
                cy += 16
        
        # Fuyants (groupés: nom x quantité)
        if army['fled']:
            cy += 4
            label = body_font.render("Fuyants:", True, (220, 170, 50))
            screen.blit(label, (col_x, cy))
            cy += 18
            for name, count in army['fled'][:8]:
                txt = f"  {name} x{count}" if count > 1 else f"  {name}"
                t = detail_font.render(txt, True, (200, 170, 80))
                screen.blit(t, (col_x, cy))
                cy += 16
            if len(army['fled']) > 8:
                rest = sum(c for _, c in army['fled'][8:])
                more = detail_font.render(f"  ...et {rest} autres", True, (150, 130, 60))
                screen.blit(more, (col_x, cy))
                cy += 16
        
        # Morts (groupés: nom x quantité)
        if army['dead']:
            cy += 4
            label = body_font.render("Morts:", True, (220, 80, 80))
            screen.blit(label, (col_x, cy))
            cy += 18
            for name, count in army['dead'][:8]:
                txt = f"  {name} x{count}" if count > 1 else f"  {name}"
                t = detail_font.render(txt, True, (180, 100, 100))
                screen.blit(t, (col_x, cy))
                cy += 16
            if len(army['dead']) > 8:
                rest = sum(c for _, c in army['dead'][8:])
                more = detail_font.render(f"  ...et {rest} autres", True, (120, 80, 80))
                screen.blit(more, (col_x, cy))
                cy += 16


def run_visual(battle, cell_size):
    global pause, simulation_speed
    
    bf_w = battle.battlefield.width
    bf_h = battle.battlefield.height
    
    info = pygame.display.Info()
    SCREEN_W = info.current_w
    SCREEN_H = info.current_h
    
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.NOFRAME)
    pygame.display.set_caption("Battle Simulator")
    clock = pygame.time.Clock()
    is_borderless = True  # Mode actuel: True=borderless, False=fullscreen
    
    font_small_size = max(9, cell_size // 3)
    font_tiny_size = max(7, cell_size // 4)
    small_font = pygame.font.SysFont("arial", font_small_size)
    tiny_font = pygame.font.SysFont("arial", font_tiny_size)
    banner_font = pygame.font.SysFont("arial", 22, bold=True)
    pause_font = pygame.font.SysFont("arial", 30, bold=True)
    
    battle.cell_size = cell_size
    grid_surface = build_grid_surface(battle, cell_size)

    # ─── Caméra ───
    world_w = bf_w * cell_size
    world_h = bf_h * cell_size
    
    # Centrer la caméra au départ
    cam_x = (world_w - SCREEN_W) / 2
    cam_y = (world_h - (SCREEN_H - HUD_HEIGHT)) / 2
    cam_x = max(0, cam_x)
    cam_y = max(0, cam_y)
    
    CAM_SPEED = 12  # pixels/frame
    EDGE_SCROLL_MARGIN = 30
    dragging = False
    drag_start = (0, 0)
    drag_cam_start = (0, 0)
    
    def clamp_camera():
        nonlocal cam_x, cam_y
        view_h = SCREEN_H - HUD_HEIGHT
        max_x = max(0, world_w - SCREEN_W)
        max_y = max(0, world_h - view_h)
        cam_x = max(0, min(cam_x, max_x))
        cam_y = max(0, min(cam_y, max_y))
    
    clamp_camera()
    
    running = True
    _return_action = None
    winner = None
    battle_report = None
    show_lines = True
    
    # Bannières d'événements dramatiques (sortie, portes, charges...)
    event_banners = []  # [texte, couleur, timer_frames]
    prev_gates_open = getattr(battle.battlefield, 'gates_open', False)
    prev_intact_gates = sum(1 for h in battle.battlefield.gate_hp.values() if h > 0)
    prev_postures = [getattr(battle.commander1, 'posture', 'balanced'),
                     getattr(battle.commander2, 'posture', 'balanced')]
    prev_maneuvers = [getattr(battle.commander1, 'maneuver', None),
                      getattr(battle.commander2, 'maneuver', None)]
    
    # Animation: progression d'interpolation du déplacement
    move_anim_progress = 1.0   # 0.0 = début mouvement, 1.0 = arrivé
    round_frame = 10 ** 6      # force la simulation du premier round
    screen_shake = 0.0         # secousse de caméra (impacts lourds)
    
    _original_army1 = battle._restart_army1
    _original_army2 = battle._restart_army2
    _bf_w = battle.battlefield.width
    _bf_h = battle.battlefield.height
    _obstacle_count = 8
    _map_name = battle.map_name
    
    while running:
        now = pygame.time.get_ticks()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                _return_action = None
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 2:  # Middle click → drag
                    dragging = True
                    drag_start = event.pos
                    drag_cam_start = (cam_x, cam_y)
            
            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 2:
                    dragging = False
            
            if event.type == pygame.MOUSEMOTION and dragging:
                dx = drag_start[0] - event.pos[0]
                dy = drag_start[1] - event.pos[1]
                cam_x = drag_cam_start[0] + dx
                cam_y = drag_cam_start[1] + dy
                clamp_camera()
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    pause = not pause
                elif event.key == pygame.K_f:
                    simulation_speed, pause = "fast", False
                elif event.key == pygame.K_n:
                    simulation_speed, pause = "normal", False
                elif event.key == pygame.K_p:
                    pause = True
                elif event.key == pygame.K_ESCAPE:
                    running = False
                    _return_action = None
                elif event.key == pygame.K_m:
                    running = False
                    _return_action = "menu"
                elif event.key == pygame.K_r:
                    from battle import Battle
                    battle = Battle(_original_army1, _original_army2, _bf_w, _bf_h, _obstacle_count, map_name=_map_name)
                    grid_surface = build_grid_surface(battle, cell_size)
                    world_w = _bf_w * cell_size
                    world_h = _bf_h * cell_size
                    cam_x = max(0, (world_w - SCREEN_W) / 2)
                    cam_y = max(0, (world_h - (SCREEN_H - HUD_HEIGHT)) / 2)
                    clamp_camera()
                    winner = None
                    battle_report = None
                    move_anim_progress = 1.0
                    round_frame = 10 ** 6
                    screen_shake = 0.0
                    event_banners = []
                    prev_gates_open = getattr(battle.battlefield, 'gates_open', False)
                    prev_intact_gates = sum(1 for h in battle.battlefield.gate_hp.values() if h > 0)
                    prev_postures = [getattr(battle.commander1, 'posture', 'balanced'),
                                     getattr(battle.commander2, 'posture', 'balanced')]
                    prev_maneuvers = [getattr(battle.commander1, 'maneuver', None),
                                      getattr(battle.commander2, 'maneuver', None)]
                elif event.key == pygame.K_t:
                    show_lines = not show_lines
                elif event.key == pygame.K_b:
                    # Basculer entre borderless windowed et fullscreen exclusif
                    is_borderless = not is_borderless
                    if is_borderless:
                        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.NOFRAME)
                    else:
                        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
                    clear_token_cache()
                    grid_surface = build_grid_surface(battle, cell_size)
        
        # Déplacement caméra continu (touches maintenues)
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_q]:
            cam_x -= CAM_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            cam_x += CAM_SPEED
        if keys[pygame.K_UP] or keys[pygame.K_z]:
            cam_y -= CAM_SPEED
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            cam_y += CAM_SPEED
        
        # Edge scroll (souris au bord de l'écran)
        mx, my = pygame.mouse.get_pos()
        if mx < EDGE_SCROLL_MARGIN:
            cam_x -= CAM_SPEED
        elif mx > SCREEN_W - EDGE_SCROLL_MARGIN:
            cam_x += CAM_SPEED
        if my < EDGE_SCROLL_MARGIN:
            cam_y -= CAM_SPEED
        elif my > SCREEN_H - HUD_HEIGHT - EDGE_SCROLL_MARGIN:
            cam_y += CAM_SPEED
        
        clamp_camera()
        
        if not pause and winner is None:
            # ── Cadence CONTINUE ──
            # Le round n'est plus « simuler, animer, puis attendre »: sa
            # durée est fixée en frames, le moteur y répartit toutes les
            # actions (cf. battle.T_*), et le round suivant enchaîne sans
            # temps mort. C'est ce qui donne la sensation de temps réel.
            frames = ROUND_FRAMES_FAST if simulation_speed == "fast" else ROUND_FRAMES_NORMAL

            if round_frame >= frames:
                round_frame = 0
                battle.fx_frames_per_round = frames
                battle.simulate_round()
                # Rafraîchir la grille si siège (portes détruites)
                if battle.map_name == "Siège":
                    grid_surface = build_grid_surface(battle, cell_size)

                # ─── Détection d'événements → bannières ───
                bfb = battle.battlefield
                ng = getattr(bfb, 'gates_open', False)
                if ng != prev_gates_open:
                    if ng:
                        event_banners.append(["LES PORTES S'OUVRENT — SORTIE !", (255, 210, 70), 180])
                    else:
                        event_banners.append(["LES PORTES SE REFERMENT", (150, 200, 255), 150])
                    prev_gates_open = ng
                n_intact = sum(1 for h in bfb.gate_hp.values() if h > 0)
                if n_intact < prev_intact_gates and not ng:
                    if n_intact == 0:
                        event_banners.append(["LA PORTE EST ENFONCÉE !", (255, 120, 60), 180])
                    prev_intact_gates = n_intact
                for ci, cmd in enumerate((battle.commander1, battle.commander2)):
                    p = getattr(cmd, 'posture', 'balanced')
                    if p != prev_postures[ci]:
                        prev_postures[ci] = p
                        side = f"Armée {ci + 1}"
                        label = _POSTURE_BANNERS.get(p)
                        if label:
                            event_banners.append([f"{side} : {label[0]}", label[1], 150])
                    m = getattr(cmd, 'maneuver', None)
                    if m != prev_maneuvers[ci]:
                        prev_maneuvers[ci] = m
                        side = f"Armée {ci + 1}"
                        if m == "envelop":
                            event_banners.append([f"{side} déborde sur les ailes !", (255, 190, 80), 160])
                        elif m == "concentrate":
                            event_banners.append([f"{side} concentre ses forces !", (170, 230, 120), 160])
                        elif m == "collapse":
                            event_banners.append([f"{side} fond sur un isolé !", (255, 140, 140), 140])
                        elif m == "breach":
                            event_banners.append([f"{side} s'engouffre dans la brèche !", (255, 170, 90), 160])
                for txt, col, imp in getattr(battle, 'round_events', ()):
                    if imp >= 2:
                        event_banners.append([txt, col, 140])

                result = battle.is_battle_over()
                if result:
                    winner = result
                    battle_report = battle.get_battle_report()
            else:
                round_frame += 1

            # Le déplacement occupe la première moitié du round et se
            # termine avant que l'échange général ne batte son plein.
            move_anim_progress = min(1.0, round_frame / max(1.0, frames * MOVE_WINDOW))
        else:
            move_anim_progress = min(1.0, move_anim_progress)

        # Décompter les timers de lunge (seulement une fois l'instant venu)
        for u in battle.army1 + battle.army2:
            if u._lunge_timer > 0 and round_frame >= getattr(u, '_lunge_delay', 0):
                u._lunge_timer -= 1

        # Vieillir effets visuels
        for p in battle.visual_effects['projectiles'][:]:
            p.age += 1
            if not p.is_alive():
                battle.visual_effects['projectiles'].remove(p)

        for l in battle.visual_effects['attack_lines'][:]:
            l.age += 1
            if not l.is_alive():
                battle.visual_effects['attack_lines'].remove(l)

        # Effets de sorts, impacts, morts en fondu
        for key in ['aoe_explosions', 'heal_beams', 'armor_shimmers', 'wall_effects',
                    'death_fades', 'impacts', 'shockwaves']:
            for fx in battle.visual_effects.get(key, [])[:]:
                fx.age += 1
                if not fx.is_alive():
                    battle.visual_effects[key].remove(fx)

        # ── Secousse de caméra: juste un frémissement sur les chocs les
        # plus lourds. Au-delà de 2 px ça devient illisible et laid. ──
        for fx in battle.visual_effects.get('shockwaves', []):
            if fx.age == fx.delay:
                screen_shake = min(SHAKE_MAX, screen_shake + 1.1)
        screen_shake *= 0.72
        if screen_shake < 0.25:
            screen_shake = 0.0

        screen.fill((25, 40, 30))
        
        # Camera offset pour le rendu monde
        ox = int(-cam_x)
        oy = int(-cam_y)
        if screen_shake > 0.25:
            ox += int(round(math.sin(now * 0.07) * screen_shake))
            oy += int(round(math.cos(now * 0.11) * screen_shake * 0.6))
        
        # Clipper le rendu monde pour ne pas déborder sur le HUD
        view_h = SCREEN_H - HUD_HEIGHT
        screen.set_clip(pygame.Rect(0, 0, SCREEN_W, view_h))
        
        screen.blit(grid_surface, (ox, oy))
        
        # Ligne centrale
        center_x = bf_w // 2 * cell_size + ox
        view_h = SCREEN_H - HUD_HEIGHT
        pygame.draw.line(screen, (60, 60, 60), (center_x, 0), (center_x, view_h), 1)
        
        # Lignes de ciblage (couleur selon type d'attaque)
        if show_lines:
            for att, tgt in battle.visual_effects['target_indicators']:
                if att.is_alive and tgt.is_alive:
                    sp = (att.position[0] * cell_size + cell_size // 2 + ox,
                          att.position[1] * cell_size + cell_size // 2 + oy)
                    ep = (tgt.position[0] * cell_size + cell_size // 2 + ox,
                          tgt.position[1] * cell_size + cell_size // 2 + oy)
                    dist = battle.battlefield.manhattan_distance(att.position, tgt.position)
                    if dist <= att._max_range:
                        # Pas de ligne de visée à travers un mur/porte fermée
                        if (att.attack_type == "ranged"
                                and not battle.battlefield.has_line_of_fire(att, tgt)):
                            continue
                        if att.attack_type == "spell":
                            color = (120, 60, 180)
                        elif att.attack_type == "ranged":
                            color = (60, 120, 180)
                        elif att.attack_type == "reach":
                            color = (180, 150, 40)
                        else:
                            color = (180, 60, 60)
                        pygame.draw.line(screen, color, sp, ep, 1)
        
        # Lignes d'attaque (rouge=CaC, jaune=portée)
        for line in battle.visual_effects['attack_lines']:
            if not line.is_visible():
                continue
            alpha = line.get_alpha()
            t = alpha / 255
            r, g, b = line.color
            color = (int(r * t), int(g * t), int(b * t))
            sp = (line.start_pos[0] + ox, line.start_pos[1] + oy)
            ep = (line.end_pos[0] + ox, line.end_pos[1] + oy)
            pygame.draw.line(screen, color, sp, ep, max(1, int(3 * t)))
        
        # Projectiles (les flèches en attente de volée ne sont pas dessinées)
        for proj in battle.visual_effects['projectiles']:
            if proj.is_flying():
                draw_projectile(screen, proj, ox, oy)
        
        # ── Gerbes d'impact: chaque coup qui BLESSE projette des éclats ──
        for imp in battle.visual_effects.get('impacts', []):
            if not imp.is_visible():
                continue
            a = imp.get_alpha()
            if a <= 8:
                continue
            prog = imp.get_progress()
            cxi = imp.center_pos[0] + ox
            cyi = imp.center_pos[1] + oy
            reach = int((cell_size * 0.35 + cell_size * 0.5 * imp.power) * (0.35 + prog))
            n_shards = 5 if imp.power < 1.5 else 8
            for k in range(n_shards):
                ang = imp.angle + (k - n_shards / 2) * 0.28
                x2 = cxi + int(math.cos(ang) * reach)
                y2 = int(cyi + math.sin(ang) * reach - prog * cell_size * 0.25)
                x1 = cxi + int(math.cos(ang) * reach * 0.35)
                y1 = cyi + int(math.sin(ang) * reach * 0.35)
                t_i = a / 255.0
                col = (int(imp.color[0] * t_i), int(imp.color[1] * t_i), int(imp.color[2] * t_i))
                pygame.draw.line(screen, col, (x1, y1), (x2, y2), 1)
            flash_r = max(2, int(cell_size * 0.18 * imp.power * (1.0 - prog)))
            if flash_r > 1:
                fs = pygame.Surface((flash_r * 2, flash_r * 2), pygame.SRCALPHA)
                pygame.draw.circle(fs, (*imp.color, min(200, a)), (flash_r, flash_r), flash_r)
                screen.blit(fs, (cxi - flash_r, cyi - flash_r))

        # ── Ondes de choc au sol (charge, coup décisif) ──
        for sw in battle.visual_effects.get('shockwaves', []):
            if not sw.is_visible():
                continue
            r_sw = sw.get_current_radius()
            a_sw = sw.get_alpha()
            if r_sw <= 1 or a_sw <= 8:
                continue
            surf = pygame.Surface((r_sw * 2 + 4, r_sw * 2 + 4), pygame.SRCALPHA)
            pygame.draw.ellipse(surf, (*sw.color, a_sw),
                                (2, 2 + r_sw // 2, r_sw * 2, r_sw), max(1, cell_size // 14))
            screen.blit(surf, (sw.center_pos[0] - r_sw - 2 + ox,
                               sw.center_pos[1] - r_sw - 2 + oy))

        # Explosions AoE (boule de feu)
        for aoe in battle.visual_effects.get('aoe_explosions', []):
            if not aoe.is_visible():
                continue
            alpha = aoe.get_alpha()
            r_px = aoe.get_current_radius()
            if r_px > 0 and alpha > 10:
                surf = pygame.Surface((r_px * 2, r_px * 2), pygame.SRCALPHA)
                # Cercle extérieur orange
                pygame.draw.circle(surf, (*aoe.color, min(alpha, 150)),
                                   (r_px, r_px), r_px)
                # Cercle intérieur jaune
                inner_r = max(1, r_px // 2)
                pygame.draw.circle(surf, (255, 220, 50, min(alpha, 200)),
                                   (r_px, r_px), inner_r)
                screen.blit(surf, (aoe.center_pos[0] - r_px + ox, aoe.center_pos[1] - r_px + oy))
        
        # Rayons de soin
        for beam in battle.visual_effects.get('heal_beams', []):
            if not beam.is_visible():
                continue
            alpha = beam.get_alpha()
            if alpha > 10:
                t = alpha / 255
                # Ligne verte épaisse + scintillements
                c = (int(50 * t), int(255 * t), int(100 * t))
                sp = (beam.start_pos[0] + ox, beam.start_pos[1] + oy)
                ep = (beam.end_pos[0] + ox, beam.end_pos[1] + oy)
                pygame.draw.line(screen, c, sp, ep, max(2, int(4 * t)))
                # Croix verte au point d'arrivée
                ex, ey = ep
                s = max(3, int(8 * t))
                pygame.draw.line(screen, c, (ex - s, ey), (ex + s, ey), 2)
                pygame.draw.line(screen, c, (ex, ey - s), (ex, ey + s), 2)
        
        # Scintillements d'armure
        for shim in battle.visual_effects.get('armor_shimmers', []):
            if not shim.is_visible():
                continue
            alpha = shim.get_alpha()
            if alpha > 10:
                r_px = shim.radius_px + 4
                surf = pygame.Surface((r_px * 2, r_px * 2), pygame.SRCALPHA)
                # Anneau bleu qui pulse
                pygame.draw.circle(surf, (80, 180, 255, min(alpha, 120)),
                                   (r_px, r_px), r_px, max(2, r_px // 4))
                screen.blit(surf, (shim.center_pos[0] - r_px + ox, shim.center_pos[1] - r_px + oy))
        
        # Effets de mur
        for wall in battle.visual_effects.get('wall_effects', []):
            if not wall.is_visible():
                continue
            alpha = wall.get_alpha()
            if alpha > 10:
                for wx, wy in wall.positions:
                    px = wx * cell_size + ox
                    py = wy * cell_size + oy
                    surf = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
                    surf.fill((160, 80, 220, min(alpha, 180)))
                    screen.blit(surf, (px, py))
                    pygame.draw.rect(screen, (200, 120, 255),
                                     (px, py, cell_size, cell_size), 2)
        
        # Morts en fondu: croix qui s'estompe + nuage de poussière
        for df in battle.visual_effects.get('death_fades', []):
            if not df.is_visible():
                continue
            prog = df.get_progress()
            alpha = int(210 * (1 - prog))
            if alpha <= 8:
                continue
            dx_px = df.center_pos[0] + ox
            dy_px = df.center_pos[1] + oy
            gh = df.radius
            # Poussière: anneau qui s'étend et se dissipe (premier tiers)
            if prog < 0.45:
                dust_p = prog / 0.45
                dust_r = int(gh * (0.6 + dust_p * 1.3))
                dust_a = int(110 * (1 - dust_p))
                dsurf = pygame.Surface((dust_r * 2 + 2, dust_r * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(dsurf, (160, 150, 130, dust_a),
                                   (dust_r + 1, dust_r + 1), dust_r, max(1, dust_r // 3))
                screen.blit(dsurf, (dx_px - dust_r - 1, dy_px - dust_r - 1))
            # Croix qui s'estompe
            xsurf = pygame.Surface((gh * 2 + 4, gh * 2 + 4), pygame.SRCALPHA)
            cc = (80, 80, 80, alpha)
            pygame.draw.line(xsurf, cc, (2, 2), (gh * 2 + 1, gh * 2 + 1), 2)
            pygame.draw.line(xsurf, cc, (gh * 2 + 1, 2), (2, gh * 2 + 1), 2)
            tc = df.team_color
            pygame.draw.circle(xsurf, (tc[0] // 3, tc[1] // 3, tc[2] // 3, alpha),
                               (gh + 2, gh + 2), gh + 1, 1)
            screen.blit(xsurf, (dx_px - gh - 2, dy_px - gh - 2))
        
        # Unités
        ur_base = max(3, cell_size // 2 - 4)
        tick_time = pygame.time.get_ticks()
        pulse = (tick_time // 200) % 4
        army1_set = set(id(u) for u in battle.army1)
        # Une armée articulée en plusieurs groupes: chacun reçoit une
        # pastille de couleur. On ne se sert pas de la couleur de faction:
        # deux groupes de la même faction doivent rester distinguables.
        group_colors = [{}, {}]
        for side_i, army_l in enumerate((battle.army1, battle.army2)):
            seen_g = []
            for u in army_l:
                if u.contingent not in seen_g:
                    seen_g.append(u.contingent)
            for gi_, name_g in enumerate(seen_g):
                group_colors[side_i][name_g] = GROUP_PIPS[gi_ % len(GROUP_PIPS)]
        multi_contingent = (len(group_colors[0]) > 1, len(group_colors[1]) > 1)
        drawn_ids = set()  # Éviter de dessiner 2 fois les grosses unités
        
        for u in battle.army1 + battle.army2:
            if u.position is None or id(u) in drawn_ids:
                continue
            drawn_ids.add(id(u))
            
            x, y = u.position
            # Dimensions en cases selon la taille
            if u.size <= 1:
                uw, uh = 1, 1
            elif u.size == 2:
                uw, uh = 2, 2
            else:
                uw, uh = 2, 4
            
            # === Animation: interpolation fluide entre positions ===
            # Chaque unité a un léger décalage de départ et une vitesse propre
            # (déterministes par unité) → l'armée ne bouge plus en bloc robotique
            prev_x, prev_y = getattr(u, '_prev_position', u.position)
            seed_u = id(u) % 9973
            is_moving = (prev_x != x or prev_y != y)
            
            if is_moving:
                delay_u = (seed_u % 11) / 11.0 * 0.22        # 0 → 0.22 de retard
                speed_u = 1.0 + ((seed_u // 11) % 7) / 7.0 * 0.25  # 1.0 → 1.25x
                t_u = max(0.0, min(1.0, (move_anim_progress - delay_u) * speed_u
                                   / max(0.05, 1.0 - delay_u)))
            else:
                t_u = 1.0
            # Ease-out pour un mouvement plus naturel (rapide au début, lent à la fin)
            t_ease = 1.0 - (1.0 - t_u) * (1.0 - t_u)
            
            interp_x = prev_x + (x - prev_x) * t_ease
            interp_y = prev_y + (y - prev_y) * t_ease
            
            # Centre pixel de l'unité (avec interpolation)
            cx = int(interp_x * cell_size + (uw * cell_size) // 2) + ox
            cy = int(interp_y * cell_size + (uh * cell_size) // 2) + oy
            
            # Balancement de marche: petit rebond vertical pendant le trajet
            # (un "pas" par case parcourue, amorti en fin de course)
            if is_moving and t_u < 1.0 and u.is_alive and not u.fleeing:
                dist_cells = abs(x - prev_x) + abs(y - prev_y)
                steps = max(1, min(4, dist_cells))
                bob = abs(math.sin(t_u * math.pi * steps)) * cell_size * 0.07 * (1.0 - t_u * 0.5)
                cy -= int(bob)
            
            # Secousse d'impact: l'unité tremble brièvement quand elle encaisse
            hit_flash = getattr(u, '_hit_flash', 0)
            if (hit_flash > 0 and u.is_alive
                    and round_frame >= getattr(u, '_hit_flash_delay', 0)):
                sh_amp = max(1.0, cell_size / 14.0) * (hit_flash / 12.0)
                cx += int(math.sin(tick_time * 0.09 + seed_u) * sh_amp)
                cy += int(math.cos(tick_time * 0.11 + seed_u) * sh_amp * 0.6)
            
            # === Animation de lunge CaC ===
            lunge_target = getattr(u, '_lunge_target', None)
            lunge_timer = getattr(u, '_lunge_timer', 0)
            if lunge_target and lunge_timer > 0 and u.is_alive:
                # Phase aller (10 premières frames) puis retour (10 suivantes)
                total_lunge = 20
                lunge_progress = 1.0 - (lunge_timer / total_lunge)
                # Aller-retour: sin donne 0→1→0 sur [0, pi]
                lunge_amount = math.sin(lunge_progress * math.pi)
                # Se déplacer de 30-40% vers la cible
                lunge_strength = 0.35
                tx_px = lunge_target[0] * cell_size + cell_size // 2 + ox
                ty_px = lunge_target[1] * cell_size + cell_size // 2 + oy
                cx = int(cx + (tx_px - cx) * lunge_amount * lunge_strength)
                cy = int(cy + (ty_px - cy) * lunge_amount * lunge_strength)
            
            # Rayon adapté à la taille
            ur = max(3, min(uw, uh) * cell_size // 2 - 4)
            
            # Aura de peur
            if u.fear_aura > 0 and u.is_alive:
                for i in range(6):
                    ang = i * 60 + pulse * 20
                    rad = math.radians(ang)
                    px = cx + int((ur + 8) * math.cos(rad))
                    py = cy + int((ur + 8) * math.sin(rad))
                    fc = (220, 40, 40) if u.fear_aura == 1 else (240, 140, 0) if u.fear_aura == 2 else (255, 50, 150)
                    pygame.draw.circle(screen, fc, (px, py), max(1, 3 * cell_size // 32))
            
            
            # Symbole d'attaque au-dessus de l'unité
            # ⚔ CaC pur = X rouge | Lance/portée = | jaune | Tir = → bleu | Sort = ✦ violet
            if u.is_alive and u.current_target and u.current_target.is_alive and not u.fleeing:
                sy = cy - ur - 10
                s = max(3, cell_size // 8)  # Taille adaptative
                
                if u.attack_type == "spell":
                    # Étoile violette (losange + croix)
                    c = (180, 80, 255)
                    pygame.draw.line(screen, c, (cx, sy - s), (cx, sy + s), 2)
                    pygame.draw.line(screen, c, (cx - s, sy), (cx + s, sy), 2)
                    pygame.draw.line(screen, c, (cx - s + 1, sy - s + 1), (cx + s - 1, sy + s - 1), 1)
                    pygame.draw.line(screen, c, (cx + s - 1, sy - s + 1), (cx - s + 1, sy + s - 1), 1)
                
                elif u.attack_type == "ranged":
                    # Flèche bleue →
                    c = (80, 160, 255)
                    pygame.draw.line(screen, c, (cx - s, sy), (cx + s, sy), 2)
                    pygame.draw.line(screen, c, (cx + s, sy), (cx + s - 3, sy - 3), 2)
                    pygame.draw.line(screen, c, (cx + s, sy), (cx + s - 3, sy + 3), 2)
                
                elif u.attack_type == "reach":
                    # Lance jaune (trait vertical + pointe)
                    c = (255, 200, 50)
                    pygame.draw.line(screen, c, (cx, sy + s), (cx, sy - s), 2)
                    pygame.draw.line(screen, c, (cx, sy - s), (cx - 2, sy - s + 3), 2)
                    pygame.draw.line(screen, c, (cx, sy - s), (cx + 2, sy - s + 3), 2)
                
                else:
                    # X rouge (CaC pur)
                    c = (220, 80, 80)
                    pygame.draw.line(screen, c, (cx - s, sy - s), (cx + s, sy + s), 2)
                    pygame.draw.line(screen, c, (cx + s, sy - s), (cx - s, sy + s), 2)
            
            # Corps: cercle d'équipe (bleu=A1, rouge=A2) + token ou cercle intérieur
            token_size = min(uw, uh) * cell_size - 4
            is_army1 = id(u) in army1_set
            team_color = (60, 120, 220) if is_army1 else (220, 60, 60)
            
            if u.is_alive:
                # Ombre portée (profondeur) — surface mise en cache
                sh_w = max(4, ur * 2)
                sh_h = max(2, ur // 2 + 2)
                screen.blit(get_shadow(sh_w, sh_h), (cx - sh_w // 2, cy + ur - sh_h // 2))
                
                if u.fleeing:
                    pygame.draw.circle(screen, (255, 140, 0), (cx, cy), ur)
                else:
                    token_img = load_token(u.token_name, token_size) if u.token_name else None
                    if token_img:
                        screen.blit(token_img, (cx - token_size // 2, cy - token_size // 2))
                    else:
                        pygame.draw.circle(screen, u.color, (cx, cy), ur)
                        dot_r = max(1, 3 * cell_size // 32)
                        rc = (255, 255, 255) if u.role == "front" else (128, 128, 128) if u.role == "mid" else (0, 0, 0)
                        pygame.draw.circle(screen, rc, (cx, cy), dot_r)
                # Contour d'équipe PAR-DESSUS (outline épaisse)
                ring_r = ur + 2
                ring_w = max(2, cell_size // 8)
                pygame.draw.circle(screen, team_color, (cx, cy), ring_r, ring_w)

                # Pastille de contingent (couleur de la faction), seulement
                # si l'équipe aligne plusieurs armées alliées
                side_idx = 0 if is_army1 else 1
                if multi_contingent[side_idx] and cell_size >= 16:
                    pip_c = group_colors[side_idx].get(u.contingent, (220, 220, 220))
                    pip_r = max(2, cell_size // 9)
                    ppx = cx + int(ring_r * 0.72)
                    ppy = cy - int(ring_r * 0.72)
                    pygame.draw.circle(screen, (15, 18, 22), (ppx, ppy), pip_r + 1)
                    pygame.draw.circle(screen, pip_c, (ppx, ppy), pip_r)
                
                # Flash de dégâts (au moment PRÉCIS où le coup porte)
                hit_flash = getattr(u, '_hit_flash', 0)
                if hit_flash > 0 and round_frame >= getattr(u, '_hit_flash_delay', 0):
                    u._hit_flash = hit_flash - 1
                    fa = int(150 * (hit_flash / 12))
                    fr = ur + 3
                    fsurf = pygame.Surface((fr * 2 + 2, fr * 2 + 2), pygame.SRCALPHA)
                    pygame.draw.circle(fsurf, (255, 40, 40, fa), (fr + 1, fr + 1), fr)
                    screen.blit(fsurf, (cx - fr - 1, cy - fr - 1))
            else:
                # Cadavre: croix grise discrète au sol (moins de bruit visuel
                # que l'ancien double cercle)
                gh = max(2, ur - 2)
                corpse_c = (70, 70, 70)
                pygame.draw.line(screen, corpse_c, (cx - gh, cy - gh), (cx + gh, cy + gh), 2)
                pygame.draw.line(screen, corpse_c, (cx + gh, cy - gh), (cx - gh, cy + gh), 2)
                tc_dim = (team_color[0] // 3, team_color[1] // 3, team_color[2] // 3)
                pygame.draw.circle(screen, tc_dim, (cx, cy), gh + 3, 1)
            
            # Barre HP (couleur selon l'état: vert → jaune → rouge)
            if u.is_alive:
                bw = max(4, uw * cell_size - 8)
                hp_r = max(0, u.hp / u.max_hp) if u.max_hp > 0 else 0
                by = cy - ur - 5
                if hp_r > 0.6:
                    hp_c = (50, 190, 50)
                elif hp_r > 0.3:
                    hp_c = (220, 190, 40)
                else:
                    hp_c = (230, 70, 50)
                pygame.draw.rect(screen, (15, 15, 15), (cx - bw // 2 - 1, by - 1, bw + 2, 5))
                pygame.draw.rect(screen, (90, 25, 25), (cx - bw // 2, by, bw, 3))
                pygame.draw.rect(screen, hp_c, (cx - bw // 2, by, int(bw * hp_r), 3))
            
            # Nom et moral
            if cell_size >= 20 and u.is_alive:
                name_txt = tiny_font.render(u.name[:5], True, (220, 220, 220))
                # Ombre du texte pour la lisibilité sur tout terrain
                name_sh = tiny_font.render(u.name[:5], True, (10, 10, 10))
                screen.blit(name_sh, (cx - name_txt.get_width() // 2 + 1, cy + ur + 3))
                screen.blit(name_txt, (cx - name_txt.get_width() // 2, cy + ur + 2))
                
                # Moral en pastilles (plus lisible que "M:3")
                effective_morale = u.get_effective_morale()
                n_pips = max(0, min(6, effective_morale))
                pip_r = max(1, cell_size // 14)
                pip_gap = pip_r * 2 + 2
                total_w = n_pips * pip_gap - 2 if n_pips > 0 else 0
                pip_y = cy + ur + 13
                moral_color = ((100, 255, 100) if effective_morale >= 3
                               else (255, 230, 90) if effective_morale >= 2
                               else (255, 100, 100))
                for pi in range(n_pips):
                    pygame.draw.circle(screen, moral_color,
                                       (cx - total_w // 2 + pi * pip_gap + pip_r, pip_y), pip_r)
            
            # Statut
            if u.status_text and cell_size >= 16:
                st = small_font.render(u.status_text, True, (255, 80, 80))
                screen.blit(st, (cx - st.get_width() // 2, cy - ur - 18))
            
            # Textes flottants
            if cell_size >= 16:
                ft_oy = -ur - 6
                for ft in list(u.floating_texts):
                    ft.age += 1
                    if not ft.is_alive():
                        u.floating_texts.remove(ft)
                        continue
                    if not ft.is_visible():
                        continue  # l'action n'a pas encore eu lieu
                    prog = ft.get_progress()
                    ts = tiny_font.render(ft.text, True, ft.color)
                    ts.set_alpha(255 - int(255 * prog))
                    screen.blit(ts, (cx - ts.get_width() // 2,
                                     cy + ft_oy - int(prog * ft.duration / 4)))
                    ft_oy -= 10
        
        # ═══ BANDEAU SUPÉRIEUR: rapport de forces + postures IA ═══
        screen.set_clip(None)
        a1c = sum(1 for u in battle.army1 if u.is_alive)
        a2c = sum(1 for u in battle.army2 if u.is_alive)
        a1f = len(battle.army1_fled) + sum(1 for u in battle.army1 if u.fleeing and u.is_alive)
        a2f = len(battle.army2_fled) + sum(1 for u in battle.army2 if u.fleeing and u.is_alive)
        
        top_h = 30
        top_surf = pygame.Surface((SCREEN_W, top_h), pygame.SRCALPHA)
        top_surf.fill((12, 16, 20, 195))
        screen.blit(top_surf, (0, 0))
        pygame.draw.line(screen, (60, 70, 85), (0, top_h), (SCREEN_W, top_h), 1)
        
        # Barre "bras de fer" centrale (proportion des forces vivantes)
        bar_w_total = min(420, SCREEN_W // 3)
        bar_x = (SCREEN_W - bar_w_total) // 2
        bar_y = 8
        bar_h = 14
        total_alive = max(1, a1c + a2c)
        a1_w = int(bar_w_total * a1c / total_alive)
        pygame.draw.rect(screen, (25, 30, 38), (bar_x - 1, bar_y - 1, bar_w_total + 2, bar_h + 2))
        pygame.draw.rect(screen, (60, 120, 220), (bar_x, bar_y, a1_w, bar_h))
        pygame.draw.rect(screen, (220, 60, 60), (bar_x + a1_w, bar_y, bar_w_total - a1_w, bar_h))
        pygame.draw.line(screen, (240, 240, 240), (bar_x + a1_w, bar_y), (bar_x + a1_w, bar_y + bar_h), 2)
        
        # Effectifs de part et d'autre de la barre
        c1 = small_font.render(f"{a1c}", True, (140, 190, 255))
        c2 = small_font.render(f"{a2c}", True, (255, 150, 150))
        screen.blit(c1, (bar_x - c1.get_width() - 8, bar_y))
        screen.blit(c2, (bar_x + bar_w_total + 8, bar_y))
        
        # Round au centre de la barre
        rt = tiny_font.render(f"Round {battle.round - 1}", True, (230, 220, 180))
        screen.blit(rt, ((SCREEN_W - rt.get_width()) // 2, bar_y + bar_h + 1))
        
        # Postures IA aux extrémités
        p1 = getattr(battle.commander1, 'posture', 'balanced')
        p2 = getattr(battle.commander2, 'posture', 'balanced')
        l1, pc1 = POSTURE_LABELS.get(p1, (p1, (180, 180, 180)))
        l2, pc2 = POSTURE_LABELS.get(p2, (p2, (180, 180, 180)))
        t1 = small_font.render(f"Armée 1 — {l1}", True, pc1)
        t2 = small_font.render(f"{l2} — Armée 2", True, pc2)
        screen.blit(t1, (12, 8))
        screen.blit(t2, (SCREEN_W - t2.get_width() - 12, 8))

        # Tempérament du général + manoeuvre en cours: on comprend d'un
        # coup d'oeil POURQUOI l'IA joue comme elle joue.
        _MANEUVER_FR = {"envelop": "débordement", "concentrate": "concentration",
                        "collapse": "curée", "breach": "percée"}
        for cmd, right in ((battle.commander1, False), (battle.commander2, True)):
            temper = getattr(cmd, 'temperament', None)
            if not temper:
                continue
            man = _MANEUVER_FR.get(getattr(cmd, 'maneuver', None))
            sub = temper if not man else f"{temper} · {man}"
            st_t = tiny_font.render(sub, True, (150, 155, 165))
            screen.blit(st_t, (SCREEN_W - st_t.get_width() - 12 if right else 12, 8 + 15))
        
        # ═══ BANNIÈRES D'ÉVÉNEMENTS (centre haut, fondu) ═══
        banner_y = top_h + 14
        for eb in event_banners[:]:
            eb[2] -= 1
            if eb[2] <= 0:
                event_banners.remove(eb)
                continue
            fade = min(1.0, eb[2] / 40)
            txt = banner_font.render(eb[0], True, eb[1])
            bw_b = txt.get_width() + 30
            bh_b = txt.get_height() + 10
            bsurf = pygame.Surface((bw_b, bh_b), pygame.SRCALPHA)
            bsurf.fill((10, 12, 16, int(190 * fade)))
            pygame.draw.rect(bsurf, (*eb[1], int(200 * fade)), (0, 0, bw_b, bh_b), 2)
            txt.set_alpha(int(255 * fade))
            bsurf.blit(txt, (15, 5))
            screen.blit(bsurf, ((SCREEN_W - bw_b) // 2, banner_y))
            banner_y += bh_b + 6
        
        # ═══ OVERLAY PAUSE ═══
        if pause and winner is None and not battle_report:
            pt = pause_font.render("PAUSE", True, (255, 220, 120))
            ps = pygame.Surface((pt.get_width() + 50, pt.get_height() + 18), pygame.SRCALPHA)
            ps.fill((10, 12, 16, 170))
            pygame.draw.rect(ps, (255, 220, 120, 160), ps.get_rect(), 2)
            ps.blit(pt, (25, 9))
            screen.blit(ps, ((SCREEN_W - ps.get_width()) // 2,
                             (SCREEN_H - HUD_HEIGHT - ps.get_height()) // 2))
            hint = small_font.render("ESPACE pour reprendre", True, (200, 200, 200))
            screen.blit(hint, ((SCREEN_W - hint.get_width()) // 2,
                               (SCREEN_H - HUD_HEIGHT) // 2 + 35))
        
        # ═══ HUD BAS ═══
        view_h = SCREEN_H - HUD_HEIGHT
        pygame.draw.rect(screen, (16, 20, 26), (0, view_h, SCREEN_W, HUD_HEIGHT))
        pygame.draw.line(screen, (70, 85, 105), (0, view_h), (SCREEN_W, view_h), 2)
        hy = view_h + 6
        
        status = "VICTOIRE: " + winner if winner else ("PAUSE" if pause else (">> RAPIDE" if simulation_speed == "fast" else "> NORMAL"))
        color = (255, 215, 0) if winner else ((255, 130, 100) if pause else ((255, 220, 80) if simulation_speed == "fast" else (110, 220, 110)))
        hud = small_font.render(
            f"{status}   |   Armée 1: {a1c} vivants, {a1f} fuyants   |   Armée 2: {a2c} vivants, {a2f} fuyants",
            True, color)
        screen.blit(hud, (10, hy))
        
        # Rapport de bataille (overlay)
        if battle_report:
            draw_battle_report(screen, battle_report, SCREEN_W, view_h, small_font, tiny_font)
        
        # Légende
        ly = hy + 18
        lx = 10
        # Rôles
        pygame.draw.circle(screen, (255, 255, 255), (lx + 5, ly + 5), 4)
        screen.blit(tiny_font.render("Front", True, (180, 180, 180)), (lx + 15, ly))
        pygame.draw.circle(screen, (128, 128, 128), (lx + 60, ly + 5), 4)
        screen.blit(tiny_font.render("Mid", True, (180, 180, 180)), (lx + 70, ly))
        pygame.draw.circle(screen, (0, 0, 0), (lx + 105, ly + 5), 4)
        screen.blit(tiny_font.render("Back", True, (180, 180, 180)), (lx + 115, ly))
        
        lx2 = lx + 160
        pygame.draw.line(screen, (220, 80, 80), (lx2, ly + 1), (lx2 + 8, ly + 9), 2)
        pygame.draw.line(screen, (220, 80, 80), (lx2 + 8, ly + 1), (lx2, ly + 9), 2)
        screen.blit(tiny_font.render("CaC", True, (180, 180, 180)), (lx2 + 12, ly))
        
        lx3 = lx2 + 45
        pygame.draw.line(screen, (255, 200, 50), (lx3 + 4, ly + 9), (lx3 + 4, ly + 1), 2)
        pygame.draw.line(screen, (255, 200, 50), (lx3 + 4, ly + 1), (lx3 + 2, ly + 4), 2)
        pygame.draw.line(screen, (255, 200, 50), (lx3 + 4, ly + 1), (lx3 + 6, ly + 4), 2)
        screen.blit(tiny_font.render("Portée", True, (180, 180, 180)), (lx3 + 12, ly))
        
        lx4 = lx3 + 60
        pygame.draw.line(screen, (80, 160, 255), (lx4, ly + 5), (lx4 + 8, ly + 5), 2)
        pygame.draw.line(screen, (80, 160, 255), (lx4 + 8, ly + 5), (lx4 + 5, ly + 2), 2)
        pygame.draw.line(screen, (80, 160, 255), (lx4 + 8, ly + 5), (lx4 + 5, ly + 8), 2)
        screen.blit(tiny_font.render("Tir", True, (180, 180, 180)), (lx4 + 12, ly))
        
        lx5 = lx4 + 40
        sc = lx5 + 4
        pygame.draw.line(screen, (180, 80, 255), (sc, ly + 1), (sc, ly + 9), 2)
        pygame.draw.line(screen, (180, 80, 255), (sc - 4, ly + 5), (sc + 4, ly + 5), 2)
        pygame.draw.line(screen, (180, 80, 255), (sc - 3, ly + 2), (sc + 3, ly + 8), 1)
        pygame.draw.line(screen, (180, 80, 255), (sc + 3, ly + 2), (sc - 3, ly + 8), 1)
        screen.blit(tiny_font.render("Sort", True, (180, 180, 180)), (lx5 + 12, ly))
        
        # Contrôles
        ctrl = tiny_font.render("ESPACE=Pause  ZQSD/Flèches=Caméra  F=Vite  N=Normal  R=Reset  T=Lignes  B=Bordure  M=Menu  ESC=Quit", True, (150, 170, 200))
        screen.blit(ctrl, (10, ly + 18))
        
        size = tiny_font.render(f"Grille {bf_w}x{bf_h} | Cell {cell_size}px | FPS: {int(clock.get_fps())}", True, (120, 120, 120))
        screen.blit(size, (SCREEN_W - size.get_width() - 10, ly + 18))
        
        pygame.display.flip()
        clock.tick(60)
    
    return _return_action