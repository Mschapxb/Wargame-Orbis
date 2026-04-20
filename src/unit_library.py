"""Bibliothèque d'unités WW1 — Orbis Naturae Battle : Grande Guerre.

Factions disponibles:
    • Infanterie Alliée (France / Empire Britannique)
    • Puissances Centrales (Empire Allemand)
    • Corps Expéditionnaire (troupes d'élite et matériel lourd)
    • Unités custom

Format d'une arme:
    ("Nom arme", portée, nb_attaques, toucher, blesser, perforation, "dégâts")

    portée  1  = corps à corps (baïonnette, crosse, couteau)
    portée  2  = portée courte (pistolet, fusil court)
    portée  6  = tir moyen (fusil, carabine)
    portée 10  = tir long (fusil de précision, mitrailleuse)
    portée 14+ = artillerie / mortier

Champs d'une unité:
    nom          str  — nom complet
    deplacement  int  — cases / round (0 = immobile)
    blessure     int  — points de vie
    bravoure     int  — moral (1-6)
    sauvegarde   int  — seuil de sauvegarde (7 = aucune armure)
    role         str  — "front" | "mid" | "back"
    size         int  — 1=1×1, 2=2×2, 3=2×4
    unit_type    str  — "Infanterie" | "Cavalerie" | "Artillerie" | "Blindé" | "Héros"
    armes        list — tuples (nom, portée, attaques, toucher, blesser, perf, dégâts)
    traits       list — traits spéciaux WW1
"""

from models import Arme, SpellFireball, SpellHeal, SpellMagicArmor, SpellMagicProjectile, SpellWall
from unit import Unit
import os


# ═══════════════════════════════════════════════════════════════
#                     BASE DE DONNÉES WW1
# ═══════════════════════════════════════════════════════════════

