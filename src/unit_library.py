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
    traits          : list      — liste de strings (accents et casse indifférents):
        Encouragement       +1 bravoure à l'armée, +2 au ralliement (rayon 6)
        Anti-Infanterie     -1 toucher et -1 blesser contre l'Infanterie
        Anti-Large          -1 toucher et -1 blesser contre Large/Cavalerie/Monstre
        Phalange            -1 sauvegarde (meilleure) au contact d'une autre Phalange
        Charge montée       +1 dégât à l'attaque de charge
        Charge d'Aïda       -1 blesser à l'attaque de charge
        Sort de bataille (N)  N sorts par round
        Peur / Effroi / Terreur   aura (4 cases): -1 / -2 / -3 bravoure aux ennemis
        Intimidant          un ennemi au contact doit réussir un test de moral pour frapper
        Immunité mentale    insensible à la peur
        Régénération (N)    regagne N % de ses PV max par round (défaut 10), peut se relever
        Vengeance de sang (N)  peut renvoyer un coup reçu à l'attaquant
        Munitions (N)       N volées de tir (défaut 10)
        Rechargement (N)    N rounds de rechargement après un tir sur des troupes
        Débordement         n'est pas arrêté en passant au contact (cavalerie),
                            mais tout coup d'opportunité sur lui touche à -1
        Tirailleur (N)      peut encore faire N cases (défaut 1) après être
                            entré au contact (infanterie légère, escarmouche)
"""

from models import Arme, SpellFireball, SpellHeal, SpellMagicArmor, SpellMagicProjectile, SpellWall
from unit import Unit
import os
import re
import unicodedata
import shutil


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
                "traits": ["Tirailleur"],
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
                "traits": [],
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
                "traits": [],
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
                "size": 2,
                "unit_type": "Cavalerie",
                "armes": [
                    ("Lance", 2, 1, 3, 3, 0, "1"),
                    ("Arc",   9, 1, 3, 3, 0, "1"),
                ],
                "traits": ["Débordement", "Charge montée"],
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
                "traits": [],
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
                "traits": ["Débordement", "Charge montée"],
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

    # ──────────────── ENGINS DE SIÈGE (toute armée peut en aligner) ────────────────
    # Pilotés par siege_engines.py: ils marchent seuls vers leur objectif,
    # POUSSÉS par deux guerriers de mêlée au contact. Toute machine de tir
    # (Artillerie) ne tire et ne bouge qu'avec deux Artilleurs au contact.

    "Engins de siège": {
        "color": (150, 118, 78),
        "units": [
            {
                # Servant de machine: reste collé à sa baliste, son scorpion
                # ou sa catapulte (il en faut deux par machine)
                "nom": "Artilleur",
                "deplacement": 3,
                "blessure": 1,
                "bravoure": 3,
                "sauvegarde": 6,
                "role": "back",
                "size": 1,
                "unit_type": "Infanterie",
                "armes": [
                    ("Coutelas", 1, 1, 5, 5, 0, "1"),
                ],
                "traits": ["Artilleur"],
            },
            {
                # Poutre ferrée sous un toit de peaux mouillées: ×3 contre une
                # porte, ne frappe jamais les troupes. Le toit arrête les
                # flèches, pas l'huile bouillante.
                "nom": "Bélier",
                "deplacement": 2,
                "blessure": 6,
                "bravoure": 6,
                "sauvegarde": 3,
                "role": "front",
                "size": 2,
                "unit_type": "Large",
                "armes": [
                    ("Tête de bélier", 1, 2, 2, 2, -3, "1d3"),
                ],
                "traits": ["Bélier", "Immunité mentale"],
            },
            {
                # Beffroi roulant: ses archers tirent à hauteur du rempart;
                # accolé au mur, il devient une rampe et une passerelle.
                "nom": "Tour de siège",
                "deplacement": 2,
                "blessure": 10,
                "bravoure": 6,
                "sauvegarde": 4,
                "role": "mid",
                "size": 3,
                "unit_type": "Large",
                "armes": [
                    ("Archers de la tour", 10, 2, 4, 4, 0, "1"),
                ],
                "traits": ["Tour de siège", "Immunité mentale", "Munitions (20)"],
            },
        ],
    },
}


# ═══════════════════════════════════════════════════════════════
#                     FONCTIONS DE CRÉATION
# ═══════════════════════════════════════════════════════════════

# Portée ajoutée aux armes de tir des unités « Artillerie » (baliste 18 → 23,
# scorpion 13 → 18, catapulte 24 → 29, baliste de tour comprise)
SIEGE_RANGE_BONUS = 5


def _build_arme(arme_tuple):
    """Crée un objet Arme depuis un tuple (nom, portée, attaques, toucher, blesser, perf, dégâts)."""
    nom, portee, nb_att, toucher, blesser, perf, degats = arme_tuple
    return Arme(nom, nb_attaque=nb_att, toucher=toucher, blesser=blesser,
                perforation=perf, degats=degats, porte=portee)


def _norm(text):
    """Minuscules sans accents: « Régénération » → « regeneration »."""
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c)).lower().strip()


def _trait_number(trait, default):
    """Valeur N d'un trait « Nom (N) », « Nom [N] » ou « Nom (xN) »."""
    m = re.search(r'[\(\[]\s*x?\s*(\d+)\s*x?\s*[\)\]]', trait)
    return int(m.group(1)) if m else default


