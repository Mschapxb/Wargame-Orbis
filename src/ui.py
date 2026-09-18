"""Interface de bataille (lot D): zoom, mini-carte, fiche d'unité au survol,
bandeau inférieur, chevrons d'orientation.

Le renderer garde la boucle et le dessin du monde; ce module fournit les
calculs (conversions écran ↔ monde, bornes de caméra, unité survolée) et les
panneaux, testables sans ouvrir de fenêtre.
"""
import math

import pygame

import terrain as tr
import theme as T

ZOOM_LEVELS = (0.5, 0.67, 0.8, 1.0, 1.25, 1.6, 2.0)

TEAM_COLORS = T.TEAM

_ORDER_FR = {
    "attack": "attaque", "flank": "contournement", "hold": "tient la position",
    "protect": "garde la ligne", "support": "gagne son poste", "guard": "escorte",
    "kite": "recule en tirant", "withdraw": "décroche", "demolish": "démolit",
    "form": "marche en formation",
}
_ROLE_FR = {
    "hammer": "marteau", "lure": "leurre", "refused": "aile refusée",
    "hill": "tient la colline",
}


# ─── Zoom et caméra ───

def next_zoom(zoom, direction):
    """Niveau de zoom voisin (+1 = rapprocher, -1 = éloigner)."""
    idx = min(range(len(ZOOM_LEVELS)), key=lambda i: abs(ZOOM_LEVELS[i] - zoom))
    idx = max(0, min(len(ZOOM_LEVELS) - 1, idx + direction))
    return ZOOM_LEVELS[idx]


def screen_to_world(mx, my, cam_x, cam_y, zoom):
    """Pixel écran → pixel monde (caméra en pixels monde)."""
    return cam_x + mx / zoom, cam_y + my / zoom


def zoom_around(cam_x, cam_y, mx, my, old_zoom, new_zoom):
    """Nouvelle caméra pour que le point sous le curseur ne bouge pas."""
    wx, wy = screen_to_world(mx, my, cam_x, cam_y, old_zoom)
    return wx - mx / new_zoom, wy - my / new_zoom


def clamp_camera(cam_x, cam_y, world_w, world_h, view_w, view_h, zoom):
    """Bornes de caméra pour une vue écran (view_w × view_h) au zoom donné.
    Si le monde est plus petit que la vue, il est centré."""
    vw, vh = view_w / zoom, view_h / zoom
    if world_w <= vw:
        cam_x = (world_w - vw) / 2
    else:
        cam_x = max(0.0, min(cam_x, world_w - vw))
    if world_h <= vh:
        cam_y = (world_h - vh) / 2
    else:
        cam_y = max(0.0, min(cam_y, world_h - vh))
    return cam_x, cam_y


