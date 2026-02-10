import random


class Arme:
    def __init__(self, name, nb_attaque, toucher, blesser, perforation, degats, porte=1, special=None):
        self.name = name
        self.nb_attaque = nb_attaque
        self.toucher = toucher
        self.blesser = blesser
        self.perforation = perforation
        self.degats = degats
        self.porte = porte
        self.range = porte
        self.special = special or {}
        
        # Pré-calculer les infos de dégâts pour éviter parsing répété
        # Supporte: "1", "1d6", "1+1d4", "2+1d3"
        self._bonus = 0
        degats_str = str(degats).lower().strip()
        
        if '+' in degats_str and 'd' in degats_str:
            # Format "X+YdZ"
            parts = degats_str.split('+')
            try:
                self._bonus = int(parts[0])
            except ValueError:
                self._bonus = 0
            dice_part = parts[1]
            dp = dice_part.split('d')
            self._nb_des = int(dp[0])
            self._faces = int(dp[1])
            self._is_dice = True
        elif 'd' in degats_str:
            dp = degats_str.split('d')
            self._nb_des = int(dp[0])
            self._faces = int(dp[1])
            self._is_dice = True
        else:
            self._nb_des = 0
            self._faces = 0
            self._is_dice = False
            try:
                self._fixed_damage = int(float(degats_str))
            except (ValueError, TypeError):
                self._fixed_damage = 1
    
    def lancer_degats(self):
        if self._is_dice:
            return self._bonus + sum(random.randint(1, self._faces) for _ in range(self._nb_des))
        return self._fixed_damage


class Spell:
    def __init__(self, name, damage, aoe_radius=0, perforation=0, auto_hit=False):
        self.name = name
        self.damage = damage
        self.aoe_radius = aoe_radius
        self.perforation = perforation
        self.auto_hit = auto_hit
        self.is_fire = "feu" in name.lower()
        
        # Pré-calculer les infos de dégâts
        self._bonus = 0
        if isinstance(damage, str):
            damage_str = damage.lower().strip()
            if '+' in damage_str and 'd' in damage_str:
                parts = damage_str.split('+')
                try:
                    self._bonus = int(parts[0])
                except ValueError:
                    self._bonus = 0
                dp = parts[1].split('d')
                self._nb_des = int(dp[0])
                self._faces = int(dp[1])
                self._is_dice = True
                self._is_tuple = False
            elif 'd' in damage_str:
                dp = damage_str.split('d')
                self._nb_des = int(dp[0])
                self._faces = int(dp[1])
                self._is_dice = True
                self._is_tuple = False
            else:
                self._is_dice = False
                self._is_tuple = False
                self._fixed = int(float(damage_str))
        elif isinstance(damage, tuple):
            self._is_dice = False
            self._is_tuple = True
            self._min, self._max = damage
        else:
            self._is_dice = False
            self._is_tuple = False
            self._fixed = int(damage)
    
    def lancer_degats(self):
        if self._is_dice:
            return self._bonus + sum(random.randint(1, self._faces) for _ in range(self._nb_des))
        elif self._is_tuple:
            return random.randint(self._min, self._max)
        return self._fixed
