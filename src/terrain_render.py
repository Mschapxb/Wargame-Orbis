"""Rendu du terrain à effets.

Règle de lisibilité: chaque terrain a une teinte ET un motif (courbes,
hachures, ondes, planches…). On ne doit jamais avoir besoin de distinguer
deux couleurs proches pour savoir où l'on marche.
"""
import pygame

import theme as T

import terrain as tr

# Pseudo-terrain de légende: une case en feu n'est pas un terrain, mais le
# joueur doit pouvoir lire ce qu'elle fait.
FIRE = "feu"

LEGEND = {
    tr.HILL:   "Colline — tir depuis la hauteur: +1 portée · mêlée contre une unité en hauteur: +1 au seuil de toucher (plus difficile) · monter ×1,5",
    tr.WOOD:   "Bois — déplacement ×2 · tirs reçus: +1 au seuil de toucher (plus difficile) · pas de charge · 3 cases masquent la vue",
    tr.RIVER:  "Rivière — infranchissable",
    tr.FORD:   "Gué — déplacement ×2 · sauvegarde -1 · pas de charge",
    tr.BRIDGE: "Pont — passage étroit, déplacement normal",
    tr.MARSH:  "Marais — déplacement ×3 · sauvegarde -1 · pas de charge",
    tr.RUBBLE: "Décombres — déplacement ×2 · tirs reçus: +1 au seuil de toucher (couvert) · pas de charge",
    tr.BURNT:  "Brûlé — terrain dégagé: ne ralentit, ne couvre ni ne masque plus rien",
    FIRE:      "En feu — déplacement ×4 · 1 dégât par round · la fumée masque comme un bois",
}
_ORDER = (tr.HILL, tr.WOOD, tr.RIVER, tr.FORD, tr.BRIDGE, tr.MARSH, tr.RUBBLE, tr.BURNT, FIRE)


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
    elif name == tr.RUBBLE:
        ov.fill((92, 84, 74, 200), r)
        # Blocs anguleux et poutre calcinée: motif non chromatique
        for k in range(4):
            bx = x0 + 1 + ((sd >> (k * 3)) % max(1, cs - 5))
            by = y0 + 1 + ((sd >> (k * 3 + 4)) % max(1, cs - 5))
            bw = max(2, cs // 4 - (k & 1))
            block = [(bx, by + bw), (bx + bw // 2, by), (bx + bw, by + bw // 3), (bx + bw - 1, by + bw)]
            pygame.draw.polygon(ov, (134, 126, 114, 240), block)
            pygame.draw.polygon(ov, (54, 48, 42, 230), block, 1)
        if (sd & 3) == 0 and cs >= 10:
            pygame.draw.line(ov, (40, 28, 20, 240), (x0 + 2, y0 + cs - 3),
                             (x0 + cs - 3, y0 + cs // 3), max(2, cs // 9))
    elif name == tr.BURNT:
        ov.fill((26, 22, 18, 175), r)
        step = max(3, cs // 4)
        for k in range(0, cs, step):
            pygame.draw.line(ov, (70, 64, 58, 140), (x0 + k, y0 + 1),
                             (x0 + k + step // 2, y0 + step // 2 + 1), 1)
            pygame.draw.line(ov, (70, 64, 58, 140), (x0 + k + step // 2, y0 + cs - 2),
                             (x0 + k, y0 + cs - step // 2 - 2), 1)
        if (sd & 7) < 3 and cs >= 10:
            # souche noire
            sx, sy = x0 + cs // 2 + (sd & 3) - 1, y0 + cs // 2
            pygame.draw.circle(ov, (14, 10, 8, 255), (sx, sy), max(2, cs // 7))
            pygame.draw.circle(ov, (60, 48, 36, 255), (sx, sy), max(1, cs // 12))
    elif name == FIRE:
        ov.fill((70, 26, 8, 230), r)
        for k in range(3):
            fx = x0 + cs * (k + 1) // 4
            pygame.draw.polygon(ov, (255, 150 + 40 * k, 40, 255),
                                [(fx - cs // 8, y0 + cs - 3), (fx, y0 + cs // 4 + k * 2),
                                 (fx + cs // 8, y0 + cs - 3)])
    elif name == tr.MARSH:
        ov.fill((58, 70, 38, 130), r)
        step = max(3, cs // 3)
        for k in range(-cs, cs, step):
            pygame.draw.line(ov, (28, 40, 20, 170), (x0 + k, y0 + cs - 1), (x0 + k + cs - 1, y0), 1)
        if cs >= 10:
            tx, ty = x0 + cs // 3 + (sd & 3), y0 + cs // 2
            pygame.draw.line(ov, (130, 150, 76, 210), (tx, ty), (tx, ty - cs // 4), 1)
            pygame.draw.line(ov, (130, 150, 76, 210), (tx + 2, ty), (tx + 3, ty - cs // 5), 1)


def draw_terrain(surf, bf, cs, region=None):
    """Pose les motifs de terrain sur la surface statique de la grille.
    `region` (x0, y0, x1, y1) borne les cases peintes (repeint incrémental)."""
    if getattr(bf, 'terrain', None) is None:
        return
    x0, y0, x1, y1 = region if region is not None else (0, 0, bf.width - 1, bf.height - 1)
    ox, oy = x0 * cs, y0 * cs
    ov = pygame.Surface(((x1 - x0 + 1) * cs, (y1 - y0 + 1) * cs), pygame.SRCALPHA)
    for x in range(x0, x1 + 1):
        col = bf.terrain[x]
        for y in range(y0, y1 + 1):
            name = col[y]
            if name == tr.PLAIN or bf.grid[x][y] != 0:
                continue
            edges = (not _is(bf, x, y - 1, name), not _is(bf, x + 1, y, name),
                     not _is(bf, x, y + 1, name), not _is(bf, x - 1, y, name))
            draw_cell(ov, name, pygame.Rect(x * cs - ox, y * cs - oy, cs, cs), cs, _seed(x, y), edges)
    surf.blit(ov, (ox, oy))


def legend_surface(bf, font):
    """Encart des terrains présents sur la carte (None s'il n'y en a pas)."""
    if getattr(bf, 'terrain', None) is None:
        return None
    present = {n for col in bf.terrain for n in col}
    if getattr(bf, 'structures', None):
        # Tout ce qui peut brûler ou s'effondrer: la légende l'annonce d'emblée
        present |= {tr.RUBBLE, tr.BURNT, FIRE}
    rows = [n for n in _ORDER if n in present]
    if not rows:
        return None
    sw, pad, gap = 22, 10, 6
    texts = [font.render(LEGEND[n], True, T.PARCHMENT) for n in rows]
    title = T.gold_text("Terrain  (L pour masquer)", T.font('title', max(12, font.get_height())))
    w = pad * 2 + max([sw + 10 + t.get_width() for t in texts] + [title.get_width()])
    h = pad * 2 + title.get_height() + gap + sum(max(sw, t.get_height()) + gap for t in texts)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    T.glass(surf, surf.get_rect(), 225, 8)
    T.corner_marks(surf, surf.get_rect(), T.GOLD_DIM, 6)
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
        pygame.draw.rect(surf, (*T.GOLD_DIM, 220), box, 1)
        surf.blit(t, (pad + sw + 10, y + (sw - t.get_height()) // 2))
        y += max(sw, t.get_height()) + gap
    return surf
