"""Plan de bataille — la couche STRATÉGIQUE du commandant IA.

Le CommanderAI décide round par round (posture, manœuvres opportunistes,
couloirs). Ce module lui donne une intention qui DURE: un plan choisi au
début de la bataille, joué en phases sur plusieurs rounds, abandonné s'il
échoue, et lisible à l'écran (flèches, zones, bannières).

Plans:
  • marteau  — Enclume et marteau: le centre accroche l'ennemi, un
               détachement rapide contourne un flanc puis frappe ses arrières
  • feinte   — deux leurres attaquent une aile; le corps principal attend
               que l'ennemi s'y porte, puis frappe l'autre aile
  • oblique  — ordre oblique: l'aile forte engage, l'aile refusée se tient en
               retrait jusqu'à ce que le choc ait eu lieu
  • colline  — les tireurs prennent une colline, la mêlée tient devant, on
               contre-attaque quand l'ennemi arrive au pied — ou dès qu'il
               refuse de venir (deux armées retranchées ne se battent pas)
  • direct   — pas de manœuvre (petite armée, ou plan abandonné)
Pas de réserve: toute l'armée marche au combat. Les phases d'attente sont
courtes — l'IA doit rester agressive.

Module pur (sans Pygame). Les ordres sont rendus sous forme de tuples
(type, unité cible, position cible, priorité) que CommanderAI convertit en
TacticalOrder — ce qui évite une dépendance circulaire.
"""

import terrain as tr
import tactics

NAMES = {
    "marteau": "Enclume et marteau",
    "feinte": "Feinte",
    "oblique": "Ordre oblique",
    "colline": "Tenir la colline",
    "direct": "Assaut direct",
}
PHASE_NAMES = {
    "approche": "approche", "frappe": "frappe",
    "feinte": "feinte", "assaut": "assaut",
    "refus": "aile refusée", "engagement": "engagement",
    "prise": "prise", "tenue": "tenue", "contre": "contre-attaque",
    "": "",
}
_EVENT_COLOR = (240, 210, 140)


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _center(units):
    if not units:
        return (0.0, 0.0)
    return (sum(u.position[0] for u in units) / len(units),
            sum(u.position[1] for u in units) / len(units))


def _is_melee(u):
    return (u._max_range < 4 and not u.spells and u.vitesse > 0
            and u.encouragement_range == 0 and not getattr(u, 'is_artillery', False))


def _soft(e):
    """Cible d'arrière: tireur, mage, machine ou officier."""
    return (e._max_range >= 4 or bool(e.spells) or getattr(e, 'is_artillery', False)
            or e.encouragement_range > 0)