UNIT_DATABASE = {

    # ─────────────── INFANTERIE ALLIÉE ───────────────
    # France, Empire britannique — troupes de l'Entente

    "Infanterie Alliée": {
        "color": (60, 100, 180),   # Bleu horizon / kaki britannique
        "units": [

            {
                "nom": "Poilu",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Lebel + Baïonnette", 6, 1, 3, 3,  0, "1"),
                    ("Baïonnette",          1, 2, 3, 3,  0, "1"),
                ],
                "traits": [],
            },

            {
                "nom": "Tommy",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Lee-Enfield", 7, 1, 3, 3,  0, "1"),
                    ("Baïonnette",   1, 1, 3, 3,  0, "1"),
                ],
                "traits": ["Tir rapide"],
            },

            {
                "nom": "Tireur d'élite",
                "deplacement": 3,
                "blessure": 1,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Fusil de précision", 14, 1, 2, 2, -1, "1d2"),
                ],
                "traits": ["Planqué", "Embusqué"],
            },

            {
                "nom": "Mitrailleur",
                "deplacement": 2,
                "blessure": 3,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Artillerie",
                "armes": [
                    ("Mitrailleuse Hotchkiss", 10, 3, 3, 3, 0, "1"),
                ],
                "traits": ["Artillerie legere", "Tir de saturation"],
            },

            {
                "nom": "Grenadier",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Grenade Mills",  4, 2, 3, 2, -1, "1d2"),
                    ("Baïonnette",      1, 1, 3, 3,  0, "1"),
                ],
                "traits": ["Anti-Infanterie"],
            },

            {
                "nom": "Officier allié",
                "deplacement": 3,
                "blessure": 3,
                "bravoure": 3,
                "sauvegarde": 6,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Pistolet Webley", 3, 2, 3, 3, 0, "1"),
                    ("Canne de marche", 1, 1, 3, 3, 0, "1"),
                ],
                "traits": ["Encouragement"],
            },

            {
                "nom": "Cavalier allié",
                "deplacement": 7,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "mid",
                "size": 2,
                "unit_type": "Cavalerie",
                "armes": [
                    ("Lance de cavalerie", 2, 1, 3, 2, -1, "1d2"),
                    ("Carabine",            5, 1, 3, 3,  0, "1"),
                ],
                "traits": ["Charge montée", "Reconnaissance"],
            },

            {
                "nom": "Artillerie de campagne",
                "deplacement": 1,
                "blessure": 4,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "back",
                "size": 2,
                "unit_type": "Artillerie",
                "armes": [
                    ("Canon 75mm", 20, 1, 3, 2, -3, "2+1d4"),
                ],
                "traits": ["Artillerie", "Tir indirect"],
            },

            {
                "nom": "Mortier de tranchée",
                "deplacement": 1,
                "blessure": 3,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Artillerie",
                "armes": [
                    ("Mortier Stokes", 12, 1, 4, 2, -2, "1+1d4"),
                ],
                "traits": ["Artillerie legere", "Tir indirect"],
            },

            {
                "nom": "Tank Mark IV",
                "deplacement": 2,
                "blessure": 10,
                "bravoure": 3,
                "sauvegarde": 3,
                "role": "front",
                "size": 2,
                "unit_type": "Blindé",
                "armes": [
                    ("Canon de flanc 6-pdr", 8, 1, 3, 2, -3, "1d4"),
                    ("Mitrailleuse Lewis",    6, 2, 3, 3,  0, "1"),
                ],
                "traits": ["Blindage", "Ecrase barbelés", "Terreur"],
            },

            {
                "nom": "Sapeur",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Explosif C2",  2, 1, 2, 1, -3, "1d4"),
                    ("Pelle de tranchée", 1, 1, 3, 3, 0, "1"),
                ],
                "traits": ["Sapeur", "Anti-Blindé"],
            },
        ],
    },

    # ─────────────── PUISSANCES CENTRALES ───────────────
    # Empire Allemand — Kaiserreich

    "Puissances Centrales": {
        "color": (160, 120, 60),   # Feldgrau / gris-vert allemand
        "units": [

            {
                "nom": "Feldsoldat",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Gewehr 98 + Baïonnette", 7, 1, 3, 3,  0, "1"),
                    ("Baïonnette Seitengewehr", 1, 1, 3, 3,  0, "1"),
                ],
                "traits": [],
            },

            {
                "nom": "Sturmtruppen",
                "deplacement": 4,
                "blessure": 2,
                "bravoure": 3,
                "sauvegarde": 6,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Grenade à manche",  4, 2, 2, 2, -1, "1d2"),
                    ("Pistolet P08 Luger", 2, 2, 3, 3,  0, "1"),
                    ("Trench knife",       1, 2, 3, 3,  0, "1"),
                ],
                "traits": ["Anti-Infanterie", "Assaut", "Infiltration"],
            },

            {
                "nom": "Scharfschütze",
                "deplacement": 3,
                "blessure": 1,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Gew 98 optique", 16, 1, 2, 2, -1, "1d2"),
                ],
                "traits": ["Planqué", "Embusqué"],
            },

            {
                "nom": "MG-Trupp",
                "deplacement": 2,
                "blessure": 3,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Artillerie",
                "armes": [
                    ("MG 08 Maxim", 11, 3, 2, 3, 0, "1"),
                ],
                "traits": ["Artillerie legere", "Tir de saturation", "Position défensive"],
            },

            {
                "nom": "Lanceur de gaz",
                "deplacement": 2,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Obus de gaz moutarde", 6, 1, 3, 2, 0, "1"),
                    ("Baïonnette",            1, 1, 4, 4, 0, "1"),
                ],
                "traits": ["Gaz de combat", "Terreur"],
            },

            {
                "nom": "Officier allemand",
                "deplacement": 3,
                "blessure": 3,
                "bravoure": 3,
                "sauvegarde": 6,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("P08 Luger", 3, 2, 3, 3, 0, "1"),
                    ("Sabre",     1, 2, 3, 3, 0, "1"),
                ],
                "traits": ["Encouragement", "Tactique d'assaut"],
            },

            {
                "nom": "Uhlanen",
                "deplacement": 7,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "mid",
                "size": 2,
                "unit_type": "Cavalerie",
                "armes": [
                    ("Lance de uhlan", 2, 1, 3, 2, -1, "1d2"),
                    ("Carabine Kar98",  5, 1, 3, 3,  0, "1"),
                ],
                "traits": ["Charge montée", "Reconnaissance"],
            },

            {
                "nom": "Artillerie lourde",
                "deplacement": 0,
                "blessure": 5,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "back",
                "size": 2,
                "unit_type": "Artillerie",
                "armes": [
                    ("Obusier 150mm", 24, 1, 4, 2, -4, "3+1d4"),
                ],
                "traits": ["Artillerie", "Tir indirect", "Barrage"],
            },

            {
                "nom": "Minenwerfer",
                "deplacement": 1,
                "blessure": 3,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Artillerie",
                "armes": [
                    ("Minenwerfer 76mm", 10, 1, 3, 2, -2, "1+1d3"),
                ],
                "traits": ["Artillerie legere", "Tir indirect"],
            },

            {
                "nom": "A7V Sturmpanzer",
                "deplacement": 2,
                "blessure": 12,
                "bravoure": 3,
                "sauvegarde": 2,
                "role": "front",
                "size": 3,
                "unit_type": "Blindé",
                "armes": [
                    ("Canon Maxim-Nordenfeld", 10, 1, 3, 2, -4, "1d4"),
                    ("Mitrailleuse MG 08",      6, 3, 2, 3,  0, "1"),
                ],
                "traits": ["Blindage lourd", "Ecrase barbelés", "Terreur", "Anti-Infanterie"],
            },

            {
                "nom": "Pionier",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Lance-flammes",  3, 1, 2, 1, -2, "1d3"),
                    ("Hache de pionier", 1, 1, 3, 3, 0, "1"),
                ],
                "traits": ["Lance-flammes", "Terreur", "Anti-Infanterie"],
            },
        ],
    },

    # ─────────────── CORPS EXPÉDITIONNAIRE ───────────────
    # Unités d'élite, matériel spécialisé — jouable par les deux camps

    "Corps Expéditionnaire": {
        "color": (120, 90, 50),  # Kaki universel

        "units": [

            {
                "nom": "Légion étrangère",
                "deplacement": 3,
                "blessure": 3,
                "bravoure": 3,
                "sauvegarde": 6,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Lebel + Baïonnette", 6, 1, 3, 3,  0, "1"),
                    ("Baïonnette Rosalie",  1, 2, 3, 2,  0, "1"),
                ],
                "traits": ["Anti-Infanterie", "Moral d'acier"],
            },

            {
                "nom": "Stosstruppen d'élite",
                "deplacement": 4,
                "blessure": 3,
                "bravoure": 3,
                "sauvegarde": 5,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("MP 18 Bergmann",   4, 3, 3, 3,  0, "1"),
                    ("Grenade à manche",  3, 2, 2, 2, -1, "1d2"),
                    ("Trench knife",       1, 2, 3, 3,  0, "1"),
                ],
                "traits": ["Assaut", "Anti-Infanterie", "Infiltration"],
            },

            {
                "nom": "Tireur de clocher",
                "deplacement": 2,
                "blessure": 2,
                "bravoure": 3,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Fusil Mauser G98 optique", 18, 1, 2, 2, -2, "1d2+1"),
                ],
                "traits": ["Planqué", "Embusqué", "Position haute"],
            },

            {
                "nom": "Section mitrailleuse lourde",
                "deplacement": 1,
                "blessure": 4,
                "bravoure": 2,
                "sauvegarde": 6,
                "role": "back",
                "size": 2,
                "unit_type": "Artillerie",
                "armes": [
                    ("Vickers / MG 08 (position)", 12, 4, 2, 3, 0, "1"),
                ],
                "traits": ["Artillerie legere", "Tir de saturation", "Position défensive", "Anti-Infanterie"],
            },

            {
                "nom": "Canon antichar de campagne",
                "deplacement": 1,
                "blessure": 4,
                "bravoure": 2,
                "sauvegarde": 7,
                "role": "back",
                "size": 2,
                "unit_type": "Artillerie",
                "armes": [
                    ("Canon 37mm AT", 10, 1, 2, 1, -5, "1d4"),
                ],
                "traits": ["Artillerie legere", "Anti-Blindé"],
            },

            {
                "nom": "Général de brigade",
                "deplacement": 4,
                "blessure": 4,
                "bravoure": 4,
                "sauvegarde": 5,
                "role": "mid",
                "size": 1,
                "unit_type": "Héros",
                "armes": [
                    ("Pistolet de commandement", 3, 2, 3, 3, 0, "1"),
                ],
                "traits": ["Encouragement", "Moral d'acier", "Tactique d'assaut"],
            },

            {
                "nom": "Hussard de la Mort",
                "deplacement": 8,
                "blessure": 3,
                "bravoure": 3,
                "sauvegarde": 6,
                "role": "mid",
                "size": 2,
                "unit_type": "Cavalerie",
                "armes": [
                    ("Sabre de hussard",  1, 2, 2, 2,  0, "1d2"),
                    ("Carabine légère",   5, 1, 3, 3,  0, "1"),
                ],
                "traits": ["Charge montée", "Terreur", "Reconnaissance"],
            },

            {
                "nom": "Tank FT-17",
                "deplacement": 2,
                "blessure": 7,
                "bravoure": 3,
                "sauvegarde": 4,
                "role": "front",
                "size": 1,
                "unit_type": "Blindé",
                "armes": [
                    ("Canon Puteaux 37mm", 7, 1, 3, 2, -3, "1d3"),
                ],
                "traits": ["Blindage", "Ecrase barbelés"],
            },

            {
                "nom": "Tankiste de soutien",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 6,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Pistolet + grenades", 3, 1, 3, 3, 0, "1"),
                    ("Clef à molette",       1, 1, 4, 4, 0, "1"),
                ],
                "traits": ["Réparation blindé", "Anti-Blindé"],
            },
        ],
    },
}