# Traits de lanceur de sorts (nom normalisé), dont les synonymes du livre
_CASTER_TRAITS = ("sort de bataille", "sorts de bataille", "sortilege", "lanceur de sort",
                  "sort (", "sort eternel", "sorts du tao")


# Traits qui alimentent Unit.special (cf. Unit.__init__). Nom normalisé
# (sans accent) au début du trait → fonction(trait) -> {clé: valeur}.
_SPECIAL_TRAITS = (
    ("peur", lambda t: {"causes_fear": True}),            # aura -1 moral
    ("effroi", lambda t: {"causes_dread": True}),         # aura -2 moral
    ("terreur", lambda t: {"causes_terror": True}),       # aura -3 moral
    ("intimidant", lambda t: {"awe:1": True}),            # mêlée: test de moral pour frapper
    ("immunite mentale", lambda t: {"immune_mind": True}),
    # Synonymes du livre: morts-vivants, créatures artificielles, moines...
    ("mort vivant", lambda t: {"immune_mind": True}),
    ("etre artificiel", lambda t: {"immune_mind": True}),
    ("indemoralisable", lambda t: {"immune_mind": True}),
    ("regeneration", lambda t: {"regeneration": _trait_number(t, 10)}),  # % PV max / round
    ("vengeance de sang", lambda t: {"blood_vengeance": _trait_number(t, 1)}),
    ("munitions", lambda t: {f"ammo:{_trait_number(t, 10)}": True}),
    ("rechargement", lambda t: {f"reload:{_trait_number(t, 1)}": True}),
)


def _traits_to_special(traits):
    """Dictionnaire `special` d'une unité à partir de ses traits lisibles."""
    special = {}
    for t in traits:
        n = _norm(t)
        for prefix, build in _SPECIAL_TRAITS:
            if n.startswith(prefix):
                special.update(build(t))
    return special