class BattlePlan:
    def __init__(self):
        self.kind = None
        self.phase = ""
        self.roles = {}              # id(unit) -> rôle
        self.events = []             # (texte, couleur) à annoncer ce round
        self.suspended = False
        self.rounds = 0              # rounds dans la phase courante
        self.total_rounds = 0
        self.side = 1                # flanc du marteau / aile forte / aile B (perpendiculaire)
        self.lane_bias = (0.0, 0.0)  # décalage du centre des couloirs (cases)
        self.points = {}             # points nommés (grille) pour ordres et rendu
        self.hill_slots = {}         # id(unit) -> case assignée (colline)
        self._arrived = set()
        self._engaged_streak = 0
        self._hurting_streak = 0
        self._enemy_lat0 = 0.0
        self._enemy_proj0 = None
        self._geo = None

    # ─── Lecture ───

    def active(self):
        return self.kind not in (None, "direct") and not self.suspended

    def has_hammer(self):
        return self.kind == "marteau" and not self.suspended

    def label(self):
        if self.kind is None:
            return ""
        ph = PHASE_NAMES.get(self.phase, self.phase)
        return NAMES[self.kind] + (f" · {ph}" if ph else "")

    def pop_events(self):
        ev, self.events = self.events, []
        return ev

    # ─── Géométrie ───

    def _frame(self, cmd, enemies):
        ax, ay = cmd._axis
        px, py = -ay, ax
        ec = _center(enemies)
        lats = [(e.position[0] - ec[0]) * px + (e.position[1] - ec[1]) * py for e in enemies]
        half = (max(lats) - min(lats)) / 2.0 if lats else 3.0
        self._geo = (ax, ay, px, py, ec, max(3.0, half))
        return self._geo

    def _lat(self, pos):
        ax, ay, px, py, ec, _ = self._geo
        return (pos[0] - ec[0]) * px + (pos[1] - ec[1]) * py

    def _point(self, cmd, lat, depth):
        """Point à `lat` cases latéralement du centre ennemi et `depth` cases
        au-delà (depth > 0: derrière la ligne ennemie)."""
        ax, ay, px, py, ec, _ = self._geo
        return cmd._clamp_pos(ec[0] + px * lat + ax * depth, ec[1] + py * lat + ay * depth)

    def _weaker_side(self, cmd, enemies):
        """Flanc (+1 / -1) où l'ennemi aligne le moins de valeur. À égalité,
        tirage: un départage fixe servirait toujours le même côté de la carte."""
        pos = sum(tactics.remaining_value(e) for e in enemies if self._lat(e.position) > 0.5)
        neg = sum(tactics.remaining_value(e) for e in enemies if self._lat(e.position) < -0.5)
        if abs(pos - neg) < 1e-6:
            return 1 if cmd.rng.random() < 0.5 else -1
        return 1 if pos < neg else -1

    def _enemy_lat(self, enemies):
        ax, ay, px, py, _, _ = self._geo
        return sum(e.position[0] * px + e.position[1] * py for e in enemies) / max(1, len(enemies))

    # ─── Choix du plan ───

    def _find_hill(self, cmd, alive, enemies):
        """Colline objectif: plus proche de nous que de l'ennemi, au contact de
        plusieurs cases de colline, pas trop loin de notre armée."""
        bf = cmd.battlefield
        terr = getattr(bf, 'terrain', None)
        if terr is None:
            return None
        mc, ec = _center(alive), _center(enemies)
        best, best_score = None, None
        for x in range(1, bf.width - 1):
            col = terr[x]
            for y in range(1, bf.height - 1):
                if col[y] != tr.HILL or bf.grid[x][y] != 0:
                    continue
                dm, de = _dist((x, y), mc), _dist((x, y), ec)
                if dm >= de or dm > 26:
                    continue
                mass = sum(1 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                           if 0 <= x + dx < bf.width and 0 <= y + dy < bf.height
                           and terr[x + dx][y + dy] == tr.HILL)
                if mass < 5:
                    continue
                score = dm - mass * 0.8 + abs(de - 14) * 0.3
                if best_score is None or score < best_score:
                    best, best_score = (x, y), score
        return best

    def _flank_is_open(self, cmd, alive, enemies):
        """Le contournement est-il praticable ? On échantillonne le trajet de
        notre centre vers les deux points d'attente possibles: au-delà d'un
        quart de bois, marais, eau ou obstacles, le marteau arriverait trop
        tard (mesuré: 33 % de victoires en Forêt contre 56 % en Prairie)."""
        bf = cmd.battlefield
        terr = getattr(bf, 'terrain', None)
        mc = _center(alive)
        half = self._geo[5]
        for side in (1, -1):
            wp = self._point(cmd, side * (half + 7), -5)
            bad = n = 0
            for k in range(1, 21):
                x = int(round(mc[0] + (wp[0] - mc[0]) * k / 20))
                y = int(round(mc[1] + (wp[1] - mc[1]) * k / 20))
                n += 1
                if bf.grid[x][y] != 0 or (terr is not None and terr[x][y] in (tr.WOOD, tr.MARSH, tr.RIVER, tr.FORD)):
                    bad += 1
            if bad * 4 <= n:
                return True
        return False

    def _contact_zone_is_close(self, cmd, alive, enemies):
        """Terrain boisé entre les deux armées ? En sous-bois on ne manœuvre
        pas: les détachements s'y perdent et arrivent en ordre dispersé
        (mesuré en Forêt: assaut direct 60 %, manœuvres 33 à 46 %).

        Critère: part de cases de bois dans la bande qui sépare nos fronts.
        Mesurée sur 60×40: Forêt 8 à 25 %, Village 1 à 2 %, Prairie et
        Défilé 0 % — le seuil de 5 % les sépare nettement."""
        bf = cmd.battlefield
        terr = getattr(bf, 'terrain', None)
        if terr is None:
            return False
        our_front = max(cmd._proj(u.position) for u in alive)
        their_front = min(cmd._proj(e.position) for e in enemies)
        if their_front - our_front < 4:
            return False
        xs = [u.position[0] for u in alive] + [e.position[0] for e in enemies]
        ys = [u.position[1] for u in alive] + [e.position[1] for e in enemies]
        wood = n = 0
        for x in range(max(0, min(xs)), min(bf.width, max(xs) + 1)):
            col = terr[x]
            for y in range(max(0, min(ys) - 4), min(bf.height, max(ys) + 5)):
                pr = cmd._proj((x, y))
                if our_front + 2 <= pr <= their_front - 2:
                    n += 1
                    wood += col[y] == tr.WOOD
        return n > 0 and wood * 20 >= n

    def choose(self, cmd, alive, enemies, s):
        melee = [u for u in alive if _is_melee(u)]
        # La cavalerie de mêlée seule fait le marteau: une cavalerie armée de
        # javelots intercepte déjà les tireurs d'elle-même (_cav_order), et la
        # figer à un point d'attente lui coûtait l'initiative (30 % de
        # victoires contre 45 % sans plan).
        fast = [u for u in melee if u.vitesse >= 6]
        scores = {}
        closed = self._contact_zone_is_close(cmd, alive, enemies)
        # Dominés au tir: manœuvrer sous les traits est un luxe. Assaut direct.
        outgunned = s['en_ranged'] > 1.0 and s['my_ranged'] < s['en_ranged'] * 0.6
        if len(alive) >= 6 and not closed and not outgunned:
            if (len(fast) >= 2 or len(melee) >= 8) and self._flank_is_open(cmd, alive, enemies):
                scores["marteau"] = 0.8 + 0.3 * min(3, len(fast)) + 0.3 * cmd.aggression + 0.3 * cmd.ruse
            if len(melee) >= 6:
                scores["feinte"] = 0.2 + 0.7 * cmd.ruse
                scores["oblique"] = 0.4 + 0.5 * cmd.prudence + (0.4 if s['ratio'] < 1.0 else 0.0)
        if len(alive) >= 6 and len(s['my_ranged_units']) >= 2 and not outgunned:
            hill = self._find_hill(cmd, alive, enemies)
            if hill is not None:
                self.points['colline'] = hill
                scores["colline"] = (0.5 + 0.5 * cmd.patience
                                     + (0.5 if s['my_ranged'] > s['en_ranged'] else 0.0))
        scores["direct"] = 0.35 if scores else 1.0
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        pick = ranked[0][0]
        if len(ranked) > 1 and cmd.rng.random() >= 2.0 / 3.0:
            pick = ranked[1][0]
        self._start(pick, cmd, alive, enemies)

    def _start(self, kind, cmd, alive, enemies, announce=True):
        self.kind = kind
        self.rounds = 0
        self.roles = {}
        self._arrived = set()
        self._engaged_streak = 0
        self.lane_bias = (0.0, 0.0)
        self.hill_slots = {}
        free = sorted((u for u in alive if _is_melee(u)), key=lambda u: u.uid)

        if kind == "marteau":
            self.side = self._weaker_side(cmd, enemies)
            fast = [u for u in free if u.vitesse >= 6]
            hammer = fast if len(fast) >= 2 else sorted(
                free, key=lambda u: (-u.vitesse, u.uid))[:max(2, int(len(free) * 0.3))]
            if len([u for u in free if u not in hammer]) < 3:
                return self._start("direct", cmd, alive, enemies, announce)
            for u in hammer:
                self.roles[id(u)] = "hammer"
            self.phase = "approche"
        elif kind == "feinte":
            self.side = self._weaker_side(cmd, enemies)      # aile B: frappe principale
            lures = sorted(free, key=lambda u: (tactics.unit_value(u), u.uid))[:2]
            for u in lures:
                self.roles[id(u)] = "lure"
            self._enemy_lat0 = self._enemy_lat(enemies)
            self.phase = "feinte"
        elif kind == "oblique":
            # Concentration: la masse se porte sur l'aile où l'ennemi est le
            # plus faible; une petite aile refusée (le quart le moins précieux,
            # du côté opposé) fixe l'autre aile sans s'y user.
            self.side = self._weaker_side(cmd, enemies)
            far = sorted((u for u in free if self._lat(u.position) * self.side < 0),
                         key=lambda u: (tactics.unit_value(u), u.uid))
            for u in far[:max(1, len(free) // 4)]:
                self.roles[id(u)] = "refused"
            if not any(r == "refused" for r in self.roles.values()):
                return self._start("direct", cmd, alive, enemies, announce)
            self.phase = "refus"
        elif kind == "colline":
            hill = self.points.get('colline') or self._find_hill(cmd, alive, enemies)
            if hill is None:
                return self._start("direct", cmd, alive, enemies, announce)
            self.points['colline'] = hill
            self._assign_hill_slots(cmd, alive, hill)
            self.phase = "prise"
        else:
            self.phase = ""
        if announce:
            self.events.append((f"plan « {NAMES[kind]} »", _EVENT_COLOR))

    def _assign_hill_slots(self, cmd, alive, hill):
        bf = cmd.battlefield
        cells = sorted(((x, y) for x in range(hill[0] - 4, hill[0] + 5)
                        for y in range(hill[1] - 4, hill[1] + 5)
                        if 0 < x < bf.width - 1 and 0 < y < bf.height - 1
                        and bf.terrain[x][y] == tr.HILL and bf.grid[x][y] == 0),
                       key=lambda c: (_dist(c, hill), c))
        shooters = sorted((u for u in alive
                           if u._max_range >= 4 and not getattr(u, 'is_artillery', False)),
                          key=lambda u: u.uid)
        for u, c in zip(shooters, cells):
            self.roles[id(u)] = "hill"
            self.hill_slots[id(u)] = c

    # ─── Mise à jour par round ───

    def update(self, cmd, alive, enemies, s):
        if not alive or not enemies:
            return
        self._frame(cmd, enemies)
        if cmd.posture == "exploit":
            if self.kind not in (None, "direct"):
                self.kind, self.phase, self.roles = "direct", "", {}
                self.lane_bias = (0.0, 0.0)
            self.suspended = True
            return
        # Charge générale (aucun tir face à des tireurs): chaque round d'attente
        # coûte des hommes; les plans qui temporisent sont suspendus (mesuré:
        # une armée de mêlée face à des arbalétriers tombait de 70 % à 55 %).
        if cmd.posture in ("regroup", "screen", "rush"):
            self.suspended = True
            return
        self.suspended = False
        if self.kind is None:
            self.choose(cmd, alive, enemies, s)
        self.rounds += 1
        self.total_rounds += 1
        ids = {id(u) for u in alive}
        self.roles = {k: v for k, v in self.roles.items() if k in ids}
        self.hill_slots = {k: v for k, v in self.hill_slots.items() if k in ids}

        by_role = {}
        for u in alive:
            by_role.setdefault(self.roles.get(id(u)), []).append(u)
        melee_main = [u for u in by_role.get(None, []) if _is_melee(u)]

        getattr(self, '_update_' + self.kind)(cmd, alive, enemies, s, by_role, melee_main)

    def _in_contact(self, units, enemies, reach=2):
        if not units:
            return 0.0
        n = sum(1 for u in units if any(_dist(u.position, e.position) <= reach for e in enemies))
        return n / len(units)

    def _set_phase(self, phase, text=None):
        self.phase = phase
        self.rounds = 0
        if text:
            self.events.append((text, _EVENT_COLOR))

    def _update_direct(self, cmd, alive, enemies, s, by_role, melee_main):
        pass

    def _update_marteau(self, cmd, alive, enemies, s, by_role, melee_main):
        hammer = by_role.get("hammer", [])
        if not hammer:
            self.events.append(("le marteau est brisé, assaut direct", _EVENT_COLOR))
            self._start("direct", cmd, alive, enemies, announce=False)
            return
        half = self._geo[5]
        self.points['attente'] = self._point(cmd, self.side * (half + 7), -5)
        self.points['revers'] = self._point(cmd, self.side * (half + 2), 4)
        if self.phase == "approche":
            anvil_contact = self._in_contact(melee_main, enemies)
            ready = sum(1 for u in hammer if _dist(u.position, self.points['attente']) <= 4) * 2 >= len(hammer)
            if (anvil_contact >= 0.4 and (ready or self.rounds >= 2)) or self.rounds >= 7:
                self._set_phase("frappe", "le marteau frappe !")
        for u in hammer:
            if _dist(u.position, self.points['revers']) <= 4:
                self._arrived.add(id(u))

    def _update_feinte(self, cmd, alive, enemies, s, by_role, melee_main):
        lures = by_role.get("lure", [])
        side_a = -self.side
        self.points['leurre'] = self._point(cmd, side_a * (self._geo[5] + 2), -5)
        self.points['assaut'] = self._point(cmd, self.side * self._geo[5] * 0.6, 0)
        ax, ay, px, py, _, half = self._geo
        # Le corps principal se masse d'emblée face à l'aile B pendant que les
        # leurres se montrent sur l'aile A.
        push = min(6.0, half * 0.6)
        self.lane_bias = (px * self.side * push, py * self.side * push)
        if self.phase == "feinte":
            shift = (self._enemy_lat(enemies) - self._enemy_lat0) * side_a
            if (shift >= 2.0 or self.rounds >= 3 or not lures
                    or self._in_contact(melee_main, enemies, 3) > 0):
                self._set_phase("assaut", "assaut principal sur l'autre aile !")
                self.roles = {k: v for k, v in self.roles.items() if v != "lure"}

    def _update_oblique(self, cmd, alive, enemies, s, by_role, melee_main):
        ax, ay, px, py, _, half = self._geo
        push = min(6.0, half * 0.6)
        self.lane_bias = (px * self.side * push, py * self.side * push)
        self.points['aile'] = self._point(cmd, self.side * half * 0.7, 0)
        if self.phase == "refus":
            if self._in_contact(melee_main, enemies) >= 0.4:
                self._engaged_streak += 1
            else:
                self._engaged_streak = 0
            if self._engaged_streak >= 1 or self.rounds >= 4 or not melee_main:
                self._set_phase("engagement", "l'aile refusée entre dans la bataille")
                self.roles = {k: v for k, v in self.roles.items() if v != "refused"}

    def _update_colline(self, cmd, alive, enemies, s, by_role, melee_main):
        hill = self.points['colline']
        holders = by_role.get("hill", [])
        if self.phase == "prise":
            on = sum(1 for u in holders if _dist(u.position, self.hill_slots[id(u)]) <= 1)
            if not holders or on * 10 >= len(holders) * 6 or self.rounds >= 3:
                self._set_phase("tenue", "tient la colline")
                self._enemy_proj0 = self._enemy_front(cmd, enemies)
        elif self.phase == "tenue":
            foes = [e for e in enemies if e._max_range < 4 and _dist(e.position, hill) <= 7]
            if s['bleeding'] > s['hurting_them'] + 0.05:
                self._hurting_streak += 1
            else:
                self._hurting_streak = 0
            # L'ennemi refuse de venir (il tient lui aussi sa hauteur): on ne
            # le regarde pas pendant dix rounds, on va le chercher.
            stalled = (self.rounds >= 1 and self._enemy_proj0 is not None
                       and self._enemy_front(cmd, enemies) >= self._enemy_proj0 - 1.5)
            if foes or stalled or self._hurting_streak >= 2 or self.rounds >= 3:
                self._set_phase("contre", "contre-attaque depuis la colline !")
                self.roles = {}
                self.hill_slots = {}

    def _enemy_front(self, cmd, enemies):
        """Projection, sur notre axe, de l'ennemi le plus proche de nous
        (plus petit = plus proche)."""
        return min(cmd._proj(e.position) for e in enemies)

    # ─── Ordres ───

    def order_for(self, cmd, unit, enemies):
        """(type, unité, position, priorité) ou None (logique par défaut)."""
        if not self.active() or not enemies or self._geo is None:
            return None
        role = self.roles.get(id(unit))
        up = unit.position
        if role == "hammer":
            if self.phase == "approche":
                return ("support", None, self.points['attente'], 5)
            if id(unit) in self._arrived:
                soft = [e for e in enemies if _soft(e)] or enemies
                t = min(soft, key=lambda e: (_dist(e.position, up), e.uid))
                return ("attack", t, None, 6)
            return ("flank", None, self.points['revers'], 6)
        if role == "lure":
            # Démonstration: se montrer sur l'aile A à distance de charge,
            # sans aller mourir seuls au contact (mesuré: des leurres qui
            # chargeaient faisaient perdre la bataille 3 fois sur 4).
            if self.phase != "feinte" or any(_dist(up, e.position) <= 2 for e in enemies):
                return None
            return ("support", None, self.points['leurre'], 5)
        if role == "refused" and self.phase == "refus":
            strong = [u for u in cmd.army
                      if u.is_alive and _is_melee(u) and self.roles.get(id(u)) is None]
            if not strong:
                return None
            if any(_dist(up, e.position) <= 5 for e in enemies):
                return None  # menacée: on ne se laisse pas prendre en détail
            front = max(cmd._proj(u.position) for u in strong) - 2
            proj_u = cmd._proj(up)
            if proj_u > front:
                ax, ay = cmd._axis
                return ("support", None, cmd._clamp_pos(up[0] - ax * (proj_u - front),
                                                         up[1] - ay * (proj_u - front)), 4)
            return ("hold", None, up, 3)
        if role == "hill":
            slot = self.hill_slots.get(id(unit))
            if slot is None:
                return None
            if _dist(up, slot) > 1:
                return ("support", None, slot, 5)
            return ("hold", None, slot, 4)
        if role is None and _is_melee(unit):
            if self.kind == "colline" and self.phase in ("prise", "tenue"):
                if any(_dist(up, e.position) <= 2 for e in enemies):
                    return None
                hill = self.points['colline']
                ax, ay = cmd._axis
                px, py = -ay, ax
                lat = max(-5.0, min(5.0, self._lat(up) - self._lat(hill)))
                post = cmd._clamp_pos(hill[0] + ax * 3 + px * lat, hill[1] + ay * 3 + py * lat)
                if _dist(up, post) > 1:
                    return ("support", None, post, 3)
                return ("hold", None, post, 3)
        return None

    # ─── Rendu ───

    def intents(self, cmd):
        """Ce que le plan cherche à faire, en coordonnées de grille:
        [{'type': 'arrow'|'zone'|'flag', ...}]."""
        out = []
        if self.kind in (None, "direct") or self.suspended or self._geo is None:
            return out
        alive = [u for u in cmd.army if u.is_alive and not u.fleeing]

        def group(role):
            return [u for u in alive if self.roles.get(id(u)) == role]

        if self.kind == "marteau":
            hammer = group("hammer")
            if hammer:
                hc = _center(hammer)
                if self.phase == "approche":
                    out.append({'type': 'arrow', 'points': [hc, self.points['attente']],
                                'label': "marteau"})
                else:
                    out.append({'type': 'arrow', 'points': [hc, self.points['revers']],
                                'label': "le marteau frappe"})
        elif self.kind == "feinte":
            lures = group("lure")
            if lures and self.phase == "feinte":
                out.append({'type': 'arrow', 'points': [_center(lures), self.points['leurre']],
                            'label': "feinte"})
            main = [u for u in alive if self.roles.get(id(u)) is None and _is_melee(u)]
            if main and self.phase == "assaut":
                out.append({'type': 'arrow', 'points': [_center(main), self.points['assaut']],
                            'label': "assaut"})
        elif self.kind == "oblique":
            strong = [u for u in alive if self.roles.get(id(u)) is None and _is_melee(u)]
            if strong:
                out.append({'type': 'arrow', 'points': [_center(strong), self.points['aile']],
                            'label': "aile forte"})
            refused = group("refused")
            if refused:
                out.append({'type': 'zone', 'center': _center(refused), 'radius': 3.0,
                            'label': "aile refusée"})
        elif self.kind == "colline" and self.phase in ("prise", "tenue"):
            out.append({'type': 'flag', 'pos': self.points['colline'], 'label': "colline"})
        return out
