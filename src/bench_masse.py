"""Banc de charge: combien de temps coûte un round selon l'effectif.

Le coût d'un round ne dépend pas seulement du nombre d'unités: une bataille
naïve pose à chaque unité des questions qui balaient l'armée adverse, et le
temps grandit alors comme le CARRÉ des effectifs. L'index spatial
(`spatial.py`) est là pour l'en empêcher. Ce banc le vérifie: la colonne
« par unité » doit rester à peu près plate quand on double les effectifs.

    python src/bench_masse.py [ROUNDS=15] [W=178] [H=64] [--carte NOM]

Il ne mesure QUE le temps: aucune conclusion d'équilibrage à en tirer
(cf. bench.py pour cela).
"""
import os, sys, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle

# Une armée type, multipliée par l'échelle: mêlée, tir, cavalerie, officier.
A1 = ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 3,
                           "Housecarl": 2, "Officier": 1})
A2 = ("Armée Orlandar", {"Fantassin covaliir": 6, "Archer covaliir": 3,
                         "Cavalier covaliir": 2, "Officier covaliir": 1})
SCALES = (1, 2, 4, 8, 16, 32)

args = [a for a in sys.argv[1:]]
mapname = "Prairie"
if "--carte" in args:
    i = args.index("--carte")
    mapname = args[i + 1]
    del args[i:i + 2]
ROUNDS = int(args[0]) if args else 15
W = int(args[1]) if len(args) > 1 else 178
H = int(args[2]) if len(args) > 2 else 64


def build(spec, scale):
    return ul.build_army(spec[0], [(name, n * scale) for name, n in spec[1].items()])


print(f"{mapname} {W}x{H}, {ROUNDS} rounds par mesure")
print(f"{'unités':>7} {'ms/round':>9} {'µs/unité/round':>15}")
t0 = time.time()
for scale in SCALES:
    random.seed(1234)
    b = Battle(build(A1, scale), build(A2, scale), W, H, 8, map_name=mapname)
    n_units = len(b.army1) + len(b.army2)
    t = time.perf_counter()
    played = 0
    while played < ROUNDS and not b.is_battle_over():
        b.simulate_round()
        played += 1
    dt = (time.perf_counter() - t) / max(1, played)
    print(f"{n_units:7d} {dt * 1000:9.1f} {dt * 1e6 / n_units:15.1f}")
print(f"({time.time() - t0:.1f}s)")
