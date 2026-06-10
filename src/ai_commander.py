"""
AI Commander v3 — Commandement tactique adaptatif.

Nouveautés v3:
  • Évaluation de situation chaque round (puissance de tir / mêlée / cavalerie
    des deux camps, recalculée au fil des pertes).
  • Système de POSTURES dynamiques:
      - Champ ouvert : "rush" (aucun tireur vs armée de tireurs → charger à
        fond), "hold_line" (supériorité de tir → tenir la ligne et laisser
        l'ennemi venir sous le feu), "balanced".
      - Siège défenseur : "hold_walls" (défense classique), "sortie" (ouvrir
        les portes et sortir attaquer quand on se fait canarder sans pouvoir
        répliquer), "recall" (repli derrière les murs + fermeture des portes
        une fois la menace de tir éliminée).
  • Kiting : les tireurs menacés par de la mêlée reculent en tirant.
  • Focus fire : les tireurs concentrent leur feu sur une cible commune.
  • Chasse à l'artillerie : l'artillerie ennemie devient cible prioritaire.
"""
import random


class TacticalOrder:
    __slots__ = ['order_type', 'target_unit', 'target_pos', 'priority', 'lane']
    def __init__(self, order_type, target_unit=None, target_pos=None, priority=0, lane=0):
        self.order_type = order_type
        self.target_unit = target_unit
        self.target_pos = target_pos
        self.priority = priority
        self.lane = lane


# ─── Estimation de puissance ───

def _avg_arme_damage(arme):
    """Dégâts moyens espérés d'une arme par round (approximation)."""
    if getattr(arme, '_is_dice', False):
        avg = arme._bonus + arme._nb_des * (arme._faces + 1) / 2.0
    else:
        avg = getattr(arme, '_fixed_damage', 1)
    hit_p = max(0.1, min(1.0, (7 - arme.toucher) / 6.0))
    return arme.nb_attaque * avg * hit_p


def unit_ranged_power(u):
    """Puissance de tir (armes portée >= 4 + sorts offensifs)."""
    p = 0.0
    for a in u.armes:
        if a.porte >= 4:
            p += _avg_arme_damage(a)
    for s in u.spells:
        if s.spell_type in ("fireball", "projectile"):
            p += 3.0  # estimation forfaitaire d'un sort offensif
    return p


def unit_melee_power(u):
    p = 0.0
    for a in u.armes:
        if a.porte < 4:
            p += _avg_arme_damage(a)
    return p