# ═══════════════════════════════════════════════════════════════
#               MAPPING DES TRAITS WW1
# ═══════════════════════════════════════════════════════════════

WW1_TRAIT_MAP = {
    # Traits réutilisés du système de base
    "encouragement":       lambda u: setattr(u, 'encouragement_range', 4),
    "anti-infanterie":     lambda u: setattr(u, 'anti_infanterie', True),
    "anti-large":          lambda u: setattr(u, 'anti_large', True),
    "planqué":             lambda u: None,  # géré par battle.py
    "charge montée":       lambda u: setattr(u, 'charge_montee', True),
    "artillerie":          lambda u: setattr(u, 'vitesse', 0),       # immobile
    "artillerie legere":   lambda u: None,                           # peut bouger mais lentement

    # Traits WW1 spécifiques — mappés sur les attributs existants
    "terreur":             lambda u: setattr(u, 'fear_aura', 2),     # Effroi (= causes_dread)
    "blindage":            lambda u: setattr(u, 'sauvegarde', max(2, u.sauvegarde - 1)),
    "blindage lourd":      lambda u: setattr(u, 'sauvegarde', max(2, u.sauvegarde - 2)),
    "tir rapide":          lambda u: _boost_nb_attacks(u, 1),        # +1 attaque pour la première arme à tir
    "tir de saturation":   lambda u: setattr(u, 'anti_infanterie', True),
    "embusqué":            lambda u: setattr(u, 'morale_bonus', u.morale_bonus + 1),
    "assaut":              lambda u: setattr(u, 'charge_aida', True),
    "anti-blindé":         lambda u: setattr(u, 'anti_large', True), # anti_large = anti-blindé
    "écrase barbelés":     lambda u: None,                           # effet carte géré par battle.py
    "ecrase barbelés":     lambda u: None,
    "infiltration":        lambda u: setattr(u, 'vitesse', u.vitesse + 1),
    "gaz de combat":       lambda u: setattr(u, 'fear_aura', 1),
    "lance-flammes":       lambda u: setattr(u, 'fear_aura', 2),
    "moral d'acier":       lambda u: setattr(u, 'immune_mind', True),
    "tir indirect":        lambda u: None,                           # déjà pris en compte via portée
    "barrage":             lambda u: None,
    "position défensive":  lambda u: setattr(u, '_phalange_bonus_active', True),
    "position haute":      lambda u: setattr(u, 'morale_bonus', u.morale_bonus + 1),
    "réparation blindé":   lambda u: setattr(u, 'regeneration', 5),
    "reconnaissance":      lambda u: setattr(u, 'vitesse', u.vitesse + 1),
    "sapeur":              lambda u: None,
    "tactique d'assaut":   lambda u: setattr(u, 'encouragement_range', 4),
}


