"""Plan de siège — la couche STRATÉGIQUE du commandant IA sur une carte de
siège (Siège, Citadelle). Pendant de battle_plan.py, même interface: en
siège, CommanderAI.plan est un SiegePlan (bannières, bandeau, touche I).

Offensive (armée 1), un plan choisi au premier round selon l'armée:
  • engins     — Assaut coordonné: la mêlée marche en colonne derrière
                 l'engin le plus avancé, les tireurs sur son flanc; assaut
                 quand un engin touche au but. (Attendre hors de portée a
                 été mesuré: toute la garnison tirait alors sur le bélier et
                 ses pousseurs — bélier au Siège niveau 2: 17 % → 3 %.)
  • pilonnage  — les machines de tir percent pendant que tout le monde
                 attend hors de portée; assaut à la brèche (ou au bout de
                 BOMBARD_MAX rounds, ou si l'on perd l'échange)
  • feinte     — Citadelle: deux leurres se montrent devant la porte
                 secondaire, le corps principal attend puis frappe l'autre
  • direct     — pas de temporisation (comportement de base du commandant)

Défensive (armée 2), plan « defense »: la phase est la MENACE du moment
(brèche, bélier, tour, porte pressée). La mêlée hors rempart forme une
réserve mobile postée juste derrière le point menacé (ou sur le chemin de
ronde, à la sortie de la passerelle d'une tour); les tireurs visent ceux
qui font avancer les engins.

Module pur (sans Pygame). Les ordres sont des tuples (type, unité cible,
position cible, priorité), comme battle_plan.
Spec: docs/superpowers/specs/2026-09-21-strategies-siege-design.md
"""

import siege_engines as se
from maps.fortification import _gate_groups

NAMES = {
    "engins": "Assaut coordonné",
    "pilonnage": "Pilonnage",
    "feinte": "Feinte sur une porte",
    "direct": "Assaut direct",
    "defense": "Défense des murs",
}
PHASE_NAMES = {
    "approche": "approche des engins", "bombardement": "bombardement",
    "feinte": "feinte", "assaut": "assaut",
    "murs": "tenir les murs", "porte": "réserve à la porte",
    "tour": "face à la tour", "breche": "tenir la brèche",
    "": "",
}
_EVENT_COLOR = (240, 210, 140)

# Réglages (rounds, cases)
ENGINE_ASSAULT_DIST = 6     # un engin à ≤ N cases de son but: l'infanterie part
BOMBARD_MAX = 5             # rounds de bombardement au plus
FEINT_ROUNDS = 3            # rounds de feinte une fois les leurres en place
FEINT_MAX = 12              # la feinte ne dure pas plus
LURES = 2
# Assaut coordonné: la mêlée escorte les engins (sinon: attente hors de portée)
ESCORT_ENGINES = True
STAGING_MARGIN = 2          # cases de marge hors de portée du rempart
ENGINE_WALL_WATCH = 12      # la garnison guette les engins à ≤ N cases du mur
TOWER_WATCH = 8             # une tour à ≤ N cases de son poste: la réserve y monte


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _center(units):
    if not units:
        return (0.0, 0.0)
    return (sum(u.position[0] for u in units) / len(units),
            sum(u.position[1] for u in units) / len(units))


def _staff(u):
    """Machine, artilleur, ou servant affecté: ils ont leur propre logique."""
    return se.is_machine(u) or se.is_crew(u) or getattr(u, '_attends', None) is not None


def _is_melee(u):
    """Mêlée qui manœuvre (officiers compris: ils suivent leurs hommes)."""
    return u._max_range < 4 and not u.spells and u.vitesse > 0 and not _staff(u)


def _is_shooter(u):
    return (u._max_range >= 4 or bool(u.spells)) and u.vitesse > 0 and not _staff(u)


