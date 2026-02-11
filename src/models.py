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
        
        self._bonus = 0
        degats_str = str(degats).lower().strip()
        
        if '+' in degats_str and 'd' in degats_str:
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


# ═══════════════════════════════════════════════════════════════
#                          SORTS
# ═══════════════════════════════════════════════════════════════

class Spell:
    """Classe de base pour les sorts.
    
    Attributs communs:
        name        : str   — nom du sort
        spell_type  : str   — "fireball", "heal", "armor", "projectile", "wall"
        porte       : int   — portée en cases
        cooldown    : int   — rounds de recharge (0 = chaque round)
        _cd_timer   : int   — compteur interne de cooldown
    """
    def __init__(self, name, spell_type, porte=9, cooldown=0):
        self.name = name
        self.spell_type = spell_type
        self.porte = porte
        self.cooldown = cooldown
        self._cd_timer = 0
    
    def is_ready(self):
        return self._cd_timer <= 0
    
    def use(self):
        self._cd_timer = self.cooldown
    
    def tick_cooldown(self):
        if self._cd_timer > 0:
            self._cd_timer -= 1


class SpellFireball(Spell):
    """Boule de feu — AoE 3×3, dégâts + toucher/blesser/perforation."""
    def __init__(self, porte=9, toucher=3, blesser=1, perforation=-2,
                 degats="1d4", aoe_size=3, cooldown=2):
        super().__init__("Boule de feu", "fireball", porte, cooldown)
        self.toucher = toucher
        self.blesser = blesser
        self.perforation = perforation
        self.degats = degats
        self.aoe_size = aoe_size  # 3 = zone 3×3
        
        # Parser dégâts
        self._parse_degats(degats)
    
    def _parse_degats(self, degats):
        s = str(degats).lower().strip()
        self._bonus = 0
        if '+' in s and 'd' in s:
            parts = s.split('+')
            self._bonus = int(parts[0])
            dp = parts[1].split('d')
            self._nb_des, self._faces = int(dp[0]), int(dp[1])
            self._is_dice = True
        elif 'd' in s:
            dp = s.split('d')
            self._nb_des, self._faces = int(dp[0]), int(dp[1])
            self._is_dice = True
        else:
            self._is_dice = False
            self._fixed = int(float(s))
    
    def lancer_degats(self):
        if self._is_dice:
            return self._bonus + sum(random.randint(1, self._faces) for _ in range(self._nb_des))
        return self._fixed


class SpellHeal(Spell):
    """Sort de soin — soigne totalement une unité alliée."""
    def __init__(self, porte=6, cooldown=3):
        super().__init__("Soin", "heal", porte, cooldown)


class SpellMagicArmor(Spell):
    """Armure magique — +2 de sauvegarde à une unité (temporaire, dure X rounds)."""
    def __init__(self, porte=4, bonus=2, duration=3, cooldown=4):
        super().__init__("Armure magique", "armor", porte, cooldown)
        self.bonus = bonus        # Bonus de sauvegarde
        self.duration = duration  # Durée en rounds


class SpellMagicProjectile(Spell):
    """Projectile magique — cible unique, longue portée, 3d2 dégâts."""
    def __init__(self, porte=15, toucher=3, blesser=1, degats="3d2", cooldown=1):
        super().__init__("Projectile magique", "projectile", porte, cooldown)
        self.toucher = toucher
        self.blesser = blesser
        self.degats = degats
        
        s = str(degats).lower().strip()
        self._bonus = 0
        if '+' in s and 'd' in s:
            parts = s.split('+')
            self._bonus = int(parts[0])
            dp = parts[1].split('d')
            self._nb_des, self._faces = int(dp[0]), int(dp[1])
            self._is_dice = True
        elif 'd' in s:
            dp = s.split('d')
            self._nb_des, self._faces = int(dp[0]), int(dp[1])
            self._is_dice = True
        else:
            self._is_dice = False
            self._fixed = int(float(s))
    
    def lancer_degats(self):
        if self._is_dice:
            return self._bonus + sum(random.randint(1, self._faces) for _ in range(self._nb_des))
        return self._fixed


class SpellWall(Spell):
    """Mur de force — crée 3 obstacles devant les ennemis les plus proches."""
    def __init__(self, porte=8, nb_obstacles=3, wall_duration=5, cooldown=5):
        super().__init__("Mur de force", "wall", porte, cooldown)
        self.nb_obstacles = nb_obstacles
        self.wall_duration = wall_duration
