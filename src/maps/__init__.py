"""Système de cartes — génère différents terrains pour le champ de bataille.

Types de cellules dans la grille:
    0 = vide (traversable)
    1 = obstacle (infranchissable; rocher, maison, haie ou cœur de bosquet:
        coupe la ligne de tir, comme les murs, les portes fermées intactes
        et le terrain à effets — bois, collines, cf. terrain.blocks_line)
    2 = mur (infranchissable, unités dessus = +2 svg, CaC ne passe pas)
    3 = porte (destructible, a des PV)

Les cartes de bataille rangée (Prairie, Forêt, Désert, Village, Défilé)
sont symétriques: grille et terrain de la moitié ouest sont recopiés à
l'est. Les obstacles `1` de Prairie, Forêt, Désert et Village sont des
structures destructibles (cf. generate_structures et structures.py).

Thèmes: chaque carte (sauf le Défilé) accepte un biome et un relief
(rivière, collines) posés en couches procédurales — cf. « THÈMES ET
RELIEF » (maps/themes.py) et procgen.py.

Organisation du paquet:
    catalog     types de cartes, biomes, reliefs, options du menu
    common      miroir, chemins (BFS), front de déploiement
    open_field  Prairie, Forêt, Désert
    village     Village
    siege       Siège et Citadelle
    defile      Défilé
    themes      couches de relief et de biome
    advantage   avantage de terrain
    decor       décor visuel, taches de sol, structures
Tous leurs noms sont réexportés ici: `import maps; maps.generate_map(...)`.
"""

import random

from rng_scope import RNG

from .catalog import (  # noqa: F401
    BIOMES,
    MAP_TYPES,
    NATURAL_RELIEF,
    OPEN_MAPS,
    NATURAL_SEASON,
    RANDOM_RELIEF,
    RANDOM_SEASON,
    RELIEFS,
    SEASONS,
    SIEGE_MAPS,
    THEMED_MAPS,
    _BIOME_TINT,
    describe_options,
    get_map_info,
    get_map_names,
    natural_biome,
    natural_relief_name,
    resolve_options,
    resolve_season,
    theme_info,
)
from .common import (  # noqa: F401
    _bfs_path,
    _carve,
    _connected,
    _mirror_grid,
    _mirror_terrain,
    _paint_disc,
    deploy_front,
)
from .open_field import (  # noqa: F401
    generate_desert,
    generate_forest,
    generate_prairie,
)
from .village import (  # noqa: F401
    generate_village,
)
from .siege import (  # noqa: F401
    _build_wall,
    _siege_copses,
    generate_citadel,
    generate_siege,
)
from .defile import (  # noqa: F401
    generate_defile,
)
from .themes import (  # noqa: F401
    _add_hills,
    _add_river,
    _apply_biome,
    _clear_village_houses_near,
    _ensure_crossing,
    _field_x_range,
    _gate_rows,
    _remove_river,
    apply_theme,
)
from .advantage import (  # noqa: F401
    ADVANTAGE_LEVELS,
    ADVANTAGE_NONE,
    ADVANTAGE_SIDES,
    advantage_of,
    apply_advantage,
)
from .fortification import (  # noqa: F401
    GATE_HP,
    LEVELS as FORTIFICATION_LEVELS,
    DESCRIPTIONS as FORTIFICATION_DESCRIPTIONS,
    apply_fortification,
    level_of as fortification_of,
)
from .landscape import (  # noqa: F401
    CROPS,
    generate_fields,
    generate_paths,
    siege_camp,
)
from .open_field import (  # noqa: F401
    DESERT_STYLES,
    FOREST_STYLES,
    PRAIRIE_STYLES,
)
from .decor import (  # noqa: F401
    _DECOR_TABLES,
    _DESERT_SWAP,
    _NO_DECOR_TERRAIN,
    _WOOD_DECOR,
    _WOOD_DECOR_DESERT,
    _decor_table,
    _weighted_pick,
    generate_decor,
    generate_ground_patches,
    generate_structures,
)


# ═══════════════════════════════════════════════════════════════
#                    FONCTION PRINCIPALE
# ═══════════════════════════════════════════════════════════════

def generate_map(map_name, width, height, options=None):
    """Génère la grille et les données spéciales pour un type de map.

    options: {'biome', 'relief'} ou {'biome', 'river', 'hills'} (cf.
    resolve_options), plus 'advantage' (0/1/2 ou "Armée 1"…) et
    'advantage_level' (cf. apply_advantage), et pour un siège
    'fortification' (1-3, cf. maps/fortification.py). Sans options, la
    carte historique.

    Retourne (grid, map_data) où:
        grid: [[int]] — grille 2D (0=vide, 1=obstacle, 2=mur, 3=porte)
        map_data: dict — données spéciales (siege_data, etc.), dont
            'theme': les options résolues {'biome', 'river', 'hills'}
    """
    generators = {
        "Prairie": generate_prairie,
        "Forêt": generate_forest,
        "Désert": generate_desert,
        "Village": generate_village,
        "Siège": generate_siege,
        "Citadelle": generate_citadel,
        "Défilé": generate_defile,
    }

    gen = generators.get(map_name, generate_prairie)
    opts = resolve_options(map_name, options)
    grid, map_data = gen(width, height)
    map_data = dict(map_data or {})
    # Clés privées des générateurs: le style tiré va dans le thème, les
    # tracés de rues et de sentiers deviennent des chemins (visuels)
    style = map_data.pop('_style', None)
    hint_paths = map_data.pop('_paths', None)
    if style:
        opts = dict(opts, style=style)
    apply_theme(map_name, grid, map_data, width, height, opts)
    side, level = advantage_of(options)
    if side and map_name not in SIEGE_MAPS:
        apply_advantage(map_name, grid, map_data, width, height, side, level)
        opts = dict(opts, advantage=side, advantage_level=level)
    if map_name in SIEGE_MAPS:
        apply_fortification(map_data, fortification_of(options))
    map_data['theme'] = opts
    # Paysage visuel (chemins, champs, camp) et décor: un seul dé tiré du
    # flux de la carte, tout le reste sur un générateur local
    local = random.Random(RNG.randrange(1 << 30))
    terr = map_data.get('terrain')
    paths = generate_paths(map_name, grid, width, height, map_data, hint_paths, local)
    map_data['paths'] = paths
    map_data['fields'] = generate_fields(map_name, grid, width, height, map_data, style, local)
    on_road = {(int(x), int(y)) for p in paths for (x, y) in p}
    decor = generate_decor(map_name, grid, width, height, terr, opts['biome'],
                           opts.get('season'), rng=local, avoid=on_road)
    if map_name in SIEGE_MAPS:
        camp = siege_camp(grid, width, height, local)
        taken = {(x, y) for (x, y, _k, _s) in camp}
        decor = [d for d in decor if (d[0], d[1]) not in taken] + camp
    map_data['decor'] = decor
    map_data['ground_patches'] = generate_ground_patches(map_name, width, height,
                                                         opts['biome'])
    if 'structures' not in map_data:
        map_data['structures'] = generate_structures(map_name, grid, width, height)
    return grid, map_data