class SiegePlan:
    def __init__(self, attacker):
        self.attacker = attacker
        self.kind = None if attacker else "defense"
        self.phase = "" if attacker else "murs"
        self.roles = {}              # id(unit) -> rôle ("lure")
        self.events = []
        self.suspended = False
        self.rounds = 0              # rounds dans la phase courante
        self.total_rounds = 0
        self.lane_bias = (0.0, 0.0)  # (interface BattlePlan)
        self.points = {}             # points nommés (grille) pour ordres et rendu
        self.staging_x = None
        self.threat_rows = []        # défense: rangées du point menacé
        self._lures_in_place = 0

    # ─── Lecture (interface BattlePlan) ───

    def active(self):
        return self.kind not in (None, "direct") and not self.suspended

    def has_hammer(self):
        return False

    def label(self):
        if self.kind is None:
            return ""
        ph = PHASE_NAMES.get(self.phase, self.phase)
        return NAMES[self.kind] + (f" · {ph}" if ph else "")

    def pop_events(self):
        ev, self.events = self.events, []
        return ev

    def _set_phase(self, phase, text=None):
        if phase != self.phase:
            self.phase = phase
            self.rounds = 0
            if text:
                self.events.append((text, _EVENT_COLOR))

    # ─── Mise à jour ───

    def update(self, cmd, alive, enemies, s):
        if not alive or not enemies or not cmd.battlefield.is_siege:
            return
        self.rounds += 1
        self.total_rounds += 1
        ids = {id(u) for u in alive}
        self.roles = {k: v for k, v in self.roles.items() if k in ids}
        if self.attacker:
            self._update_attack(cmd, alive, enemies, s)
        else:
            self._update_defense(cmd, alive, enemies)

    # ═══════════════════════ OFFENSIVE ═══════════════════════

    def _staging(self, cmd, enemies):
        """Colonne de la ligne d'attente: hors de portée des tireurs du mur."""
        bf = cmd.battlefield
        reach = max((e._max_range for e in enemies if e._max_range >= 4), default=0)
        return max(2, bf.wall_x - reach - STAGING_MARGIN)

    def _gate_rows(self, cmd):
        """(x, rangée centrale) de chaque porte (battant) de l'enceinte active."""
        groups = _gate_groups(list(cmd.battlefield.active_gates))
        return [(g[0][0], (g[0][1] + g[-1][1]) // 2) for g in groups]

    def _assault_row(self, cmd, alive):
        gate = getattr(cmd, 'assault_gate', None)
        if gate is not None:
            return gate[1]
        rows = self._gate_rows(cmd)
        if not rows:
            return cmd.battlefield.height // 2
        mc = _center(alive)
        return min(rows, key=lambda g: (abs(g[1] - mc[1]), g))[1]

    def _choose_attack(self, cmd, alive):
        engines = [u for u in alive if se.is_engine(u)]
        guns = [u for u in alive if se.needs_crew(u)]
        melee = [u for u in alive if _is_melee(u) and u.encouragement_range <= 0]
        if engines:
            kind, phase, text = "engins", "approche", "assaut coordonné: l'infanterie escorte ses engins"
        elif guns:
            kind, phase, text = "pilonnage", "bombardement", "pilonnage: les machines d'abord"
        elif len(self._gate_rows(cmd)) >= 2 and len(melee) >= 6:
            kind, phase, text = "feinte", "feinte", "feinte sur la porte secondaire"
            for u in sorted(melee, key=lambda u: u.uid)[:LURES]:
                self.roles[id(u)] = "lure"
        else:
            kind, phase, text = "direct", "assaut", None
        self.kind = kind
        self._set_phase(phase, text)
        self.rounds = 1

    def _update_attack(self, cmd, alive, enemies, s):
        bf = cmd.battlefield
        if self.kind is None:
            self._choose_attack(cmd, alive)
        self.staging_x = self._staging(cmd, enemies)
        row = self._assault_row(cmd, alive)
        self.points['attente'] = (self.staging_x, row)
        self.points['assaut'] = (bf.wall_x, row)
        if self.phase == "assaut" or self.kind == "direct":
            return
        if cmd.posture == "exploit":
            self._set_phase("assaut", "la garnison s'effondre: à l'assaut !")
            return
        # Ce qui déclenche l'assaut dans tous les plans: un passage ouvert,
        # ou l'échange de tir qu'on perd en attendant
        opened = se.passage_open(bf)
        losing = (s.get('bleeding', 0.0) > s.get('hurting_them', 0.0) + 0.05
                  and self.rounds >= 2)
        if self.kind == "engins":
            engines = [u for u in alive if se.is_engine(u) and not u.docked]
            close = any(self._engine_left(bf, u) <= ENGINE_ASSAULT_DIST for u in engines)
            if opened or close or not engines:
                self._set_phase("assaut", "les engins touchent au but: à l'assaut !")
        elif self.kind == "pilonnage":
            if opened or self.rounds >= BOMBARD_MAX or losing:
                self._set_phase("assaut", "fin du bombardement: à l'assaut !")
        elif self.kind == "feinte":
            lures = [u for u in alive if self.roles.get(id(u)) == "lure"]
            spot = self._lure_spot(cmd, row)
            self.points['leurre'] = spot
            if spot is not None and lures and all(_dist(u.position, spot) <= 4 for u in lures):
                self._lures_in_place += 1
            if (opened or not lures or spot is None or losing
                    or self._lures_in_place >= FEINT_ROUNDS or self.rounds >= FEINT_MAX):
                self._set_phase("assaut", "assaut sur l'autre porte !")

    @staticmethod
    def _engine_left(bf, u):
        """Cases qu'il reste à l'engin avant son but (0 s'il y est)."""
        goal = se.engine_goal(bf, u)
        if goal is None:
            return 0
        return _dist(u.position, goal)

    def _lure_spot(self, cmd, assault_row):
        """Devant la porte secondaire, à portée du rempart (on se montre)."""
        rows = [g for g in self._gate_rows(cmd) if abs(g[1] - assault_row) > 3]
        if not rows:
            return None
        gx, gy = min(rows, key=lambda g: (abs(g[1] - assault_row), g))
        return cmd._clamp_pos(gx - 4, gy)

    def _attack_order(self, cmd, unit, enemies):
        if self.kind in (None, "direct") or self.phase == "assaut" or _staff(unit):
            return None
        up = unit.position
        if any(_dist(up, e.position) <= 2 for e in enemies):
            return None                          # au contact: on se bat
        if self.roles.get(id(unit)) == "lure":
            spot = self.points.get('leurre')
            if spot is None:
                return None
            return ("support", None, spot, 5) if _dist(up, spot) > 1 else ("hold", None, spot, 5)
        bf = cmd.battlefield
        if self.kind == "engins" and _is_shooter(unit):
            # Escorte: à hauteur de l'engin le plus en retard, sur son flanc
            engines = [u for u in cmd.army if u.is_alive and se.is_engine(u) and not u.docked]
            if engines:
                eng = max(engines, key=lambda u: (self._engine_left(bf, u), u.uid))
                ex, ey = eng.position
                side = 1 if up[1] >= ey else -1
                post = cmd._clamp_pos(ex - 1, ey + side * 3)
                return ("support", None, post, 4) if _dist(up, post) > 2 else None
        if self.kind == "engins" and _is_melee(unit) and ESCORT_ENGINES:
            # Colonne d'assaut: la mêlée marche derrière l'engin le plus
            # avancé (elle partage le feu avec lui et arrive en même temps)
            engines = [u for u in cmd.army if u.is_alive and se.is_engine(u) and not u.docked]
            if engines:
                eng = min(engines, key=lambda u: (self._engine_left(bf, u), u.uid))
                ex, ey = eng.position
                x = min(ex - 2, bf.wall_x - 3)
                post = cmd._clamp_pos(x, max(ey - 4, min(ey + 5, up[1])))
                if _dist(up, post) <= 1:
                    return ("hold", None, post, 4)
                return ("support", None, post, 4)
        if _is_melee(unit) or _is_shooter(unit):
            # Ligne d'attente, alignée sur l'axe d'assaut (±5 rangées)
            x = self.staging_x - (2 if _is_shooter(unit) else 0)
            row = self.points['attente'][1]
            post = cmd._clamp_pos(x, max(row - 5, min(row + 5, up[1])))
            if _dist(up, post) <= 1:
                return ("hold", None, post, 4)
            return ("support", None, post, 4)
        return None

    # ═══════════════════════ DÉFENSIVE ═══════════════════════

    def _update_defense(self, cmd, alive, enemies):
        bf = cmd.battlefield
        wall_x = bf.wall_x
        breaches = sorted(bf.active_breaches)
        rams = [e for e in enemies if e.siege_engine == se.RAM and not e.docked
                and se.ram_target_gate(bf, e) is not None]
        towers = [e for e in enemies if e.siege_engine == se.TOWER and not e.docked]
        phase, rows, anchor = "murs", [], None
        if breaches:
            b = min(breaches, key=lambda c: (min(_dist(c, e.position) for e in enemies), c))
            phase, rows, anchor = "breche", [b[1] - 1, b[1], b[1] + 1], b
        elif rams:
            ram = min(rams, key=lambda e: (abs(wall_x - e.position[0]), e.uid))
            gate = se.ram_target_gate(bf, ram)
            phase, rows, anchor = "porte", [gate[1] - 1, gate[1], gate[1] + 1], gate
        else:
            docking = [(t, se.tower_dock_site(bf, t)) for t in towers]
            docking = [(t, site) for t, site in docking
                       if site is not None and _dist(t.position, site) <= TOWER_WATCH]
            if docking:
                _t, site = min(docking, key=lambda ts: (_dist(ts[0].position, ts[1]), ts[0].uid))
                phase, rows, anchor = "tour", [site[1] + 1, site[1] + 2], (wall_x, site[1] + 1)
            else:
                gates = self._gate_rows(cmd)
                foes = [e for e in enemies if e._max_range < 4 and not se.is_machine(e)]
                if gates and foes:
                    g = min(gates, key=lambda g: (min(_dist(g, e.position) for e in foes), g))
                    rows, anchor = [g[1] - 1, g[1], g[1] + 1], g
                    if min(_dist(g, e.position) for e in foes) <= 8:
                        phase = "porte"
        self.threat_rows = rows
        self.points['menace'] = anchor
        texts = {"breche": "la garnison tient la brèche",
                 "porte": "réserve à la porte menacée",
                 "tour": "la réserve monte au-devant de la tour"}
        self._set_phase(phase, texts.get(phase))

    def _reserve_post(self, cmd, index):
        """Poste de réserve n° index: derrière le point menacé, étalé sur ses
        rangées; sur le chemin de ronde face à une tour."""
        bf = cmd.battlefield
        rows = self.threat_rows
        if not rows:
            return None
        wall_x = bf.wall_x
        if self.phase == "tour":
            cells = [(wall_x + dx, y) for dx in (1, 2, 3) for y in rows]
        else:
            mid = rows[len(rows) // 2]
            spread = sorted(set(rows) | {min(rows) - 1, max(rows) + 1},
                            key=lambda y: (abs(y - mid), y))
            cells = [(wall_x + d, y) for d in (2, 3, 4) for y in spread]
        cells = [c for c in cells if 0 <= c[0] < bf.width and 0 < c[1] < bf.height - 1
                 and bf.is_valid(*c)]
        if not cells:
            return None
        return cells[index % len(cells)]

    def _defense_order(self, cmd, unit, enemies):
        """Réserve mobile (mêlée hors rempart). None: logique de base."""
        if not _is_melee(unit) or unit.encouragement_range > 0:
            return None
        bf = cmd.battlefield
        up = unit.position
        on_wall = bf.is_rampart(*up)
        if on_wall and self.phase != "tour":
            return None
        if any(_dist(up, e.position) <= 2 for e in enemies):
            return None
        if any(e.position[0] > bf.wall_x for e in enemies):
            return None                          # intrus: la logique de base intercepte
        reserve = sorted((u for u in cmd.army if u.is_alive and not u.fleeing and _is_melee(u)
                          and u.encouragement_range <= 0
                          and (self.phase == "tour" or not bf.is_rampart(*u.position))),
                         key=lambda u: u.uid)
        index = next((i for i, u in enumerate(reserve) if u is unit), 0)
        post = self._reserve_post(cmd, index)
        if post is None:
            return None
        if up == post:
            return ("hold", None, post, 4)
        return ("support", None, post, 4)

    # ═══════════════════════ COMMUN ═══════════════════════

    def order_for(self, cmd, unit, enemies):
        """(type, unité, position, priorité) ou None (logique par défaut)."""
        if not enemies or self.suspended or not cmd.battlefield.is_siege:
            return None
        if self.attacker:
            return self._attack_order(cmd, unit, enemies)
        return self._defense_order(cmd, unit, enemies)

    def target_bonus(self, cmd, e):
        """Bonus de priorité d'une cible, selon la stratégie."""
        bf = cmd.battlefield
        if self.attacker:
            if self.kind == "engins" and bf.is_rampart(*e.position):
                engines = [u for u in cmd.army if u.is_alive and se.is_engine(u) and not u.docked]
                if any(_dist(e.position, u.position) <= 10 for u in engines):
                    return 3.0                   # couvrir l'approche des engins
            return 0.0
        m = getattr(e, '_attends', None)
        if (m is not None and m.is_alive and se.is_engine(m)
                and m.position[0] >= bf.wall_x - ENGINE_WALL_WATCH):
            return 6.0                           # sans pousseurs, l'engin s'arrête
        if se.is_crew(e):
            return 3.0                           # contre-batterie
        return 0.0

    def intents(self, cmd):
        """Flèches, zones et drapeaux lisibles (touche I)."""
        out = []
        if self.kind in (None, "direct") or self.suspended:
            return out
        alive = [u for u in cmd.army if u.is_alive and not u.fleeing]
        if self.attacker:
            melee = [u for u in alive if _is_melee(u) and self.roles.get(id(u)) != "lure"]
            if (self.kind in ("pilonnage", "feinte") and self.phase != "assaut"
                    and self.points.get('attente')):
                out.append({'type': 'zone', 'center': self.points['attente'], 'radius': 3.0,
                            'label': "hors de portée"})
            if self.phase == "assaut" and melee and self.points.get('assaut'):
                out.append({'type': 'arrow', 'points': [_center(melee), self.points['assaut']],
                            'label': "assaut"})
            lures = [u for u in alive if self.roles.get(id(u)) == "lure"]
            if lures and self.points.get('leurre') and self.phase == "feinte":
                out.append({'type': 'arrow', 'points': [_center(lures), self.points['leurre']],
                            'label': "feinte"})
            for u in alive:
                if se.is_engine(u) and not u.docked:
                    goal = se.engine_goal(cmd.battlefield, u)
                    if goal is not None and goal != u.position:
                        out.append({'type': 'arrow', 'points': [u.position, goal],
                                    'label': "bélier" if u.siege_engine == se.RAM else "tour"})
        elif self.points.get('menace') is not None and self.phase != "murs":
            out.append({'type': 'flag', 'pos': self.points['menace'],
                        'label': PHASE_NAMES[self.phase]})
        return out
