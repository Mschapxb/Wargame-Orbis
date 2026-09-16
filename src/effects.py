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
                 'projectile_type', 'cell_size', 'delay', '_dx', '_dy',
                 'arc', 'spawned', 'landed', 'seed']

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
        # Hauteur de la cloche: proportionnelle à la portée (un tir long
        # monte haut), plus tendue pour les carreaux et les traits de baliste
        dist = math.hypot(self._dx, self._dy)
        tension = {"arrow": 0.22, "bolt": 0.12, "ballista": 0.07,
                   "fireball": 0.16, "magic": 0.05}.get(projectile_type, 0.15)
        self.arc = min(dist * tension, 90.0)
        self.spawned = False   # le renderer a-t-il lancé ses particules ?
        self.landed = False    # a-t-il touché le sol (poussière) ?
        self.seed = (int(start_pos[0]) * 31 + int(end_pos[1]) * 17) & 0xFFFF

    def get_progress(self):
        eff_age = max(0, self.age - self.delay)
        return min(1.0, eff_age / max(1.0, self.duration * 0.7))

    def pos_at(self, progress):
        x = self.start_pos[0] + self._dx * progress
        y = self.start_pos[1] + self._dy * progress - self.arc * math.sin(progress * math.pi)
        return (x, y)

    def get_current_pos(self):
        return self.pos_at(self.get_progress())

    def get_heading(self):
        """Angle de la tangente à la trajectoire (le trait pique du nez
        en fin de course au lieu de voler à plat)."""
        p = self.get_progress()
        a = self.pos_at(max(0.0, p - 0.02))
        b = self.pos_at(min(1.0, p + 0.02))
        if abs(b[0] - a[0]) + abs(b[1] - a[1]) < 1e-6:
            return self.get_angle()
        return math.atan2(b[1] - a[1], b[0] - a[0])

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
    __slots__ = ['duration', 'age', 'delay', 'spawned']

    def _init_timing(self, duration, delay):
        self.duration = duration
        self.age = 0
        self.delay = _resolve_delay(delay)
        self.spawned = False  # particules d'apparition déjà émises ?

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
    __slots__ = ['center_pos', 'color', 'power', 'angle', 'kind']

    def __init__(self, center_pos, color=(255, 90, 60), power=1.0, angle=0.0,
                 duration=20, delay=None, kind="melee"):
        self.center_pos = center_pos
        self.color = color
        self.power = power     # 1.0 = coup normal, >1 = coup lourd
        self.angle = angle     # Direction de l'impact (radians)
        self.kind = kind       # "melee" | "ranged" | "fire" | "magic" | "gate"
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


class SlashEffect(_TimedEffect):
    """Coup de taille au corps à corps: un arc de lame qui balaie la cible.

    `mirror` alterne le sens du balayage d'un coup à l'autre (revers,
    coup droit) pour qu'une série d'attaques ne soit pas un tampon répété.
    """
    __slots__ = ['center_pos', 'angle', 'color', 'mirror', 'scale']

    def __init__(self, center_pos, angle, color=(255, 240, 220), mirror=False,
                 scale=1.0, duration=14, delay=None):
        self.center_pos = center_pos
        self.angle = angle
        self.color = color
        self.mirror = mirror
        self.scale = scale
        self._init_timing(duration, delay)


class ThrustEffect(_TimedEffect):
    """Estoc d'arme d'hast: une traînée qui file de l'attaquant vers la cible."""
    __slots__ = ['start_pos', 'end_pos', 'color']

    def __init__(self, start_pos, end_pos, color=(255, 230, 170), duration=12, delay=None):
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.color = color
        self._init_timing(duration, delay)


class DeathAnimation(_TimedEffect):
    """Mort d'une unité: recul sous le coup, chute, puis dépouille qui
    s'efface en laissant une trace au sol.

    Le moteur retire l'unité de la grille dès la fin de la simulation du
    round, alors que le coup fatal n'est MONTRÉ que plus tard dans le round.
    C'est cet effet qui continue d'afficher le token intact jusqu'à
    l'instant du coup — sinon la victime disparaissait avant d'être touchée.
    """
    __slots__ = ['from_pos', 'to_pos', 'cells', 'token_name', 'unit_color',
                 'team_color', 'fall_angle', 'texts', 'decal_done', 'seed']

    def __init__(self, from_pos, to_pos, cells, token_name, unit_color, team_color,
                 fall_angle, texts=(), duration=70, delay=None, seed=0):
        self.from_pos = from_pos        # centre pixel au début du round
        self.to_pos = to_pos            # centre pixel à la mort
        self.cells = cells              # (largeur, hauteur) en cases
        self.token_name = token_name
        self.unit_color = unit_color
        self.team_color = team_color
        self.fall_angle = fall_angle    # direction de chute (radians)
        self.texts = list(texts)        # textes flottants encore à afficher
        self.decal_done = False
        self.seed = seed
        self._init_timing(duration, delay)
