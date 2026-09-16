"""Rendu du terrain à effets.

Règle de lisibilité: chaque terrain a une teinte ET un motif (courbes,
hachures, ondes, planches…). On ne doit jamais avoir besoin de distinguer
deux couleurs proches pour savoir où l'on marche.
"""
import pygame

import terrain as tr

LEGEND = {
    tr.HILL:   "Colline — tir: +1 portée vers le bas · mêlée: -1 pour toucher qui est en haut · monter ×1,5",
    tr.WOOD:   "Bois — déplacement ×2 · tirs reçus: -1 pour toucher · pas de charge · 3 cases masquent la vue",
    tr.RIVER:  "Rivière — infranchissable",
    tr.FORD:   "Gué — déplacement ×2 · sauvegarde -1 · pas de charge",
    tr.BRIDGE: "Pont — passage étroit, déplacement normal",
    tr.MARSH:  "Marais — déplacement ×3 · sauvegarde -1 · pas de charge",
}
_ORDER = (tr.HILL, tr.WOOD, tr.RIVER, tr.FORD, tr.BRIDGE, tr.MARSH)


def _seed(x, y):
    return ((x * 73856093) ^ (y * 19349663)) & 0xFFFF


def _is(bf, x, y, name):
    return 0 <= x < bf.width and 0 <= y < bf.height and bf.terrain[x][y] == name


