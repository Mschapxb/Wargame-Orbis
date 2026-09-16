import random
from collections import deque

from effects import FloatingText, FX_CLOCK

import itertools

# Identifiant stable: sert de clé de tri déterministe (id() change d'une
# exécution à l'autre et rendait les graines non reproductibles).
_UID = itertools.count(1)


class Unit:
    def __init__(self, name, pv, vitesse, morale, sauvegarde, color,
                 armes=None, spells=None, special=None, role="front",
                 size=1, unit_type="Infanterie"):
        self.name = name
        self.uid = next(_UID)
        self.token_name = ""
        self.pv = pv
        self.max_pv = pv
        self.vitesse = vitesse
        self.base_morale = morale
        self.sauvegarde = sauvegarde
        self.armes = armes or []
        self.spells = spells or []
        self.special = special or {}
        self.role = role
        # Contingent d'appartenance: une même équipe peut aligner plusieurs
        # armées de factions différentes, déployées et comptées séparément.
        self.contingent = ""
        self.position = (0, 0)
        self.is_alive = True
        
        # Animation: position précédente pour interpolation fluide
        self._prev_position = (0, 0)  # Position au début du round
        self._last_step = (0, 0)      # Déplacement du round précédent
        self._lunge_target = None     # Position pixel de la cible pour lunge CaC
        self._lunge_timer = 0         # Timer du lunge (frames restantes)
        self._hit_flash = 0           # Frames restantes de flash de dégâts
        self.color = color
        self.afraid = False
        self.fleeing = False
        self.fled = False  # A quitté la map en fuyant (ni vivant ni mort)
        self.status_text = ""
        self.floating_texts = deque(maxlen=10)
        self.down_timer = 0
        self.fear_aura = 0
        self.current_target = None
        self.morale_malus = 0
        self.morale_bonus = 0
        self.encouragement_range = 0
        
        # Taille en cases (1=1x1, 2=2x2, 3=3x3, etc.)
        self.size = size
        # Type: "Infanterie", "Large", "Artillerie", "Cavalerie", "Monstre", "Héros"
        self.unit_type = unit_type
        # Nombre de sorts lancables par round
        self.spells_per_round = 1
        
        # Traits de combat
        self.anti_infanterie = False
        self.anti_large = False
        self.phalange = False
        self.charge_montee = False  # Cavalerie: +1 dégâts sur charge
        self.charge_aida = False    # Infanterie: -1 blesser sur charge
        self.has_charged = False    # A déjà chargé ce round
        self._phalange_bonus_active = False
        self._on_wall = False  # Sur un mur (siège)
        self._armor_buff = False
        self._armor_buff_rounds = 0
        self._armor_buff_amount = 0

        # ─── État de réaction / rythme de combat (réinitialisé chaque round) ───
        self._opportunity_used = False   # A déjà porté une attaque d'opportunité
        self._momentum_used = False      # A déjà enchaîné après un kill (élan)
        self._acted_this_round = False   # A déjà résolu son attaque du round
        self._damage_taken_round = 0     # Dégâts encaissés ce round
        self._shock = 0                  # Coups violents encaissés (ébranlement)
        self._suppression = 0            # Sous le feu (tirs reçus récemment)
        self._kills = 0                  # Ennemis abattus (sert à l'élan/moral)
        self._last_attacker = None
        self._reaction_text = ""         # Libellé de la dernière réaction
        self._hit_flash_delay = 0        # Estampille du flash de dégâts
        self._lunge_delay = 0            # Estampille du bond de mêlée
        self._threatened_by = 0          # Ennemis au contact (calculé par battle)
        self._witnessed_deaths = 0       # Camarades tombés juste à côté
        self._under_fire = 0             # Traits reçus (touchés ou non)
        self._damage_prev_round = 0      # Dégâts encaissés au round précédent
        self._cells_moved = 0            # Cases parcourues dans le round
        self._calm_rounds = 0            # Rounds consécutifs au calme
        
        # Pré-calculer les propriétés spéciales
        if self.special.get("causes_fear"):
            self.fear_aura = 1
        elif self.special.get("causes_dread"):
            self.fear_aura = 2
        elif self.special.get("causes_terror"):
            self.fear_aura = 3
        
        self.awe = next((int(k.split(":")[1]) for k in self.special if k.startswith("awe:")), 0)
        self.immune_mind = bool(self.special.get("immune_mind"))
        self.regeneration = self.special.get("regeneration", 0)
        self.blood_vengeance = self.special.get("blood_vengeance", 0)
        
        # Cache pour les calculs
        self._max_range = max((a.porte for a in self.armes), default=1) if self.armes else 1
        
        # Type d'attaque principal pour le symbole visuel
        # "spell" > "ranged" > "reach" > "melee"
        if self.spells:
            self.attack_type = "spell"
        elif self._max_range >= 4:
            self.attack_type = "ranged"
        elif self._max_range >= 2:
            self.attack_type = "reach"
        else:
            self.attack_type = "melee"

    def take_damage(self, dmg, is_magic=False, attacker=None, ranged=False):
        """Encaisse des dégâts. Retourne True si le coup a abattu l'unité
        (le moteur s'en sert pour enchaîner: élan du tueur, choc des
        témoins, moral de l'unité voisine...)."""
        if is_magic:
            dmg = max(0, dmg - random.randint(0, self.sauvegarde))
        if dmg <= 0:
            return False

        if self.blood_vengeance > 0 and attacker:
            penalty = self.blood_vengeance
            mr_roll = random.randint(1, 20) + attacker.sauvegarde - penalty
            if mr_roll < 10 + penalty:
                attacker.take_damage(dmg)
                attacker.floating_texts.append(FloatingText("VENGEANCE!", (220, 0, 220), 90))
                return False

        self.pv -= dmg
        self._hit_flash = 12  # Frames de flash rouge (rendu visuel)
        self._hit_flash_delay = FX_CLOCK.current_delay
        self._damage_taken_round += dmg
        if attacker is not None:
            self._last_attacker = attacker
        # Choc: un coup qui emporte une grosse part des PV ébranle l'unité
        if dmg >= max(2, self.max_pv * 0.3):
            self._shock += 1
        if ranged:
            self._suppression += 1
        self.floating_texts.append(FloatingText(f"-{dmg}", (220, 40, 40)))

        if self.pv <= 0:
            if self.pv > -(self.max_pv // 2) and self.regeneration > 0:
                self.is_alive = False
                self.down_timer = random.randint(4, 8)
                self.status_text = "DOWN"
            else:
                self.is_alive = False
                self.status_text = "MORT!"
            return True
        return False

    def start_round(self):
        """Réinitialise l'état de réaction en début de round."""
        # Position de départ du round (pour l'animation) et dernier pas
        # effectué (pour l'anticipation). Auparavant _prev_position n'était
        # mise à jour qu'au mouvement: une unité arrêtée rejouait son ancien
        # déplacement à chaque round et l'IA lui prêtait une vitesse fantôme.
        if self.position is not None:
            pp = self._prev_position or self.position
            self._last_step = (self.position[0] - pp[0], self.position[1] - pp[1])
            self._prev_position = self.position
        self._opportunity_used = False
        self._momentum_used = False
        self._acted_this_round = False
        self._damage_taken_round = 0
        self._cells_moved = 0
        self._reaction_text = ""
        # Les estampilles se lisent par rapport au DÉBUT du round courant:
        # un flash ou un bond encore en cours finit sa course tout de suite
        # (délai remis à zéro) au lieu d'être coupé net.
        self._hit_flash_delay = 0
        self._lunge_delay = 0

    def end_round(self):
        """Vieillissement de la pression subie, EN FIN de round.

        Ces compteurs (traits reçus, camarades tombés, coups violents) sont
        consultés par la phase de moral du round SUIVANT. Les décrémenter
        en début de round les ramenait sous leurs seuils avant même d'être
        lus: les mécaniques de feu nourri et de camarade tombé ne se
        déclenchaient jamais.
        """
        self._damage_prev_round = self._damage_taken_round
        self._suppression = max(0, self._suppression - 1)
        self._shock = max(0, self._shock - 1)
        # Être pris sous un feu nourri pèse même quand les traits manquent:
        # on se met à couvert, on baisse la tête, on ne combat plus pareil.
        self._under_fire = self._under_fire * 2 // 3

    def regenerate(self):
        if not self.is_alive:
            if self.down_timer > 0:
                self.down_timer -= 1
                heal = random.randint(1, 4)
                self.pv += heal
                self.floating_texts.append(FloatingText(f"+{heal}", (100, 220, 100), 60))
                if self.pv >= 1:
                    self.is_alive = True
                    self.status_text = "REVIVED"
                    self.down_timer = 0
            return
        
        if self.regeneration > 0:
            heal = max(1, int(self.max_pv * self.regeneration / 100))
            self.pv = min(self.max_pv, self.pv + heal)
            self.floating_texts.append(FloatingText(f"+{heal}", (40, 220, 40)))

    def get_effective_morale(self):
        return max(0, self.base_morale + self.morale_bonus - self.morale_malus)

    def morale_check(self):
        effective_morale = self.get_effective_morale()
        if effective_morale == 0:
            return False
        return random.randint(1, 6) <= effective_morale

    def apply_fear_effect(self, aura_level, distance):
        """Applique l'effet de peur. La portée est déjà vérifiée par battle.py (4 cases)."""
        if self.immune_mind or aura_level == 0:
            return None
        
        if not hasattr(self, '_fear_malus_applied') or not self._fear_malus_applied:
            self.morale_malus += 1
            self._fear_malus_applied = True
            self.afraid = True
            self.floating_texts.append(FloatingText("-1 Moral", (255, 180, 60), 80))
            
            if self.get_effective_morale() == 0:
                self.fleeing = True
                self.status_text = "FUITE!"
                return "flee"
            else:
                self.status_text = "PEUR"
                return "afraid"
        elif not self.fleeing:
            self.afraid = True
            self.status_text = "PEUR"
            return "afraid"
        return None

    def perform_attacks(self, target, battlefield, battle=None, weapons=None,
                        kind="normal"):
        """Résout les attaques de cette unité sur une cible.

        kind: "normal" | "charge" | "opportunity" (attaque de rupture de
        contact) | "momentum" (enchaînement après un kill) | "reaction"
        (tir de réaction pendant le mouvement adverse).
        """
        events = []
        self._last_attack_killed = False
        # Estampille de l'action: tous les effets de cette attaque sont
        # positionnés dans le temps par rapport à elle (départ du tir,
        # temps de vol du projectile, impact...).
        base_t = FX_CLOCK.current_delay
        dist = battlefield.manhattan_distance(self.position, target.position)
        armes = self.armes if weapons is None else weapons

        if dist > self._max_range or self.fleeing:
            self.current_target = None
            return events

        # Vérifier si un mur bloque le CaC
        target_on_rampart = battlefield.is_rampart(*target.position)
        attacker_on_stairs = (self.position in battlefield.stairs) if battlefield.stairs else False

        if target_on_rampart and self._max_range < 4 and not attacker_on_stairs:
            # CaC ne peut pas atteindre les unités sur les remparts (sauf depuis les escaliers)
            self.floating_texts.append(FloatingText("Mur!", (180, 180, 180)))
            self.current_target = None
            return events

        # Bonus sauvegarde rempart (+2 pour les défenseurs sur rempart)
        wall_save_bonus = 2 if target_on_rampart else 0

        # Bonus toucher rempart (-1 = plus facile de toucher depuis le mur)
        wall_toucher_bonus = -1 if self._on_wall else 0

        self.current_target = target

        # Animation de lunge CaC: si l'unité est au corps à corps, elle bondit
        # brièvement vers la cible (pas pour les tirs à distance)
        if dist <= 2 and self._max_range <= 2:
            self._lunge_target = target.position  # grid coords
            self._lunge_timer = 20  # 20 frames de lunge
            self._lunge_delay = FX_CLOCK.current_delay

        # Bonus anti-type
        anti_toucher = 0
        anti_blesser = 0
        if self.anti_infanterie and target.unit_type == "Infanterie":
            anti_toucher = -1  # Plus facile à toucher (valeur basse = mieux)
            anti_blesser = -1
        if self.anti_large and target.unit_type in ("Large", "Cavalerie", "Monstre"):
            anti_toucher = -1
            anti_blesser = -1

        # ─── Tir d'arrêt: on lâche la volée à la hâte, sur une cible qui
        # débouche. Le gain de tempo se paie d'un peu de précision. ───
        snap_toucher = 1 if kind == "reaction" else 0

        # ─── Prise à revers: une cible déjà accrochée par un camarade se
        # défend moins bien. C'est ce qui rend le débordement PAYANT et
        # récompense la concentration des efforts. ───
        flank_toucher = 0
        if battle is not None and dist <= 2 and self._max_range <= 2:
            tx_f, ty_f = target.position
            engaged_allies = 0
            for a in battle.get_allies(self):
                if a is self or not a.is_alive or a.fleeing:
                    continue
                if abs(a.position[0] - tx_f) + abs(a.position[1] - ty_f) <= 1:
                    engaged_allies += 1
                    break
            if engaged_allies >= 1:
                flank_toucher = -1
                if kind == "normal":
                    self.floating_texts.append(
                        FloatingText("À revers!", (255, 200, 120), 45))


        # Bonus de charge (appliqué si has_charged ce round)
        charge_toucher = 0
        charge_blesser = 0
        charge_perf = 0
        charge_degats = 0
        if self.has_charged:
            if self.charge_montee:
                charge_degats = 1
            elif self.charge_aida:
                charge_blesser = -1
            self.has_charged = False  # Reset après application

        for arme in armes:
            if dist > arme.porte:
                continue
            # Ligne de vue: un mur ou une porte fermée bloque les tirs
            if arme.porte >= 4 and not battlefield.has_line_of_fire(self, target):
                continue

            is_ranged_weapon = arme.porte >= 4
            # Sprite du projectile: trait de baliste, carreau ou flèche
            if self.is_artillery or arme.porte >= 16:
                proj_kind = "ballista"
            elif "arbal" in arme.name.lower() or "carreau" in arme.name.lower():
                proj_kind = "bolt"
            else:
                proj_kind = "arrow"
            # Temps de vol: le tir part maintenant, il touche plus tard.
            # Les textes (Raté!/-3) sont donc décalés à l'ARRIVÉE.
            flight = 16 if is_ranged_weapon else 0
            FX_CLOCK.at(base_t + flight)

            for _ in range(arme.nb_attaque):
                if is_ranged_weapon:
                    target._under_fire += 1
                # Événement visuel selon le type d'arme / le type d'action
                if is_ranged_weapon:
                    events.append({'type': 'arrow', 'from_grid': self.position,
                                   'to_grid': target.position, 'kind': kind,
                                   'proj': proj_kind, 'at': 0})
                elif arme.porte >= 2:
                    events.append({'type': 'reach', 'from_grid': self.position,
                                   'to_grid': target.position, 'kind': kind,
                                   'at': 0})
                else:
                    events.append({'type': 'melee', 'from_grid': self.position,
                                   'to_grid': target.position, 'kind': kind,
                                   'at': 0})

                # Résolution combat avec bonus
                toucher_final = (arme.toucher + (1 if self.afraid else 0)
                                 + anti_toucher + charge_toucher + wall_toucher_bonus
                                 + flank_toucher + snap_toucher)
                blesser_final = arme.blesser + anti_blesser + charge_blesser
                perf_final = arme.perforation + charge_perf

                if dist <= 1 and target.awe > 0 and not self.morale_check():
                    target.floating_texts.append(FloatingText("Intimidé!", (255, 180, 60)))
                    continue

                # Toucher
                if random.randint(1, 6) < toucher_final:
                    target.floating_texts.append(FloatingText("Raté!", (255, 220, 80)))
                    continue

                # Blessure
                if random.randint(1, 6) < blesser_final:
                    target.floating_texts.append(FloatingText("Pas blessé!", (255, 200, 120)))
                    continue

                # Sauvegarde
                save_modifie = min(7, target.sauvegarde - perf_final - wall_save_bonus)
                if random.randint(1, 6) >= save_modifie:
                    target.floating_texts.append(FloatingText("Sauvé!", (100, 200, 255)))
                    continue

                # Dégâts
                dmg = arme.lancer_degats() + charge_degats
                killed = target.take_damage(dmg, False, self, ranged=is_ranged_weapon)
                events.append({
                    'type': 'impact',
                    'at_grid': target.position,
                    'from_grid': self.position,
                    'power': min(2.5, dmg / max(1.0, target.max_pv * 0.25)),
                    'ranged': is_ranged_weapon,
                    'fx': 'ranged' if is_ranged_weapon else 'melee',
                    'at': flight + (0 if is_ranged_weapon else 2),
                })
                if killed:
                    self._kills += 1
                    self._last_attack_killed = True
                    if not target.is_alive and target.down_timer <= 0:
                        events.append({'type': 'shockwave', 'at_grid': target.position,
                                       'unit_size': target.size,
                                       'at': flight + 4})
                    break  # Cible abattue: inutile de continuer à la frapper

            if not target.is_alive:
                break

        FX_CLOCK.at(base_t)
        return events

    def cast_random_spell(self, battle):
        """Lance un sort disponible (pas en cooldown). Gère 5 types de sorts."""
        events = []
        if not self.spells or self.fleeing:
            return events

        # Tick cooldowns
        for s in self.spells:
            s.tick_cooldown()

        # Sorts prêts
        ready = [s for s in self.spells if s.is_ready()]
        if not ready:
            return events

        # Nombre de sorts lançables ce round (trait "Sort de bataille[N]")
        max_casts = getattr(self, 'spells_per_round', 1)
        casts_done = 0

        # Priorité tactique des sorts:
        # heal → utile si allié blessé à portée
        # fireball → utile si plusieurs ennemis regroupés
        # armor → buffer un allié vulnérable
        # projectile → tir ciblé
        # wall → ralentir l'ennemi (dernier recours)
        def _spell_priority(spell):
            if spell.spell_type == "heal":
                allies = battle.get_allies(self)
                wounded_count = sum(
                    1 for a in allies
                    if a.is_alive and a != self and a.hp < a.max_hp * 0.75
                    and battle.battlefield.manhattan_distance(self.position, a.position) <= spell.porte
                )
                return (0, -wounded_count)
            elif spell.spell_type == "fireball":
                enemies = battle.get_enemies(self)
                close_count = sum(
                    1 for e in enemies
                    if e.is_alive
                    and battle.battlefield.manhattan_distance(self.position, e.position) <= spell.porte
                )
                return (1, -close_count)
            elif spell.spell_type == "armor":
                allies = battle.get_allies(self)
                vulnerable = sum(
                    1 for a in allies
                    if a.is_alive and not getattr(a, '_armor_buff', False)
                    and battle.battlefield.manhattan_distance(self.position, a.position) <= spell.porte
                )
                return (2, -vulnerable)
            elif spell.spell_type == "projectile":
                return (3, 0)
            elif spell.spell_type == "wall":
                return (4, 0)
            return (5, 0)

        ready.sort(key=_spell_priority)
        
        for spell in ready:
            if casts_done >= max_casts:
                break
            
            cast_ok = False
            
            if spell.spell_type == "fireball":
                cast_ok = self._cast_fireball(spell, battle, events)
            elif spell.spell_type == "heal":
                cast_ok = self._cast_heal(spell, battle, events)
            elif spell.spell_type == "armor":
                cast_ok = self._cast_armor(spell, battle, events)
            elif spell.spell_type == "projectile":
                cast_ok = self._cast_projectile(spell, battle, events)
            elif spell.spell_type == "wall":
                cast_ok = self._cast_wall(spell, battle, events)

            if cast_ok:
                spell.use()
                casts_done += 1

        return events
    
    def _cast_fireball(self, spell, battle, events):
        """Boule de feu — AoE sur la zone 3×3 couvrant le plus d'ennemis."""
        enemies = [e for e in battle.get_enemies(self) if e.is_alive]
        if not enemies:
            return False

        half = spell.aoe_size // 2

        # Trouver l'ennemi dont la zone AoE touche le plus d'ennemis à portée
        best_target = None
        best_count = -1
        for candidate in enemies:
            dist = battle.battlefield.manhattan_distance(self.position, candidate.position)
            if dist > spell.porte:
                continue
            tx, ty = candidate.position
            count = sum(
                1 for e in enemies
                if abs(e.position[0] - tx) <= half and abs(e.position[1] - ty) <= half
            )
            if count > best_count:
                best_count = count
                best_target = candidate

        target = best_target
        if not target:
            return False

        base_t = FX_CLOCK.current_delay
        FLIGHT = 22
        events.append({
            'type': 'fireball',
            'from_grid': self.position,
            'to_grid': target.position,
            'aoe_size': spell.aoe_size,
            'at': 0,
        })

        self.floating_texts.append(FloatingText("Boule de feu!", (255, 120, 0), 70))

        # Les dégâts (et leurs textes) tombent à l'impact, pas au départ
        FX_CLOCK.at(base_t + FLIGHT)

        # Dégâts sur zone
        tx, ty = target.position
        for enemy in battle.get_enemies(self):
            if not enemy.is_alive:
                continue
            ex, ey = enemy.position
            if abs(ex - tx) <= half and abs(ey - ty) <= half:
                if random.randint(1, 6) < spell.toucher:
                    enemy.floating_texts.append(FloatingText("Raté!", (255, 220, 80)))
                    continue
                if spell.blesser > 1 and random.randint(1, 6) < spell.blesser:
                    enemy.floating_texts.append(FloatingText("Résiste!", (255, 200, 120)))
                    continue
                save_mod = min(7, enemy.sauvegarde + spell.perforation)
                if random.randint(1, 6) >= save_mod:
                    enemy.floating_texts.append(FloatingText("Sauvé!", (100, 200, 255)))
                    continue
                dmg_f = spell.lancer_degats()
                if enemy.take_damage(dmg_f, False, self):
                    self._kills += 1
                events.append({'type': 'impact', 'at_grid': enemy.position,
                               'from_grid': target.position,
                               'power': min(2.5, dmg_f / max(1.0, enemy.max_pv * 0.25)),
                               'ranged': True, 'fx': 'fire', 'at': FLIGHT + 2})

        FX_CLOCK.at(base_t)
        return True

    def _cast_heal(self, spell, battle, events):
        """Soin — soigne totalement l'allié le plus blessé à portée."""
        allies = battle.get_allies(self)
        wounded = []
        for ally in allies:
            if ally.is_alive and ally != self and ally.hp < ally.max_hp:
                d = battle.battlefield.manhattan_distance(self.position, ally.position)
                if d <= spell.porte:
                    wounded.append((ally.hp / ally.max_hp, ally))

        if not wounded:
            return False

        wounded.sort(key=lambda x: x[0])
        target = wounded[0][1]

        events.append({'type': 'heal', 'from_grid': self.position, 'to_grid': target.position})

        healed = target.max_hp - target.hp
        target.pv = target.max_pv
        target.floating_texts.append(FloatingText(f"+{healed} SOIN!", (50, 255, 100), 80))
        self.floating_texts.append(FloatingText("Soin!", (50, 255, 100), 60))

        return True

    def _cast_armor(self, spell, battle, events):
        """Armure magique — +2 de sauvegarde à l'allié le plus vulnérable à portée."""
        candidates = [self]
        for ally in battle.get_allies(self):
            if ally.is_alive and ally != self:
                d = battle.battlefield.manhattan_distance(self.position, ally.position)
                if d <= spell.porte:
                    candidates.append(ally)

        unbuffed = [c for c in candidates if not getattr(c, '_armor_buff', False)]
        if not unbuffed:
            return False

        target = min(unbuffed, key=lambda c: (c.sauvegarde, c.hp / max(1, c.max_hp)))

        target._armor_buff = True
        target._armor_buff_rounds = spell.duration
        target._armor_buff_amount = spell.bonus
        target.sauvegarde = max(1, target.sauvegarde - spell.bonus)

        events.append({'type': 'armor', 'at_grid': target.position, 'unit_size': target.size})

        target.floating_texts.append(FloatingText(f"+{spell.bonus} Armure!", (80, 180, 255), 70))
        self.floating_texts.append(FloatingText("Armure!", (80, 180, 255), 60))

        return True

    def _cast_projectile(self, spell, battle, events):
        """Projectile magique — cible unique, longue portée."""
        target = battle.get_closest_enemy(self)
        if not target:
            return False
        dist = battle.battlefield.manhattan_distance(self.position, target.position)
        if dist > spell.porte:
            return False

        base_t = FX_CLOCK.current_delay
        FLIGHT = 16
        events.append({'type': 'magic_projectile', 'from_grid': self.position,
                       'to_grid': target.position, 'at': 0})

        self.floating_texts.append(FloatingText("Projectile!", (180, 80, 255), 60))
        FX_CLOCK.at(base_t + FLIGHT)

        if random.randint(1, 6) < spell.toucher:
            target.floating_texts.append(FloatingText("Raté!", (255, 220, 80)))
            FX_CLOCK.at(base_t)
            return True
        if spell.blesser > 1 and random.randint(1, 6) < spell.blesser:
            target.floating_texts.append(FloatingText("Résiste!", (255, 200, 120)))
            FX_CLOCK.at(base_t)
            return True

        dmg_p = spell.lancer_degats()
        if target.take_damage(dmg_p, False, self):
            self._kills += 1
        events.append({'type': 'impact', 'at_grid': target.position,
                       'from_grid': self.position,
                       'power': min(2.5, dmg_p / max(1.0, target.max_pv * 0.25)),
                       'ranged': True, 'fx': 'magic', 'at': FLIGHT + 2})
        FX_CLOCK.at(base_t)
        return True

    def _cast_wall(self, spell, battle, events):
        """Mur de force — crée des obstacles devant les ennemis les plus proches."""
        enemies = [(battle.battlefield.manhattan_distance(self.position, e.position), e)
                   for e in battle.get_enemies(self) if e.is_alive]
        if not enemies:
            return False

        enemies.sort(key=lambda x: x[0])
        bf = battle.battlefield

        wall_positions = []
        for _, enemy in enemies:
            if len(wall_positions) >= spell.nb_obstacles:
                break
            ex, ey = enemy.position
            dx = 1 if self.position[0] > ex else -1 if self.position[0] < ex else 0
            dy = 1 if self.position[1] > ey else -1 if self.position[1] < ey else 0

            wx, wy = ex + dx, ey + dy
            if bf.is_valid(wx, wy) and not bf.is_occupied(wx, wy):
                wall_positions.append((wx, wy))

        if not wall_positions:
            return False

        for wx, wy in wall_positions:
            original = bf.grid[wx][wy]
            if original in (2, 3, 4, 5):
                continue
            bf.grid[wx][wy] = 1  # Obstacle
            if not hasattr(bf, '_temp_walls'):
                bf._temp_walls = []
            bf._temp_walls.append((wx, wy, spell.wall_duration, original))

        events.append({'type': 'wall', 'positions': wall_positions})

        self.floating_texts.append(FloatingText("Mur de force!", (160, 80, 220), 70))
        return True
    
    def tick_armor_buff(self):
        """Appelé chaque round pour décrémenter les buffs d'armure."""
        if getattr(self, '_armor_buff', False):
            self._armor_buff_rounds -= 1
            if self._armor_buff_rounds <= 0:
                self.sauvegarde += self._armor_buff_amount
                self._armor_buff = False
                self.floating_texts.append(FloatingText("Armure dissipée", (150, 150, 200), 50))

    @property
    def is_artillery(self):
        """Machine de guerre: type 'Artillerie' (Baliste, Scorpion, Catapulte...)
        ou unité immobile dotée d'une arme de tir. Important: les machines du
        jeu ont une vitesse de 1-2 (repositionnement lent), PAS 0 — c'est
        pourquoi le test `vitesse <= 0` seul ne les détectait jamais."""
        return self.unit_type == "Artillerie" or (self.vitesse <= 0 and self._max_range >= 4)

    @property
    def hp(self):
        return self.pv

    @hp.setter
    def hp(self, value):
        self.pv = value

    @property
    def max_hp(self):
        return self.max_pv

    @max_hp.setter
    def max_hp(self, value):
        self.max_pv = value

    @property
    def speed(self):
        return self.vitesse

    @speed.setter
    def speed(self, value):
        self.vitesse = value

    @property
    def attacks(self):
        return self.armes

    @attacks.setter
    def attacks(self, value):
        self.armes = value

    @property
    def morale(self):
        return self.base_morale

    @morale.setter
    def morale(self, value):
        self.base_morale = value