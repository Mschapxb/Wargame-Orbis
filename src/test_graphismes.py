"""Graphismes et cartes aléatoires: saisons, sprites de décor, figurines,
styles de carte, étangs, chemins et champs. Script exécutable:
    python test_graphismes.py            # tout
    python test_graphismes.py saison     # seulement les tests dont le nom contient 'saison'
"""
import os, sys, random, traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("WARGAME_ORBIS_SETTINGS", "memory")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pygame
pygame.init()
pygame.display.set_mode((1, 1))

import maps
import renderer as R
import scenery
import structures as st
import terrain as tr
import terrain_render as trr
import unit_library as ul
import unit_sprites
from battle import Battle
from maps.common import deploy_front

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def small_army():
    return ul.build_army("Armée Skaldienne", [("Infanterie régulière", 3)])


# ─── Saisons ───

@test
def test_saison_aleatoire_deduite_de_la_graine_sans_tirer_de_de():
    assert set(maps.SEASONS) == set(scenery.SEASONS)
    seen = set()
    for seed in range(40):
        opts = {'season': maps.RANDOM_SEASON, 'seed': seed}
        state = random.getstate()
        s1 = maps.resolve_season(opts)
        assert random.getstate() == state, "la saison ne doit pas tirer de dé"
        assert s1 == maps.resolve_season(opts) and s1 in maps.SEASONS
        seen.add(s1)
    assert seen == set(maps.SEASONS), seen
    assert maps.resolve_season({'season': maps.RANDOM_SEASON}) == maps.NATURAL_SEASON
    assert maps.resolve_season({'season': "Hiver", 'seed': 3}) == "Hiver"
    assert maps.resolve_season(None) == maps.NATURAL_SEASON


@test
def test_saison_ne_change_pas_la_carte():
    """La saison est purement visuelle: même grille, même terrain."""
    for name in ("Prairie", "Village", "Siège"):
        random.seed(12)
        base = maps.generate_map(name, 60, 40, {'seed': 12})
        for season in maps.SEASONS:
            random.seed(12)
            g, d = maps.generate_map(name, 60, 40, {'seed': 12, 'season': season})
            assert g == base[0] and d['terrain'] == base[1]['terrain'], (name, season)
            assert d['theme']['season'] == season


@test
def test_hiver_enneige_le_sol_sauf_au_desert():
    snow = maps.get_map_info("Prairie", "Prairie", "Hiver")["bg_color"]
    summer = maps.get_map_info("Prairie", "Prairie", "Été")["bg_color"]
    assert sum(snow) > 500 and sum(summer) < 300, (snow, summer)
    desert = maps.get_map_info("Désert", "Désert", "Hiver")["bg_color"]
    assert sum(desert) < 400, desert


# ─── Sprites ───

@test
def test_tous_les_sprites_de_decor_se_dessinent():
    for biome in ("Prairie", "Forêt", "Désert"):
        for season in scenery.SEASONS:
            for kind in scenery.KINDS:
                for state in (0, 2, 3) if kind.startswith("arbre") or kind == "rocher" else (0,):
                    img, (ax, ay) = scenery.sprite(kind, 3, 24, biome, season, state)
                    assert img.get_width() > 4 and img.get_height() > 4, (kind, biome, season)
                    assert 0 <= ax <= img.get_width() and 0 <= ay <= img.get_height()


@test
def test_figurines_toutes_classes_et_orientations():
    for glyph in ("melee", "ranged", "cavalry", "mage", "officer", "artillery", "monster", "hero"):
        for d in range(unit_sprites.N_DIRS):
            img = unit_sprites.figure(glyph, (60, 90, 160), 24, d)
            assert img.get_size() == (24, 24)
    assert unit_sprites.dir_index(0.0) == 0
    assert unit_sprites.dir_index(3.14159) == 8
    assert unit_sprites.dir_index(None) is None
    # Sans image de jeton: figurine; trop petit: insigne (pas d'erreur)
    for ur in (5, 11):
        body, half = R.unit_body((None, False, None, (60, 90, 160), "cavalry", ur, 1, 1, 28,
                                  (96, 152, 255), 4))
        assert body.get_width() == half * 2


# ─── Styles de carte et étangs ───

def _styles(name, n=60, w=120, h=48):
    out = {}
    for seed in range(n):
        g, d = maps.generate_map(name, w, h, {'seed': seed})
        out.setdefault(d['theme']['style'], (g, d))
    return out


