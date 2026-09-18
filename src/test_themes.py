"""Tests des thèmes de carte (biome × relief procéduraux). Script exécutable:
    python test_themes.py            # tout
    python test_themes.py riviere    # seulement les tests dont le nom contient 'riviere'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import maps
import structures as st
import terrain as tr
import unit_library as ul
from battle import Battle

TESTS = []
SIZES = ((40, 30), (178, 64))
SYMMETRIC = ("Prairie", "Forêt", "Désert", "Village")


def test(fn):
    TESTS.append(fn)
    return fn


def combos(names=maps.THEMED_MAPS):
    for name in names:
        for biome in maps.BIOMES:
            for relief in maps.RELIEFS:
                if name in maps.OPEN_MAPS and biome != name:
                    continue            # le biome d'une rase campagne est son nom
                yield name, {'biome': biome, 'relief': relief}


def names_in(terr):
    return {n for col in terr for n in col}


@test
def test_theme_naturel_identique_a_la_carte_historique():
    """Choisir le thème naturel rend EXACTEMENT la carte sans options: même
    grille, même terrain, même décor (donc mêmes équilibrages mesurés)."""
    for name in maps.THEMED_MAPS:
        opts = {'biome': maps.natural_biome(name), 'relief': maps.natural_relief_name(name)}
        for seed in range(3):
            random.seed(seed)
            g1, d1 = maps.generate_map(name, 60, 40)
            after1 = random.random()
            random.seed(seed)
            g2, d2 = maps.generate_map(name, 60, 40, opts)
            assert g1 == g2 and d1['terrain'] == d2['terrain'], (name, seed)
            assert d1['decor'] == d2['decor'], (name, seed)
            assert random.random() == after1, f"{name}: dés consommés en plus"


@test
def test_miroir_des_themes():
    for name, opts in combos(SYMMETRIC):
        for (w, h) in SIZES:
            random.seed(31)
            grid, data = maps.generate_map(name, w, h, opts)
            terr = data['terrain']
            for x in range(w // 2):
                for y in range(h):
                    assert grid[x][y] == grid[w - 1 - x][y], (name, opts, w, x, y)
                    assert terr[x][y] == terr[w - 1 - x][y], (name, opts, w, x, y, terr[x][y])
            s = data['structures']
            for (x, y), kind in s.items():
                assert s.get((w - 1 - x, y)) == kind, (name, opts, x, y)


@test
def test_riviere_et_collines_presentes_ou_absentes():
    for name, opts in combos():
        river, hills = maps.RELIEFS[opts['relief']]
        for (w, h) in SIZES:
            random.seed(47)
            grid, data = maps.generate_map(name, w, h, opts)
            got = names_in(data['terrain'])
            assert data['theme']['river'] == river and data['theme']['hills'] == hills
            if river:
                assert tr.RIVER in got and (got & {tr.FORD, tr.BRIDGE}), (name, opts, w)
            else:
                assert not (got & {tr.RIVER, tr.FORD, tr.BRIDGE}), (name, opts, w, got)
            if name in maps.SIEGE_MAPS:
                # Glacis et butte du donjon sont des ouvrages, pas du relief
                wall_x = data['rings'][0]['wall_x'] if data.get('rings') else data['wall_x']
                natural = any(data['terrain'][x][y] == tr.HILL
                              for x in range(wall_x) for y in range(h))
                assert natural == hills, (name, opts, w)
            else:
                assert (tr.HILL in got) == hills, (name, opts, w, got)


@test
def test_passages_d_un_camp_a_l_autre():
    """Deux passages disjoints (grande carte), un sans marais."""
    for name, opts in combos(SYMMETRIC):
        for (w, h) in SIZES:
            for seed in range(4):
                random.seed(200 + seed)
                grid, data = maps.generate_map(name, w, h, opts)
                terr = data['terrain']
                ok = lambda x, y: grid[x][y] == 0 and tr.MOVE[terr[x][y]] is not None  # noqa: B023
                left = [(1, y) for y in range(h) if ok(1, y)]
                right = [(w - 2, y) for y in range(h) if ok(w - 2, y)]
                p1 = maps._bfs_path(grid, w, h, left, right, terr)
                assert p1, (name, opts, w, seed)
                if w > 60:
                    assert maps._bfs_path(grid, w, h, left, right, terr,
                                          blocked=set(p1[1:-1])), (name, opts, w, seed)
                assert maps._bfs_path(grid, w, h, left, right, terr, avoid=(tr.MARSH,)), \
                    (name, opts, w, seed)


@test
def test_siege_riviere_franchissable_devant_chaque_porte():
    for name in maps.SIEGE_MAPS:
        for (w, h) in SIZES:
            for seed in range(4):
                random.seed(300 + seed)
                grid, data = maps.generate_map(name, w, h, {'biome': "Désert", 'relief': "Rivière"})
                terr = data['terrain']
                wall_x = data['rings'][0]['wall_x'] if data.get('rings') else data['wall_x']
                river_x = [x for x in range(w) for y in range(h) if terr[x][y] == tr.RIVER]
                assert river_x and max(river_x) < wall_x - 3, (name, w, seed)
                for gy in data['gate_positions']:
                    assert tr.BRIDGE in {terr[x][gy] for x in range(wall_x)}, (name, w, seed, gy)
                    start = [(1, y) for y in range(1, h - 1) if grid[1][y] == 0]
                    assert maps._bfs_path(grid, w, h, start, [(wall_x - 1, gy)], terr), (name, w, seed)
                for (x, y), kind in data['structures'].items():
                    assert grid[x][y] == (2 if kind == st.WALL else 1), (name, x, y, kind)


@test
def test_biome_desert_et_foret():
    random.seed(8)
    _, prairie = maps.generate_map("Village", 178, 64, {'biome': "Prairie", 'relief': "Collines"})
    random.seed(8)
    _, foret = maps.generate_map("Village", 178, 64, {'biome': "Forêt", 'relief': "Collines"})
    random.seed(8)
    _, desert = maps.generate_map("Village", 178, 64, {'biome': "Désert", 'relief': "Plat"})
    wood = lambda d: sum(col.count(tr.WOOD) for col in d['terrain'])
    assert wood(foret) > wood(prairie) > wood(desert), (wood(foret), wood(prairie), wood(desert))
    green = {"herbe", "herbe_haute", "fleurs", "fougere", "arbre_pin"}
    assert not any(k in green for (_, _, k, _) in desert['decor'])
    assert maps.get_map_info("Village", "Désert")['bg_color'] != maps.get_map_info("Village")['bg_color']


@test
def test_deploiement_hors_des_couches():
    """Aucune unité déployée dans l'eau, le bois ou le marais d'un thème."""
    comp1 = [("Infanterie régulière", 10), ("Arbaletrier régulier", 5)]
    comp2 = [("Fantassin covaliir", 10), ("Archer covaliir", 5), ("Cavalier covaliir", 3)]
    for name, opts in combos():
        if opts['relief'] != "Rivière + collines" and opts['biome'] != "Forêt":
            continue
        for (w, h) in SIZES:
            random.seed(77)
            b = Battle(ul.build_army("Armée Skaldienne", comp1),
                       ul.build_army("Armée Orlandar", comp2), w, h, 8,
                       map_name=name, map_options=opts)
            bf = b.battlefield
            assert bf.theme['biome'] == opts['biome'] if name not in maps.OPEN_MAPS else True
            for u in b.army1 + b.army2:
                t = tr.at(bf, *u.position)
                assert tr.MOVE[t] == 1.0, (name, opts, w, u.name, u.position, t)


@test
def test_relief_aleatoire_et_bataille_jouable():
    random.seed(5)
    seen = set()
    for _ in range(12):
        opts = maps.resolve_options("Prairie", {'relief': maps.RANDOM_RELIEF})
        seen.add((opts['river'], opts['hills']))
    assert len(seen) >= 3, seen
    comp = [("Infanterie régulière", 4), ("Arbaletrier régulier", 2)]
    for name in ("Désert", "Citadelle"):
        random.seed(9)
        b = Battle(ul.build_army("Armée Skaldienne", comp), ul.build_army("Armée Skaldienne", comp),
                   40, 30, 8, map_name=name,
                   map_options={'biome': "Désert", 'relief': "Rivière + collines"})
        for _ in range(25):
            if b.is_battle_over():
                break
            b.simulate_round()


# ── Runner (ajouter les nouveaux tests AU-DESSUS de cette ligne) ──

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    fails = []
    for fn in TESTS:
        if only and only not in fn.__name__:
            continue
        try:
            random.seed(7)
            fn()
            print(f"  OK    {fn.__name__}")
        except Exception:
            fails.append(fn.__name__)
            print(f"  ECHEC {fn.__name__}")
            traceback.print_exc()
    print()
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests de thèmes passent.")
    sys.exit(1 if fails else 0)
