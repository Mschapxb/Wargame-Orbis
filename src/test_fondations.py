"""Tests du lot A (fondations): symétrie des cartes et du déploiement,
obstacles qui coupent la ligne de tir, estimation IA du rempart, aucune
méthode définie deux fois. Script exécutable:
    python test_fondations.py            # tout
    python test_fondations.py miroir     # seulement les tests dont le nom contient 'miroir'
"""
import ast, glob, os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import maps
import tactics
import unit_library as ul
from battle import Battle
from battlefield import Battlefield
from models import Arme
from unit import Unit

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def archer(pos):
    u = Unit("Archer", pv=100, vitesse=4, morale=3, sauvegarde=7, color=(1, 1, 1),
             armes=[Arme("Arc", nb_attaque=1, toucher=3, blesser=1, perforation=0,
                         degats="1", porte=8)])
    u.position = pos
    return u


def target(pos, save=7):
    u = Unit("Cible", pv=100000, vitesse=4, morale=5, sauvegarde=save, color=(2, 2, 2),
             armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    u.position = pos
    return u


# ── Symétrie ──

BATTLE_MAPS = ("Prairie", "Forêt", "Village", "Défilé")


@test
def test_miroir_cartes_de_bataille_rangee():
    """Grille bâtie ET terrain identiques de part et d'autre: aucun camp
    n'hérite de plus de couverts que l'autre."""
    for name in BATTLE_MAPS:
        for (w, h) in ((40, 30), (178, 64)):
            for seed in range(3):
                random.seed(seed)
                grid, data = maps.generate_map(name, w, h)
                terr = data['terrain']
                for x in range(w // 2):
                    for y in range(h):
                        assert grid[x][y] == grid[w - 1 - x][y], (name, w, seed, x, y)
                        assert terr[x][y] == terr[w - 1 - x][y], (name, w, seed, x, y)


@test
def test_miroir_colonnes_de_deploiement():
    """L'armée 2 se range sur le reflet exact des colonnes de l'armée 1."""
    for name in BATTLE_MAPS:
        for seed in range(3):
            random.seed(100 + seed)
            comp = [("Infanterie régulière", 6), ("Arbaletrier régulier", 3)]
            b = Battle(ul.build_army("Armée Skaldienne", comp),
                       ul.build_army("Armée Skaldienne", comp), 40, 30, 8, map_name=name)
            w = b.battlefield.width
            xs1 = sorted(w - 1 - u.position[0] for u in b.army1)
            xs2 = sorted(u.position[0] for u in b.army2)
            assert xs1 == xs2, (name, seed, xs1, xs2)


# ── Ligne de tir ──

@test
def test_obstacle_coupe_la_ligne_de_tir():
    grid = [[0] * 6 for _ in range(12)]
    grid[4][2] = 1                      # un rocher, une maison, une haie…
    bf = Battlefield(12, 6, 0, "Prairie", grid, {})
    assert bf.has_line_of_fire(archer((0, 2)), target((8, 2))) is False
    assert bf.has_line_of_fire(archer((0, 3)), target((8, 3))) is True


@test
def test_rempart_toujours_visible_par_dessus_le_mur():
    grid = [[0] * 6 for _ in range(12)]
    grid[4][2] = 2
    bf = Battlefield(12, 6, 0, "Siège", grid,
                     {'walls': [(4, 2)], 'ramparts': [(8, 2)]})
    assert bf.has_line_of_fire(archer((0, 2)), target((8, 2))) is True


# ── Estimation IA ──

@test
def test_estimation_rempart_conforme_au_moteur():
    """L'IA doit voir le rempart PROTÉGER le défenseur, comme le moteur."""
    grid = [[0] * 6 for _ in range(12)]
    bf = Battlefield(12, 6, 0, "Siège", grid, {'walls': [(5, 5)], 'ramparts': [(6, 1)]})
    a, t = archer((0, 1)), target((6, 1), save=5)
    bf.place_unit(a)
    bf.place_unit(t)
    open_ground = target((6, 3), save=5)
    est_wall = tactics.expected_damage(a, t, 6, bf)
    est_open = tactics.expected_damage(a, open_ground, 6, bf)
    assert est_wall < est_open, (est_wall, est_open)
    n, total = 4000, 0
    for _ in range(n):
        before = t.hp
        a.perform_attacks(t, bf)
        total += before - t.hp
        t.hp = t.max_hp
        t.is_alive = True
    got = total / n
    assert abs(got - est_wall) / est_wall < 0.12, (got, est_wall)


# ── Hygiène du code ──

@test
def test_aucune_methode_definie_deux_fois():
    """Une seconde définition écrase silencieusement la première (c'est
    ainsi que les versions riches de l'IA ne tournaient jamais)."""
    for path in glob.glob(os.path.join(HERE, "*.py")):
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        for scope in scopes:
            seen = set()
            for node in scope.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # @x.setter / @x.deleter redéfinissent légitimement x
                    if any(isinstance(d, ast.Attribute) and d.attr in ("setter", "deleter")
                           for d in node.decorator_list):
                        continue
                    key = node.name
                    assert key not in seen, f"{os.path.basename(path)}: {key} défini deux fois"
                    seen.add(key)


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests fondations passent.")
    sys.exit(1 if fails else 0)