@test
def test_chaque_style_est_tire_et_reste_equitable():
    for name, styles in (("Prairie", maps.PRAIRIE_STYLES), ("Désert", maps.DESERT_STYLES),
                         ("Forêt", maps.FOREST_STYLES)):
        found = _styles(name)
        assert set(found) == set(styles), (name, set(styles) - set(found))
        for style, (g, d) in found.items():
            w, h = len(g), len(g[0])
            terr = d['terrain']
            for x in range(w // 2):
                for y in range(h):
                    assert g[x][y] == g[w - 1 - x][y], (name, style, x, y)
                    assert terr[x][y] == terr[w - 1 - x][y], (name, style, x, y)
            left = [(1, y) for y in range(h) if g[1][y] == 0 and tr.MOVE[terr[1][y]] is not None]
            right = [(w - 2, y) for y in range(h)
                     if g[w - 2][y] == 0 and tr.MOVE[terr[w - 2][y]] is not None]
            assert maps._bfs_path(g, w, h, left, right, terr), (name, style)


@test
def test_etangs_hors_des_lignes_de_deploiement():
    lakes = 0
    for seed in range(80):
        g, d = maps.generate_map("Prairie", 120, 48, {'seed': seed})
        if d['theme']['style'] != "étangs":
            continue
        front = deploy_front(120)
        for x in range(120):
            for y in range(48):
                if d['terrain'][x][y] == tr.LAKE:
                    lakes += 1
                    assert front < x < 120 - 1 - front, (seed, x, y)
    assert lakes > 0


@test
def test_etang_infranchissable_mais_pas_une_riviere():
    t = tr.TERRAINS[tr.LAKE]
    assert t['move'] is None and not t['passable'] and t['blocks_los'] == 0
    assert tr.LAKE in trr.LEGEND and tr.LAKE in trr.WATER
    # Relief « Plat »: pas de rivière, mais un étang reste possible
    g, d = maps.generate_map("Désert", 120, 48, {'seed': 1, 'relief': "Plat"})
    got = {n for col in d['terrain'] for n in col}
    assert not (got & {tr.RIVER, tr.FORD, tr.BRIDGE}), got


# ─── Paysage visuel ───

@test
def test_chemins_champs_et_camp_ne_touchent_pas_au_jeu():
    for name in maps.get_map_names():
        g, d = maps.generate_map(name, 120, 48, {'seed': 5})
        assert isinstance(d['paths'], list) and isinstance(d['fields'], list)
        b = Battle(small_army(), small_army(), 120, 48, 8, map_name=name, map_options={'seed': 5})
        bf = b.battlefield
        # Rien de visuel ne doit passer pour des données de siège
        assert bf.is_siege == (name in maps.SIEGE_MAPS), name
        assert 'paths' not in bf.siege_data and 'fields' not in bf.siege_data
        assert bf.paths and isinstance(bf.fields, list), name
    g, d = maps.generate_map("Siège", 120, 48, {'seed': 2})
    assert any(k == "tente" for (_x, _y, k, _s) in d['decor'])
    g, d = maps.generate_map("Village", 120, 48, {'seed': 2})
    assert d['fields'], "le village a ses champs"


@test
def test_style_affiche_dans_le_resume():
    g, d = maps.generate_map("Prairie", 60, 40, {'seed': 4, 'season': "Automne"})
    label = maps.describe_options("Prairie", d['theme'])
    assert d['theme']['style'] in label and "automne" in label, label


# ─── Rendu: repeint exact après un incendie de bois ───

@test
def test_repeint_du_bois_brule_egal_reconstruction():
    """Un bois qui brûle perd ses arbres et devient du brûlé: repeindre la
    région donne exactement les pixels d'une reconstruction complète."""
    random.seed(3)
    b = Battle(small_army(), small_army(), 70, 40, 8, map_name="Forêt", map_options={'seed': 9})
    bf = b.battlefield
    cs = 16
    surf = R.build_grid_surface(b, cs)
    wood = [(x, y) for x in range(bf.width) for y in range(bf.height)
            if bf.terrain[x][y] == tr.WOOD and bf.grid[x][y] == 0 and (x, y) not in bf.structures]
    assert wood
    burnt = wood[len(wood) // 2:len(wood) // 2 + 5]
    for (x, y) in burnt:
        bf.terrain[x][y] = tr.BURNT
    R.repaint_region(surf, b, cs, set(burnt))
    full = R.build_grid_surface(b, cs)
    xs = [c[0] for c in burnt]
    ys = [c[1] for c in burnt]
    clip = pygame.Rect((min(xs) - 1) * cs, (min(ys) - 1) * cs,
                       (max(xs) - min(xs) + 3) * cs, (max(ys) - min(ys) + 3) * cs)
    diff = 0
    for px in range(clip.left, clip.right, 2):
        for py in range(clip.top, clip.bottom, 2):
            if 0 <= px < surf.get_width() and 0 <= py < surf.get_height():
                diff += surf.get_at((px, py)) != full.get_at((px, py))
    assert diff == 0, diff


@test
def test_rendu_toutes_cartes_et_saisons():
    for name in maps.get_map_names():
        for season in maps.SEASONS:
            b = Battle(small_army(), small_army(), 60, 40, 8, map_name=name,
                       map_options={'seed': 6, 'season': season})
            surf = R.build_grid_surface(b, 12)
            assert surf.get_size() == (60 * 12, 40 * 12)
            leg = trr.legend_surface(b.battlefield, pygame.font.SysFont("arial", 12))
            assert leg is None or leg.get_height() > 20


@test
def test_structures_brulees_et_effondrees_se_dessinent():
    random.seed(4)
    b = Battle(small_army(), small_army(), 60, 40, 8, map_name="Village", map_options={'seed': 4})
    bf = b.battlefield
    surf = R.build_grid_surface(b, 16)
    house = next(g for g, k in bf.structure_kind.items() if k == st.HOUSE)
    st.damage(bf, house, 999)
    R.repaint_region(surf, b, 16, set(bf.structure_members[house]))


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests de graphismes passent.")
    sys.exit(1 if fails else 0)
