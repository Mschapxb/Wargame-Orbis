"""Météo: une condition par bataille, qui pèse sur le tir, le feu et la
fatigue. Choisie au menu (rangée « Météo »), portée par `bf.weather`.

| Météo      | Effets                                                            |
|------------|-------------------------------------------------------------------|
| Clair      | aucun (équilibrage historique)                                    |
| Pluie      | tirs: +1 au seuil de toucher; feu: allumage ×0,5, s'éteint 2× vite|
| Brouillard | portée des tirs plafonnée à 7 cases; la hauteur (colline,         |
|            | rempart) ne fait plus voir plus loin                              |
| Vent       | tir dans le vent +1 portée, contre le vent +1 au seuil de toucher;|
|            | le feu court sous le vent (×1,8) et remonte mal (×0,4)            |
| Crépuscule | portée des tirs -2                                                |
| Chaleur    | fatigue ×2; feu: allumage ×1,3                                    |

Le moteur et l'IA lisent les mêmes règles: brouillard et crépuscule
raccourcissent les armes au déploiement (apply_to_unit), le vent passe par
terrain.range_bonus et terrain.combat_mods. Une machine garde sa portée
nominale (Arme.base_porte) contre un mur ou une porte: une cible fixe se
bat au jugé. Clair ne tire aucun dé: une graine rejoue
exactement la même bataille qu'avant l'ajout de la météo.
"""
import random

CLEAR, RAIN, FOG, WIND, DUSK, HEAT = (
    "Clair", "Pluie", "Brouillard", "Vent", "Crépuscule", "Chaleur")
WEATHERS = (CLEAR, RAIN, FOG, WIND, DUSK, HEAT)
RANDOM_WEATHER = "Aléatoire"

FOG_RANGE = 7
DUSK_RANGE = -2
RAIN_TOUCHER = 1
WIND_RANGE = 1           # tir dans le vent: +1 portée
WIND_TOUCHER = 1         # tir contre le vent: +1 au seuil de toucher
HEAT_FATIGUE = 2.0

# Probabilités du tirage « Aléatoire » selon le biome
_ODDS = {
    "Prairie": {CLEAR: 4, RAIN: 2, FOG: 1, WIND: 2, DUSK: 1},
    "Forêt":   {CLEAR: 3, RAIN: 3, FOG: 3, WIND: 1, DUSK: 1},
    "Désert":  {CLEAR: 3, WIND: 3, HEAT: 3, DUSK: 1},
}

DESCRIPTIONS = {
    CLEAR: "Ciel dégagé.",
    RAIN: "Pluie: tirs moins précis, le feu prend mal.",
    FOG: f"Brouillard: on ne tire pas au-delà de {FOG_RANGE} cases, même en hauteur.",
    WIND: "Vent: tir porté par le vent +1 portée, contre le vent moins précis; le feu court sous le vent.",
    DUSK: "Crépuscule: portée des tirs -2.",
    HEAT: "Chaleur: la mêlée épuise deux fois plus vite.",
}


class Weather:
    """Condition météo d'une bataille. `wind`: +1 souffle vers l'est,
    -1 vers l'ouest, 0 sans vent."""

    def __init__(self, name=CLEAR, wind=0):
        self.name = name if name in WEATHERS else CLEAR
        self.wind = wind if self.name == WIND else 0

    @property
    def label(self):
        if self.name == WIND:
            return "Vent d'ouest" if self.wind > 0 else "Vent d'est"
        return self.name

    # ─── Tir ───

    def range_mod(self, shooter_pos, target_pos, max_range):
        """Modificateur de portée DIRECTIONNEL (vent): +1 dans le vent.
        Le brouillard et le crépuscule, eux, raccourcissent les armes une
        fois pour toutes (apply_to_unit): l'IA place alors ses tireurs à
        leur vraie portée au lieu de se poster hors d'atteinte."""
        if self.name == WIND and (target_pos[0] - shooter_pos[0]) * self.wind > 0:
            return WIND_RANGE
        return 0

    def weapon_range(self, porte):
        """Portée d'une arme de tir sous cette météo (jamais sous 4)."""
        if porte < 4:
            return porte
        if self.name == FOG:
            return max(4, min(porte, FOG_RANGE))
        if self.name == DUSK:
            return max(4, porte + DUSK_RANGE)
        return porte

    def apply_to_unit(self, unit):
        """Au déploiement: portées des armes de tir, rythme de fatigue."""
        changed = False
        for a in unit.armes:
            r = self.weapon_range(a.base_porte)
            if r != a.porte:
                a.porte = a.range = r
                changed = True
        if changed:
            unit._max_range = max(a.porte for a in unit.armes)
        unit.fatigue_rate = self.fatigue_rate()

    def ranged_toucher(self, shooter_pos=None, target_pos=None):
        """Seuil de toucher des tirs: pluie, ou tir contre le vent."""
        if self.name == RAIN:
            return RAIN_TOUCHER
        if (self.name == WIND and shooter_pos is not None
                and (target_pos[0] - shooter_pos[0]) * self.wind < 0):
            return WIND_TOUCHER
        return 0

    def height_helps_range(self):
        """Dans le brouillard, être en hauteur ne fait pas voir plus loin
        (sinon la garnison, +1 sur son rempart, tirait seule: l'assaillant
        arrêté au fossé ne l'atteignait plus — siège 0 %)."""
        return self.name != FOG

    # ─── Feu ───

    def ignite_factor(self, dx=0):
        """Multiplicateur de la chance qu'une case voisine prenne feu;
        dx: direction de propagation (+1 vers l'est)."""
        if self.name == RAIN:
            return 0.5
        if self.name == HEAT:
            return 1.3
        if self.name == WIND and dx:
            return 1.8 if dx * self.wind > 0 else 0.4
        return 1.0

    def extra_burn(self):
        """Rounds de combustion retirés en plus chaque round (la pluie
        éteint plus vite)."""
        return 1 if self.name == RAIN else 0

    # ─── Fatigue ───

    def fatigue_rate(self):
        return HEAT_FATIGUE if self.name == HEAT else 1.0


# En siège, brouillard et crépuscule écrasent l'assaillant (mesuré: 0-10 %
# de victoires contre 25 % par temps clair: la garnison protégée par le
# rempart gagne tout échange de tir à courte portée). Le tirage aléatoire
# ne les propose pas; on peut toujours les choisir explicitement.
_SIEGE_EXCLUDED = (FOG, DUSK)


def resolve(choice, biome="Prairie", rng=random, siege=False):
    """Weather pour un choix du menu. None/Clair ne tire aucun dé."""
    if choice in (None, CLEAR):
        return Weather(CLEAR)
    if choice == RANDOM_WEATHER:
        odds = dict(_ODDS.get(biome, _ODDS["Prairie"]))
        if siege:
            for name in _SIEGE_EXCLUDED:
                odds.pop(name, None)
        names = list(odds)
        choice = rng.choices(names, weights=[odds[n] for n in names])[0]
    wind = rng.choice((-1, 1)) if choice == WIND else 0
    return Weather(choice, wind)


def of(bf):
    """Météo d'un champ de bataille (Clair si aucune)."""
    return getattr(bf, 'weather', None) or _CLEAR


_CLEAR = Weather(CLEAR)
