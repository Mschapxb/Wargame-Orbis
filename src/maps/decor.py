"""Décor purement visuel, taches de sol et structures destructibles."""

import random

from rng_scope import RNG
import structures as st
import terrain as tr

from .catalog import natural_biome


# ═══════════════════════════════════════════════════════════════
#                 DÉCOR (purement visuel)
# ═══════════════════════════════════════════════════════════════
# Ces objets n'ont AUCUN effet de jeu: ils ne bloquent rien, ne coupent
# aucune ligne de vue, n'entrent pas dans la grille. Ils existent pour que
# le champ de bataille ressemble à un lieu plutôt qu'à un damier.
#
# Règle de lisibilité: les gros objets (arbres, charrettes, troncs) ne se
# posent que sur les marges et autour des couverts existants — jamais en
# plein milieu du champ où se joue le combat, sinon ils masquent les
# unités.

# Sous-bois: les ARBRES d'un bois sont dessinés par le rendu du terrain
# (terrain_render.tall_sprites: ils disparaissent quand le bois brûle); le
# décor n'y sème que ce qui pousse à leurs pieds.
_WOOD_DECOR = {
    'density': 0.30,
    'big': [("fougere", 5), ("champignon", 2), ("souche", 2), ("tronc", 1)],
}
# Au désert, le « bois » est une palmeraie clairsemée
_WOOD_DECOR_DESERT = {
    'density': 0.20,
    'big': [("buisson_sec", 3), ("caillou", 2)],
}
# Ce que la saison fait du petit décor (l'hiver couvre les fleurs, l'automne
# les fane)
_SEASON_SWAP = {
    "Hiver": {"fleurs": "caillou", "herbe_haute": "herbe", "champignon": "caillou",
              "fougere": "herbe", "botte_foin": "bois_pile"},
    "Automne": {"fleurs": "herbe_haute"},
}
# Et ce qu'elle ajoute: (nature, poids) au petit décor
_SEASON_EXTRA = {
    "Printemps": [("fleurs", 5)],
    "Automne": [("champignon", 1), ("souche", 1)],
}
# Ce que devient un objet de décor verdoyant sous le soleil du désert
_DESERT_SWAP = {
    "herbe": "caillou", "herbe_haute": "buisson_sec", "fleurs": "caillou",
    "fougere": "buisson_sec", "champignon": "caillou", "buisson": "buisson_sec",
    "arbre_pin": "buisson_sec", "arbre_rond": "rocher", "botte_foin": "caisse",
    "souche": "rocher", "tronc": "buisson_sec",
}
_NO_DECOR_TERRAIN = {tr.RIVER, tr.FORD, tr.BRIDGE, tr.LAKE}

# (nature, poids) par carte — "petit" = herbes, fleurs, cailloux…
_DECOR_TABLES = {
    "Prairie": {
        'density': 0.13,
        'small': [("herbe", 5), ("fleurs", 2), ("caillou", 2), ("herbe_haute", 2)],
        'big':   [("buisson", 4), ("arbre_rond", 2), ("souche", 1), ("rocher", 2)],
    },
    "Forêt": {
        'density': 0.20,
        'small': [("herbe", 4), ("fougere", 5), ("champignon", 1), ("caillou", 1)],
        'big':   [("buisson", 4), ("arbre_pin", 3), ("arbre_rond", 3), ("souche", 2),
                  ("tronc", 2)],
    },
    "Village": {
        'density': 0.10,
        'small': [("herbe", 3), ("caillou", 2), ("seau", 1), ("paves", 3)],
        'big':   [("caisse", 3), ("tonneau", 3), ("botte_foin", 2), ("charrette", 1),
                  ("buisson", 2)],
    },
    "Citadelle": {
        'density': 0.08,
        'small': [("caillou", 3), ("gravats", 2), ("herbe", 2)],
        'big':   [("caisse", 2), ("tonneau", 2), ("brasero", 1), ("pieux", 2),
                  ("gravats_tas", 2)],
    },
    "Siège": {
        'density': 0.09,
        'small': [("caillou", 3), ("gravats", 3), ("herbe", 1)],
        'big':   [("gravats_tas", 3), ("caisse", 2), ("tonneau", 2), ("brasero", 1),
                  ("pieux", 2)],
    },
    "Défilé": {
        'density': 0.15,
        'small': [("caillou", 5), ("gravats", 2), ("herbe", 1)],
        'big':   [("rocher", 4), ("buisson_sec", 3), ("souche", 1)],
    },
    "Désert": {
        'density': 0.09,
        'small': [("caillou", 5), ("gravats", 2)],
        'big':   [("rocher", 4), ("buisson_sec", 4), ("gravats_tas", 1)],
    },
}