def _boost_nb_attacks(unit, bonus):
    """Ajoute +bonus attaque à la première arme à tir (portée >= 4)."""
    for arme in unit.armes:
        if arme.porte >= 4:
            arme.nb_attaque += bonus
            return


# ═══════════════════════════════════════════════════════════════
#                     FONCTIONS DE CRÉATION
# ═══════════════════════════════════════════════════════════════

def _build_arme(arme_tuple):
    nom, portee, nb_att, toucher, blesser, perf, degats = arme_tuple
    return Arme(nom, nb_attaque=nb_att, toucher=toucher, blesser=blesser,
                perforation=perf, degats=degats, porte=portee)


def create_unit(unit_def, army_color):
    """Crée un objet Unit depuis un dict de définition WW1."""
    armes = [_build_arme(a) for a in unit_def["armes"]]

    unit = Unit(
        name=unit_def["nom"][:10],
        pv=unit_def["blessure"],
        vitesse=unit_def["deplacement"],
        morale=unit_def["bravoure"],
        sauvegarde=unit_def["sauvegarde"],
        color=army_color,
        armes=armes,
        role=unit_def.get("role", "front"),
        size=unit_def.get("size", 1),
        unit_type=unit_def.get("unit_type", "Infanterie"),
    )
    unit.token_name = unit_def["nom"]

    # Appliquer les traits WW1
    for trait in unit_def.get("traits", []):
        key = trait.lower().strip()
        fn = WW1_TRAIT_MAP.get(key)
        if fn:
            fn(unit)
        # Compatibilité avec le moteur de base pour "Sort de bataille"
        if "sort de bataille" in key:
            import re
            m = re.search(r'\((\d+)\)', trait)
            if m:
                unit.spells_per_round = int(m.group(1))

    # Recalcul du cache max_range après modifications
    unit._max_range = max((a.porte for a in unit.armes), default=1) if unit.armes else 1

    # Recalcul attack_type
    if unit.spells:
        unit.attack_type = "spell"
    elif unit._max_range >= 4:
        unit.attack_type = "ranged"
    elif unit._max_range >= 2:
        unit.attack_type = "reach"
    else:
        unit.attack_type = "melee"

    return unit


