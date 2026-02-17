"""Bibliothèque d'unités — définie directement en Python.

Pour ajouter une unité, copier un bloc existant dans UNIT_DATABASE et modifier les valeurs.
Aucune dépendance externe.

Format d'une arme:
    ("Nom arme", portée, nb_attaques, toucher, blesser, perforation, "dégâts")

Champs d'une unité:
    nom             : str       — nom complet (aussi le nom du token PNG)
    deplacement     : int       — vitesse en cases par round
    blessure        : int       — points de vie
    bravoure        : int       — moral (1-6, test sur 1d6 ≤ bravoure)
    sauvegarde      : int       — sauvegarde (1-6, réussie si 1d6 ≥ sauv, 7 = aucune)
    role            : str       — "front", "mid", "back" (position de départ)
    size            : int       — taille en cases (1=1x1, 2=2x2, 3=3x3)
    unit_type       : str       — "Infanterie", "Large", "Cavalerie", "Artillerie", "Monstre", "Héros"
    armes           : list      — liste de tuples (nom, portée, attaques, toucher, blesser, perf, dégâts)
    traits          : list      — liste de strings: "Encouragement", "Planqué", "Anti-Large", etc.
"""

from models import Arme, SpellFireball, SpellHeal, SpellMagicArmor, SpellMagicProjectile, SpellWall
from unit import Unit


# ═══════════════════════════════════════════════════════════════
#                     BASE DE DONNÉES
# ═══════════════════════════════════════════════════════════════

