"""
AI Commander v4 — Commandement tactique adaptatif et opportuniste.

v3 raisonnait déjà en postures et manœuvres. Elle restait cependant
prévisible: mêmes seuils, mêmes cibles, mêmes réponses. v4 ajoute ce qui
manquait pour qu'une bataille ne ressemble pas à la précédente:

  • TEMPÉRAMENT: chaque commandant reçoit un caractère (audace, prudence,
    patience, goût du débordement) tiré au début de la bataille. Les seuils
    de décision en découlent — deux généraux ne jouent pas la même partie.
  • MÉMOIRE ET INERTIE: la posture est verrouillée quelques rounds
    (fini le clignotement rush/hold d'un round à l'autre), sauf urgence
    réelle — percée, effondrement d'une aile, tireurs débordés.
  • ÉVALUATION CHIFFRÉE: dégâts espérés, probabilité de tuer, valeur
    résiduelle des unités, rapport de forces LOCAL (module `tactics`).
  • CARTE DE MENACE: on sait quelles cases sont battues par le feu ennemi;
    replis, kiting et contournements l'évitent au lieu de la traverser.
  • ANTICIPATION: on vise le point d'interception d'une cible mobile, pas
    sa position actuelle.
  • OPPORTUNISME: unité ennemie isolée, tireur découvert, aile enfoncée →
    on y jette immédiatement ce qu'on a sous la main.
  • CONSERVATION: une unité à l'agonie décroche et laisse la place au lieu
    de mourir bêtement — si la ligne peut l'absorber.
"""
import random

import tactics
import terrain as tr


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


