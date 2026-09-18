"""Résolution d'une attaque au d6 — LA source de vérité des seuils.

Le moteur (Unit.perform_attacks, sorts, portes, structures), l'IA
(tactics.expected_damage) et l'interface (fiche d'unité) passent tous par
ce module: ils voient donc exactement les mêmes chiffres, et une convention
de signe ne peut plus diverger d'un appelant à l'autre (c'est ainsi que la
perforation de la boule de feu s'était retrouvée inversée).

Conventions:
    - toucher et blesser réussissent sur 1d6 >= seuil (plus bas = meilleur);
    - seuil de sauvegarde = sauvegarde - perforation + modificateurs,
      plafonné à NO_SAVE (7: aucune sauvegarde possible); la sauvegarde
      annule le coup sur 1d6 >= seuil. Une perforation négative est donc
      meilleure pour l'attaquant;
    - un modificateur POSITIF est toujours un désavantage pour celui qui
      lance le dé (seuil plus haut).
"""
import random

import terrain

MISS, NO_WOUND, SAVED, HIT = "miss", "no_wound", "saved", "hit"
NO_SAVE = 7

TOUCHER, BLESSER, SAVE, DEGATS = "toucher", "blesser", "save", "degats"


# ── Seuils et dés ──


def save_threshold(save, perforation=0, mod=0):
    """Seuil de sauvegarde: sauvegarde - perforation + mod, plafonné à 7."""
    return min(NO_SAVE, save - perforation + mod)


def p_ge(threshold):
    """P(1d6 >= seuil)."""
    if threshold <= 1:
        return 1.0
    if threshold > 6:
        return 0.0
    return (7 - threshold) / 6.0


def saves(threshold):
    """Jet de sauvegarde seul (cible fixe: porte, structure, éboulis)."""
    return random.randint(1, 6) >= threshold


def roll(toucher, blesser, save_thr=None):
    """Toucher, blesser, sauvegarder. save_thr=None: pas de sauvegarde
    (projectile magique). Renvoie MISS, NO_WOUND, SAVED ou HIT."""
    if random.randint(1, 6) < toucher:
        return MISS
    if random.randint(1, 6) < blesser:
        return NO_WOUND
    if save_thr is not None and saves(save_thr):
        return SAVED
    return HIT


def p_hit(toucher, blesser, save_thr=None):
    """Probabilité qu'un jet passe les trois étapes."""
    p = p_ge(toucher) * p_ge(blesser)
    return p if save_thr is None else p * (1.0 - p_ge(save_thr))


# ── Profil d'attaque: seuils finaux + détail des modificateurs ──


class AttackProfile:
    """Seuils finaux d'une arme contre une cible, et la liste des
    modificateurs appliqués: [(libellé, stat, delta)], stat parmi
    TOUCHER, BLESSER, SAVE, DEGATS."""
    __slots__ = ("arme", "toucher", "blesser", "save", "dmg_bonus", "details")

    def __init__(self, arme, toucher, blesser, save, dmg_bonus, details):
        self.arme = arme
        self.toucher = toucher
        self.blesser = blesser
        self.save = save
        self.dmg_bonus = dmg_bonus
        self.details = details

    def roll(self):
        return roll(self.toucher, self.blesser, self.save)

    @property
    def p_hit(self):
        return p_hit(self.toucher, self.blesser, self.save)

    def expected_damage(self):
        """Dégâts moyens espérés de TOUTES les attaques de l'arme."""
        return (self.arme.nb_attaque * self.p_hit
                * (self.arme.dice.average + self.dmg_bonus))


def attack_profile(attacker, target, arme, bf=None, kind="normal", charging=False):
    """Tous les modificateurs d'une attaque d'`attacker` sur `target`.

    kind: "normal" | "charge" | "opportunity" | "momentum" | "reaction".
    charging: l'attaquant porte sa charge (Unit.has_charged)."""
    ranged = arme.porte >= 4
    details = []

    def add(label, stat, delta):
        if delta:
            details.append((label, stat, delta))

    if attacker.afraid:
        add("Ébranlé", TOUCHER, 1)
    if attacker.anti_infanterie and target.unit_type == "Infanterie":
        add("Anti-Infanterie", TOUCHER, -1)
        add("Anti-Infanterie", BLESSER, -1)
    if attacker.anti_large and target.unit_type in ("Large", "Cavalerie", "Monstre"):
        add("Anti-Large", TOUCHER, -1)
        add("Anti-Large", BLESSER, -1)
    if charging:
        if attacker.charge_montee:
            add("Charge montée", DEGATS, 1)
        elif attacker.charge_aida:
            add("Charge d'Aïda", BLESSER, -1)
    if getattr(attacker, '_on_wall', False):
        add("Depuis le rempart", TOUCHER, -1)
    if kind == "reaction":
        add("Tir de réaction", TOUCHER, 1)
    if bf is not None:
        terrain.combat_mods(bf, attacker, target, ranged, details=details)
        is_rampart = getattr(bf, 'is_rampart', None)
        if is_rampart is not None and target.position is not None and is_rampart(*target.position):
            add("Cible sur le rempart", SAVE, -2)

    sums = {TOUCHER: 0, BLESSER: 0, SAVE: 0, DEGATS: 0}
    for _, stat, delta in details:
        sums[stat] += delta
    return AttackProfile(
        arme,
        arme.toucher + sums[TOUCHER],
        arme.blesser + sums[BLESSER],
        save_threshold(target.sauvegarde, arme.perforation, sums[SAVE]),
        sums[DEGATS],
        details)


def describe(profile):
    """Texte court du profil: « Toucher 3+ (Flanc -1) · Blesser 3+ · Svg 5+ »."""
    def part(name, value, stat):
        mods = [f"{label} {delta:+d}" for label, s, delta in profile.details if s == stat]
        shown = "aucune" if stat == SAVE and value >= NO_SAVE else f"{value}+"
        return f"{name} {shown}" + (f" ({', '.join(mods)})" if mods else "")
    out = [part("Toucher", profile.toucher, TOUCHER),
           part("Blesser", profile.blesser, BLESSER),
           part("Svg", profile.save, SAVE)]
    dmg = [f"{label} {delta:+d}" for label, s, delta in profile.details if s == DEGATS]
    if dmg:
        out.append("Dégâts " + ", ".join(dmg))
    return " · ".join(out)