UNIT_DATABASE = {

    # ──────────────── ARMÉE SKALDIENNE ────────────────

    "Armée Skaldienne": {
        "color": (80, 140, 200),
        "units": [
            {
                "nom": "Infanterie régulière",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 1,
                "sauvegarde": 6,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Epée",          1, 2, 3, 3,  0, "1"),
                    ("Lance",         2, 1, 3, 3,  0, "1"),
                    ("Hache courte",  1, 1, 3, 3, -1, "1d2"),
                ],
                "traits": [],
            },
            {
                "nom": "Eclaireur",
                "deplacement": 5,
                "blessure": 1,
                "bravoure": 1,
                "sauvegarde": 7,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Coutelas", 1, 2, 4, 4, 1, "1"),
                ],
                "traits": ["Planqué", "Eclaireur", "Rapide"],
            },
            {
                "nom": "Arbaletrier régulier",
                "deplacement": 4,
                "blessure": 1,
                "bravoure": 1,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Arbalète", 9, 1, 3, 3, -1, "1"),
                ],
                "traits": [],
            },
            {
                "nom": "Hallbardier",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 1,
                "sauvegarde": 6,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Hallbarde", 2, 1, 3, 3, -1, "1"),
                ],
                "traits": ["Anti-Large"],
            },
            {
                "nom": "Officier",
                "deplacement": 3,
                "blessure": 3,
                "bravoure": 2,
                "sauvegarde": 5,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Hallebarde", 2, 1, 3, 3, -1, "1d2"),
                    ("Epée",       1, 2, 3, 3,  1, "1"),
                ],
                "traits": ["Encouragement"],
            },
            {
                "nom": "Mage de guerre",
                "deplacement": 3,
                "blessure": 3,
                "bravoure": 2,
                "sauvegarde": 5,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Epée", 1, 2, 3, 3, 0, "1"),
                ],
                "traits": ["Sort de bataille (2)"],
                "sorts": ["Boule de feu", "Soin", "Armure magique", "Projectile magique", "Mur de force"],
            },
            {
                "nom": "Scorpion",
                "deplacement": 2,
                "blessure": 2,
                "bravoure": 1,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Artillerie",
                "armes": [
                    ("Carreaux de Scorpion", 13, 1, 3, 2, -1, "1d2"),
                ],
                "traits": ["Artillerie legere"],
            },
            {
                "nom": "Baliste",
                "deplacement": 1,
                "blessure": 4,
                "bravoure": 1,
                "sauvegarde": 7,
                "role": "back",
                "size": 2,
                "unit_type": "Artillerie",
                "armes": [
                    ("Carreaux de baliste", 18, 1, 4, 2, -2, "1d4"),
                ],
                "traits": ["Artillerie"],
            },
            {
                "nom": "Housecarl",
                "deplacement": 3,
                "blessure": 4,
                "bravoure": 3,
                "sauvegarde": 6,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Hache à deux mains", 1, 1, 2, 2, -1, "1d2"),
                ],
                "traits": [],
            },
        ],
    },

    # ──────────────── ARMÉE ORLANDAR ────────────────

    "Armée Orlandar": {
        "color": (60, 160, 60),
        "units": [
            {
                "nom": "Fantassin covaliir",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 1,
                "sauvegarde": 7,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Epée",         1, 2, 3, 3,  0, "1"),
                    ("Lance",        2, 1, 3, 3,  0, "1"),
                    ("Hache lourde", 1, 1, 3, 3, -1, "1d2"),
                ],
                "traits": ["Phalange"],
            },
            {
                "nom": "Archer covaliir",
                "deplacement": 4,
                "blessure": 1,
                "bravoure": 1,
                "sauvegarde": 7,
                "role": "back",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Arc long", 11, 1, 3, 3, 0, "1"),
                    ("Glaive",    1, 1, 4, 4, 0, "1"),
                ],
                "traits": [],
            },
            {
                "nom": "Cavalier covaliir",
                "deplacement": 8,
                "blessure": 2,
                "bravoure": 1,
                "sauvegarde": 7,
                "role": "mid",
                "size": 1,
                "unit_type": "Cavalerie",
                "armes": [
                    ("Lance", 2, 1, 3, 3, 0, "1"),
                    ("Arc",   9, 1, 3, 3, 0, "1"),
                ],
                "traits": ["Charge montée"],
            },
            {
                "nom": "Officier covaliir",
                "deplacement": 3,
                "blessure": 3,
                "bravoure": 2,
                "sauvegarde": 6,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Epée à deux mains", 1, 1, 2, 3, 0, "1d2"),
                    ("Epée",              1, 2, 3, 3, 1, "1"),
                ],
                "traits": [],
            },
            {
                "nom": "Equipée de piquier",
                "deplacement": 2,
                "blessure": 2,
                "bravoure": 1,
                "sauvegarde": 6,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Pique", 3, 1, 3, 3, 0, "1"),
                ],
                "traits": ["Phalange", "Anti-Large"],
            },
            {
                "nom": "Catapulte covaliir",
                "deplacement": 1,
                "blessure": 6,
                "bravoure": 1,
                "sauvegarde": 7,
                "role": "back",
                "size": 2,
                "unit_type": "Artillerie",
                "armes": [
                    ("Roche", 24, 1, 5, 5, -3, "2+1d4"),
                ],
                "traits": ["Artillerie"],
            },
            {
                "nom": "Porte-étendard",
                "deplacement": 3,
                "blessure": 1,
                "bravoure": 1,
                "sauvegarde": 7,
                "role": "mid",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Pique drappée", 2, 1, 4, 4, 0, "1"),
                ],
                "traits": ["Encouragement"],
            },
        ],
    },

    # ──────────────── DRACONIE ────────────────

    "Draconie": {
        "color": (200, 60, 60),
        "units": [
            {
                "nom": "Suppléant de Draconie",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 1,
                "sauvegarde": 6,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Epée", 1, 2, 3, 3, 0, "1"),
                ],
                "traits": [],
            },
            {
                "nom": "Cheval de Draconie",
                "deplacement": 8,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 6,
                "role": "front",
                "size": 2,
                "unit_type": "Cavalerie",
                "armes": [
                    ("Sabots", 1, 2, 3, 3, 0, "1"),
                ],
                "traits": ["Charge montée"],
            },
            {
                "nom": "Pourfendeur de Draconie",
                "deplacement": 8,
                "blessure": 6,
                "bravoure": 3,
                "sauvegarde": 5,
                "role": "front",
                "size": 2,
                "unit_type": "Large",
                "armes": [
                    ("Képesh géant",    2, 2, 3, 3,  0, "1d2"),
                    ("Lance d'arçon",   2, 1, 3, 2, -2, "1d3"),
                ],
                "traits": ["Charge montée", "Anti-Infanterie"],
            },
            {
                "nom": "Chevalier-dragon",
                "deplacement": 4,
                "blessure": 6,
                "bravoure": 2,
                "sauvegarde": 5,
                "role": "front",
                "size": 2,
                "unit_type": "Large",
                "armes": [
                    ("Epée à deux mains", 2, 2, 4, 4, 0, "1d2"),
                    ("Hallebarde",        3, 1, 3, 3, -1, "1d2"),
                ],
                "traits": [],
            },
        ],
    },

    # ──────────────── LÉGION SACRÉE ────────────────

    "Légion sacrée": {
        "color": (220, 200, 60),
        "units": [
            {
                "nom": "Légionnaire sacré",
                "deplacement": 2,
                "blessure": 3,
                "bravoure": 2,
                "sauvegarde": 3,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Epée", 1, 2, 3, 2, 0, "1"),
                ],
                "traits": [],
            },
            {
                "nom": "Archer sacré",
                "deplacement": 3,
                "blessure": 2,
                "bravoure": 2,
                "sauvegarde": 5,
                "role": "back",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Arc sacré", 13, 1, 3, 2, -2, "1d2"),
                ],
                "traits": [],
            },
            {
                "nom": "Capitaine sacré",
                "deplacement": 2,
                "blessure": 4,
                "bravoure": 3,
                "sauvegarde": 4,
                "role": "front",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Masse à deux mains", 2, 1, 2, 2, -1, "1d2"),
                ],
                "traits": ["Encouragement"],
            },
        ],
    },

    # ──────────────── HÉROS ────────────────

    "Héros": {
        "color": (255, 215, 0),
        "units": [
            {
                "nom": "Général Kaiden",
                "deplacement": 6,
                "blessure": 6,
                "bravoure": 3,
                "sauvegarde": 4,
                "role": "front",
                "size": 1,
                "unit_type": "Héros",
                "armes": [
                    ("Epée", 1, 3, 3, 2, 0, "1d2"),
                ],
                "traits": ["Encouragement"],
            },
            {
                "nom": "Edolion",
                "deplacement": 6,
                "blessure": 12,
                "bravoure": 3,
                "sauvegarde": 3,
                "role": "front",
                "size": 3,
                "unit_type": "Monstre",
                "armes": [
                    ("Griffe",          3, 2, 4, 2, -2, "1+1d3"),
                    ("Charge Volante", 2, 1, 3, 2, -3, "2+1d4"),
                ],
                "traits": [],
            },
        ],
    },
}