# ─── Tempéraments ───
# Chaque profil déforme les seuils de décision. Le tirage se fait à la
# création du commandant: une même composition ne se joue pas deux fois
# de la même façon.
_TEMPERAMENTS = {
    "audacieux":   {'aggression': 1.35, 'prudence': 0.7,  'patience': 0.6, 'ruse': 1.0},
    "méthodique":  {'aggression': 0.9,  'prudence': 1.15, 'patience': 1.3, 'ruse': 0.9},
    "prudent":     {'aggression': 0.7,  'prudence': 1.45, 'patience': 1.5, 'ruse': 0.95},
    "manœuvrier":  {'aggression': 1.0,  'prudence': 1.0,  'patience': 1.0, 'ruse': 1.5},
    "brutal":      {'aggression': 1.5,  'prudence': 0.55, 'patience': 0.5, 'ruse': 0.7},
}


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
        self.maneuver = None            # "envelop", "concentrate", "collapse", None
        self._assignments = {}          # id(unit) -> (rôle, target_pos|unit)
        self._axis = (1.0, 0.0)         # Axe du front (vers l'ennemi)
        self._melee_front = None        # Projection de la ligne de mêlée
        self._melee_center = None
        self._mc = (0, 0)

        # ── Tempérament: tiré une fois, il colore toute la bataille ──
        self.rng = random.Random(random.randrange(1 << 30))
        self.temperament = self.rng.choice(list(_TEMPERAMENTS))
        t = _TEMPERAMENTS[self.temperament]
        self.aggression = t['aggression'] * self.rng.uniform(0.9, 1.1)
        self.prudence = t['prudence'] * self.rng.uniform(0.9, 1.1)
        self.patience = t['patience'] * self.rng.uniform(0.9, 1.1)
        self.ruse = t['ruse'] * self.rng.uniform(0.9, 1.1)

        # ── Mémoire: sans elle, l'IA change d'avis à chaque round ──
        self._posture_lock = 0          # Rounds restants avant réévaluation libre
        self._last_strength = None      # Valeur de l'armée au round précédent
        self._losses_rate = 0.0         # Pertes subies au dernier round
        self._enemy_losses_rate = 0.0
        self._threat = None             # Carte de menace du round
        self._round = 0
        self._prey = {}                 # id(unité) -> id(proie) : évite le zapping
        self.assault_gate = None        # Porte choisie pour l'assaut
        self._gate_lock = 0             # Inertie du choix de porte
        self._line_hold_rounds = 0      # Rounds passés à dresser la ligne
        self._artillery_wait = 0        # Rounds passés à couvert des machines
        self.breach = None              # Faille repérée dans la ligne adverse
        self._lane_center = None        # Secteur visé par l'avance

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
        """Bilan de forces des deux camps, recalculé chaque round.

        On y ajoute la DYNAMIQUE (qui saigne le plus vite), la menace
        pesant sur nos fragiles et les occasions à saisir: c'est de là que
        naissent les décisions contextuelles."""
        mine = [u for u in self.army if u.is_alive and not u.fleeing]
        theirs = [e for e in self.enemy_army if e.is_alive]
        my_val = sum(tactics.remaining_value(u) for u in mine)
        en_val = sum(tactics.remaining_value(e) for e in theirs)

        s = {
            'my_ranged': sum(unit_ranged_power(u) for u in mine),
            'my_melee': sum(unit_melee_power(u) for u in mine),
            'en_ranged': sum(unit_ranged_power(e) for e in theirs),
            'en_melee': sum(unit_melee_power(e) for e in theirs),
            'my_ranged_units': [u for u in mine if u._max_range >= 4 or u.spells],
            'en_ranged_units': [e for e in theirs if e._max_range >= 4 or e.spells],
            'en_artillery': [e for e in theirs if getattr(e, 'is_artillery', False)],
            'my_artillery': [u for u in mine if getattr(u, 'is_artillery', False)],
            'my_fast': [u for u in mine if u.vitesse >= 6],
            'mine': mine, 'theirs': theirs,
            'my_value': my_val, 'en_value': en_val,
            'ratio': my_val / max(1.0, en_val),
        }

        # Dynamique: est-ce que ça tourne à notre avantage ou l'inverse ?
        if self._last_strength is not None:
            prev_my, prev_en = self._last_strength
            self._losses_rate = max(0.0, prev_my - my_val) / max(1.0, prev_my)
            self._enemy_losses_rate = max(0.0, prev_en - en_val) / max(1.0, prev_en)
        self._last_strength = (my_val, en_val)
        s['bleeding'] = self._losses_rate
        s['hurting_them'] = self._enemy_losses_rate

        # Nos fragiles sont-ils sur le point d'être joints ?
        threatened = []
        for u in s['my_ranged_units']:
            if self.battlefield.is_rampart(*u.position):
                continue
            for e in theirs:
                if e._max_range >= 4:
                    continue
                d = abs(u.position[0] - e.position[0]) + abs(u.position[1] - e.position[1])
                if d <= max(3, e.vitesse + 1):
                    threatened.append(u)
                    break
        s['threatened_shooters'] = threatened

        # Occasions: ennemis isolés ou découverts, à portée raisonnable
        opportunities = []
        for e in theirs:
            if tactics.is_isolated(e, theirs, 5, 1):
                d_mine = min((abs(u.position[0] - e.position[0])
                              + abs(u.position[1] - e.position[1]) for u in mine),
                             default=999)
                if d_mine <= 14:
                    opportunities.append(e)
        s['opportunities'] = opportunities

        # Nos machines de guerre tirent-elles VRAIMENT ?
        # Tant qu'une baliste martèle la ligne adverse, jeter l'infanterie
        # au contact revient à lui couper son champ de tir et à perdre des
        # hommes que la machine aurait fauchés gratuitement.
        bf = self.battlefield
        firing = 0
        for a in s['my_artillery']:
            for e in theirs:
                d = abs(a.position[0] - e.position[0]) + abs(a.position[1] - e.position[1])
                if d <= tr.effective_range(bf, a, e) and bf.has_line_of_fire(a, e):
                    firing += 1
                    break
        s['artillery_firing'] = firing
        # Idem pour l'ensemble de notre tir: une ligne qui attend sous
        # couverture de ses archers gagne l'échange.
        s['support_fire'] = firing + sum(
            1 for u in s['my_ranged_units']
            if any(abs(u.position[0] - e.position[0]) + abs(u.position[1] - e.position[1])
                   <= tr.effective_range(bf, u, e) and bf.has_line_of_fire(u, e) for e in theirs))
        return s

    # ─── Posture: décision + inertie ───

    def _decide_posture(self, s, is_siege_defender):
        """Choisit la posture du round. Une posture engage: on ne la change
        pas tous les rounds pour un écart de dé — sauf urgence."""
        bf = self.battlefield
        is_siege = bool(bf.siege_data)
        is_siege_attacker = is_siege and self.is_army1

        if is_siege_defender:
            # ── SORTIE: l'ennemi nous arrose et on ne peut pas répliquer. ──
            seuil = 0.35 * self.prudence
            outgunned = (s['en_ranged'] > 0 and s['my_ranged'] < s['en_ranged'] * seuil)
            # ── CONTRE-ATTAQUE: l'assaillant n'a plus de quoi prendre le fort ──
            counter = (s['en_melee'] < s['my_melee'] * (0.4 * self.aggression)
                       and s['theirs'])
            if self.committed_sortie:
                if (s['en_ranged'] <= 0.5 and s['en_melee'] > s['my_melee'] * 1.2):
                    return "recall"
                return "sortie"
            if outgunned or counter:
                self.committed_sortie = True
                return "sortie"
            return "hold_walls"

        candidate = self._posture_candidate(s, is_siege_attacker)

        # Urgences: elles brisent le verrou (on ne laisse pas égorger ses
        # tireurs par fidélité au plan précédent)
        urgent = candidate in ("screen", "rush") or (
            candidate == "exploit" and (s['ratio'] >= 3.0 or len(s['theirs']) <= 2))
        if candidate != self.posture:
            if self._posture_lock > 0 and not urgent:
                return self.posture
            self._posture_lock = 2 + int(self.patience * 1.5)
        return candidate

    def _posture_candidate(self, s, is_siege_attacker):
        bf = self.battlefield
        if is_siege_attacker:
            # L'assaillant ne peut pas attendre: l'ennemi a une forteresse.
            defenders_out = bf.gates_open or any(
                e.position[0] < bf.siege_data.get('wall_x', 0) for e in s['theirs'])
            if not defenders_out:
                if s['my_ranged'] <= 0.5 and s['en_ranged'] > 3.0:
                    return "rush"
                return "balanced"

        # 0) Coup de grâce: l'adversaire est anéanti ou presque. On ne tient
        # plus de ligne, on ne se regroupe plus: on traque les survivants.
        if s['theirs'] and (s['ratio'] >= 3.0
                            or (len(s['theirs']) <= 2 and len(s['mine']) >= 2 * len(s['theirs']))):
            return "exploit"

        my_melee_units = [u for u in s['mine']
                          if u._max_range < 4 and not u.spells and u.vitesse > 0]

        # 1) Nos fragiles vont être joints: on interpose la mêlée, tout de suite
        if (s['threatened_shooters'] and len(s['my_ranged_units']) >= 2
                and len(my_melee_units) >= 2):
            return "screen"

        # 2) Aucun tir chez nous, l'ennemi en a: chaque round d'approche coûte
        if s['my_ranged'] <= 0.5 and s['en_ranged'] > 3.0:
            return "rush"

        # 3) L'ennemi craque et nous dominons: on pousse pour achever
        if (s['ratio'] > 1.35 / max(0.7, self.aggression)
                and s['hurting_them'] >= s['bleeding']
                and len(s['theirs']) <= max(2, len(s['mine']) - 1)):
            return "exploit"

        # 4) Nos machines de guerre tirent: chaque round d'attente est une
        # salve gratuite. Envoyer l'infanterie au contact maintenant, ce
        # serait masquer notre propre feu et arriver en ordre dispersé.
        # On tient la ligne tant que l'échange nous est favorable.
        if (s.get('artillery_firing', 0) >= 1
                and s['my_ranged'] >= s['en_ranged'] * 0.75
                and s['bleeding'] <= s['hurting_them'] + 0.02
                and self._artillery_wait < 4 + int(self.patience * 3)):
            return "hold_line"

        # 5) Supériorité de tir nette: laisser l'ennemi traverser la zone de feu
        if (s['my_ranged'] > s['en_ranged'] * (2.0 / max(0.7, self.patience))
                and len(s['my_ranged_units']) >= 2):
            return "hold_line"

        # 6) On saigne vite et on est en dessous: se resserrer avant de rompre
        if (s['bleeding'] > 0.16 and s['ratio'] < 0.85
                and self.prudence >= 1.0 and len(s['mine']) >= 3):
            return "regroup"

        return "balanced"

    # ─── Hiérarchie des cibles ───

    def _rank_targets(self, enemies):
        """Ce qui nous fait le plus mal, pondéré par ce qu'on peut réellement
        abattre — et légèrement bruité pour que deux batailles identiques ne
        produisent pas le même plan de feu."""
        mine = [u for u in self.army if u.is_alive and not u.fleeing]
        scored = []
        for e in enemies:
            ex, ey = e.position
            d = 0.0
            if e.encouragement_range > 0:
                d += 5.0
            if e.spells:
                d += 4.0
                if any(sp.spell_type == "heal" for sp in e.spells):
                    d += 4.0
            if getattr(e, 'is_artillery', False):
                d += 4.0
            if e._max_range >= 8:
                d += 3.0
            elif e._max_range >= 4:
                d += 2.0
            if e.awe > 0:
                d += 1.0
            # Une cible entamée vaut de l'or: la tuer supprime tout son feu
            d += (1.0 - e.hp / max(1, e.max_hp)) * 4.0
            # Accessibilité: désigner un objectif hors d'atteinte ne sert à rien
            dmin = min((abs(u.position[0] - ex) + abs(u.position[1] - ey)
                        for u in mine), default=99)
            d -= dmin * 0.08
            if tactics.is_isolated(e, enemies, 5, 1):
                d += 2.5 * self.ruse
            d *= self.rng.uniform(0.94, 1.06)
            scored.append((d, e))
        scored.sort(key=lambda x: (-x[0], x[1].uid))
        return scored

    def _pick_focus_target(self, s, prio):
        """Cible commune des tireurs: on cherche celle qu'on peut ABATTRE ce
        round (concentrer sur un colosse intouchable ne sert à rien)."""
        shooters = s['my_ranged_units']
        if not shooters or not prio:
            self.focus_target = None
            return
        bf = self.battlefield
        best, best_score = None, -1e9
        for score, e in prio[:6]:
            ex, ey = e.position
            total, n = 0.0, 0
            for u in shooters:
                rng_u = max(tr.effective_range(bf, u, e),
                            max((sp.porte for sp in u.spells), default=0))
                d = abs(u.position[0] - ex) + abs(u.position[1] - ey)
                if d > rng_u:
                    continue
                if u._max_range >= 4 and not bf.has_line_of_fire(u, e):
                    continue
                total += tactics.expected_damage(u, e, d, bf)
                n += 1
            if n == 0:
                continue
            killable = 1.0 if total >= e.hp else total / max(1.0, e.hp)
            val = score + killable * 12.0 + n * 1.5
            if val > best_score:
                best, best_score = e, val
        if best is None:
            rc = self._center(shooters)
            best = min((e for _, e in prio),
                       key=lambda e: abs(e.position[0] - rc[0]) + abs(e.position[1] - rc[1]),
                       default=None)
        self.focus_target = best

    # ─── Émission des ordres ───

    def issue_orders(self, battle):
        alive = [u for u in self.army if u.is_alive and not u.fleeing]
        enemies = [e for e in self.enemy_army if e.is_alive]
        if not alive or not enemies:
            return

        self._round += 1
        if self._posture_lock > 0:
            self._posture_lock -= 1
        # L'attente en ligne se compte: on ne reste pas éternellement au
        # garde-à-vous sous prétexte de discipline.
        # Cumulé sur toute la bataille: en terrain difficile (forêt), les
        # retardataires arrivent au compte-gouttes et un compteur remis à
        # zéro à chaque round sans attente laissait l'armée piétiner.
        if getattr(self, '_line_held_this_round', False):
            self._line_hold_rounds += 1
        self._line_held_this_round = False

        bf = self.battlefield
        is_siege = bool(bf.siege_data)
        is_defender = is_siege and not self.is_army1

        # Réévaluation chaque round (les pertes changent la donne)
        self._refresh_style()
        s = self.assess()
        self._threat = tactics.ThreatField(enemies, bf)
        self.posture = self._decide_posture(s, is_defender)
        if self.posture == "hold_line" and s.get('artillery_firing', 0):
            self._artillery_wait += 1
        else:
            self._artillery_wait = 0

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

        # ── Formation: axe du front + ligne de mêlée (discipline arrière) ──
        self._compute_formation(alive, ec)

        # ── CONCENTRATION: ennemi scindé en deux groupes → battre en
        # détail le plus faible avec toute l'armée ──
        target_group = None
        if not (is_siege and is_defender):
            target_group = self._enemy_clusters(enemies)
        if target_group is not None:
            self.maneuver = "concentrate"
            enemies_f = target_group
            prio = self._rank_targets(enemies_f)
            self._pick_focus_target(s, prio)
            ec = self._center(enemies_f)
        else:
            if self.maneuver == "concentrate":
                self.maneuver = None
            enemies_f = enemies

        # ── Manoeuvres: curée sur les isolés, gardes du corps, débordement ──
        if not (is_defender and is_siege):
            self._plan_maneuvers(alive, enemies_f, ec, s)
        else:
            self._assignments = {}

        # ── Assaut de siège: choisir PAR OÙ entrer (la porte la moins
        # défendue, pas la plus proche) et s'y tenir. ──
        if is_siege and self.is_army1 and bf.gate_hp:
            self._pick_assault_gate(alive)
            for u in alive:
                u._assault_gate = self.assault_gate

        lanes = self._assign_lanes(alive, enemies_f)

        rush = (self.posture in ("rush", "exploit") or
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
                order = self._standard(unit, enemies_f, prio, ec, mc, battle, s)
            order.lane = lane
            unit._tactical_order = order

    def _pick_assault_gate(self, alive):
        """Porte d'assaut: on entre là où l'on sera le moins arrosé.

        Prendre la porte la plus proche mène droit sous le secteur le mieux
        tenu; une porte un peu plus loin mais faiblement couverte coûte
        beaucoup moins d'hommes. Le choix est verrouillé quelques rounds —
        une armée qui change d'axe tous les tours n'arrive jamais."""
        bf = self.battlefield
        gates = [g for g, hp in bf.gate_hp.items() if hp > 0] or list(bf.gate_hp.keys())
        if not gates:
            self.assault_gate = None
            return
        if (self.assault_gate in gates and self._gate_lock > 0):
            self._gate_lock -= 1
            return
        mc = self._center(alive)
        best, best_score = None, None
        for g in gates:
            approach = (max(0, g[0] - 2), g[1])   # case d'où l'on frappera
            danger = self._threat.at(approach) if self._threat else 0.0
            march = abs(mc[0] - g[0]) + abs(mc[1] - g[1])
            score = danger * 1.6 + march * 0.8
            if best_score is None or score < best_score:
                best, best_score = g, score
        self.assault_gate = best
        self._gate_lock = 5

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

    # ─── Formation: axe du front et ligne de mêlée ───

    def _front_axis(self, mc, ec):
        """Vecteur unitaire de mon centre vers le centre ennemi."""
        dx = ec[0] - mc[0]
        dy = ec[1] - mc[1]
        n = (dx * dx + dy * dy) ** 0.5
        if n < 1e-6:
            return (1.0, 0.0) if self.is_army1 else (-1.0, 0.0)
        return (dx / n, dy / n)

    def _proj(self, pos):
        """Projection sur l'axe du front (plus grand = plus proche de l'ennemi)."""
        return ((pos[0] - self._mc[0]) * self._axis[0]
                + (pos[1] - self._mc[1]) * self._axis[1])

    def _compute_formation(self, alive, ec):
        """Axe du front + ligne de mêlée (70e percentile des projections,
        robuste aux isolés partis devant)."""
        self._mc = self._center(alive)
        self._axis = self._front_axis(self._mc, ec)
        melee = [u for u in alive
                 if u._max_range < 4 and not u.spells and u.vitesse > 0]
        if not melee:
            self._melee_front = None
            self._melee_center = None
            return
        projs = sorted(self._proj(u.position) for u in melee)
        idx = min(len(projs) - 1, int(len(projs) * 0.7))
        self._melee_front = projs[idx]
        self._melee_center = self._center(melee)

    def _clamp_pos(self, x, y):
        bf = self.battlefield
        return (max(1, min(bf.width - 2, int(round(x)))),
                max(1, min(bf.height - 2, int(round(y)))))

    def _rear_fallback_pos(self, unit):
        """Si le tireur est devant la ligne de mêlée (exposé), retourne sa
        position de repli derrière la ligne. Sinon None."""
        if self._melee_front is None:
            return None
        ux, uy = unit.position
        if self.battlefield.is_rampart(ux, uy):
            return None
        proj_u = self._proj((ux, uy))
        safety = self._melee_front - 2
        if proj_u <= safety + 0.5:
            return None
        delta = proj_u - (self._melee_front - 4)
        ax, ay = self._axis
        return self._clamp_pos(ux - ax * delta, uy - ay * delta)

    def _support_advance_pos(self, unit):
        """Avance par bonds: progresser vers l'ennemi SANS jamais dépasser
        la ligne de sécurité — la mêlée ouvre la voie, les tireurs suivent."""
        if self._melee_front is None:
            return None
        ux, uy = unit.position
        proj_u = self._proj((ux, uy))
        new_proj = min(self._melee_front - 3, proj_u + unit.vitesse)
        if new_proj - proj_u < 1.0:
            return (ux, uy)  # Déjà collé à la ligne: tenir le poste
        ax, ay = self._axis
        delta = new_proj - proj_u
        return self._clamp_pos(ux + ax * delta, uy + ay * delta)

    def _rally_pos(self, unit):
        """Point de ralliement en posture 'regroup': se resserrer autour du
        centre de la mêlée plutôt que de se faire prendre en détail."""
        center = self._melee_center or self._mc
        ax, ay = self._axis
        bx = center[0] - ax * 2.0
        by = center[1] - ay * 2.0
        ux, uy = unit.position
        dx, dy = bx - ux, by - uy
        n = (dx * dx + dy * dy) ** 0.5
        if n < 1.5:
            return None  # déjà en place
        step = min(unit.vitesse, n)
        return self._clamp_pos(ux + dx / n * step, uy + dy / n * step)

    def _withdraw_pos(self, unit, enemies):
        """Décrochage d'une unité à l'agonie.

        Une unité à bout de PV sur une case battue par le feu va mourir
        pour rien: si la ligne peut encaisser sans elle, elle rompt le
        contact et va se refaire à l'arrière. Deux garde-fous:
          • on ne décroche pas avec un souffle de vie alors qu'un ennemi
            est AU CONTACT — le coup d'opportunité l'achèverait dans le dos;
          • on ne décroche que si quelqu'un peut combler le trou.
        """
        if unit.vitesse <= 0 or unit.max_hp < 3:
            return None
        if unit.hp > unit.max_hp * 0.5:
            return None
        if getattr(unit, 'is_artillery', False):
            return None
        bf = self.battlefield
        ux, uy = unit.position
        if bf.is_rampart(ux, uy):
            return None
        if self._threat is None:
            return None
        in_contact = any(
            e._max_range < 4
            and abs(ux - e.position[0]) + abs(uy - e.position[1]) <= min(2, e._max_range)
            for e in enemies)
        if in_contact and unit.hp <= 1:
            return None  # décrocher là, c'est offrir son dos
        if self._threat.at((ux, uy)) < unit.hp * 1.1:
            return None  # la menace n'est pas encore mortelle
        if tactics.support_count((ux, uy), self.army, 4, exclude=unit) < 2:
            return None  # personne pour combler le trou: on tient
        ax, ay = self._axis
        step = max(2, unit.vitesse)
        cands = []
        for k in (step, max(1, step - 1)):
            for off in (-2, -1, 0, 1, 2):
                cands.append(self._clamp_pos(ux - ax * k - ay * off,
                                             uy - ay * k + ax * off))
        best = self._threat.safest(cands)
        if best is None or best == (ux, uy):
            return None
        return best

    def _hold_the_line_pos(self, unit, enemies, s):
        """Discipline de ligne — on ne s'engage PAS tout seul.

        Deux raisons de dresser la ligne avant de donner l'assaut:
          • une unité qui déborde arrive isolée au contact, prise à revers
            par trois adversaires pendant que le reste de l'armée marche
            encore;
          • tant que nos machines de guerre (baliste, scorpion) et nos
            archers ont un champ de tir dégagé, chaque round d'attente est
            une salve gratuite. Se précipiter, c'est masquer son propre feu.

        Retourne la case où se ranger, ou None s'il n'y a pas lieu d'attendre.
        """
        if self.posture in ("rush", "exploit", "sortie", "recall"):
            return None
        if self._melee_front is None or unit.vitesse <= 0:
            return None
        # Assaut de forteresse: l'ennemi ne viendra pas à nous et chaque
        # round passé à découvert coûte des hommes. Dresser la ligne sous
        # le feu des remparts serait absurde.
        bf_h = self.battlefield
        if bf_h.gate_hp and self.is_army1 and not bf_h.gates_open:
            return None
        ux, uy = unit.position

        # Déjà engagé (ou sur le point de l'être): on ne se dérobe jamais
        for e in enemies:
            if abs(ux - e.position[0]) + abs(uy - e.position[1]) <= unit._max_range + 1:
                return None

        # L'attente a une limite: au bout de quelques rounds, l'assaut part
        # de toute façon (sinon deux armées prudentes se regardent).
        if self._line_hold_rounds > 6:
            return None

        proj_u = self._proj((ux, uy))
        ahead = proj_u - self._melee_front

        support = s.get('artillery_firing', 0)
        if support:
            tol = 0.5          # nos machines tirent: on serre les rangs
        elif s.get('support_fire', 0) >= 2:
            tol = 1.2          # nos archers travaillent: on avance groupé
        else:
            tol = 2.5          # sans appui, pas de raison de traîner

        if ahead <= tol:
            return None

        # Assez de camarades autour pour encaisser le choc ? Alors on peut
        # y aller — sauf si l'artillerie a encore besoin de son champ libre.
        if (not support
                and tactics.support_count((ux, uy), self.army, 3, exclude=unit) >= 2):
            return None

        unit.status_text = "EN LIGNE"
        ax, ay = self._axis
        delta = ahead - tol * 0.5
        return self._clamp_pos(ux - ax * delta, uy - ay * delta)

    def _find_breach(self, alive, enemies, ec):
        """Repère une FAILLE dans la ligne ennemie.

        Pousser là où ils sont denses, c'est payer plein tarif. Un trou
        entre deux groupes, lui, ouvre sur leurs arrières — archers et
        machines — et coupe leur ligne en deux.

        Retourne (point_de_penetration, coordonnee_laterale) ou None.
        """
        if len(enemies) < 4:
            return None
        ax, ay = self._axis
        px, py = -ay, ax  # perpendiculaire au front

        lat = sorted(((e.position[0] - ec[0]) * px + (e.position[1] - ec[1]) * py, e.uid, e)
                     for e in enemies)
        if len(lat) < 5:
            return None

        # On ignore les deux extrémités: un trou au bout n'est pas une
        # faille, c'est un flanc (traité par le débordement).
        best_gap, best_mid = 0.0, None
        # Avec peu d'ennemis restants, la distinction faille/flanc n'a plus
        # de sens: tout trou est bon à prendre.
        i_from = 1 if len(lat) > 5 else 0
        i_to = len(lat) - 2 if len(lat) > 5 else len(lat) - 1
        for i in range(i_from, i_to):
            gap = lat[i + 1][0] - lat[i][0]
            if gap > best_gap:
                best_gap = gap
                best_mid = (lat[i][0] + lat[i + 1][0]) / 2.0
        if best_mid is None or best_gap < 4.0:
            return None

        # Le point de pénétration se situe juste DERRIÈRE leur ligne
        depth = 2.0
        bx = ec[0] + px * best_mid + ax * depth
        by = ec[1] + py * best_mid + ay * depth
        return self._clamp_pos(bx, by), best_mid

    # ─── Manoeuvres: concentration, curée, débordement, gardes du corps ───

    def _enemy_clusters(self, enemies):
        """Deux groupes ennemis séparés latéralement ? Retourne le groupe
        CIBLE (le plus faible) ou None."""
        if len(enemies) < 6:
            return None
        es = sorted(enemies, key=lambda e: e.position[1])
        best_gap, split = 0, None
        for i in range(1, len(es)):
            gap = es[i].position[1] - es[i - 1].position[1]
            if gap > best_gap:
                best_gap, split = gap, i
        if best_gap < 12 or split is None:
            return None
        g1, g2 = es[:split], es[split:]
        if min(len(g1), len(g2)) < 2:
            return None
        p1 = sum(unit_melee_power(e) + unit_ranged_power(e) for e in g1)
        p2 = sum(unit_melee_power(e) + unit_ranged_power(e) for e in g2)
        return g1 if p1 <= p2 else g2

    def _assign_soft_sector(self, enemies, ys):
        """Repère le secteur latéral le moins tenu de la ligne adverse.

        On mesure la densité de valeur par tranche et on penche le front
        vers la plus faible: l'armée converge d'elle-même sur le point de
        moindre résistance au lieu de pousser au plus épais. Le décalage
        reste partiel — on ne déserte pas le centre.
        """
        self._lane_center = None
        if len(enemies) < 4 or not ys:
            return
        y_lo, y_hi = min(ys), max(ys)
        if y_hi - y_lo < 6:
            return
        ec_y = sum(ys) / len(ys)
        band = max(3, (y_hi - y_lo) // 4)
        best_c, best_d = ec_y, None
        cy_b = y_lo
        while cy_b <= y_hi:
            dens = sum(tactics.remaining_value(e) for e in enemies
                       if abs(e.position[1] - cy_b) <= band)
            if best_d is None or dens < best_d:
                best_d, best_c = dens, cy_b
            cy_b += max(2, band // 2)
        self._lane_center = ec_y * 0.55 + best_c * 0.45

    def _assign_lanes(self, alive, enemies):
        """Couloirs d'avance SANS croisement, et resserrés pour la mêlée.

        Deux largeurs de front distinctes:
          • la MÊLÉE forme un mur compact (un peu plus d'une case par
            homme): c'est ce qui donne une ligne de boucliers plutôt qu'une
            nuée dispersée, et ce qui permet de se soutenir mutuellement;
          • les tireurs et les machines s'étalent davantage, pour dégager
            leurs angles de tir et ne pas offrir de cible groupée.
        """
        bf = self.battlefield
        mobile = [u for u in alive if u.vitesse > 0]
        if not mobile:
            return {}
        ys = [e.position[1] for e in enemies] or [bf.height // 2]
        ec_y = sum(ys) / len(ys)
        enemy_spread = (max(ys) - min(ys)) + 4

        # ── Siège: l'axe d'assaut est dicté par la PORTE ──
        # Chercher le secteur le moins défendu n'a aucun sens quand on ne
        # peut entrer que par un point précis: la colonne se mettrait à
        # longer le mur au lieu d'enfoncer les battants.
        gate_lane = None
        if bf.gate_hp and not bf.gates_open and self.is_army1:
            gate = self.assault_gate or min(
                bf.gate_hp.keys(),
                key=lambda g: abs(g[1] - ec_y), default=None)
            if gate is not None:
                gate_lane = gate[1]
        if gate_lane is not None:
            ec_y = gate_lane
            enemy_spread = 8  # colonne serrée sur la porte
        else:
            self._assign_soft_sector(enemies, ys)
            ec_y = self._lane_center if self._lane_center is not None else ec_y


        melee = [u for u in mobile
                 if u._max_range < 4 and not u.spells
                 and not getattr(u, 'is_artillery', False)]
        others = [u for u in mobile if u not in melee]

        lanes = {}

        def spread(units, span):
            if not units:
                return
            span = max(4, min(bf.height - 6, span))
            units.sort(key=lambda u: (u.position[1], u.uid))
            n = len(units)
            for i, u in enumerate(units):
                frac = (i + 0.5) / n - 0.5
                ty = int(round(ec_y + frac * span))
                lanes[id(u)] = max(2, min(bf.height - 3, ty))

        # Mur de boucliers: serré, mais jamais plus étroit que ce qu'exige
        # le nombre d'hommes, ni plus large que le front ennemi + marge.
        melee_span = min(max(5, int(len(melee) * 1.25)), int(enemy_spread) + 6)
        spread(melee, melee_span)
        spread(others, max(melee_span, enemy_spread))
        return lanes

    def _hold_the_line_pos(self, unit, enemies, s):
        """Discipline de ligne — on ne s'engage PAS tout seul.

        Deux raisons de dresser la ligne avant de donner l'assaut:
          • une unité qui déborde arrive isolée au contact, prise à revers
            par trois adversaires pendant que le reste de l'armée marche
            encore;
          • tant que nos machines de guerre (baliste, scorpion) et nos
            archers ont un champ de tir dégagé, chaque round d'attente est
            une salve gratuite. Se précipiter, c'est masquer son propre feu.

        Retourne la case où se ranger, ou None s'il n'y a pas lieu d'attendre.
        """
        if self.posture in ("rush", "exploit", "sortie", "recall"):
            return None
        if self._melee_front is None or unit.vitesse <= 0:
            return None
        ux, uy = unit.position

        # Déjà engagé (ou sur le point de l'être): on ne se dérobe jamais
        for e in enemies:
            if abs(ux - e.position[0]) + abs(uy - e.position[1]) <= unit._max_range + 1:
                return None

        # L'attente a une limite: au bout de quelques rounds, l'assaut part
        # de toute façon (sinon deux armées prudentes se regardent).
        if self._line_hold_rounds > 6:
            return None

        proj_u = self._proj((ux, uy))
        ahead = proj_u - self._melee_front

        support = s.get('artillery_firing', 0)
        if support:
            tol = 0.5          # nos machines tirent: on serre les rangs
        elif s.get('support_fire', 0) >= 2:
            tol = 1.2          # nos archers travaillent: on avance groupé
        else:
            tol = 2.5          # sans appui, pas de raison de traîner

        if ahead <= tol:
            return None

        # Assez de camarades autour pour encaisser le choc ? Alors on peut
        # y aller — sauf si l'artillerie a encore besoin de son champ libre.
        if (not support
                and tactics.support_count((ux, uy), self.army, 3, exclude=unit) >= 2):
            return None

        unit.status_text = "EN LIGNE"
        ax, ay = self._axis
        delta = ahead - tol * 0.5
        return self._clamp_pos(ux - ax * delta, uy - ay * delta)

    def _find_breach(self, alive, enemies, ec):
        """Repère une FAILLE dans la ligne ennemie.

        Pousser là où ils sont denses, c'est payer plein tarif. Un trou
        entre deux groupes, lui, ouvre sur leurs arrières — archers et
        machines — et coupe leur ligne en deux.

        Retourne (point_de_penetration, coordonnee_laterale) ou None.
        """
        if len(enemies) < 5:
            return None
        ax, ay = self._axis
        px, py = -ay, ax  # perpendiculaire au front

        lat = sorted(((e.position[0] - ec[0]) * px + (e.position[1] - ec[1]) * py, e.uid)
                     for e in enemies)
        if len(lat) < 4:
            return None

        # On ignore les deux extrémités: un trou au bout n'est pas une
        # faille, c'est un flanc (traité par le débordement).
        best_gap, best_mid = 0.0, None
        for i in range(1, len(lat) - 2):
            gap = lat[i + 1][0] - lat[i][0]
            if gap > best_gap:
                best_gap = gap
                best_mid = (lat[i][0] + lat[i + 1][0]) / 2.0
        if best_mid is None or best_gap < 5.0:
            return None

        # Le point de pénétration se situe juste DERRIÈRE leur ligne
        depth = 2.0
        bx = ec[0] + px * best_mid + ax * depth
        by = ec[1] + py * best_mid + ay * depth
        return self._clamp_pos(bx, by), best_mid

    # ─── Manoeuvres: concentration, curée, débordement, gardes du corps ───

    def _enemy_clusters(self, enemies):
        """Deux groupes ennemis séparés latéralement ? Retourne le groupe
        CIBLE (le plus faible) ou None."""
        if len(enemies) < 6:
            return None
        es = sorted(enemies, key=lambda e: e.position[1])
        best_gap, split = 0, None
        for i in range(1, len(es)):
            gap = es[i].position[1] - es[i - 1].position[1]
            if gap > best_gap:
                best_gap, split = gap, i
        if best_gap < 12 or split is None:
            return None
        g1, g2 = es[:split], es[split:]
        if min(len(g1), len(g2)) < 2:
            return None
        p1 = sum(unit_melee_power(e) + unit_ranged_power(e) for e in g1)
        p2 = sum(unit_melee_power(e) + unit_ranged_power(e) for e in g2)
        return g1 if p1 <= p2 else g2

    def _assign_lanes(self, alive, enemies):
        """Couloirs d'avance SANS croisement: on conserve l'ordre relatif
        des unités du haut vers le bas. Les colonnes ne se traversent plus
        et l'avance reste lisible — chacun garde sa place dans la ligne."""
        bf = self.battlefield
        mobile = [u for u in alive if u.vitesse > 0]
        if not mobile:
            return {}
        ys = [e.position[1] for e in enemies] or [bf.height // 2]
        ec_y = sum(ys) / len(ys)
        spread = (max(ys) - min(ys)) + 6
        span = max(6, min(bf.height - 6, spread))
        mobile.sort(key=lambda u: (u.position[1], u.uid))
        n = len(mobile)
        lanes = {}
        for i, u in enumerate(mobile):
            frac = (i + 0.5) / n - 0.5
            ty = int(round(ec_y + frac * span))
            lanes[id(u)] = max(2, min(bf.height - 3, ty))
        return lanes

    def _plan_maneuvers(self, alive, enemies, ec, s):
        """Affectations spéciales du round: curée sur les isolés, gardes du
        corps des tireurs, débordement par les ailes."""
        self._assignments = {}
        bf = self.battlefield
        if bf.siege_data and not bf.gates_open:
            if self.maneuver == "envelop":
                self.maneuver = None
            return  # Pas de manoeuvres d'ailes contre/derrière des murs

        melee = [u for u in alive
                 if u._max_range < 4 and not u.spells
                 and u.encouragement_range == 0 and u.vitesse > 0]
        en_melee_n = sum(1 for e in enemies if e._max_range < 4 and not e.spells)
        used = set()

        # ── CURÉE: un ennemi isolé est une occasion à saisir TOUT DE SUITE.
        # On lui envoie les deux unités disponibles les plus proches: deux
        # contre un, on le détruit avant que ses camarades n'arrivent. ──
        opportunities = [e for e in s.get('opportunities', ()) if e in enemies]
        if opportunities and melee and self.posture != "screen":
            opportunities.sort(key=lambda e: -(tactics.remaining_value(e)))
            for prey in opportunities[:2]:
                px, py = prey.position
                pack = sorted(
                    (u for u in melee if id(u) not in used),
                    key=lambda u: abs(u.position[0] - px) + abs(u.position[1] - py))
                n_send = 2 if len(melee) >= 6 else 1
                sent = 0
                for u in pack:
                    d = abs(u.position[0] - px) + abs(u.position[1] - py)
                    if d > max(6, u.vitesse * 3):
                        break  # trop loin: la proie aura rejoint les siens
                    self._assignments[id(u)] = ("collapse", prey)
                    used.add(id(u))
                    sent += 1
                    if sent >= n_send:
                        break
            if used:
                self.maneuver = "collapse"
        elif self.maneuver == "collapse":
            self.maneuver = None

        # ── GARDES DU CORPS: unités rapides ennemies menaçant nos tireurs ──
        en_fast = [e for e in enemies if e.vitesse >= 6]
        my_shooters = [u for u in alive
                       if (u._max_range >= 4 or u.spells)
                       and not bf.is_rampart(*u.position)]
        # Les machines de guerre comptent parmi les biens à couvrir: lentes,
        # chères, sans défense au contact — les perdre, c'est perdre le duel
        # de tir. Une menace lente qui s'en approche justifie une escorte
        # autant qu'une charge de cavalerie.
        my_engines = [u for u in alive if getattr(u, 'is_artillery', False)]
        engine_threats = []
        for eng in my_engines:
            for e in enemies:
                d = abs(eng.position[0] - e.position[0]) + abs(eng.position[1] - e.position[1])
                if d <= max(10, e.vitesse * 2) and e._max_range < 4:
                    engine_threats.append(e)
                    break
        protected = my_shooters + my_engines
        threats = en_fast + engine_threats
        if (threats and len(protected) >= 1 and len(melee) >= 3
                and self.posture != "rush"):
            rc = self._center(my_engines if my_engines else my_shooters)
            # Anticipation: on se poste là où la menace SERA, pas où elle
            # est — sinon la garde arrive toujours trop tard.
            tc_unit = min(threats, key=lambda e: abs(e.position[0] - rc[0])
                          + abs(e.position[1] - rc[1]))
            tc = tactics.predicted_position(tc_unit, 1, (bf.width, bf.height))
            dx, dy = tc[0] - rc[0], tc[1] - rc[1]
            n = max(1e-6, (dx * dx + dy * dy) ** 0.5)
            base = (rc[0] + dx / n * 2.5, rc[1] + dy / n * 2.5)
            # Autant d'escorteurs que de cavaliers menaçants (2 au plus,
            # et jamais au point de vider la ligne)
            n_guard = max(1, min(2, min(len(threats), len(melee) - 2)))
            guards = sorted((u for u in melee if id(u) not in used),
                            key=lambda u: abs(u.position[0] - rc[0])
                            + abs(u.position[1] - rc[1]))[:n_guard]
            for gi, g in enumerate(guards):
                off = -1 if gi == 0 else 1
                post = self._clamp_pos(base[0] - dy / n * off * 2,
                                       base[1] + dx / n * off * 2)
                self._assignments[id(g)] = ("guard", post)
                used.add(id(g))

        # ── BRÈCHE: la ligne adverse est trouée → on s'y engouffre ──
        # Une colonne qui passe derrière leur front y trouve les archers et
        # les machines: bien plus rentable que de pousser sur le bouclier.
        # Seules les unités NON engagées peuvent être détournées vers la
        # brèche: décrocher d'un corps à corps offrirait un coup gratuit.
        free_now = [u for u in melee
                    if id(u) not in used
                    and not any(abs(u.position[0] - e.position[0])
                                + abs(u.position[1] - e.position[1]) <= 2
                                for e in enemies)]
        self.breach = None
        if (len(free_now) >= 2 and self.posture not in ("screen", "regroup")
                and self.maneuver != "concentrate"):
            found = self._find_breach(alive, enemies, ec)
            if found is not None:
                bpos, blat = found
                ax_b, ay_b = self._axis
                px_b, py_b = -ay_b, ax_b
                # Les unités déjà du bon côté de la faille y vont: pas de
                # traversée du front pour rejoindre le point de passage.
                cand = sorted(
                    free_now,
                    key=lambda u: abs(((u.position[0] - ec[0]) * px_b
                                       + (u.position[1] - ec[1]) * py_b) - blat))
                # On n'envoie que ceux qui peuvent réellement y arriver
                cand = [u for u in cand
                        if abs(u.position[0] - bpos[0]) + abs(u.position[1] - bpos[1])
                        <= max(10, u.vitesse * 4)]
                n_send = min(len(cand), max(2, len(free_now) // 3))
                if n_send >= 1:
                    self.breach = bpos
                    for u in cand[:n_send]:
                        self._assignments[id(u)] = ("breach", bpos)
                        used.add(id(u))
                    self.maneuver = "breach"
        if self.breach is None and self.maneuver == "breach":
            self.maneuver = None

        # ── DÉBORDEMENT (envelopment): nette supériorité de mêlée ──
        free_melee = [u for u in melee if id(u) not in used]
        seuil = 1.4 / max(0.7, self.ruse)
        if (self.posture in ("balanced", "exploit")
                and self.maneuver not in ("concentrate", "collapse")
                and len(free_melee) >= 6
                and en_melee_n > 0 and len(free_melee) >= en_melee_n * seuil
                and len(free_melee) - max(2, len(free_melee) // 4) >= 4):
            n_flank = max(2, int(len(free_melee) * 0.25 * self.ruse))
            n_flank = min(n_flank, len(free_melee) - 4)
            flankers = sorted(free_melee, key=lambda u: -u.vitesse)[:n_flank]
            ax, ay = self._axis
            px, py = -ay, ax  # Perpendiculaire au front
            wing = max(8, bf.height // 4)
            for u in flankers:
                side_val = ((u.position[0] - ec[0]) * px
                            + (u.position[1] - ec[1]) * py)
                sgn = 1 if side_val >= 0 else -1
                tgt = self._clamp_pos(ec[0] + px * sgn * wing + ax * 2,
                                      ec[1] + py * sgn * wing + ay * 2)
                self._assignments[id(u)] = ("envelop", tgt)
            self.maneuver = "envelop"
        elif self.maneuver == "envelop":
            self.maneuver = None

    # ─── Kiting (tir en reculant) ───

    def _kite_threat(self, unit, enemies):
        """Retourne l'ennemi de mêlée menaçant si le tireur doit reculer."""
        if unit._max_range < 4 or unit.vitesse < 3:
            return None
        ux, uy = unit.position
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
        # Déjà au contact: décrocher, c'est offrir un coup gratuit. On ne le
        # fait que si rester est pire (peu de PV).
        if threat_d <= 1 and unit.hp > unit.max_hp * 0.5:
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
        """Case de repli: on s'éloigne de la menace ET on évite les zones
        battues par le reste de l'armée adverse (reculer dans la ligne de
        mire d'un autre archer n'a aucun intérêt)."""
        bf = self.battlefield
        ux, uy = unit.position
        tx, ty = threat.position
        dx = 0 if ux == tx else (1 if ux > tx else -1)
        dy = 0 if uy == ty else (1 if uy > ty else -1)
        if dx == 0 and dy == 0:
            dx = 1
        step = max(2, unit.vitesse - 1)
        cands = []
        for ddx, ddy in ((dx, dy), (dx, 0), (0, dy), (dx, -dy), (-dy, dx)):
            if ddx == 0 and ddy == 0:
                continue
            cands.append((max(1, min(bf.width - 2, ux + ddx * step)),
                          max(1, min(bf.height - 2, uy + ddy * step))))
        if self._threat is not None:
            best = self._threat.safest(cands)
            if best is not None:
                return best
        return cands[0]

    # ─── Ordres champ ouvert ───

    def _standard(self, unit, enemies, prio, ec, mc, battle, s):
        bf = self.battlefield

        # ── Affectation de manoeuvre (curée / débordement / garde du corps) ──
        assign = self._assignments.get(id(unit))
        if assign is not None:
            kind, pos = assign
            if kind == "collapse":
                prey = pos
                if prey.is_alive:
                    return TacticalOrder("attack", target_unit=prey, priority=6)
            elif kind == "breach":
                ux, uy = unit.position
                # Passé la brèche: on tombe sur ce qu'il y a derrière
                # (tireurs, machines, officiers) — c'est tout l'intérêt.
                if abs(ux - pos[0]) + abs(uy - pos[1]) <= 3:
                    soft = [e for e in enemies
                            if e._max_range >= 4 or e.spells
                            or getattr(e, 'is_artillery', False)
                            or e.encouragement_range > 0]
                    pool = soft if soft else enemies
                    t = min(pool, key=lambda e: abs(ux - e.position[0])
                            + abs(uy - e.position[1]))
                    return TacticalOrder("attack", target_unit=t, priority=6)
                return TacticalOrder("flank", target_pos=pos, priority=5)
            elif kind == "guard":
                return TacticalOrder("guard", target_pos=pos, priority=4)
            elif kind == "envelop":
                ux, uy = unit.position
                # Arrivé sur l'aile → tomber sur le flanc/dos ennemi
                if abs(ux - pos[0]) + abs(uy - pos[1]) <= 4:
                    shooters = [e for e in enemies if e._max_range >= 4 or e.spells]
                    pool = shooters if shooters else enemies
                    t = min(pool, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
                    return TacticalOrder("attack", target_unit=t, priority=5)
                return TacticalOrder("flank", target_pos=pos, priority=4)

        # ── Décrochage d'une unité à l'agonie (mieux vaut ça qu'un cadavre) ──
        wd = self._withdraw_pos(unit, enemies)
        if wd is not None:
            unit.status_text = "REPLI"
            return TacticalOrder("withdraw", target_pos=wd, priority=6)

        # ── Tireurs/mages: unités fragiles → discipline stricte ──
        if unit._max_range >= 4 or unit.spells:
            threat = self._kite_threat(unit, enemies)
            if threat is not None:
                return TacticalOrder("kite",
                                     target_pos=self._kite_destination(unit, threat),
                                     priority=5)
            fb = self._rear_fallback_pos(unit)
            if fb is not None:
                return TacticalOrder("support", target_pos=fb, priority=4)

        if unit.spells:
            return self._mage_order(unit, enemies, prio)
        if unit.vitesse >= 6 and self.style in ("flanker", "balanced"):
            return self._cav_order(unit, enemies, prio, ec, s)
        if unit._max_range >= 4:
            return self._ranged_order(unit, enemies, prio)
        if unit.encouragement_range > 0:
            return self._officer_order(unit, enemies, mc)

        # ── Ne pas s'engager seul: dresser la ligne d'abord ──
        hold_pos = self._hold_the_line_pos(unit, enemies, s)
        if hold_pos is not None:
            self._line_held_this_round = True
            return TacticalOrder("protect", target_pos=hold_pos, priority=3)

        # ── Postures de mêlée ──
        if self.posture in ("hold_line", "screen"):
            return self._screen_order(unit, enemies, mc)
        if self.style == "ranged_heavy" and unit.role == "front":
            return self._screen_order(unit, enemies, mc)

        if self.posture == "regroup":
            ux, uy = unit.position
            contact = any(abs(ux - e.position[0]) + abs(uy - e.position[1]) <= unit._max_range + 1
                          for e in enemies)
            if not contact:
                rp = self._rally_pos(unit)
                if rp is not None:
                    return TacticalOrder("protect", target_pos=rp, priority=3)

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
        ft = self.focus_target
        if ft and ft.is_alive:
            d = abs(ux - ft.position[0]) + abs(uy - ft.position[1])
            if d <= max_spell_range:
                return TacticalOrder("attack", target_unit=ft, priority=5)
        for _, e in prio[:3]:
            d = abs(ux - e.position[0]) + abs(uy - e.position[1])
            if d <= max_spell_range:
                return TacticalOrder("attack", target_unit=e, priority=5)
        adv = self._support_advance_pos(unit)
        if adv is not None:
            return TacticalOrder("support", target_pos=adv, priority=2)
        if prio:
            return TacticalOrder("attack", target_unit=prio[0][1], priority=2)
        closest = min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
        return TacticalOrder("attack", target_unit=closest, priority=1)

    def _cav_order(self, unit, enemies, prio, ec, s):
        """La cavalerie ne court plus derrière sa proie: elle vise le point
        d'INTERCEPTION, et garde sa cible d'un round sur l'autre au lieu de
        changer d'avis dès qu'un ennemi passe plus près."""
        bf = self.battlefield
        ux, uy = unit.position
        clamp = (bf.width, bf.height)

        # Fidélité à la proie désignée au round précédent (si toujours valable)
        prev_id = self._prey.get(id(unit))
        prey = None
        if prev_id is not None:
            for e in enemies:
                if id(e) == prev_id and e.is_alive:
                    prey = e
                    break

        if prey is None:
            pool = [e for e in enemies
                    if e._max_range >= 4 or e.spells or getattr(e, 'is_artillery', False)]
            if s['en_artillery']:
                pool = s['en_artillery']
            if pool:
                prey = min(pool, key=lambda e: abs(ux - e.position[0])
                           + abs(uy - e.position[1]))

        if prey is not None:
            self._prey[id(unit)] = id(prey)
            d = abs(ux - prey.position[0]) + abs(uy - prey.position[1])
            if d <= unit.vitesse + 2:
                return TacticalOrder("attack", target_unit=prey, priority=5)
            ip = tactics.intercept_point(unit, prey, clamp)
            return TacticalOrder("flank", target_pos=ip, priority=4)

        self._prey.pop(id(unit), None)
        fy = 3 if uy < bf.height // 2 else bf.height - 4
        return TacticalOrder("flank", target_pos=(int(ec[0]), fy), priority=3)

    def _ranged_order(self, unit, enemies, prio):
        ux, uy = unit.position
        bf = self.battlefield

        def visible(e):
            return (abs(ux - e.position[0]) + abs(uy - e.position[1]) <= tr.effective_range(bf, unit, e)
                    and bf.has_line_of_fire(unit, e))

        ft = self.focus_target
        if ft and ft.is_alive and visible(ft):
            return TacticalOrder("attack", target_unit=ft, priority=4)
        for _, e in prio:
            if visible(e):
                return TacticalOrder("attack", target_unit=e, priority=3)
        if self.posture in ("hold_line", "screen"):
            return TacticalOrder("hold", target_pos=unit.position, priority=3)
        if self.posture == "exploit":
            # Plus besoin d'écran: on se porte à portée des survivants
            c = min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
            return TacticalOrder("attack", target_unit=c, priority=3)
        adv = self._support_advance_pos(unit)
        if adv is not None:
            return TacticalOrder("support", target_pos=adv, priority=2)
        c = min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
        return TacticalOrder("attack", target_unit=c, priority=1)

    def _melee_order(self, unit, enemies, prio):
        """Choix du combat: meilleur RAPPORT entre ce qu'on peut abattre et
        le chemin à parcourir pour y arriver."""
        bf = self.battlefield
        ux, uy = unit.position
        reach = max(unit.vitesse * 2, 6)
        best, best_score = None, -1e9
        for score, e in prio:
            d = abs(ux - e.position[0]) + abs(uy - e.position[1])
            if d > reach * 2:
                continue
            dmg = tactics.expected_damage(unit, e, 1, bf)
            val = score * 0.6 + tactics.kill_chance(dmg, e) * 10.0
            if e.hp < e.max_hp * 0.4:
                val += 4.0                       # achever
            if self.posture == "exploit":
                val += tactics.kill_chance(dmg, e) * 6.0
            val -= d * 1.65 / max(1, unit.vitesse)
            if val > best_score:
                best, best_score = e, val
        if best is not None:
            return TacticalOrder("attack", target_unit=best, priority=3)
        c = min(enemies, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
        return TacticalOrder("attack", target_unit=c, priority=1)

    def _screen_order(self, unit, enemies, mc):
        bf = self.battlefield
        my_r = [u for u in self.army if u.is_alive and (u._max_range >= 4 or u.spells)]
        if not my_r:
            c = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=c, priority=1)
        rc = self._center(my_r)
        rc_i = (int(rc[0]), int(rc[1]))
        # Menace prioritaire: celle qui atteindra nos tireurs en premier
        ce = min(enemies, key=lambda e: (bf.manhattan_distance(rc_i, e.position)
                                         - e.vitesse * 1.5))
        if bf.manhattan_distance(ce.position, rc_i) <= 6:
            return TacticalOrder("attack", target_unit=ce, priority=4)
        # Se placer entre le danger et nos tireurs, sur son axe d'approche
        ip = tactics.predicted_position(ce, 1, (bf.width, bf.height))
        sx = int(rc[0] * 0.4 + ip[0] * 0.6)
        sy = int(rc[1] * 0.4 + ip[1] * 0.6)
        return TacticalOrder("protect", target_pos=(sx, sy), priority=2)

    def _officer_order(self, unit, enemies, mc):
        bf = self.battlefield
        fighters = [u for u in self.army if u.is_alive and u != unit
                    and u._max_range < 4 and not u.fleeing]
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
        if d > tr.effective_range(battlefield, unit, e):
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
            return min(in_r, key=lambda ed: (ed[0].hp / max(1, ed[0].max_hp), ed[0].uid))[0]

    if order and order.order_type in ("flank", "hold", "protect", "kite",
                                      "support", "guard", "withdraw"):
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

    if order.order_type in ("kite", "withdraw") and order.target_pos:
        # Rompre le contact: le tir reste géré séparément
        return None, order.target_pos

    if order.order_type in ("support", "guard") and order.target_pos:
        if order.order_type == "guard":
            post = order.target_pos
            intruders = [e for e in enemies
                         if abs(e.position[0] - post[0]) + abs(e.position[1] - post[1]) <= 6]
            if intruders:
                return min(intruders, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1])), None
        if abs(ux - order.target_pos[0]) + abs(uy - order.target_pos[1]) > 1:
            return None, order.target_pos
        return None, None  # Au poste: ne pas bouger (géré par compute_move)

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
