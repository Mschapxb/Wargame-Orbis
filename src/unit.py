import random
from collections import deque

from effects import (FloatingText, Projectile, AttackLine,
                     AoeExplosion, HealBeam, ArmorShimmer, WallEffect)


class Unit:
    def __init__(self, name, pv, vitesse, morale, sauvegarde, color,
                 armes=None, spells=None, special=None, role="front",
                 size=1, unit_type="Infanterie"):
        self.name = name
        self.token_name = ""
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
        """Lance un sort disponible (pas en cooldown). Gère 5 types de sorts."""
        if not self.spells or self.fleeing:
            return
        
        # Tick cooldowns
        for s in self.spells:
            s.tick_cooldown()
        
        # Sorts prêts
        ready = [s for s in self.spells if s.is_ready()]
        if not ready:
            return
        
        # Nombre de sorts lançables ce round (trait "Sort de bataille[N]")
        max_casts = getattr(self, 'spells_per_round', 1)
        casts_done = 0
        
        random.shuffle(ready)
        
        for spell in ready:
            if casts_done >= max_casts:
                break
            
            cast_ok = False
            
            if spell.spell_type == "fireball":
                cast_ok = self._cast_fireball(spell, battle, visual_effects, cell_size)
            elif spell.spell_type == "heal":
                cast_ok = self._cast_heal(spell, battle, visual_effects, cell_size)
            elif spell.spell_type == "armor":
                cast_ok = self._cast_armor(spell, battle, visual_effects, cell_size)
            elif spell.spell_type == "projectile":
                cast_ok = self._cast_projectile(spell, battle, visual_effects, cell_size)
            elif spell.spell_type == "wall":
                cast_ok = self._cast_wall(spell, battle, visual_effects, cell_size)
            
            if cast_ok:
                spell.use()
                casts_done += 1
    
    def _pos_to_px(self, pos, cell_size):
        return (pos[0] * cell_size + cell_size // 2, pos[1] * cell_size + cell_size // 2)
    
    def _cast_fireball(self, spell, battle, visual_effects, cell_size):
        """Boule de feu — AoE sur zone 3×3 autour de l'ennemi le plus proche."""
        target = battle.get_closest_enemy(self)
        if not target:
            return False
        dist = battle.battlefield.manhattan_distance(self.position, target.position)
        if dist > spell.porte:
            return False
        
        start_px = self._pos_to_px(self.position, cell_size)
        end_px = self._pos_to_px(target.position, cell_size)
        
        # Projectile boule de feu
        visual_effects['projectiles'].append(
            Projectile(start_px, end_px, (255, 100, 0), 35, "fireball", cell_size)
        )
        
        # Explosion AoE
        aoe_radius_px = (spell.aoe_size // 2) * cell_size + cell_size // 2
        visual_effects.setdefault('aoe_explosions', []).append(
            AoeExplosion(end_px, aoe_radius_px, (255, 120, 0), 35)
        )
        
        self.floating_texts.append(FloatingText("Boule de feu!", (255, 120, 0), 70))
        
        # Dégâts sur zone
        half = spell.aoe_size // 2
        tx, ty = target.position
        for enemy in battle.get_enemies(self):
            if not enemy.is_alive:
                continue
            ex, ey = enemy.position
            if abs(ex - tx) <= half and abs(ey - ty) <= half:
                # Toucher
                if random.randint(1, 6) < spell.toucher:
                    enemy.floating_texts.append(FloatingText("Raté!", (255, 220, 80)))
                    continue
                # Blesser (1 = blesse d'office)
                if spell.blesser > 1 and random.randint(1, 6) < spell.blesser:
                    enemy.floating_texts.append(FloatingText("Résiste!", (255, 200, 120)))
                    continue
                # Sauvegarde
                save_mod = min(7, enemy.sauvegarde + spell.perforation)
                if random.randint(1, 6) >= save_mod:
                    enemy.floating_texts.append(FloatingText("Sauvé!", (100, 200, 255)))
                    continue
                enemy.take_damage(spell.lancer_degats(), False, self)
        
        return True
    
    def _cast_heal(self, spell, battle, visual_effects, cell_size):
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
        
        start_px = self._pos_to_px(self.position, cell_size)
        end_px = self._pos_to_px(target.position, cell_size)
        
        visual_effects.setdefault('heal_beams', []).append(
            HealBeam(start_px, end_px, 30)
        )
        
        healed = target.max_hp - target.hp
        target.hp = target.max_hp
        target.pv = target.max_pv
        target.floating_texts.append(FloatingText(f"+{healed} SOIN!", (50, 255, 100), 80))
        self.floating_texts.append(FloatingText("Soin!", (50, 255, 100), 60))
        
        return True
    
    def _cast_armor(self, spell, battle, visual_effects, cell_size):
        """Armure magique — +2 de sauvegarde à soi-même ou un allié."""
        # Chercher un allié sans buff à portée (ou soi-même)
        candidates = [self]
        for ally in battle.get_allies(self):
            if ally.is_alive and ally != self:
                d = battle.battlefield.manhattan_distance(self.position, ally.position)
                if d <= spell.porte:
                    candidates.append(ally)
        
        # Préférer ceux qui n'ont pas déjà le buff
        unbuffed = [c for c in candidates if not getattr(c, '_armor_buff', False)]
        target = random.choice(unbuffed) if unbuffed else None
        
        if not target:
            return False
        
        # Appliquer le buff
        target._armor_buff = True
        target._armor_buff_rounds = spell.duration
        target._armor_buff_amount = spell.bonus
        target.sauvegarde = max(1, target.sauvegarde - spell.bonus)
        
        px = self._pos_to_px(target.position, cell_size)
        ur = max(3, cell_size // 2 - 4) * max(1, target.size)
        visual_effects.setdefault('armor_shimmers', []).append(
            ArmorShimmer(px, ur, 40)
        )
        
        target.floating_texts.append(FloatingText(f"+{spell.bonus} Armure!", (80, 180, 255), 70))
        self.floating_texts.append(FloatingText("Armure!", (80, 180, 255), 60))
        
        return True
    
    def _cast_projectile(self, spell, battle, visual_effects, cell_size):
        """Projectile magique — cible unique, longue portée."""
        target = battle.get_closest_enemy(self)
        if not target:
            return False
        dist = battle.battlefield.manhattan_distance(self.position, target.position)
        if dist > spell.porte:
            return False
        
        start_px = self._pos_to_px(self.position, cell_size)
        end_px = self._pos_to_px(target.position, cell_size)
        
        # 3 petits projectiles violets
        for i in range(3):
            offset = (random.randint(-8, 8), random.randint(-8, 8))
            ep = (end_px[0] + offset[0], end_px[1] + offset[1])
            visual_effects['projectiles'].append(
                Projectile(start_px, ep, (180, 80, 255), 25 + i * 5, "magic", cell_size)
            )
        
        self.floating_texts.append(FloatingText("Projectile!", (180, 80, 255), 60))
        
        # Toucher
        if random.randint(1, 6) < spell.toucher:
            target.floating_texts.append(FloatingText("Raté!", (255, 220, 80)))
            return True
        # Blesser (1 = d'office)
        if spell.blesser > 1 and random.randint(1, 6) < spell.blesser:
            target.floating_texts.append(FloatingText("Résiste!", (255, 200, 120)))
            return True
        
        target.take_damage(spell.lancer_degats(), False, self)
        return True
    
    def _cast_wall(self, spell, battle, visual_effects, cell_size):
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
            # Placer l'obstacle entre l'ennemi et nous
            dx = 1 if self.position[0] > ex else -1 if self.position[0] < ex else 0
            dy = 1 if self.position[1] > ey else -1 if self.position[1] < ey else 0
            
            wx, wy = ex + dx, ey + dy
            if bf.is_valid(wx, wy) and not bf.is_occupied(wx, wy):
                wall_positions.append((wx, wy))
        
        if not wall_positions:
            return False
        
        # Créer les obstacles temporaires
        for wx, wy in wall_positions:
            bf.grid[wx][wy] = 1  # Obstacle
            # Stocker pour retrait futur
            if not hasattr(bf, '_temp_walls'):
                bf._temp_walls = []
            bf._temp_walls.append((wx, wy, spell.wall_duration))
        
        visual_effects.setdefault('wall_effects', []).append(
            WallEffect(wall_positions, cell_size, 25)
        )
        
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