def get_library():
    return UNIT_DATABASE


def list_armies():
    return sorted(UNIT_DATABASE.keys())


def list_units(army_name):
    army = UNIT_DATABASE.get(army_name)
    if not army:
        return []
    return [u["nom"] for u in army["units"]]


def make_unit(army_name, unit_name):
    army = UNIT_DATABASE.get(army_name)
    if not army:
        return None
    for u_def in army["units"]:
        if u_def["nom"] == unit_name:
            return create_unit(u_def, army["color"])
    return None


def build_army(army_name, composition):
    """Construit une liste de Units.

    composition: liste de tuples (nom_unité, quantité)
    Exemple: build_army("Infanterie Alliée", [("Poilu", 8), ("Tank Mark IV", 1)])
    """
    army_data = UNIT_DATABASE.get(army_name)
    if not army_data:
        print(f"ERREUR: armée '{army_name}' introuvable.")
        print(f"Armées disponibles: {', '.join(sorted(UNIT_DATABASE.keys()))}")
        return []

    color = army_data["color"]
    unit_by_name = {u["nom"]: u for u in army_data["units"]}

    result = []
    for unit_name, count in composition:
        u_def = unit_by_name.get(unit_name)
        if u_def is None:
            print(f"  ATTENTION: '{unit_name}' introuvable dans '{army_name}'")
            continue
        for i in range(count):
            u = create_unit(u_def, color)
            short = unit_name[:6]
            u.name = f"{short}{i + 1}" if count > 1 else short
            result.append(u)

    return result


# ═══════════════════════════════════════════════════════════════
#               CHARGEMENT DES UNITÉS CUSTOM
# ═══════════════════════════════════════════════════════════════

CUSTOM_ARMY_NAME = "Unités custom"
CUSTOM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_units")


def load_custom_units_into_db():
    import json

    if not os.path.isdir(CUSTOM_DIR):
        UNIT_DATABASE.pop(CUSTOM_ARMY_NAME, None)
        return

    units = []
    for fname in sorted(os.listdir(CUSTOM_DIR)):
        if not fname.endswith(".json"):
            continue
        filepath = os.path.join(CUSTOM_DIR, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "nom" not in data or "armes" not in data:
                continue
            unit_def = {
                "nom":        data["nom"],
                "deplacement": data.get("deplacement", 3),
                "blessure":   data.get("blessure", 2),
                "bravoure":   data.get("bravoure", 2),
                "sauvegarde": data.get("sauvegarde", 7),
                "role":       data.get("role", "front"),
                "size":       data.get("size", 1),
                "unit_type":  data.get("unit_type", "Infanterie"),
                "armes":      data.get("armes", []),
                "traits":     data.get("traits", []),
                "sorts":      data.get("sorts", []),
            }
            token_path = data.get("token_path", "")
            if token_path and not os.path.isabs(token_path):
                token_path = os.path.normpath(os.path.join(os.path.dirname(filepath), token_path))
            if token_path and os.path.exists(token_path):
                tokens_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")
                os.makedirs(tokens_dir, exist_ok=True)
                dest = os.path.join(tokens_dir, f"{data['nom']}.png")
                if os.path.abspath(token_path) != os.path.abspath(dest):
                    import shutil
                    try:
                        shutil.copy2(token_path, dest)
                    except Exception:
                        pass
            units.append(unit_def)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"  ATTENTION: fichier custom '{fname}' invalide: {e}")

    if units:
        UNIT_DATABASE[CUSTOM_ARMY_NAME] = {
            "color": (180, 140, 220),
            "units": units,
        }
    else:
        UNIT_DATABASE.pop(CUSTOM_ARMY_NAME, None)


load_custom_units_into_db()