def unit_at(battle, wx, wy, cell_size):
    """Unité vivante sous le point monde (wx, wy), ou None."""
    gx, gy = int(wx // cell_size), int(wy // cell_size)
    u = battle.battlefield.units.get((gx, gy))
    if u is not None and u.is_alive:
        return u
    return None


# ─── Chevron d'orientation ───

def facing_angle(unit):
    """Orientation réelle de l'unité (facing.py) — celle qui décide des
    coups de flanc et de dos. À défaut: cible courante, dernier pas."""
    f = getattr(unit, 'facing', None)
    if f is not None:
        return math.atan2(f[1], f[0])
    ux, uy = unit.position
    t = getattr(unit, 'current_target', None)
    if t is not None and t.is_alive and t.position is not None and t.position != unit.position:
        return math.atan2(t.position[1] - uy, t.position[0] - ux)
    prev = getattr(unit, '_prev_position', None)
    if prev is not None and prev != unit.position:
        return math.atan2(uy - prev[1], ux - prev[0])
    return None


def draw_facing(screen, cx, cy, ring_r, angle, color):
    """Petit chevron posé sur l'anneau d'équipe, pointé dans `angle`."""
    if angle is None:
        return
    tip = ring_r + max(4, ring_r // 2)
    base = ring_r + 1
    spread = 0.42
    p0 = (cx + math.cos(angle) * tip, cy + math.sin(angle) * tip)
    p1 = (cx + math.cos(angle - spread) * base, cy + math.sin(angle - spread) * base)
    p2 = (cx + math.cos(angle + spread) * base, cy + math.sin(angle + spread) * base)
    pygame.draw.polygon(screen, color, (p0, p1, p2))
    pygame.draw.polygon(screen, (15, 15, 18), (p0, p1, p2), 1)


# ─── Mini-carte ───

_MINI_TERRAIN = {
    tr.HILL: (104, 112, 70), tr.WOOD: (26, 58, 26), tr.RIVER: (48, 96, 140),
    tr.FORD: (86, 128, 148), tr.BRIDGE: (118, 86, 52), tr.MARSH: (64, 76, 44),
    tr.RUBBLE: (104, 96, 86), tr.BURNT: (34, 30, 26),
}


class Minimap:
    """Vue d'ensemble: terrain, unités, cadre de la vue. Clic pour y aller."""

    MAX_W = 280
    MAX_H = 130

    def __init__(self, battle, cell_size, screen_w, top):
        bf = battle.battlefield
        self.cs = cell_size
        scale = min(self.MAX_W / bf.width, self.MAX_H / bf.height)
        self.w = max(20, int(bf.width * scale))
        self.h = max(10, int(bf.height * scale))
        self.rect = pygame.Rect(screen_w - self.w - 12, top, self.w, self.h)
        self.thumb = None
        self._sig = None
        self._frames = 0
        self.refresh(battle, force=True)

    @staticmethod
    def _signature(bf):
        return (len(getattr(bf, 'fires', ())), sum(getattr(bf, 'structure_hp', {}).values()),
                getattr(bf, 'active_ring', 0), len(getattr(bf, 'breaches', ())),
                tuple(sorted(getattr(bf, 'open_gate_cells', ()))),
                sum(1 for h in bf.gate_hp.values() if h > 0))

    def refresh(self, battle, force=False):
        """Reconstruit la vignette si le terrain a changé (vérifié au plus
        une fois par seconde, sauf `force`)."""
        self._frames += 1
        if not force and self._frames < 60:
            return
        self._frames = 0
        bf = battle.battlefield
        sig = self._signature(bf)
        if not force and sig == self._sig:
            return
        self._sig = sig
        from maps import theme_info
        bg = theme_info(bf)["bg_color"]
        small = pygame.Surface((bf.width, bf.height))
        small.fill(bg)
        terr = bf.terrain
        fires = getattr(bf, 'fires', {})
        for x in range(bf.width):
            col_g = bf.grid[x]
            col_t = terr[x] if terr is not None else None
            for y in range(bf.height):
                c = col_g[y]
                if c == 2:
                    small.set_at((x, y), (150, 148, 150))
                elif c == 3:
                    if bf.gate_hp.get((x, y), 0) > 0:
                        small.set_at((x, y), (140, 100, 50))
                elif c in (4, 5):
                    small.set_at((x, y), (118, 112, 104))
                elif c == 1:
                    small.set_at((x, y), (40, 38, 34))
                elif col_t is not None and col_t[y] in _MINI_TERRAIN:
                    small.set_at((x, y), _MINI_TERRAIN[col_t[y]])
                if (x, y) in fires:
                    small.set_at((x, y), (255, 130, 40))
        self.thumb = pygame.transform.smoothscale(small, (self.w, self.h))

    def draw(self, screen, battle, cam_x, cam_y, view_w, view_h, zoom):
        bf = battle.battlefield
        T.glass(screen, self.rect.inflate(12, 12), 215, 7)
        T.corner_marks(screen, self.rect.inflate(12, 12), T.GOLD_DIM, 6)
        screen.blit(self.thumb, self.rect.topleft)
        sx, sy = self.w / bf.width, self.h / bf.height
        for army, color in ((battle.army1, TEAM_COLORS[0]), (battle.army2, TEAM_COLORS[1])):
            for u in army:
                if u.is_alive and u.position is not None:
                    px = self.rect.x + int((u.position[0] + 0.5) * sx)
                    py = self.rect.y + int((u.position[1] + 0.5) * sy)
                    pygame.draw.rect(screen, color if not u.fleeing else (255, 170, 60),
                                     (px - 1, py - 1, 3, 3))
        cs = self.cs
        view = pygame.Rect(int(self.rect.x + cam_x / cs * sx), int(self.rect.y + cam_y / cs * sy),
                           max(4, int(view_w / zoom / cs * sx)), max(4, int(view_h / zoom / cs * sy)))
        pygame.draw.rect(screen, T.GOLD_BRIGHT, view.clip(self.rect), 1)
        pygame.draw.rect(screen, T.INK, self.rect, 1)

    def camera_for(self, battle, mx, my, view_w, view_h, zoom):
        """Caméra (pixels monde) centrée sur le point cliqué, ou None."""
        if not self.rect.collidepoint(mx, my):
            return None
        bf = battle.battlefield
        wx = (mx - self.rect.x) / self.rect.w * bf.width * self.cs
        wy = (my - self.rect.y) / self.rect.h * bf.height * self.cs
        return wx - view_w / zoom / 2, wy - view_h / zoom / 2


# ─── Fiche d'unité ───

def unit_card_lines(unit, battle):
    """[(texte, couleur)] décrivant une unité, du titre aux ordres."""
    side = 0 if unit in battle.army1 else 1
    team = TEAM_COLORS[side]
    title = f"{unit.name}  —  Armée {side + 1}"
    if unit.contingent:
        title += f" · {unit.contingent}"
    lines = [(title, team)]
    hp_r = unit.hp / max(1, unit.max_hp)
    hp_c = (90, 210, 90) if hp_r > 0.6 else ((230, 200, 60) if hp_r > 0.3 else (235, 90, 70))
    lines.append((f"PV {unit.hp}/{unit.max_hp}   Moral {unit.get_effective_morale()}   "
                  f"Sauvegarde {unit.sauvegarde}+   Vitesse {unit.vitesse}", hp_c))
    extra = []
    if getattr(unit, 'max_ammo', None):
        extra.append(f"Munitions {unit.ammo}/{unit.max_ammo}")
    if getattr(unit, 'fatigue', 0):
        extra.append(f"Fatigue {unit.fatigue}")
    if extra:
        lines.append(("   ".join(extra), (200, 190, 150)))
    for a in unit.armes:
        kind = "tir" if a.porte >= 4 else ("allonge" if a.porte >= 2 else "mêlée")
        lines.append((f"• {a.name} ({kind}, portée {a.porte}): {a.nb_attaque}× "
                      f"{a.toucher}+/{a.blesser}+  perf. {a.perforation}  dégâts {a.degats}",
                      (205, 205, 200)))
    for sp in getattr(unit, 'spells', ()):
        lines.append((f"• Sort: {sp.name} (portée {sp.porte})", (190, 150, 255)))
    states = []
    if unit.fleeing:
        states.append("EN FUITE")
    if unit.afraid:
        states.append("ébranlée")
    if getattr(unit, '_suppression', 0) >= 3:
        states.append("sous le feu")
    if getattr(unit, '_on_wall', False):
        states.append("sur le rempart")
    if getattr(unit, 'reloading', False):
        states.append("recharge")
    if getattr(unit, 'exhausted', False):
        states.append("épuisée")
    elif getattr(unit, 'tired', False):
        states.append("fatiguée")
    if states:
        lines.append(("État: " + ", ".join(states), (255, 170, 90)))
    order = getattr(unit, '_tactical_order', None)
    cmd = battle.commander1 if side == 0 else battle.commander2
    parts = []
    if order is not None:
        text = _ORDER_FR.get(order.order_type, order.order_type)
        if order.target_unit is not None and order.target_unit.is_alive:
            text += f" → {order.target_unit.name}"
        parts.append(text)
    plan = getattr(cmd, 'plan', None)
    role = plan.roles.get(id(unit)) if plan is not None else None
    if role:
        parts.append(f"plan: {_ROLE_FR.get(role, role)}")
    if parts:
        lines.append(("Ordre: " + " · ".join(parts), (170, 200, 235)))
    return lines


def draw_unit_card(screen, unit, battle, mx, my, font, bounds):
    """Fiche près du curseur (cadre du thème), maintenue dans `bounds`.
    Titre à empattements, jauge de PV, lignes de détail."""
    lines = unit_card_lines(unit, battle)
    title_font = T.font('title', font.get_height() + 1)
    body = T.font('ui', max(11, font.get_height() - 3))
    team = lines[0][1]
    title_img = title_font.render(lines[0][0], True, T.lighten(team, 0.3))
    rendered = [body.render(t, True, c) for t, c in lines[1:]]
    pad = 12
    w = max([title_img.get_width()] + [r.get_width() for r in rendered]) + pad * 2
    h = (title_img.get_height() + 16 + sum(r.get_height() + 3 for r in rendered) + pad * 2)
    x, y = mx + 18, my + 18
    if x + w > bounds.right:
        x = mx - w - 12
    if y + h > bounds.bottom:
        y = my - h - 12
    x = max(bounds.left + 4, x)
    y = max(bounds.top + 4, y)
    rect = pygame.Rect(x, y, w, h)
    T.glass(screen, rect, 232, 8)
    screen.blit(T.rounded_gradient(w, 3, T.lighten(team, 0.1), T.darken(team, 0.2), 2), (x, y))
    cy = y + pad - 2
    screen.blit(title_img, (x + pad, cy))
    cy += title_img.get_height() + 3
    ratio = max(0.0, min(1.0, unit.hp / max(1, unit.max_hp)))
    T.bar(screen, (x + pad, cy, w - pad * 2, 7), [(ratio, lines[1][1])])
    cy += 13
    for r in rendered:
        screen.blit(r, (x + pad, cy))
        cy += r.get_height() + 3
    return rect


# ─── Bandeau inférieur ───

def army_counts(army, roster, fled_list):
    """(au combat, en fuite, tombés) pour un camp."""
    alive = sum(1 for u in army if u.is_alive and not u.fleeing)
    fleeing = len(fled_list) + sum(1 for u in army if u.is_alive and u.fleeing)
    dead = max(0, len(roster) - alive - fleeing)
    return alive, fleeing, dead


def draw_bottom_hud(screen, battle, screen_w, top, height, fonts, status, status_color,
                    zoom, fps, help_text, posture_labels):
    """Bandeau: deux panneaux d'armée et l'état de la bataille au centre
    (cadre et jauges du thème)."""
    tiny, bold = fonts
    screen.blit(T.vgradient(screen_w, height, (26, 28, 35), (12, 13, 17)), (0, top))
    T.divider(screen, 0, screen_w, top, T.GOLD_DIM, gem=False)
    pygame.draw.line(screen, T.INK, (0, top + 1), (screen_w, top + 1))
    name_font = T.font('title', 17)
    panel_w = min(520, screen_w // 3)
    sides = ((battle.army1, battle.army1_roster, battle.army1_fled, battle.commander1),
             (battle.army2, battle.army2_roster, battle.army2_fled, battle.commander2))
    for side, (army, roster, fled, cmd) in enumerate(sides):
        x = 14 if side == 0 else screen_w - panel_w - 14
        color = TEAM_COLORS[side]
        total = max(1, len(roster))
        alive, fleeing, dead = army_counts(army, roster, fled)
        T.diamond(screen, x + 5, top + 16, 4, color)
        title = T.text(screen, f"Armée {side + 1}", name_font, (x + 14, top + 5), T.lighten(color, 0.25))
        bar_x = title.right + 14
        bar_w = max(20, x + panel_w - bar_x)
        T.bar(screen, (bar_x, top + 10, bar_w, 12),
              [(alive / total, (70, 170, 90)), (fleeing / total, T.WARNING),
               (1.0 - (alive + fleeing) / total, (110, 40, 38))])
        T.text(screen, f"{alive} au combat  ·  {fleeing} en fuite  ·  {dead} tombés",
               tiny, (x, top + 30), T.PARCHMENT)
        posture = getattr(cmd, 'posture', 'balanced')
        label, pcolor = posture_labels.get(posture, (posture, (180, 180, 180)))
        sub = label
        plan = getattr(cmd, 'plan', None)
        if plan is not None and plan.kind not in (None, "direct"):
            sub += f" · {plan.label()}"
        temper = getattr(cmd, 'temperament', None)
        if temper:
            sub += f" · {temper}"
        T.text(screen, sub, tiny, (x, top + 47), pcolor)

    cx = screen_w // 2
    st = T.gold_text(status, T.font('title', 19), T.lighten(status_color, 0.3),
                     T.darken(status_color, 0.15))
    screen.blit(st, (cx - st.get_width() // 2, top + 5))
    sky = getattr(battle.battlefield, 'weather', None)
    sky_txt = f"   ·   {sky.label}" if sky is not None and sky.name != "Clair" else ""
    T.text(screen, f"Round {battle.round - 1}{sky_txt}   ·   zoom ×{zoom:g}   ·   {fps} i/s",
           tiny, (cx, top + 31), T.PARCHMENT_DIM, align="center")
    hint = tiny.render(help_text, True, T.MUTED)
    screen.blit(hint, (cx - hint.get_width() // 2, top + height - hint.get_height() - 4))