# ═══════════════════════════════════════════════════════════════
#                     FONCTIONS DE CRÉATION
# ═══════════════════════════════════════════════════════════════

def _build_arme(arme_tuple):
    """Crée un objet Arme depuis un tuple (nom, portée, attaques, toucher, blesser, perf, dégâts)."""
    nom, portee, nb_att, toucher, blesser, perf, degats = arme_tuple
    return Arme(nom, nb_attaque=nb_att, toucher=toucher, blesser=blesser,
                perforation=perf, degats=degats, porte=portee)


def create_unit(unit_def, army_color):
    """Crée un objet Unit depuis un dict de définition."""
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
    
    # Traits
    for t in unit_def.get("traits", []):
        tl = t.lower()
        if "encouragement" in tl:
            unit.encouragement_range = 4
        if "anti-infanterie" in tl or "anti infanterie" in tl:
            unit.anti_infanterie = True
        if "anti-large" in tl or "anti large" in tl:
            unit.anti_large = True
        if "phalange" in tl:
            unit.phalange = True
        if "charge montée" in tl or "charge montee" in tl:
            unit.charge_montee = True
        if "charge d'aïda" in tl or "charge d'aida" in tl or "charge aida" in tl:
            unit.charge_aida = True
        # "Sort de bataille (N)" → N sorts par round
        if "sort de bataille" in tl:
            import re
            m = re.search(r'\((\d+)\)', t)
            if m:
                unit.spells_per_round = int(m.group(1))
    
    # Sorts
    SPELL_CATALOG = {
        "Boule de feu":        lambda: SpellFireball(porte=9, toucher=3, blesser=1, perforation=-2, degats="1d4", aoe_size=3, cooldown=2),
        "Soin":                lambda: SpellHeal(porte=6, cooldown=3),
        "Armure magique":      lambda: SpellMagicArmor(porte=4, bonus=2, duration=3, cooldown=4),
        "Projectile magique":  lambda: SpellMagicProjectile(porte=15, toucher=3, blesser=1, degats="3d2", cooldown=1),
        "Mur de force":        lambda: SpellWall(porte=8, nb_obstacles=3, wall_duration=5, cooldown=5),
    }
    
    for spell_name in unit_def.get("sorts", []):
        factory = SPELL_CATALOG.get(spell_name)
        if factory:
            unit.spells.append(factory())
        else:
            print(f"  ATTENTION: sort '{spell_name}' inconnu")
    
    return unit


def get_library():
    """Retourne la base de données brute."""
    return UNIT_DATABASE


def list_armies():
    """Liste les noms d'armées disponibles."""
    return sorted(UNIT_DATABASE.keys())


def list_units(army_name):
    """Liste les noms d'unités d'une armée."""
    army = UNIT_DATABASE.get(army_name)
    if not army:
        return []
    return [u["nom"] for u in army["units"]]


def make_unit(army_name, unit_name):
    """Crée un objet Unit depuis la bibliothèque."""
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
    Exemple: build_army("Armée Skaldienne", [("Infanterie régulière", 10), ("Officier", 2)])
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
            print(f"  Disponibles: {', '.join(unit_by_name.keys())}")
            continue
        for i in range(count):
            u = create_unit(u_def, color)
            short = unit_name[:6]
            u.name = f"{short}{i + 1}" if count > 1 else short
            result.append(u)
    
    return result