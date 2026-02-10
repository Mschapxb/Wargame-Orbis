import random
from collections import deque

from effects import FloatingText, Projectile, AttackLine


class Unit:
    def __init__(self, name, pv, vitesse, morale, sauvegarde, color,
                 armes=None, spells=None, special=None, role="front"):
        self.name = name
        self.token_name = ""  # Nom complet pour le fichier token (set par unit_library)
        self.pv = pv
        self.max_pv = pv
        self.hp = pv
        self.max_hp = pv
        self.vitesse = vitesse
        self.speed = vitesse
        self.morale = morale
        self.base_morale = morale
        self.sauvegarde = sauvegarde
        self.armes = armes or []
        self.attacks = self.armes
        self.spells = spells or []
        self.special = special or {}
        self.role = role
        self.position = (0, 0)
        self.is_alive = True
        self.color = color
        self.afraid = False
        self.fleeing = False
        self.status_text = ""
        self.floating_texts = deque(maxlen=10)
        self.down_timer = 0
        self.fear_aura = 0
        self.current_target = None
        self.morale_malus = 0
        
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

    def take_damage(self, dmg, is_magic=False, attacker=None):
        if is_magic:
            dmg = max(0, dmg - random.randint(0, self.sauvegarde))
        if dmg <= 0:
            return
        
        if self.blood_vengeance > 0 and attacker:
            penalty = self.blood_vengeance
            mr_roll = random.randint(1, 20) + attacker.sauvegarde - penalty
            if mr_roll < 10 + penalty:
                attacker.take_damage(dmg)
                attacker.floating_texts.append(FloatingText("VENGEANCE!", (220, 0, 220), 90))
                return
        
        self.pv -= dmg
        self.hp = self.pv
        self.floating_texts.append(FloatingText(f"-{dmg}", (220, 40, 40)))
        
        if self.pv <= 0:
            if self.pv > -(self.max_pv // 2) and self.regeneration > 0:
                self.is_alive = False
                self.down_timer = random.randint(4, 8)
                self.status_text = "DOWN"
            else:
                self.is_alive = False
                self.status_text = "MORT!"

    def regenerate(self):
        if not self.is_alive:
            if self.down_timer > 0:
                self.down_timer -= 1
                heal = random.randint(1, 4)
                self.pv += heal
                self.hp = self.pv
                self.floating_texts.append(FloatingText(f"+{heal}", (100, 220, 100), 60))
                if self.pv >= 1:
                    self.is_alive = True
                    self.status_text = "REVIVED"
                    self.down_timer = 0
            return
        
        if self.regeneration > 0:
            heal = max(1, int(self.max_pv * self.regeneration / 100))
            self.pv = min(self.max_pv, self.pv + heal)
            self.hp = self.pv
            self.floating_texts.append(FloatingText(f"+{heal}", (40, 220, 40)))

    def get_effective_morale(self):
        return max(0, self.base_morale - self.morale_malus)

    def morale_check(self):
        effective_morale = self.get_effective_morale()
        if effective_morale == 0:
            return False
        return random.randint(1, 6) <= effective_morale

    def apply_fear_effect(self, aura_level, distance):
        if self.immune_mind or aura_level == 0 or distance > aura_level:
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

    def perform_attacks(self, target, battlefield, visual_effects, cell_size):
        dist = battlefield.manhattan_distance(self.position, target.position)
        
        if dist > self._max_range or self.fleeing:
            self.current_target = None
            return
        
        self.current_target = target
        start_px = (self.position[0] * cell_size + cell_size // 2,
                    self.position[1] * cell_size + cell_size // 2)
        end_px = (target.position[0] * cell_size + cell_size // 2,
                  target.position[1] * cell_size + cell_size // 2)
        
        for arme in self.armes:
            if dist > arme.porte:
                continue
            
            for _ in range(arme.nb_attaque):
                # Effet visuel selon le type d'arme
                if arme.porte >= 4:
                    # Tir à distance (arc, arbalète, catapulte)
                    visual_effects['projectiles'].append(
                        Projectile(start_px, end_px, (200, 180, 100), 40, "arrow", cell_size)
                    )
                elif arme.porte >= 2:
                    # CaC à portée (lance, hallebarde, pique)
                    visual_effects['attack_lines'].append(
                        AttackLine(start_px, end_px, (255, 180, 50), 25)
                    )
                else:
                    # CaC pur (épée, hache, griffes)
                    visual_effects['attack_lines'].append(
                        AttackLine(start_px, end_px, (255, 100, 100), 25)
                    )
                
                # Résolution combat
                toucher_modifie = arme.toucher + (1 if self.afraid else 0)
                
                if dist <= 1 and target.awe > 0 and not self.morale_check():
                    target.floating_texts.append(FloatingText("Intimidé!", (255, 180, 60)))
                    continue
                
                # Toucher
                if random.randint(1, 6) < toucher_modifie:
                    target.floating_texts.append(FloatingText("Raté!", (255, 220, 80)))
                    continue
                
                # Blessure
                if random.randint(1, 6) < arme.blesser:
                    target.floating_texts.append(FloatingText("Pas blessé!", (255, 200, 120)))
                    continue
                
                # Sauvegarde
                save_modifie = min(7, target.sauvegarde + arme.perforation)
                if random.randint(1, 6) >= save_modifie:
                    target.floating_texts.append(FloatingText("Sauvé!", (100, 200, 255)))
                    continue
                
                # Dégâts
                target.take_damage(arme.lancer_degats(), False, self)

    def cast_random_spell(self, battle, visual_effects, cell_size):
        if not self.spells or random.random() > 0.4 or self.fleeing:
            return
        
        spell = random.choice(self.spells)
        target = battle.get_closest_enemy(self)
        if not target:
            return
        
        target_pos = target.position
        
        # Effet visuel
        start_px = (self.position[0] * cell_size + cell_size // 2,
                    self.position[1] * cell_size + cell_size // 2)
        end_px = (target_pos[0] * cell_size + cell_size // 2,
                  target_pos[1] * cell_size + cell_size // 2)
        
        ptype = "fireball" if spell.is_fire else "magic"
        color = (255, 100, 0) if spell.is_fire else (150, 100, 255)
        visual_effects['projectiles'].append(
            Projectile(start_px, end_px, color, 35, ptype, cell_size)
        )
        
        # Trouver unités affectées
        if spell.aoe_radius > 0:
            affected_units = battle.get_units_in_radius(target_pos, spell.aoe_radius, battle.get_enemies(self))
        else:
            affected_units = [target]
        
        # Appliquer dégâts
        for affected_unit in affected_units:
            if spell.auto_hit:
                save_modifie = min(7, affected_unit.sauvegarde + spell.perforation)
                if random.randint(1, 6) >= save_modifie:
                    affected_unit.floating_texts.append(FloatingText("Sauvé!", (100, 200, 255)))
                    continue
                affected_unit.take_damage(spell.lancer_degats(), False, self)
            else:
                affected_unit.take_damage(spell.lancer_degats(), True)