def _decor_table(map_name, biome=None):
    """Table de décor d'une disposition, adaptée à son biome."""
    table = _DECOR_TABLES.get(map_name, _DECOR_TABLES["Prairie"])
    if biome is None or biome == natural_biome(map_name):
        return table
    if biome == "Désert":
        def swap(entries):
            merged = {}
            for kind, w in entries:
                k = _DESERT_SWAP.get(kind, kind)
                merged[k] = merged.get(k, 0) + w
            return list(merged.items())
        return {'density': table['density'] * 0.8,
                'small': swap(table['small']), 'big': swap(table['big'])}
    if biome == "Forêt":
        return {'density': table['density'] * 1.2,
                'small': table['small'] + [("fougere", 3), ("champignon", 1)],
                'big': table['big'] + [("buisson", 3), ("souche", 2), ("tronc", 1)]}
    return table


def _weighted_pick(rng, table):
    total = sum(w for _, w in table)
    r = rng.uniform(0, total)
    acc = 0.0
    for kind, w in table:
        acc += w
        if r <= acc:
            return kind
    return table[-1][0]


def _clumps(rng, width, height, cell=7.0):
    """Densité locale du petit décor, en [0,3; 1,7] (moyenne ≈ 1): un bruit
    lissé qui groupe fleurs et cailloux en touffes et en prés fleuris au
    lieu de les semer uniformément."""
    nx, ny = int(width / cell) + 3, int(height / cell) + 3
    lat = [[rng.random() for _ in range(ny)] for _ in range(nx)]
    out = [[1.0] * height for _ in range(width)]
    for x in range(width):
        fx = x / cell
        ix, tx = int(fx), fx - int(fx)
        tx = tx * tx * (3 - 2 * tx)
        for y in range(height):
            fy = y / cell
            iy, ty = int(fy), fy - int(fy)
            ty = ty * ty * (3 - 2 * ty)
            a = lat[ix][iy] + (lat[ix + 1][iy] - lat[ix][iy]) * tx
            b = lat[ix][iy + 1] + (lat[ix + 1][iy + 1] - lat[ix][iy + 1]) * tx
            out[x][y] = 0.3 + 1.4 * (a + (b - a) * ty)
    return out


def _season_table(entries, season):
    swap = _SEASON_SWAP.get(season, {})
    merged = {}
    for kind, w in list(entries) + _SEASON_EXTRA.get(season, []):
        k = swap.get(kind, kind)
        merged[k] = merged.get(k, 0) + w
    return list(merged.items())