def create_unit(unit_def, army_color):
    """Crée un objet Unit depuis un dict de définition."""
    armes = [_build_arme(a) for a in unit_def["armes"]]
    if unit_def.get("unit_type") == "Artillerie":
        # Armes de siège à distance (baliste, scorpion, catapulte): portée
        # allongée, cf. SIEGE_RANGE_BONUS
        for a in armes:
            if a.porte >= 4:
                a.porte += SIEGE_RANGE_BONUS
                a.range = a.base_porte = a.porte

    unit = Unit(
        special=_traits_to_special(unit_def.get("traits", [])),
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
    unit.traits = list(unit_def.get("traits", []))  # affichés sur la fiche d'unité

    # Traits (nom normalisé: sans accent ni majuscule)
    for t in unit_def.get("traits", []):
        n = _norm(t)
        if "encouragement" in n:
            unit.encouragement_range = 4
        if "anti-infanterie" in n or "anti infanterie" in n:
            unit.anti_infanterie = True
        if "anti-large" in n or "anti large" in n:
            unit.anti_large = True
        if "phalange" in n:
            unit.phalange = True
        # Charges: d'Aïda (« Charge Aïdatienne » du livre) = -1 blesser;
        # toutes les autres (montée, de char, du minotaure, volante...)
        # sont traitées en charge montée (+1 dégât)
        if n.startswith(("charge d'aid", "charge aid")):
            unit.charge_aida = True
        elif n.startswith("charge"):
            unit.charge_montee = True
        # Règles de contact (cf. Battlefield._contact_stop)
        if n.startswith(("debordement", "cavalerie legere")):
            unit.contact_breakthrough = True
        if n.startswith(("tirailleur", "escarmouche")):
            unit.contact_slip = _trait_number(t, 1)
        # « Sort de bataille (N) » et synonymes du livre → N sorts par round
        # Engins de siège (cf. siege_engines.py)
        if n.startswith("artilleur"):
            unit.artilleur = True
        if n.startswith("belier"):
            unit.siege_engine = "ram"
        elif n.startswith("tour de siege"):
            unit.siege_engine = "tower"
        if n.startswith(_CASTER_TRAITS):
            unit.spells_per_round = _trait_number(t, unit.spells_per_round)
    
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
            u.contingent = army_name
            result.append(u)
    
    return result


# ═══════════════════════════════════════════════════════════════
#               CHARGEMENT DES UNITÉS CUSTOM
# ═══════════════════════════════════════════════════════════════

TOKENS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")


def install_token(token_path, unit_name):
    """Copie l'image token_path dans tokens/<unit_name>.png (nom que le rendu
    cherche). Renvoie True si le token est en place, False sinon (avec un
    avertissement: un token manquant ne doit pas passer inaperçu)."""
    if not token_path or not os.path.exists(token_path):
        return False
    os.makedirs(TOKENS_DIR, exist_ok=True)
    dest = os.path.join(TOKENS_DIR, f"{unit_name}.png")
    if os.path.abspath(token_path) == os.path.abspath(dest):
        return True
    try:
        shutil.copy2(token_path, dest)
    except OSError as e:
        print(f"  ATTENTION: token de '{unit_name}' non copié ({token_path}): {e}")
        return False
    return True


CUSTOM_ARMY_NAME = "Unités custom"
CUSTOM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_units")


def load_custom_units_into_db():
    """Charge toutes les fiches JSON de custom_units/ dans UNIT_DATABASE.
    
    Les unités custom sont regroupées sous l'armée 'Unités custom'.
    Appelé au démarrage et après chaque édition dans l'éditeur.
    """
    import json
    
    if not os.path.isdir(CUSTOM_DIR):
        # Pas de dossier custom → retirer l'armée custom si elle existait
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
            
            # Valider les champs obligatoires
            if "nom" not in data or "armes" not in data:
                continue
            
            # Construire le dict au format attendu par create_unit
            unit_def = {
                "nom": data["nom"],
                "deplacement": data.get("deplacement", 3),
                "blessure": data.get("blessure", 2),
                "bravoure": data.get("bravoure", 2),
                "sauvegarde": data.get("sauvegarde", 5),
                "role": data.get("role", "front"),
                "size": data.get("size", 1),
                "unit_type": data.get("unit_type", "Infanterie"),
                "armes": data.get("armes", []),
                "traits": data.get("traits", []),
                "sorts": data.get("sorts", []),
            }
            
            # Copier le token dans tokens/ si token_path existe
            token_path = data.get("token_path", "")
            if token_path and not os.path.isabs(token_path):
                token_path = os.path.normpath(os.path.join(os.path.dirname(filepath), token_path))
            install_token(token_path, data["nom"])
            
            units.append(unit_def)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"  ATTENTION: fichier custom '{fname}' invalide: {e}")
    
    if units:
        UNIT_DATABASE[CUSTOM_ARMY_NAME] = {
            "color": (180, 140, 220),  # Violet pour les custom
            "units": units,
        }
    else:
        UNIT_DATABASE.pop(CUSTOM_ARMY_NAME, None)


# ═══════════════════════════════════════════════════════════════
#          ARMÉES DU LIVRE DE RÈGLES (armees_livre.json)
# ═══════════════════════════════════════════════════════════════

LIVRE_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "armees_livre.json")


def load_livre_into_db(path=LIVRE_JSON):
    """Ajoute les armées et unités du livre (générées par livre_import.py).

    Une unité déjà définie à la main dans son armée n'est JAMAIS remplacée:
    le livre ne fait que compléter (nouvelles armées, unités manquantes).
    Renvoie le nombre d'unités ajoutées."""
    import json

    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            armies = json.load(f).get("armies", {})
    except (OSError, ValueError) as e:
        print(f"  ATTENTION: {os.path.basename(path)} illisible: {e}")
        return 0
    added = 0
    for army_name, data in armies.items():
        army = UNIT_DATABASE.setdefault(
            army_name, {"color": tuple(data.get("color", (160, 160, 160))), "units": []})
        known = {_norm(u["nom"]) for u in army["units"]}
        for u in data.get("units", []):
            if _norm(u["nom"]) in known:
                continue
            u = dict(u, armes=[tuple(a) for a in u["armes"]], source="livre")
            army["units"].append(u)
            known.add(_norm(u["nom"]))
            added += 1
    return added


# Chargement automatique au démarrage (livre d'abord: les unités custom
# gardent leur propre armée)
load_livre_into_db()
load_custom_units_into_db()