class CommanderAI:
    def __init__(self, army, enemy_army, battlefield, is_army1=True):
        self.army = army
        self.enemy_army = enemy_army
        self.battlefield = battlefield
        self.is_army1 = is_army1
        self.posture = "balanced"
        self.committed_sortie = False   # Une sortie engagée ne s'annule pas à la légère
        self.focus_target = None
        self.style = "balanced"
        self._refresh_style()

    # ─── Analyse de situation ───

    def _refresh_style(self):
        alive = [u for u in self.army if u.is_alive]
        total = max(1, len(alive))
        ranged = sum(1 for u in alive if u._max_range >= 4)
        cavalry = sum(1 for u in alive if u.vitesse >= 6)
        if cavalry / total >= 0.25:
            self.style = "flanker"
        elif ranged / total >= 0.4:
            self.style = "ranged_heavy"
        elif ranged / total <= 0.1:
            self.style = "aggressive"
        else:
            self.style = "balanced"

    def assess(self):
        """Bilan de forces des deux camps, recalculé chaque round."""
        mine = [u for u in self.army if u.is_alive and not u.fleeing]
        theirs = [e for e in self.enemy_army if e.is_alive]
        s = {
            'my_ranged': sum(unit_ranged_power(u) for u in mine),
            'my_melee': sum(unit_melee_power(u) for u in mine),
            'en_ranged': sum(unit_ranged_power(e) for e in theirs),
            'en_melee': sum(unit_melee_power(e) for e in theirs),
            'my_ranged_units': [u for u in mine if u._max_range >= 4 or u.spells],
            'en_ranged_units': [e for e in theirs if e._max_range >= 4 or e.spells],
            'en_artillery': [e for e in theirs if getattr(e, 'is_artillery', False)],
            'my_fast': [u for u in mine if u.vitesse >= 6],
            'mine': mine, 'theirs': theirs,
        }
        return s

    def _decide_posture(self, s, is_siege_defender):
        """Choisit la posture du round selon le rapport de forces."""
        bf = self.battlefield
        is_siege = bool(bf.siege_data)
        is_siege_attacker = is_siege and self.is_army1

        if is_siege_defender:
            # ── SORTIE: l'ennemi nous arrose et on ne peut pas répliquer.
            # Rester derrière les murs = se faire tirer comme des lapins.
            # Mieux vaut ouvrir les portes et aller au contact.
            outgunned = (s['en_ranged'] > 0 and
                         s['my_ranged'] < s['en_ranged'] * 0.35)
            # ── CONTRE-ATTAQUE: l'assaillant n'a plus de quoi prendre le
            # fort (mêlée laminée) → sortir achever les survivants au lieu
            # de laisser le siège pourrir en impasse.
            counter = (s['en_melee'] < s['my_melee'] * 0.4 and s['theirs'])
            if self.committed_sortie:
                # Rappel: les tireurs ennemis sont morts mais leur mêlée
                # reste supérieure → on rentre et on referme les portes.
                if (s['en_ranged'] <= 0.5 and
                        s['en_melee'] > s['my_melee'] * 1.2):
                    return "recall"
                return "sortie"
            if outgunned or counter:
                self.committed_sortie = True
                return "sortie"
            return "hold_walls"

        # ── Champ ouvert (et assaut de siège) ──
        if is_siege_attacker:
            # L'attaquant d'un siège ne peut pas attendre: l'ennemi a une
            # forteresse, il ne viendra pas à nous. Pas de hold_line…
            # SAUF si les défenseurs font une sortie: là, les laisser
            # traverser notre zone de feu est exactement la bonne réponse.
            defenders_out = bf.gates_open or any(
                e.position[0] < bf.siege_data.get('wall_x', 0)
                for e in s['theirs'])
            if not defenders_out:
                if s['my_ranged'] <= 0.5 and s['en_ranged'] > 3.0:
                    return "rush"
                return "balanced"

        if s['my_ranged'] <= 0.5 and s['en_ranged'] > 3.0:
            # Aucun tir chez nous, l'ennemi en a: chaque round d'approche
            # coûte des pertes → charge générale, vitesse maximale.
            return "rush"
        if (s['my_ranged'] > s['en_ranged'] * 2.0 and
                len(s['my_ranged_units']) >= 2):
            # Supériorité de tir nette: tenir la position, faire écran,
            # laisser l'ennemi traverser notre zone de feu.
            return "hold_line"
        return "balanced"

    def _pick_focus_target(self, s, prio):
        """Cible commune pour concentrer le feu: prioritaire ET à portée
        d'au moins deux de nos tireurs (sinon le plus proche du groupe)."""
        shooters = s['my_ranged_units']
        if not shooters:
            self.focus_target = None
            return
        for _, e in prio:
            ex, ey = e.position
            n_in_range = sum(
                1 for u in shooters
                if abs(u.position[0] - ex) + abs(u.position[1] - ey)
                <= max(u._max_range, max((sp.porte for sp in u.spells), default=0)))
            if n_in_range >= 2:
                self.focus_target = e
                return
        # Personne à portée multiple → focus sur le prioritaire le plus proche
        rc = self._center(shooters)
        self.focus_target = min(
            (e for _, e in prio),
            key=lambda e: abs(e.position[0] - rc[0]) + abs(e.position[1] - rc[1]),
            default=None)

    # ─── Émission des ordres ───

    def issue_orders(self, battle):
        alive = [u for u in self.army if u.is_alive and not u.fleeing]
        enemies = [e for e in self.enemy_army if e.is_alive]
        if not alive or not enemies:
            return

        bf = self.battlefield
        is_siege = bool(bf.siege_data)
        is_defender = is_siege and not self.is_army1

        # Réévaluation chaque round (les pertes changent la donne)
        self._refresh_style()
        s = self.assess()
        self.posture = self._decide_posture(s, is_defender)

        # Actions de posture sur le terrain (portes)
        if is_defender:
            if self.posture == "sortie" and not bf.gates_open:
                bf.open_gates()
            elif self.posture == "recall":
                self._try_close_gates(battle)

        prio = self._rank_targets(enemies)
        self._pick_focus_target(s, prio)
        ec = self._center(enemies)
        mc = self._center(alive)
        lanes = self._assign_lanes(alive, enemies)

        rush = (self.posture == "rush" or
                (is_defender and self.posture == "sortie"))

        for unit in alive:
            lane = lanes.get(id(unit), 0)
            unit._rush = rush  # battle.py: désactive le frein de cohésion
            if is_defender and is_siege:
                if self.posture == "sortie":
                    order = self._sortie_order(unit, enemies, prio, s)
                elif self.posture == "recall":
                    order = self._recall_order(unit, enemies)
                else:
                    order = self._siege_defense(unit, enemies, prio, battle)
            else:
                order = self._standard(unit, enemies, prio, ec, mc, battle, s)
            order.lane = lane
            unit._tactical_order = order

    def _try_close_gates(self, battle):
        """Referme les portes si tous nos hommes sont rentrés et
        qu'aucune unité ne bloque le passage."""
        bf = self.battlefield
        if not bf.gates_open:
            return
        wall_x = bf.siege_data.get('wall_x', 0)
        all_inside = all(u.position[0] > wall_x
                         for u in self.army if u.is_alive and not u.fleeing)
        if all_inside:
            bf.close_gates()  # ne ferme que si aucune unité sur les cases porte
            if not bf.gates_open:
                self.committed_sortie = False

    def _center(self, units):
        if not units:
            return (0, 0)
        return (sum(u.position[0] for u in units) / len(units),
                sum(u.position[1] for u in units) / len(units))

    def _rank_targets(self, enemies):
        scored = []
        for e in enemies:
            d = 0
            if e.encouragement_range > 0: d += 5
            if e.spells:
                d += 4
                if any(s.spell_type == "heal" for s in e.spells): d += 3
            if getattr(e, 'is_artillery', False):
                d += 4  # Artillerie: menace majeure, lente = proie facile
            if e._max_range >= 8: d += 3
            elif e._max_range >= 4: d += 2
            if e.hp < e.max_hp * 0.4: d += 2
            if e.awe > 0: d += 1
            scored.append((d, e))
        scored.sort(key=lambda x: (-x[0], id(x[1])))
        return scored

    def _assign_lanes(self, alive, enemies):
        bf = self.battlefield
        h = bf.height
        mobile = [u for u in alive if u.vitesse > 0]
        if not mobile:
            return {}
        ec_y = sum(e.position[1] for e in enemies) / max(1, len(enemies))
        num_lanes = max(3, min(h - 4, len(mobile)))
        spacing = max(1, (h - 6) / max(1, num_lanes))
        lanes = {}
        for i, u in enumerate(mobile):
            offset = ((i % num_lanes) - num_lanes // 2) * spacing
            ty = int(ec_y + offset)
            ty = max(2, min(h - 3, ty))
            lanes[id(u)] = ty
        return lanes

    # ─── Kiting (tir en reculant) ───

    def _kite_threat(self, unit, enemies):
        """Retourne l'ennemi de mêlée menaçant si le tireur doit reculer."""
        if unit._max_range < 4 or unit.vitesse < 3:
            return None
        ux, uy = unit.position
        # Pas de kiting sur rempart: la position est trop précieuse
        if self.battlefield.is_rampart(ux, uy):
            return None
        threat = None
        threat_d = 999
        for e in enemies:
            if e._max_range >= 4:
                continue  # Un autre tireur n'est pas une menace de contact
            d = abs(ux - e.position[0]) + abs(uy - e.position[1])
            if d <= max(3, e.vitesse) and d < threat_d:
                threat, threat_d = e, d
        if threat is None:
            return None
        # Un allié de mêlée fait-il écran à proximité immédiate ?
        for a in self.army:
            if (a.is_alive and a is not unit and a._max_range < 4
                    and not a.fleeing
                    and abs(a.position[0] - threat.position[0])
                    + abs(a.position[1] - threat.position[1]) <= 1):
                return None  # Le screen tient, pas besoin de reculer
        return threat

    def _kite_destination(self, unit, threat):
        bf = self.battlefield
        ux, uy = unit.position
        tx, ty = threat.position
        dx = 0 if ux == tx else (1 if ux > tx else -1)
        dy = 0 if uy == ty else (1 if uy > ty else -1)
        if dx == 0 and dy == 0:
            dx = 1
        step = max(2, unit.vitesse - 1)
        nx = max(1, min(bf.width - 2, ux + dx * step))
        ny = max(1, min(bf.height - 2, uy + dy * step))
        return (nx, ny)

    # ─── Ordres champ ouvert ───

    def _standard(self, unit, enemies, prio, ec, mc, battle, s):
        bf = self.battlefield

        # Tireurs/mages: d'abord vérifier la menace de contact → kiting
        if unit._max_range >= 4 or unit.spells:
            threat = self._kite_threat(unit, enemies)
            if threat is not None:
                return TacticalOrder("kite",
                                     target_pos=self._kite_destination(unit, threat),
                                     priority=5)

        if unit.spells:
            return self._mage_order(unit, enemies, prio)
        if unit.vitesse >= 6 and self.style in ("flanker", "balanced"):
            return self._cav_order(unit, enemies, prio, ec, s)
        if unit._max_range >= 4:
            return self._ranged_order(unit, enemies, prio)
        if unit.encouragement_range > 0:
            return self._officer_order(unit, enemies, mc)

        # Posture hold_line: TOUTE la mêlée fait écran devant les tireurs
        if self.posture == "hold_line":
            return self._screen_order(unit, enemies, mc)
        if self.style == "ranged_heavy" and unit.role == "front":
            return self._screen_order(unit, enemies, mc)

        # Posture rush: foncer sur les tireurs ennemis en priorité
        if self.posture == "rush":
            shooters = [e for e in enemies if e._max_range >= 4 or e.spells]
            if shooters:
                ux, uy = unit.position
                t = min(shooters, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
                return TacticalOrder("attack", target_unit=t, priority=5)
        return self._melee_order(unit, enemies, prio)

    def _mage_order(self, unit, enemies, prio):
        ux, uy = unit.position
        max_spell_range = max((sp.porte for sp in unit.spells), default=6)
        # Focus fire d'abord
        ft = self.focus_target
        if ft and ft.is_alive:
            d = abs(ux - ft.position[0]) + abs(uy - ft.position[1])
            if d <= max_spell_range:
                return TacticalOrder("attack", target_unit=ft, priority=5)
        for _, e in prio[:3]:
            d = abs(ux - e.position[0]) + abs(uy - e.position[1])
            if d <= max_spell_range:
                return TacticalOrder("attack", target_unit=e, priority=5)
        if prio:
            return TacticalOrder("attack", target_unit=prio[0][1], priority=2)
        closest = min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
        return TacticalOrder("attack", target_unit=closest, priority=1)

    def _cav_order(self, unit, enemies, prio, ec, s):
        ux, uy = unit.position
        # Artillerie ennemie = mission n°1 de la cavalerie
        if s['en_artillery']:
            t = min(s['en_artillery'],
                    key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
            return TacticalOrder("attack", target_unit=t, priority=5)
        hv = [e for _, e in prio if e._max_range >= 4 or getattr(e, 'is_artillery', False)]
        if hv:
            t = min(hv, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
            return TacticalOrder("attack", target_unit=t, priority=4)
        bf = self.battlefield
        fy = 3 if uy < bf.height // 2 else bf.height - 4
        return TacticalOrder("flank", target_pos=(int(ec[0]), fy), priority=3)

    def _ranged_order(self, unit, enemies, prio):
        ux, uy = unit.position
        max_range = unit._max_range
        bf = self.battlefield

        def visible(e):
            return (abs(ux - e.position[0]) + abs(uy - e.position[1]) <= max_range
                    and bf.has_line_of_fire(unit, e))

        # Focus fire: cible commune si à portée ET visible
        ft = self.focus_target
        if ft and ft.is_alive and visible(ft):
            return TacticalOrder("attack", target_unit=ft, priority=4)
        for _, e in prio:
            if visible(e):
                return TacticalOrder("attack", target_unit=e, priority=3)
        # Posture hold_line: ne pas avancer, attendre que l'ennemi entre
        # dans la zone de feu
        if self.posture == "hold_line":
            return TacticalOrder("hold", target_pos=unit.position, priority=3)
        c = min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
        return TacticalOrder("attack", target_unit=c, priority=1)

    def _melee_order(self, unit, enemies, prio):
        ux, uy = unit.position
        v2 = unit.vitesse * 2
        v3 = unit.vitesse * 3
        wounded = [e for e in enemies if e.hp < e.max_hp * 0.4
                   and abs(ux - e.position[0]) + abs(uy - e.position[1]) <= v2]
        if wounded:
            return TacticalOrder("attack", target_unit=min(wounded, key=lambda e: e.hp), priority=3)
        off = [e for _, e in prio[:3] if e.encouragement_range > 0
               and abs(ux - e.position[0]) + abs(uy - e.position[1]) <= v3]
        if off:
            return TacticalOrder("attack", target_unit=off[0], priority=4)
        c = min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
        return TacticalOrder("attack", target_unit=c, priority=1)

    def _screen_order(self, unit, enemies, mc):
        bf = self.battlefield
        my_r = [u for u in self.army if u.is_alive and u._max_range >= 4]
        if not my_r:
            c = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=c, priority=1)
        rc = self._center(my_r)
        ce = min(enemies, key=lambda e: bf.manhattan_distance((int(rc[0]), int(rc[1])), e.position))
        if bf.manhattan_distance(ce.position, (int(rc[0]), int(rc[1]))) <= 6:
            return TacticalOrder("attack", target_unit=ce, priority=4)
        sx = int(rc[0] * 0.4 + ce.position[0] * 0.6)
        sy = int(rc[1] * 0.4 + ce.position[1] * 0.6)
        return TacticalOrder("protect", target_pos=(sx, sy), priority=2)

    def _officer_order(self, unit, enemies, mc):
        bf = self.battlefield
        fighters = [u for u in self.army if u.is_alive and u != unit and u._max_range < 4 and not u.fleeing]
        if fighters:
            c = self._center(fighters)
            return TacticalOrder("hold", target_pos=(int(c[0]), int(c[1])), priority=2)
        c = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
        return TacticalOrder("attack", target_unit=c, priority=1)

    # ─── Siège: SORTIE ───

    def _sortie_order(self, unit, enemies, prio, s):
        """Les portes sont ouvertes: tout le monde sort tuer les tireurs
        ennemis (la raison même de la sortie), puis le reste."""
        bf = self.battlefield
        ux, uy = unit.position

        # Nos rares tireurs (s'il en reste) couvrent depuis les remparts
        if (unit._max_range >= 4 or unit.spells) and bf.is_rampart(ux, uy):
            for _, e in prio:
                if abs(ux - e.position[0]) + abs(uy - e.position[1]) <= unit._max_range:
                    return TacticalOrder("attack", target_unit=e, priority=4)
            c = min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
            return TacticalOrder("attack", target_unit=c, priority=2)

        # Mêlée: priorité absolue aux tireurs et à l'artillerie ennemis
        shooters = [e for e in enemies if e._max_range >= 4 or e.spells]
        if shooters:
            t = min(shooters, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
            return TacticalOrder("attack", target_unit=t, priority=6)
        c = min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
        return TacticalOrder("attack", target_unit=c, priority=3)

    def _recall_order(self, unit, enemies):
        """Repli derrière les murs. Si un ennemi nous colle, on le combat
        en reculant (l'ordre attack du contact est géré par compute_move)."""
        bf = self.battlefield
        wall_x = bf.siege_data.get('wall_x', 0)
        ux, uy = unit.position
        if ux > wall_x:
            # Déjà à l'intérieur → tenir position défensive
            return TacticalOrder("hold", target_pos=unit.position, priority=3)
        # Dehors → rentrer par la porte la plus proche
        gates = list(bf.gate_hp.keys())
        if gates:
            g = min(gates, key=lambda p: abs(p[1] - uy))
            return TacticalOrder("protect", target_pos=(wall_x + 2, g[1]), priority=5)
        return TacticalOrder("hold", target_pos=unit.position, priority=2)

    # ─── Siège: défense des murs ───

    def _siege_defense(self, unit, enemies, prio, battle):
        bf = self.battlefield
        wall_x = bf.siege_data.get('wall_x', 0)
        gates_intact = any(hp > 0 for hp in bf.gate_hp.values()) and not bf.gates_open
        on_ramp = bf.is_rampart(*unit.position)

        inside = [e for e in enemies if e.position[0] > wall_x]
        near_wall = [e for e in enemies if e.position[0] >= wall_x - 10]
        gate_ys = set()
        for (gx, gy), hp in bf.gate_hp.items():
            if hp > 0:
                gate_ys.add(gy)
        at_gate = [e for e in enemies if any(abs(e.position[1] - gy) <= 2 for gy in gate_ys)
                   and e.position[0] >= wall_x - 2]

        # === PRIORITÉ 1: Ennemis à l'intérieur → intercepter ===
        if inside:
            t = min(inside, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=t, priority=6)

        # === Portes intactes: défense positionnelle ===
        if gates_intact:
            if on_ramp and unit._max_range >= 4:
                if at_gate:
                    t = min(at_gate, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                    return TacticalOrder("attack", target_unit=t, priority=5)
                if near_wall:
                    t = min(near_wall, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                    return TacticalOrder("attack", target_unit=t, priority=4)
                t = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                return TacticalOrder("attack", target_unit=t, priority=3)

            if on_ramp and unit._max_range < 4:
                stair_e = [e for e in enemies if (e.position in bf.stairs)
                           or bf.manhattan_distance(unit.position, e.position) <= 2]
                if stair_e:
                    t = min(stair_e, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                    return TacticalOrder("attack", target_unit=t, priority=5)
                return TacticalOrder("hold", target_pos=unit.position, priority=3)

            if unit._max_range < 4:
                if at_gate:
                    t = min(at_gate, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                    return TacticalOrder("attack", target_unit=t, priority=4)
                return TacticalOrder("hold", target_pos=unit.position, priority=2)

            if unit._max_range >= 4 and not on_ramp:
                for y in range(1, bf.height - 1):
                    if bf.grid[wall_x + 1][y] == 4 and not bf.is_occupied(wall_x + 1, y):
                        return TacticalOrder("protect", target_pos=(wall_x + 1, y), priority=3)

        # === Portes détruites/ouvertes: combat ouvert ===
        c = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
        return TacticalOrder("attack", target_unit=c, priority=2)


# ─── Intégration ───

def select_tactical_target(unit, battle, battlefield):
    order = getattr(unit, '_tactical_order', None)
    enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
    if not enemies:
        return None

    ux, uy = unit.position
    max_range = unit._max_range
    is_ranged = max_range >= 4

    def _reachable(e, d):
        if d > max_range:
            return False
        if is_ranged and not battlefield.has_line_of_fire(unit, e):
            return False
        return True

    if order and order.order_type == "attack" and order.target_unit and order.target_unit.is_alive:
        tx, ty = order.target_unit.position
        dist = abs(ux - tx) + abs(uy - ty)
        if _reachable(order.target_unit, dist):
            return order.target_unit
        in_r = [(e, abs(ux - e.position[0]) + abs(uy - e.position[1])) for e in enemies]
        in_r = [(e, d) for e, d in in_r if _reachable(e, d)]
        if in_r:
            return min(in_r, key=lambda ed: (ed[0].hp / max(1, ed[0].max_hp), id(ed[0])))[0]

    if order and order.order_type in ("flank", "hold", "protect", "kite"):
        in_r = [(e, abs(ux - e.position[0]) + abs(uy - e.position[1])) for e in enemies]
        in_r = [(e, d) for e, d in in_r if _reachable(e, d)]
        if in_r:
            return min(in_r, key=lambda ed: ed[0].hp)[0]

    return min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))


def select_tactical_move_target(unit, battle, battlefield):
    order = getattr(unit, '_tactical_order', None)
    enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
    if not enemies:
        return None, None

    ux, uy = unit.position

    if order is None:
        return min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1])), None

    if order.order_type == "attack":
        t = order.target_unit
        if t and t.is_alive:
            return t, None
        return min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1])), None

    if order.order_type == "kite" and order.target_pos:
        # Reculer vers la position de repli (le tir reste géré séparément)
        return None, order.target_pos

    if order.order_type == "flank" and order.target_pos:
        tx, ty = order.target_pos
        if abs(ux - tx) + abs(uy - ty) <= 4:
            return min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1])), None
        return None, order.target_pos

    if order.order_type == "protect" and order.target_pos:
        tx, ty = order.target_pos
        if abs(ux - tx) + abs(uy - ty) <= 2:
            return min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1])), None
        return None, order.target_pos

    if order.order_type == "hold":
        max_range = unit._max_range
        in_r = [e for e in enemies if abs(ux - e.position[0]) + abs(uy - e.position[1]) <= max_range + 3]
        if in_r:
            return min(in_r, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1])), None
        if order.target_pos:
            return None, order.target_pos
        return None, None

    return min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1])), None


def get_lane_offset(unit, battlefield):
    order = getattr(unit, '_tactical_order', None)
    if order and order.lane:
        return order.lane
    return unit.position[1]
