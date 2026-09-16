"""
Rendu des effets de combat: particules, décalques, animations de mort,
projectiles en sprites, coups de lame, sorts.

Le moteur (battle.py) ne produit que des DONNÉES d'effets horodatées
(effects.py). Ce module les met en scène: il émet les particules au moment
où chaque effet devient visible, les fait vivre, et dessine le tout en deux
couches — au sol (sous les unités) et en surplomb (au-dessus).
"""
import math
import random

import pygame

import sprites as S

ADD = pygame.BLEND_RGB_ADD

# Indices des champs d'une particule (listes plutôt qu'objets: bien plus
# rapide à mettre à jour par centaines à chaque frame)
PX, PY, VX, VY, LIFE, MAXL, SIZE, COL, KIND, DRAG, GRAV = range(11)


def _lerp(a, b, t):
    return a + (b - a) * t


class FxRenderer:
    MAX_PARTICLES = 1400
    MAX_DECALS = 160
    DECAL_LIFE = 1800          # ~30 s à 60 i/s

    def __init__(self, cell_size, load_token, font):
        self.cs = cell_size
        self.load_token = load_token
        self.font = font
        self.rng = random.Random(4242)
        self.particles = []
        self.decals = []        # [x, y, surface, age, life]
        self._snap_cache = {}
        self.clouds = []
        self._world = (1, 1)

    def reset(self, world_w, world_h):
        self.particles.clear()
        self.decals.clear()
        self._world = (world_w, world_h)
        rng = random.Random(99)
        self.clouds = [[rng.uniform(0, world_w), rng.uniform(0, world_h),
                        rng.uniform(5, 10) * self.cs, rng.uniform(0.12, 0.3)]
                       for _ in range(5)]

    # ───────────────────────── émission ─────────────────────────

    def _emit(self, x, y, vx, vy, life, size, color, kind, drag=0.9, grav=0.0):
        self.particles.append([x, y, vx, vy, life, life, size, color, kind, drag, grav])

    def _spray(self, x, y, n, speed, life, size, color, kind, angle=None, spread=math.tau,
               drag=0.88, grav=0.0):
        rng = self.rng
        for _ in range(n):
            a = (angle if angle is not None else 0.0) + rng.uniform(-spread / 2, spread / 2)
            v = speed * rng.uniform(0.35, 1.0)
            self._emit(x + rng.uniform(-2, 2), y + rng.uniform(-2, 2),
                       math.cos(a) * v, math.sin(a) * v,
                       int(life * rng.uniform(0.6, 1.2)), size * rng.uniform(0.7, 1.3),
                       color, kind, drag, grav)

    def add_decal(self, x, y, kind, radius, seed):
        self.decals.append([x, y, S.decal(kind, radius, seed), 0, self.DECAL_LIFE])
        if len(self.decals) > self.MAX_DECALS:
            del self.decals[:len(self.decals) - self.MAX_DECALS]

    def _impact_burst(self, fx):
        x, y = fx.center_pos
        cs = self.cs
        p = max(0.6, fx.power)
        back = fx.angle  # les éclats partent dans le sens du coup
        if fx.kind == "fire":
            self._spray(x, y, int(8 * p), cs * 0.16, 26, 3, (255, 150, 40), 'ember', drag=0.9, grav=-0.03)
            self._spray(x, y, 2, cs * 0.04, 40, cs * 0.25, (150, 145, 138), 'smoke', drag=0.95)
        elif fx.kind == "magic":
            self._spray(x, y, int(9 * p), cs * 0.14, 24, 3, (200, 130, 255), 'magic', drag=0.9)
        elif fx.kind == "gate":
            self._spray(x, y, 7, cs * 0.14, 30, 2.5, (120, 90, 55), 'debris', back, 1.6, grav=0.12)
            self._spray(x, y, 3, cs * 0.05, 36, cs * 0.22, (140, 125, 100), 'dust', drag=0.94)
        elif fx.kind == "ranged":
            self._spray(x, y, int(4 * p), cs * 0.12, 12, 1.5, (255, 230, 170), 'spark', back, 1.2)
            self._spray(x, y, int(3 * p), cs * 0.09, 30, 1.6, (140, 20, 20), 'blood', back, 1.0, grav=0.08)
        else:  # mêlée
            self._spray(x, y, int(6 * p), cs * 0.18, 12, 1.5, (255, 240, 200), 'spark', back, 1.5)
            self._spray(x, y, int(5 * p), cs * 0.12, 34, 1.8, (150, 18, 18), 'blood', back, 1.3, grav=0.1)
        if p >= 1.4 and self.rng.random() < 0.6:
            self.add_decal(x, y + cs * 0.15, "blood", cs * 0.28, int(x * 7 + y))

    # ───────────────────────── mise à jour ─────────────────────────

    def update(self, battle, paused=False):
        """Émet les particules des effets qui viennent d'apparaître, puis
        fait vivre particules, décalques et nuages. En pause, tout est figé."""
        if paused:
            return
        ve = battle.visual_effects
        cs = self.cs
        rng = self.rng

        for fx in ve.get('impacts', ()):
            if not fx.spawned and fx.is_visible():
                fx.spawned = True
                self._impact_burst(fx)

        for fx in ve.get('shockwaves', ()):
            if not fx.spawned and fx.is_visible():
                fx.spawned = True
                x, y = fx.center_pos
                self._spray(x, y + cs * 0.2, 12, cs * 0.12, 40, cs * 0.3, (150, 135, 110), 'dust', drag=0.93)

        for fx in ve.get('aoe_explosions', ()):
            if not fx.spawned and fx.is_visible():
                fx.spawned = True
                x, y = fx.center_pos
                r = fx.radius_px
                self._spray(x, y, 34, r * 0.16, 34, 3.5, (255, 160, 50), 'ember', drag=0.9, grav=-0.02)
                self._spray(x, y, 12, r * 0.05, 70, r * 0.30, (150, 142, 132), 'smoke', drag=0.96)
                self._spray(x, y, 10, r * 0.14, 40, 3, (70, 50, 35), 'debris', grav=0.12)
                self.add_decal(x, y, "scorch", r * 0.8, int(x + y * 3))

        for fx in ve.get('wall_effects', ()):
            if not fx.spawned and fx.is_visible():
                fx.spawned = True
                for (wx, wy) in fx.positions:
                    self._spray(wx * cs + cs / 2, wy * cs + cs * 0.8, 6, cs * 0.08, 40,
                                cs * 0.25, (150, 140, 125), 'dust', drag=0.93)

        for fx in ve.get('heal_beams', ()):
            if fx.is_visible() and fx.get_progress() < 0.8 and rng.random() < 0.7:
                x, y = fx.end_pos
                self._emit(x + rng.uniform(-cs * 0.35, cs * 0.35), y + cs * 0.3,
                           0, -rng.uniform(0.4, 0.9), 36, rng.uniform(4, 6), (120, 255, 150), 'heal', 0.98)

        for fx in ve.get('armor_shimmers', ()):
            if fx.is_visible() and fx.get_progress() < 0.8 and rng.random() < 0.45:
                x, y = fx.center_pos
                a = rng.uniform(0, math.tau)
                r = fx.radius_px
                self._emit(x + math.cos(a) * r, y + math.sin(a) * r, 0, -0.3, 22, 3,
                           (150, 210, 255), 'magic', 0.97)

        for p in ve.get('projectiles', ()):
            if not p.is_flying():
                continue
            prog = p.get_progress()
            if prog < 1.0:
                x, y = p.get_current_pos()
                if p.projectile_type == "fireball":
                    for _ in range(2):
                        self._emit(x + rng.uniform(-3, 3), y + rng.uniform(-3, 3),
                                   rng.uniform(-0.3, 0.3), rng.uniform(-0.6, 0.1),
                                   rng.randint(14, 24), rng.uniform(2, 3.5), (255, 150, 40), 'ember', 0.92, -0.02)
                    if rng.random() < 0.35:
                        self._emit(x, y, 0, -0.2, 40, cs * 0.18, (160, 150, 140), 'smoke', 0.97)
                elif p.projectile_type == "magic" and rng.random() < 0.8:
                    self._emit(x + rng.uniform(-2, 2), y + rng.uniform(-2, 2), 0, 0, 16, 2.5,
                               (200, 140, 255), 'magic', 0.9)
            elif not p.landed:
                p.landed = True
                if p.projectile_type in ("arrow", "bolt", "ballista"):
                    x, y = p.end_pos
                    self._spray(x, y + cs * 0.2, 3, cs * 0.04, 22, cs * 0.14, (140, 125, 100), 'dust', drag=0.92)

        for d in ve.get('deaths', ()):
            for ft in list(d.texts):
                ft.age += 1
                if not ft.is_alive():
                    d.texts.remove(ft)
            if not d.is_visible():
                continue
            prog = d.get_progress()
            if prog >= 0.12 and not d.spawned:
                d.spawned = True
                x, y = d.to_pos
                self._spray(x, y, 9, cs * 0.12, 36, 1.8, (140, 16, 16), 'blood', d.fall_angle, 1.4, grav=0.1)
                self._spray(x, y + cs * 0.2, 7, cs * 0.07, 44, cs * 0.3, (140, 128, 105), 'dust', drag=0.93)
            if prog >= 0.5 and not d.decal_done:
                d.decal_done = True
                x, y = d.to_pos
                fx_, fy_ = math.cos(d.fall_angle), math.sin(d.fall_angle)
                r = max(d.cells) * cs * 0.42
                self.add_decal(x + fx_ * r * 0.5, y + fy_ * r * 0.5, "corpse", r, d.seed)

        # Physique des particules
        alive = []
        for pt in self.particles:
            pt[LIFE] -= 1
            if pt[LIFE] <= 0:
                continue
            pt[PX] += pt[VX]
            pt[PY] += pt[VY]
            pt[VX] *= pt[DRAG]
            pt[VY] = pt[VY] * pt[DRAG] + pt[GRAV]
            alive.append(pt)
        if len(alive) > self.MAX_PARTICLES:
            alive = alive[len(alive) - self.MAX_PARTICLES:]
        self.particles = alive

        for dc in self.decals:
            dc[3] += 1
        self.decals = [dc for dc in self.decals if dc[3] < dc[4]]

        ww, wh = self._world
        for c in self.clouds:
            c[0] += c[3]
            if c[0] - c[2] > ww:
                c[0] = -c[2]

    # ───────────────────────── couche sol ─────────────────────────

    def _token_snapshot(self, d):
        cs = self.cs
        uw, uh = d.cells
        tsize = max(4, min(uw, uh) * cs - 4)
        key = (d.token_name, d.unit_color, d.team_color, tsize)
        snap = self._snap_cache.get(key)
        if snap is None:
            size = tsize + 8
            snap = pygame.Surface((size, size), pygame.SRCALPHA)
            c = size // 2
            ur = max(3, tsize // 2 - 2)
            img = self.load_token(d.token_name, tsize) if d.token_name else None
            if img:
                snap.blit(img, (c - tsize // 2, c - tsize // 2))
            else:
                pygame.draw.circle(snap, d.unit_color, (c, c), ur)
            pygame.draw.circle(snap, d.team_color, (c, c), ur + 2, max(2, cs // 8))
            self._snap_cache[key] = snap
        return snap

    def _draw_death(self, screen, d, ox, oy, move_progress):
        snap = self._token_snapshot(d)
        cs = self.cs
        ur = snap.get_width() // 2 - 4
        fdx, fdy = math.cos(d.fall_angle), math.sin(d.fall_angle)

        if not d.is_visible():
            # Le coup fatal n'est pas encore tombé: l'unité est toujours debout
            t = max(0.0, min(1.0, move_progress))
            t = 1.0 - (1.0 - t) ** 2
            x = _lerp(d.from_pos[0], d.to_pos[0], t)
            y = _lerp(d.from_pos[1], d.to_pos[1], t)
            screen.blit(snap, (x - snap.get_width() / 2 + ox, y - snap.get_height() / 2 + oy))
            return

        p = d.get_progress()
        x, y = d.to_pos
        if p < 0.12:
            # Recul sous le choc + éclair blanc
            q = p / 0.12
            off = ur * 0.35 * math.sin(q * math.pi)
            img = snap.copy()
            img.fill((110, 110, 110), special_flags=ADD)
            screen.blit(img, (x + fdx * off - img.get_width() / 2 + ox,
                              y + fdy * off - img.get_height() / 2 + oy))
            return

        # Chute: la silhouette s'écrase dans le sens de la chute, glisse,
        # pivote un peu, s'assombrit, puis la dépouille s'efface.
        q = min(1.0, (p - 0.12) / 0.38)
        q = q * q * (3 - 2 * q)
        squash = 1.0 - 0.55 * q
        spin = math.degrees(0.45 * q) * (1 if (d.seed & 1) else -1)
        fall_deg = math.degrees(d.fall_angle)
        w, h = snap.get_size()
        img = pygame.transform.rotate(snap, fall_deg)          # axe de chute → x
        iw, ih = img.get_size()
        img = pygame.transform.smoothscale(img, (max(2, int(iw * squash)), ih))
        img = pygame.transform.rotate(img, -fall_deg + spin)
        k = int(255 - 120 * q)
        img.fill((k, int(k * 0.92), int(k * 0.88)), special_flags=pygame.BLEND_RGB_MULT)
        if p > 0.5:
            img.set_alpha(int(255 * max(0.0, 1.0 - (p - 0.5) / 0.5)))
        slide = ur * (0.35 + 0.55 * q)
        screen.blit(img, (x + fdx * slide - img.get_width() / 2 + ox,
                          y + fdy * slide - img.get_height() / 2 + oy))

    def draw_ground(self, screen, battle, ox, oy, view_w, view_h, move_progress):
        """Décalques et morts: sous les unités vivantes."""
        vx0, vy0 = -ox - 64, -oy - 64
        vx1, vy1 = vx0 + view_w + 128, vy0 + view_h + 128
        for x, y, surf, age, life in self.decals:
            if not (vx0 < x < vx1 and vy0 < y < vy1):
                continue
            fade = 1.0 - max(0.0, (age - life * 0.8) / (life * 0.2))
            surf.set_alpha(int(255 * fade))
            screen.blit(surf, (x - surf.get_width() / 2 + ox, y - surf.get_height() / 2 + oy))
        for d in battle.visual_effects.get('deaths', ()):
            x, y = d.to_pos
            if vx0 < x < vx1 and vy0 < y < vy1:
                self._draw_death(screen, d, ox, oy, move_progress)

    # ───────────────────────── couche surplomb ─────────────────────────

    def draw_overlay(self, screen, battle, ox, oy, view_w, view_h, now):
        ve = battle.visual_effects
        cs = self.cs
        vx0, vy0 = -ox - 96, -oy - 96
        vx1, vy1 = vx0 + view_w + 192, vy0 + view_h + 192

        def visible_pt(x, y):
            return vx0 < x < vx1 and vy0 < y < vy1

        # ── Ombres de nuages: le terrain respire ──
        for cx, cy, r, _ in self.clouds:
            if visible_pt(cx, cy) or (vx0 - r < cx < vx1 + r and vy0 - r < cy < vy1 + r):
                blob = S.soft_blob(int(r), (10, 14, 20), 42)
                screen.blit(blob, (cx - r + ox, cy - r + oy))

        # ── Traînées de charge ──
        for ln in ve.get('attack_lines', ()):
            if not ln.is_visible():
                continue
            t = 1.0 - ln.get_progress()
            if t <= 0.05:
                continue
            sx, sy = ln.start_pos[0] + ox, ln.start_pos[1] + oy
            ex, ey = ln.end_pos[0] + ox, ln.end_pos[1] + oy
            col = tuple(int(c * t) for c in ln.color)
            pygame.draw.line(screen, col, (sx, sy), (ex, ey), max(1, int(4 * t)))
            g = S.glow(int(cs * 0.5), ln.color, int(6 * t))
            screen.blit(g, (ex - g.get_width() // 2, ey - g.get_height() // 2), special_flags=ADD)

        # ── Estocs ──
        for th in ve.get('thrusts', ()):
            if not th.is_visible():
                continue
            p = th.get_progress()
            sx, sy = th.start_pos
            ex, ey = th.end_pos
            if not visible_pt(ex, ey):
                continue
            ang = math.atan2(ey - sy, ex - sx)
            reach = 0.35 + 0.65 * min(1.0, p / 0.55)
            tx, ty = _lerp(sx, ex, reach), _lerp(sy, ey, reach)
            base = S.thrust_sprite(cs, th.color)
            img = S.rotated(('thrust', cs, th.color), base, ang)
            img.set_alpha(int(255 * (1.0 if p < 0.55 else max(0.0, 1 - (p - 0.55) / 0.45))))
            # la pointe du sprite est à son extrémité: on l'aligne sur (tx, ty)
            L = base.get_width()
            cxs, cys = tx - math.cos(ang) * L / 2, ty - math.sin(ang) * L / 2
            screen.blit(img, (cxs - img.get_width() / 2 + ox, cys - img.get_height() / 2 + oy))

        # ── Coups de taille ──
        for sl in ve.get('slashes', ()):
            if not sl.is_visible():
                continue
            x, y = sl.center_pos
            if not visible_pt(x, y):
                continue
            size = max(8, int(cs * sl.scale))
            frames = S.slash_frames(size, sl.color)
            idx = min(len(frames) - 1, int(sl.get_progress() * len(frames)))
            img = S.rotated(('slash', size, sl.color, idx), frames[idx], sl.angle, sl.mirror)
            screen.blit(img, (x - img.get_width() / 2 + ox, y - img.get_height() / 2 + oy))
            if idx <= 3:
                g = S.glow(int(cs * 0.5), (255, 220, 170), 7 - idx * 2)
                screen.blit(g, (x - g.get_width() // 2 + ox, y - g.get_height() // 2 + oy), special_flags=ADD)

        # ── Projectiles ──
        for p in ve.get('projectiles', ()):
            if not p.is_flying():
                continue
            prog = p.get_progress()
            if prog >= 1.0:
                continue
            x, y = p.get_current_pos()
            if not visible_pt(x, y):
                continue
            kind = p.projectile_type
            if kind in ("arrow", "bolt", "ballista"):
                # Ombre au sol (position sans la cloche): donne la hauteur
                gx = _lerp(p.start_pos[0], p.end_pos[0], prog)
                gy = _lerp(p.start_pos[1], p.end_pos[1], prog)
                sh = S.soft_blob(max(3, cs // 6), (0, 0, 0), 90)
                screen.blit(sh, (gx - sh.get_width() / 2 + ox, gy - sh.get_height() / 2 + oy))
                # Sillage
                tx, ty = p.pos_at(max(0.0, prog - 0.06))
                pygame.draw.line(screen, (170, 165, 150), (tx + ox, ty + oy), (x + ox, y + oy), 1)
                base = S.missile(kind, cs)
                img = S.rotated(('missile', kind, cs), base, p.get_heading())
                screen.blit(img, (x - img.get_width() / 2 + ox, y - img.get_height() / 2 + oy))
            elif kind == "fireball":
                g = S.glow(int(cs * 0.75), (255, 120, 30), 6)
                screen.blit(g, (x - g.get_width() // 2 + ox, y - g.get_height() // 2 + oy), special_flags=ADD)
                frames = S.fireball_frames(cs)
                img = frames[(p.age // 3 + p.seed) % len(frames)]
                screen.blit(img, (x - img.get_width() / 2 + ox, y - img.get_height() / 2 + oy))
            elif kind == "magic":
                g = S.glow(int(cs * 0.45), (170, 90, 255), 6)
                screen.blit(g, (x - g.get_width() // 2 + ox, y - g.get_height() // 2 + oy), special_flags=ADD)
                frames = S.magic_orb_frames(cs)
                img = frames[(p.age // 3 + p.seed) % len(frames)]
                screen.blit(img, (x - img.get_width() / 2 + ox, y - img.get_height() / 2 + oy))

        # ── Impacts: éclair bref au point de contact ──
        for fx in ve.get('impacts', ()):
            if not fx.is_visible():
                continue
            p = fx.get_progress()
            if p > 0.45:
                continue
            x, y = fx.center_pos
            if not visible_pt(x, y):
                continue
            col = {"fire": (255, 130, 40), "magic": (190, 110, 255),
                   "gate": (220, 170, 90)}.get(fx.kind, (255, 210, 160))
            lvl = int(7 * (1.0 - p / 0.45) * min(1.3, fx.power))
            g = S.glow(int(cs * (0.38 + 0.16 * fx.power)), col, lvl)
            screen.blit(g, (x - g.get_width() // 2 + ox, y - g.get_height() // 2 + oy), special_flags=ADD)

        # ── Ondes de choc ──
        for sw in ve.get('shockwaves', ()):
            if not sw.is_visible():
                continue
            r = sw.get_current_radius()
            a = sw.get_alpha()
            if r <= 2 or a <= 8:
                continue
            x, y = sw.center_pos
            if not visible_pt(x, y):
                continue
            surf = pygame.Surface((r * 2 + 4, r + 4), pygame.SRCALPHA)
            pygame.draw.ellipse(surf, (*sw.color, a), (2, 2, r * 2, r), max(1, cs // 12))
            screen.blit(surf, (x - r - 2 + ox, y - r // 2 - 2 + oy + cs * 0.2))

        # ── Explosions ──
        for ex in ve.get('aoe_explosions', ()):
            if not ex.is_visible():
                continue
            x, y = ex.center_pos
            if not visible_pt(x, y):
                continue
            p = ex.get_progress()
            R = ex.radius_px
            if p < 0.5:
                g = S.glow(int(R * (0.8 + 0.6 * p)), (255, 140, 40), int(8 * (1 - p / 0.5)))
                screen.blit(g, (x - g.get_width() // 2 + ox, y - g.get_height() // 2 + oy), special_flags=ADD)
            rr = int(R * (0.3 + 0.9 * min(1.0, p / 0.6)))
            a = int(200 * max(0.0, 1.0 - p))
            if rr > 2 and a > 8:
                surf = pygame.Surface((rr * 2 + 6, rr * 2 + 6), pygame.SRCALPHA)
                pygame.draw.circle(surf, (255, 200, 90, a), (rr + 3, rr + 3), rr, max(2, cs // 8))
                screen.blit(surf, (x - rr - 3 + ox, y - rr - 3 + oy))

        # ── Soins: rayon lumineux pulsé ──
        for hb in ve.get('heal_beams', ()):
            if not hb.is_visible():
                continue
            p = hb.get_progress()
            sx, sy = hb.start_pos
            exx, eyy = hb.end_pos
            lvl = int(6 * (1.0 - p))
            if lvl <= 0:
                continue
            steps = 12
            for i in range(steps + 1):
                t = i / steps
                wob = math.sin(now * 0.02 + i * 0.9) * cs * 0.06
                bx = _lerp(sx, exx, t) + wob
                by = _lerp(sy, eyy, t)
                g = S.glow(max(3, int(cs * 0.16)), (80, 255, 130), lvl)
                screen.blit(g, (bx - g.get_width() // 2 + ox, by - g.get_height() // 2 + oy), special_flags=ADD)
            g = S.glow(int(cs * 0.7), (90, 255, 140), lvl)
            screen.blit(g, (exx - g.get_width() // 2 + ox, eyy - g.get_height() // 2 + oy), special_flags=ADD)

        # ── Armure magique: rune qui tourne ──
        for sh in ve.get('armor_shimmers', ()):
            if not sh.is_visible():
                continue
            p = sh.get_progress()
            x, y = sh.center_pos
            frames = S.rune_shield_frames(sh.radius_px + 6)
            img = frames[(sh.age // 2) % len(frames)]
            img.set_alpha(int(255 * (1.0 - p)))
            screen.blit(img, (x - img.get_width() / 2 + ox, y - img.get_height() / 2 + oy))
            g = S.glow(sh.radius_px + 8, (80, 160, 255), int(4 * (1 - p)))
            screen.blit(g, (x - g.get_width() // 2 + ox, y - g.get_height() // 2 + oy), special_flags=ADD)

        # ── Mur de force: blocs qui surgissent du sol ──
        for wl in ve.get('wall_effects', ()):
            if not wl.is_visible():
                continue
            p = wl.get_progress()
            rise = min(1.0, p / 0.4)
            for (wx, wy) in wl.positions:
                px, py = wx * cs + ox, wy * cs + oy
                hgt = int(cs * rise)
                pygame.draw.rect(screen, (118, 104, 140), (px + 2, py + cs - hgt, cs - 4, hgt))
                pygame.draw.rect(screen, (70, 58, 95), (px + 2, py + cs - hgt, cs - 4, hgt), 1)
                g = S.glow(int(cs * 0.6), (170, 90, 255), int(6 * (1 - p)))
                screen.blit(g, (px + cs // 2 - g.get_width() // 2, py + cs // 2 - g.get_height() // 2), special_flags=ADD)

        self._draw_particles(screen, ox, oy, vx0, vy0, vx1, vy1)

        # ── Derniers mots des tombés (dégâts du coup fatal) ──
        if self.font is not None and cs >= 16:
            for d in ve.get('deaths', ()):
                x, y = d.to_pos
                oy_t = -cs * 0.6
                for ft in d.texts:
                    if not ft.is_visible():
                        continue
                    pr = ft.get_progress()
                    ts = self.font.render(ft.text, True, ft.color)
                    ts.set_alpha(255 - int(255 * pr))
                    screen.blit(ts, (x - ts.get_width() // 2 + ox,
                                     y + oy_t - int(pr * ft.duration / 4) + oy))
                    oy_t -= 10

    def _draw_particles(self, screen, ox, oy, vx0, vy0, vx1, vy1):
        for pt in self.particles:
            x, y = pt[PX], pt[PY]
            if not (vx0 < x < vx1 and vy0 < y < vy1):
                continue
            life = pt[LIFE] / pt[MAXL]
            kind = pt[KIND]
            sx, sy = x + ox, y + oy
            col = pt[COL]
            if kind == 'spark':
                ex, ey = sx - pt[VX] * 2.5, sy - pt[VY] * 2.5
                c = (int(col[0] * (0.4 + 0.6 * life)), int(col[1] * (0.4 + 0.6 * life)),
                     int(col[2] * (0.3 + 0.7 * life)))
                pygame.draw.line(screen, c, (sx, sy), (ex, ey), 2 if life > 0.5 else 1)
            elif kind in ('ember', 'magic'):
                g = S.glow(max(2, int(pt[SIZE] * (0.6 + life))), col, int(8 * life))
                screen.blit(g, (sx - g.get_width() // 2, sy - g.get_height() // 2), special_flags=ADD)
            elif kind in ('smoke', 'dust'):
                r = int(pt[SIZE] * (1.0 + (1.0 - life) * 1.2)) // 2 * 2 + 2
                peak = 70 if kind == 'smoke' else 95
                blob = S.soft_blob(r, col, int(peak * life))
                screen.blit(blob, (sx - r, sy - r))
            elif kind == 'blood':
                pygame.draw.circle(screen, col, (int(sx), int(sy)), max(1, int(pt[SIZE])))
            elif kind == 'debris':
                sz = max(1, int(pt[SIZE]))
                pygame.draw.rect(screen, col, (sx, sy, sz, sz))
            elif kind == 'heal':
                img = S.plus_sprite(int(pt[SIZE]), col)
                img.set_alpha(int(255 * min(1.0, life * 1.6)))
                screen.blit(img, (sx - img.get_width() // 2, sy - img.get_height() // 2))

    # ───────────────────────── écran ─────────────────────────

    def draw_screen(self, screen, view_w, view_h):
        screen.blit(S.vignette(view_w, view_h), (0, 0))
