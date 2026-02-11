import math


class FloatingText:
    __slots__ = ['text', 'color', 'duration', 'age']
    
    def __init__(self, text, color, duration=60):
        self.text = text
        self.color = color
        self.duration = duration
        self.age = 0


class Projectile:
    __slots__ = ['start_pos', 'end_pos', 'color', 'duration', 'age', 'projectile_type', 'cell_size', '_dx', '_dy']
    
    def __init__(self, start_pos, end_pos, color, duration=30, projectile_type="arrow", cell_size=32):
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.color = color
        self.duration = duration
        self.age = 0
        self.projectile_type = projectile_type
        self.cell_size = cell_size
        # Pré-calculer les deltas
        self._dx = end_pos[0] - start_pos[0]
        self._dy = end_pos[1] - start_pos[1]
        
    def get_current_pos(self):
        progress = min(1.0, self.age / (self.duration * 0.7))
        x = self.start_pos[0] + self._dx * progress
        y = self.start_pos[1] + self._dy * progress
        if self.projectile_type == "arrow":
            y -= 40 * math.sin(progress * math.pi)
        elif self.projectile_type == "fireball":
            y -= 25 * math.sin(progress * math.pi)
        return (x, y)
    
    def get_angle(self):
        return math.atan2(self._dy, self._dx)
    
    def is_alive(self):
        return self.age < self.duration


class AttackLine:
    __slots__ = ['start_pos', 'end_pos', 'color', 'duration', 'age']
    
    def __init__(self, start_pos, end_pos, color, duration=20):
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.color = color
        self.duration = duration
        self.age = 0
    
    def is_alive(self):
        return self.age < self.duration
    
    def get_alpha(self):
        return int(255 * (1 - self.age / self.duration))


class AoeExplosion:
    """Explosion de zone (boule de feu) — cercle qui s'étend puis se dissipe."""
    __slots__ = ['center_pos', 'radius_px', 'color', 'duration', 'age']
    
    def __init__(self, center_pos, radius_px, color=(255, 100, 0), duration=30):
        self.center_pos = center_pos
        self.radius_px = radius_px
        self.color = color
        self.duration = duration
        self.age = 0
    
    def is_alive(self):
        return self.age < self.duration
    
    def get_alpha(self):
        return int(200 * (1 - self.age / self.duration))
    
    def get_current_radius(self):
        progress = min(1.0, self.age / (self.duration * 0.4))
        return int(self.radius_px * progress)


class HealBeam:
    """Rayon de soin — ligne verte du lanceur à la cible."""
    __slots__ = ['start_pos', 'end_pos', 'color', 'duration', 'age']
    
    def __init__(self, start_pos, end_pos, duration=30):
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.color = (50, 255, 100)
        self.duration = duration
        self.age = 0
    
    def is_alive(self):
        return self.age < self.duration
    
    def get_alpha(self):
        return int(255 * (1 - self.age / self.duration))


class ArmorShimmer:
    """Effet d'armure magique — scintillement bleu autour d'une position."""
    __slots__ = ['center_pos', 'radius_px', 'duration', 'age']
    
    def __init__(self, center_pos, radius_px, duration=40):
        self.center_pos = center_pos
        self.radius_px = radius_px
        self.duration = duration
        self.age = 0
    
    def is_alive(self):
        return self.age < self.duration
    
    def get_alpha(self):
        return int(180 * (1 - self.age / self.duration))


class WallEffect:
    """Effet visuel de création de mur — flash violet sur les cases."""
    __slots__ = ['positions', 'cell_size', 'duration', 'age']
    
    def __init__(self, positions, cell_size, duration=25):
        self.positions = positions  # Liste de (x, y) en cases grille
        self.cell_size = cell_size
        self.duration = duration
        self.age = 0
    
    def is_alive(self):
        return self.age < self.duration
    
    def get_alpha(self):
        return int(200 * (1 - self.age / self.duration))