def generate_decor(map_name, grid, width, height, terrain=None, biome=None, season=None,
                   rng=None, avoid=()):
    """Sème le décor sur les cases libres. Retourne [(x, y, kind, seed)].

    Utilise sa propre RNG (une seule ponction sur le flux global, ou `rng`
    fourni par l'appelant) pour ne pas décaler les dés de la bataille.
    `season`: l'hiver couvre les fleurs, le printemps en ajoute… `avoid`:
    cases où ne poser aucun gros objet (chemins).
    """
    table = _decor_table(map_name, biome)
    is_desert = (biome or natural_biome(map_name)) == "Désert"
    wood_decor = _WOOD_DECOR_DESERT if is_desert else _WOOD_DECOR
    if season and not is_desert:
        table = dict(table, small=_season_table(table['small'], season),
                     big=_season_table(table['big'], season))
        wood_decor = dict(wood_decor, big=_season_table(wood_decor['big'], season))
    if rng is None:
        rng = random.Random(RNG.randrange(1 << 30))
    avoid = set(avoid)
    clumps = _clumps(rng, width, height)

    density = table['density']
    margin_top = height // 4          # au-delà: zone de manœuvre, on allège
    margin_bottom = height - height // 4
    props = []
    occupied = set()

    for x in range(1, width - 1):
        for y in range(1, height - 1):
            if grid[x][y] != 0:
                continue
            tname = terrain[x][y] if terrain is not None else tr.PLAIN
            if tname in _NO_DECOR_TERRAIN:
                continue
            if tname == tr.WOOD:
                if rng.random() > wood_decor['density']:
                    continue
                if any((x + dx, y + dy) in occupied
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    continue
                occupied.add((x, y))
                props.append((x, y, _weighted_pick(rng, wood_decor['big']),
                              rng.randrange(1 << 16)))
                continue
            if rng.random() > density * clumps[x][y]:
                continue
            # Un gros objet n'a droit de cité que sur les marges ou en
            # lisière d'un couvert existant.
            near_cover = any(
                0 <= x + dx < width and 0 <= y + dy < height
                and grid[x + dx][y + dy] in (1, 2)
                for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            on_margin = y < margin_top or y > margin_bottom
            if (on_margin or near_cover) and rng.random() < 0.55 and (x, y) not in avoid:
                kind = _weighted_pick(rng, table['big'])
                if terrain is not None and kind in ("arbre_pin", "arbre_rond"):
                    kind = "buisson"
                # Les gros objets ne se collent pas les uns aux autres
                if any((x + dx, y + dy) in occupied
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    continue
                occupied.add((x, y))
            else:
                kind = _weighted_pick(rng, table['small'])
            props.append((x, y, kind, rng.randrange(1 << 16)))

    return props


def generate_ground_patches(map_name, width, height, biome=None):
    """Grandes taches de sol (terre battue, herbe rase, mousse, gravier).

    Le bruit calculé par case produit forcément des carrés alignés sur la
    grille. Ces ellipses, elles, ignorent la grille: c'est ce qui enlève
    l'aspect « tableur » du terrain.
    """
    rng = random.Random(RNG.randrange(1 << 30))
    n = max(12, (width * height) // 55)
    # (teinte RGB relative au fond, opacité)
    palettes = {
        "Prairie": [((-16, -10, -8), 70), ((14, 26, -10), 60), ((30, 10, -16), 48)],
        "Forêt":   [((-18, -14, -10), 74), ((4, 28, 2), 54), ((26, 12, -12), 44)],
        "Village": [((26, 16, -6), 60), ((-22, -18, -14), 62), ((10, 14, 18), 42)],
        "Siège":   [((-20, -20, -16), 60), ((22, 18, 14), 46), ((26, 10, -8), 38)],
        "Citadelle": [((-20, -20, -16), 60), ((22, 18, 14), 46), ((26, 10, -8), 38)],
        "Défilé":  [((26, 18, 2), 56), ((-24, -22, -18), 58), ((14, 14, 18), 40)],
        "Désert":  [((24, 18, 6), 58), ((-22, -20, -14), 52), ((14, 4, -10), 44)],
    }
    if biome is not None and biome != natural_biome(map_name):
        pal = palettes[biome]
    else:
        pal = palettes.get(map_name, palettes["Prairie"])

    patches = []
    for _ in range(n):
        fx = rng.uniform(1, width - 1)
        fy = rng.uniform(1, height - 1)
        rw = rng.uniform(1.8, 5.5)
        rh = rw * rng.uniform(0.45, 0.85)
        tint, alpha = pal[rng.randrange(len(pal))]
        patches.append((fx, fy, rw, rh, tint, alpha))
    return patches


def generate_structures(map_name, grid, width, height):
    """Ce que sont les obstacles `1` d'une carte, pour la destruction
    (cf. structures.py). Calculé sur la grille finale, donc déjà en miroir.
    Les masses rocheuses du Défilé restent indestructibles: pas de structure."""
    obstacles = [(x, y) for x in range(width) for y in range(height) if grid[x][y] == 1]
    if map_name == "Village":
        return st.classify_village(grid, width, height)
    if map_name == "Forêt":
        return {c: st.GROVE for c in obstacles}
    if map_name in ("Prairie", "Désert"):
        return {c: st.ROCK for c in obstacles}
    return {}
