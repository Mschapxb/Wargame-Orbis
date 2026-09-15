import math


# ═══════════════════════════════════════════════════════════════
#   HORLOGE D'EFFETS — ordonnancement temporel des actions
# ═══════════════════════════════════════════════════════════════
# Le moteur reste au tour par tour, mais toutes les actions d'un round
# sont ESTAMPILLÉES dans le temps (en frames depuis le début du round).
# Chaque effet visuel créé pendant la résolution hérite automatiquement
# du "temps d'action" courant → à l'écran, le round se déroule comme un
# échange continu (cavalerie qui percute, mêlée qui s'engage, volées qui
# partent, ripostes…) au lieu d'un unique flash simultané.

class _FxClock:
    """Estampille temporelle courante (en frames) pour les effets créés."""
    __slots__ = ['current_delay', 'frames_per_round']

    def __init__(self):
        self.current_delay = 0
        self.frames_per_round = 48

    def at(self, delay):
        self.current_delay = max(0, int(delay))

    def reset(self):
        self.current_delay = 0


FX_CLOCK = _FxClock()


def _resolve_delay(delay):
    return FX_CLOCK.current_delay if delay is None else max(0, int(delay))


class FloatingText:
    __slots__ = ['text', 'color', 'duration', 'age', 'delay']

    def __init__(self, text, color, duration=60, delay=None):
        self.text = text
        self.color = color
        self.duration = duration
        self.age = 0
        self.delay = _resolve_delay(delay)

    def is_visible(self):
        return self.age >= self.delay

    def is_alive(self):
        return self.age < self.delay + self.duration

    def get_progress(self):
        return max(0.0, min(1.0, (self.age - self.delay) / max(1, self.duration)))


class Projectile:
    __slots__ = ['start_pos', 'end_pos', 'color', 'duration', 'age',
                 'projectile_type', 'cell_size', 'delay', '_dx', '_dy']

    def __init__(self, start_pos, end_pos, color, duration=30,
                 projectile_type="arrow", cell_size=32, delay=None):
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.color = color
        self.duration = duration
        self.age = 0
        self.projectile_type = projectile_type
        self.cell_size = cell_size
        # Délai = estampille de l'action (volées en cascade incluses)
        self.delay = _resolve_delay(delay)
        self._dx = end_pos[0] - start_pos[0]
        self._dy = end_pos[1] - start_pos[1]

    def get_current_pos(self):
        eff_age = max(0, self.age - self.delay)
        progress = min(1.0, eff_age / (self.duration * 0.7))
        x = self.start_pos[0] + self._dx * progress
        y = self.start_pos[1] + self._dy * progress
        if self.projectile_type == "arrow":
            y -= 40 * math.sin(progress * math.pi)
        elif self.projectile_type == "fireball":
            y -= 25 * math.sin(progress * math.pi)
        return (x, y)

    def is_flying(self):
        """False tant que le projectile attend son tour dans la volée."""
        return self.age >= self.delay

    is_visible = is_flying

    def get_angle(self):
        return math.atan2(self._dy, self._dx)

    def is_alive(self):
        return self.age < self.duration + self.delay


class _TimedEffect:
    """Base commune: effet qui attend son estampille puis s'estompe."""
    __slots__ = ['duration', 'age', 'delay']

    def _init_timing(self, duration, delay):
        self.duration = duration
        self.age = 0
        self.delay = _resolve_delay(delay)

    def is_visible(self):
        return self.age >= self.delay

    def is_alive(self):
        return self.age < self.delay + self.duration

    def _eff_age(self):
        return max(0, self.age - self.delay)

    def get_progress(self):
        return min(1.0, self._eff_age() / max(1, self.duration))


class AttackLine(_TimedEffect):
    __slots__ = ['start_pos', 'end_pos', 'color']

    def __init__(self, start_pos, end_pos, color, duration=20, delay=None):
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.color = color
        self._init_timing(duration, delay)

    def get_alpha(self):
        return int(255 * (1 - self.get_progress()))


class AoeExplosion(_TimedEffect):
    """Explosion de zone (boule de feu) — cercle qui s'étend puis se dissipe."""
    __slots__ = ['center_pos', 'radius_px', 'color']

    def __init__(self, center_pos, radius_px, color=(255, 100, 0), duration=30, delay=None):
        self.center_pos = center_pos
        self.radius_px = radius_px
        self.color = color
        self._init_timing(duration, delay)

    def get_alpha(self):
        return int(200 * (1 - self.get_progress()))

    def get_current_radius(self):
        progress = min(1.0, self._eff_age() / (self.duration * 0.4))
        return int(self.radius_px * progress)


class HealBeam(_TimedEffect):
    """Rayon de soin — ligne verte du lanceur à la cible."""
    __slots__ = ['start_pos', 'end_pos', 'color']

    def __init__(self, start_pos, end_pos, duration=30, delay=None):
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.color = (50, 255, 100)
        self._init_timing(duration, delay)

    def get_alpha(self):
        return int(255 * (1 - self.get_progress()))


class ArmorShimmer(_TimedEffect):
    """Effet d'armure magique — scintillement bleu autour d'une position."""
    __slots__ = ['center_pos', 'radius_px']

    def __init__(self, center_pos, radius_px, duration=40, delay=None):
        self.center_pos = center_pos
        self.radius_px = radius_px
        self._init_timing(duration, delay)

    def get_alpha(self):
        return int(180 * (1 - self.get_progress()))


class WallEffect(_TimedEffect):
    """Effet visuel de création de mur — flash violet sur les cases."""
    __slots__ = ['positions', 'cell_size']

    def __init__(self, positions, cell_size, duration=25, delay=None):
        self.positions = positions
        self.cell_size = cell_size
        self._init_timing(duration, delay)

    def get_alpha(self):
        return int(200 * (1 - self.get_progress()))


class DeathFade(_TimedEffect):
    """Mort d'une unité — croix qui s'estompe + nuage de poussière."""
    __slots__ = ['center_pos', 'radius', 'team_color']

    def __init__(self, center_pos, radius, team_color, duration=55, delay=None):
        self.center_pos = center_pos
        self.radius = radius
        self.team_color = team_color
        self._init_timing(duration, delay)


class ImpactBurst(_TimedEffect):
    """Gerbe d'impact au point de contact — éclats qui partent en étoile.
    Donne du poids aux coups qui blessent VRAIMENT (vs. ceux qui ratent)."""
    __slots__ = ['center_pos', 'color', 'power', 'angle']

    def __init__(self, center_pos, color=(255, 90, 60), power=1.0, angle=0.0,
                 duration=20, delay=None):
        self.center_pos = center_pos
        self.color = color
        self.power = power     # 1.0 = coup normal, >1 = coup lourd
        self.angle = angle     # Direction de l'impact (radians)
        self._init_timing(duration, delay)

    def get_alpha(self):
        return int(230 * (1 - self.get_progress()))


class ShockWave(_TimedEffect):
    """Onde de choc au sol — anneau qui s'élargit (charge, impact lourd)."""
    __slots__ = ['center_pos', 'max_radius', 'color']

    def __init__(self, center_pos, max_radius, color=(255, 220, 140),
                 duration=26, delay=None):
        self.center_pos = center_pos
        self.max_radius = max_radius
        self.color = color
        self._init_timing(duration, delay)

    def get_alpha(self):
        return int(170 * (1 - self.get_progress()))

    def get_current_radius(self):
        return int(self.max_radius * self.get_progress())
