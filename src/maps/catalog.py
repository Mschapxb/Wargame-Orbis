"""Catalogue des cartes: types, biomes, reliefs, options du menu."""

from rng_scope import RNG


# ═══════════════════════════════════════════════════════════════
#                    DÉFINITIONS DES MAPS
# ═══════════════════════════════════════════════════════════════

MAP_TYPES = {
    "Prairie": {
        "description": "Campagne vallonnée — collines éparses, bosquets, couloir central ouvert",
        "bg_color": (45, 65, 35),
        "obstacle_color": (70, 90, 55),
        "grid_color": (55, 75, 45),
    },
    "Forêt": {
        "description": "Forêt dense — route centrale et deux chemins latéraux",
        "bg_color": (30, 55, 25),
        "obstacle_color": (20, 70, 15),
        "grid_color": (35, 60, 30),
    },
    "Village": {
        "description": "Village — deux rangées de bâtiments avec rues et place centrale",
        "bg_color": (55, 50, 40),
        "obstacle_color": (90, 70, 50),
        "grid_color": (60, 55, 45),
    },
    "Siège": {
        "description": "Forteresse avec murs et portes défensives",
        "bg_color": (64, 62, 50),
        "obstacle_color": (92, 88, 80),
        "grid_color": (70, 68, 56),
        "wall_color": (100, 100, 110),
        "gate_color": (140, 100, 50),
    },
    "Citadelle": {
        "description": "Double enceinte — mur extérieur à deux portes, basse-cour, donjon",
        "bg_color": (60, 60, 50),
        "obstacle_color": (92, 88, 80),
        "grid_color": (68, 68, 56),
        "wall_color": (100, 100, 110),
        "gate_color": (140, 100, 50),
    },
    "Défilé": {
        "description": "Goulet montagneux — chokepoint central, flancs impraticables",
        "bg_color": (55, 50, 45),
        "obstacle_color": (90, 85, 75),
        "grid_color": (65, 60, 55),
    },
}
# Le Désert est inséré après la Forêt: les trois cartes de rase campagne
# se suivent dans le menu.
MAP_TYPES = dict(list(MAP_TYPES.items())[:2] + [("Désert", {
    "description": "Désert — reg ouvert, dunes, affleurements rocheux et oasis centrale",
    "bg_color": (122, 104, 70),
    "obstacle_color": (150, 128, 92),
    "grid_color": (130, 112, 78),
})] + list(MAP_TYPES.items())[2:])


# ═══════════════════════════════════════════════════════════════
#                    THÈMES ET RELIEF
# ═══════════════════════════════════════════════════════════════
# Une carte = une DISPOSITION (Prairie, Village, Siège…) + des OPTIONS:
#   biome  — "Prairie", "Forêt" ou "Désert": couleurs, décor, végétation
#   river  — une rivière à franchir (gués, ponts)
#   hills  — des collines / dunes
# Chaque disposition a un thème NATUREL: le choisir rend exactement la carte
# historique (mêmes tirages, même équilibrage mesuré). Les autres choix
# ajoutent ou retirent des couches procédurales (cf. procgen.py).

BIOMES = ("Prairie", "Forêt", "Désert")
# Cartes de rase campagne: leur nom EST leur biome
OPEN_MAPS = ("Prairie", "Forêt", "Désert")
# Cartes dont on peut choisir le thème et le relief
THEMED_MAPS = OPEN_MAPS + ("Village", "Siège", "Citadelle")
SIEGE_MAPS = ("Siège", "Citadelle")

RELIEFS = {
    "Plat": (False, False),
    "Rivière": (True, False),
    "Collines": (False, True),
    "Rivière + collines": (True, True),
}
RANDOM_RELIEF = "Aléatoire"

# (rivière, collines) de la carte historique
NATURAL_RELIEF = {
    "Prairie": (False, True),
    "Forêt": (True, False),
    "Désert": (False, True),
    "Village": (False, True),
    "Siège": (False, False),
    "Citadelle": (False, False),
    "Défilé": (True, True),
}

# Teinte appliquée aux couleurs d'une disposition bâtie hors de son biome
_BIOME_TINT = {
    "Forêt": (-16, 2, -12),
    "Désert": (56, 40, 16),
}


def get_map_names():
    return list(MAP_TYPES.keys())


def natural_biome(map_name):
    return map_name if map_name in OPEN_MAPS else "Prairie"


def natural_relief_name(map_name):
    pair = NATURAL_RELIEF.get(map_name, (False, False))
    return next(name for name, v in RELIEFS.items() if v == pair)


def resolve_options(map_name, options=None):
    """Options complètes {biome, river, hills} d'une carte.

    `options` peut donner `relief` (clé de RELIEFS ou "Aléatoire") au lieu
    de `river`/`hills`. Sans options: le thème naturel. Le Défilé n'a pas
    d'options (sa géométrie est son relief). "Aléatoire" ne tire un dé que
    s'il est demandé."""
    river, hills = NATURAL_RELIEF.get(map_name, (False, False))
    biome = natural_biome(map_name)
    if options and map_name in THEMED_MAPS:
        if map_name not in OPEN_MAPS and options.get('biome') in BIOMES:
            biome = options['biome']
        relief = options.get('relief')
        if relief == RANDOM_RELIEF:
            relief = RNG.choice(list(RELIEFS))
        if relief in RELIEFS:
            river, hills = RELIEFS[relief]
        river = bool(options.get('river', river))
        hills = bool(options.get('hills', hills))
    return {'biome': biome, 'river': river, 'hills': hills}


def get_map_info(name, biome=None):
    """Couleurs et description d'une carte, dans le biome demandé.
    `grassy`: le sol porte des brins d'herbe (sinon des gravillons)."""
    base = MAP_TYPES.get(name, MAP_TYPES["Prairie"])
    info = dict(base)
    if biome in _BIOME_TINT and biome != natural_biome(name):
        tint = _BIOME_TINT[biome]
        for key in ("bg_color", "obstacle_color", "grid_color"):
            info[key] = tuple(max(0, min(255, c + d)) for c, d in zip(base[key], tint))
    info['grassy'] = name in ("Prairie", "Forêt") or biome == "Forêt"
    return info


def theme_info(bf):
    """Couleurs du champ de bataille `bf` (disposition + biome choisi)."""
    theme = getattr(bf, 'theme', None) or {}
    return get_map_info(bf.map_name, theme.get('biome'))


def describe_options(map_name, opts):
    """Libellé court pour la console et le menu: « Village, désert, rivière »."""
    if map_name not in THEMED_MAPS or not opts:
        return map_name
    parts = [map_name]
    if map_name not in OPEN_MAPS:
        parts.append(opts['biome'].lower())
    parts.append(next(n for n, v in RELIEFS.items()
                      if v == (opts['river'], opts['hills'])).lower())
    return ", ".join(parts)
