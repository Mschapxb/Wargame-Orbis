import random


class Dice:
    """Expression de dégâts: "3", "1d4", "2+1d6". Immuable.

    `bonus` s'ajoute toujours au jet (y compris pour des dégâts fixes, qui
    sont un bonus sans dé)."""
    __slots__ = ("count", "faces", "bonus")

    def __init__(self, count=0, faces=0, bonus=0):
        self.count = count
        self.faces = faces
        self.bonus = bonus

    @classmethod
    def parse(cls, expr):
        s = str(expr).lower().strip()
        try:
            if 'd' in s:
                bonus = 0
                if '+' in s:
                    head, s = s.split('+', 1)
                    bonus = int(head)
                count, faces = s.split('d')
                return cls(int(count), int(faces), bonus)
            return cls(0, 0, int(float(s)))
        except (ValueError, TypeError):
            return cls(0, 0, 1)

    def plus(self, extra):
        """Même jet avec un bonus fixe supplémentaire."""
        return Dice(self.count, self.faces, self.bonus + extra)

    def roll(self):
        return self.bonus + sum(random.randint(1, self.faces) for _ in range(self.count))

    @property
    def average(self):
        return self.bonus + self.count * (self.faces + 1) / 2.0

    def __repr__(self):
        if not self.count:
            return str(self.bonus)
        core = f"{self.count}d{self.faces}"
        return f"{self.bonus}+{core}" if self.bonus else core


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
        # Portée nominale: la météo peut réduire `porte` (brouillard,
        # crépuscule), pas le tir d'une machine sur un mur, cible fixe
        self.base_porte = porte
        self.special = special or {}
        self.dice = Dice.parse(degats)

    def lancer_degats(self):
        return self.dice.roll()


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
        
        self.dice = Dice.parse(degats)

    def lancer_degats(self):
        return self.dice.roll()


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
        
        self.dice = Dice.parse(degats)

    def lancer_degats(self):
        return self.dice.roll()


class SpellWall(Spell):
    """Mur de force — crée 3 obstacles devant les ennemis les plus proches."""
    def __init__(self, porte=8, nb_obstacles=3, wall_duration=5, cooldown=5):
        super().__init__("Mur de force", "wall", porte, cooldown)
        self.nb_obstacles = nb_obstacles
        self.wall_duration = wall_duration