def draw_cell(ov, name, r, cs, sd=0, edges=(False, False, False, False)):
    """Dessine une case de terrain sur une surface SRCALPHA.
    edges = (haut, droite, bas, gauche): bord de la zone (pour les contours)."""
    x0, y0 = r.x, r.y
    lw = max(1, cs // 12)
    if name == tr.HILL:
        ov.fill((255, 238, 190, 34), r)
        if (sd & 1) == 0 and cs >= 10:
            mx, my = x0 + cs // 2, y0 + cs // 2 + cs // 8
            w = cs // 4
            pygame.draw.lines(ov, (255, 246, 214, 90), False,
                              [(mx - w, my), (mx, my - w), (mx + w, my)], lw)
        dark = (52, 38, 14, 150)
        top, right, bottom, left = edges
        if top:
            pygame.draw.line(ov, dark, (x0, y0), (x0 + cs - 1, y0), lw)
        if right:
            pygame.draw.line(ov, dark, (x0 + cs - 1, y0), (x0 + cs - 1, y0 + cs - 1), lw)
        if bottom:
            pygame.draw.line(ov, dark, (x0, y0 + cs - 1), (x0 + cs - 1, y0 + cs - 1), lw)
        if left:
            pygame.draw.line(ov, dark, (x0, y0), (x0, y0 + cs - 1), lw)
    elif name == tr.WOOD:
        ov.fill((8, 28, 6, 80), r)
        for k in range(3):
            px = x0 + 2 + ((sd >> (k * 3)) % max(1, cs - 4))
            py = y0 + 2 + ((sd >> (k * 3 + 5)) % max(1, cs - 4))
            pygame.draw.circle(ov, (16, 56, 18, 190), (px, py), max(1, cs // 7))
    elif name == tr.RIVER:
        ov.fill((44, 92, 138, 245), r)
        for k in (1, 3):
            yy = y0 + k * cs // 4 + ((sd >> k) & 1)
            pts = [(x0 + i * cs // 4, yy + (1 if i % 2 else -1)) for i in range(5)]
            pygame.draw.lines(ov, (150, 200, 235, 150), False, pts, 1)
    elif name == tr.FORD:
        ov.fill((88, 132, 152, 215), r)
        for k in range(3):
            px = x0 + 2 + ((sd >> (k * 4)) % max(1, cs - 4))
            py = y0 + 2 + ((sd >> (k * 4 + 2)) % max(1, cs - 4))
            pygame.draw.circle(ov, (176, 170, 150, 230), (px, py), max(1, cs // 9))
    elif name == tr.BRIDGE:
        ov.fill((118, 86, 52, 255), r)
        step = max(3, cs // 4)
        for xx in range(x0 + step, x0 + cs, step):
            pygame.draw.line(ov, (70, 50, 30, 255), (xx, y0), (xx, y0 + cs - 1), 1)
        pygame.draw.line(ov, (58, 40, 22, 255), (x0, y0), (x0 + cs - 1, y0), lw)
        pygame.draw.line(ov, (58, 40, 22, 255), (x0, y0 + cs - 1), (x0 + cs - 1, y0 + cs - 1), lw)
    elif name == tr.MARSH:
        ov.fill((58, 70, 38, 130), r)
        step = max(3, cs // 3)
        for k in range(-cs, cs, step):
            pygame.draw.line(ov, (28, 40, 20, 170), (x0 + k, y0 + cs - 1), (x0 + k + cs - 1, y0), 1)
        if cs >= 10:
            tx, ty = x0 + cs // 3 + (sd & 3), y0 + cs // 2
            pygame.draw.line(ov, (130, 150, 76, 210), (tx, ty), (tx, ty - cs // 4), 1)
            pygame.draw.line(ov, (130, 150, 76, 210), (tx + 2, ty), (tx + 3, ty - cs // 5), 1)


def draw_terrain(surf, bf, cs):
    """Pose les motifs de terrain sur la surface statique de la grille."""
    if bf.terrain is None:
        return
    ov = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    for x in range(bf.width):
        col = bf.terrain[x]
        for y in range(bf.height):
            name = col[y]
            if name == tr.PLAIN or bf.grid[x][y] != 0:
                continue
            edges = (not _is(bf, x, y - 1, name), not _is(bf, x + 1, y, name),
                     not _is(bf, x, y + 1, name), not _is(bf, x - 1, y, name))
            draw_cell(ov, name, pygame.Rect(x * cs, y * cs, cs, cs), cs, _seed(x, y), edges)
    surf.blit(ov, (0, 0))


def legend_surface(bf, font):
    """Encart des terrains présents sur la carte (None s'il n'y en a pas)."""
    if bf.terrain is None:
        return None
    present = {n for col in bf.terrain for n in col}
    rows = [n for n in _ORDER if n in present]
    if not rows:
        return None
    sw, pad, gap = 22, 10, 6
    texts = [font.render(LEGEND[n], True, (228, 228, 220)) for n in rows]
    title = font.render("Terrain  (L pour masquer)", True, (255, 220, 120))
    w = pad * 2 + max([sw + 10 + t.get_width() for t in texts] + [title.get_width()])
    h = pad * 2 + title.get_height() + gap + sum(max(sw, t.get_height()) + gap for t in texts)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((12, 14, 18, 215))
    pygame.draw.rect(surf, (255, 220, 120, 150), surf.get_rect(), 1)
    surf.blit(title, (pad, pad))
    y = pad + title.get_height() + gap
    for n, t in zip(rows, texts):
        box = pygame.Rect(pad, y, sw, sw)
        pygame.draw.rect(surf, (72, 88, 56, 255), box)
        # draw_cell peint sur une surface SRCALPHA en remplaçant les pixels
        # (fill/draw.* ne fondent pas l'alpha) : on dessine donc la case sur
        # une surface temporaire opaque-fond puis on la blitte par-dessus,
        # comme le fait draw_terrain avec son calque.
        swatch = pygame.Surface((sw, sw), pygame.SRCALPHA)
        draw_cell(swatch, n, pygame.Rect(0, 0, sw, sw), sw, 0x5A5A, (True, True, True, True))
        surf.blit(swatch, box)
        pygame.draw.rect(surf, (200, 200, 200, 200), box, 1)
        surf.blit(t, (pad + sw + 10, y + (sw - t.get_height()) // 2))
        y += max(sw, t.get_height()) + gap
    return surf
