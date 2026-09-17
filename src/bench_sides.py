"""Banc de biais de CÔTÉ: la même armée affronte son double sur chaque
carte de bataille rangée. Sans avantage de terrain, l'Armée 1 (à gauche)
doit gagner ~50 % des parties; un écart net trahit une carte asymétrique.

    python src/bench_sides.py [N=100] [OFF=5000] [W=40] [H=30]

Le Siège est exclu: il est asymétrique par construction (un camp défend).
"""
import os, sys, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle

MAPS = ["Prairie", "Forêt", "Village", "Défilé"]
ARMY = ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 3,
                             "Housecarl": 2})

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
OFF = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
W = int(sys.argv[3]) if len(sys.argv) > 3 else 40
H = int(sys.argv[4]) if len(sys.argv) > 4 else 30

t0 = time.time()
for mapname in MAPS:
    w1 = w2 = draw = 0
    for seed in range(N):
        random.seed(OFF + seed)
        a1 = ul.build_army(ARMY[0], list(ARMY[1].items()))
        a2 = ul.build_army(ARMY[0], list(ARMY[1].items()))
        b = Battle(a1, a2, W, H, 8, map_name=mapname)
        while not b.is_battle_over() and b.round <= 90:
            b.simulate_round()
        res = b.is_battle_over()
        if res == "Armée 1":
            w1 += 1
        elif res == "Armée 2":
            w2 += 1
        else:
            draw += 1
    decided = max(1, w1 + w2)
    print(f"{mapname:10s} A1={w1:3d} A2={w2:3d} nul={draw:3d} | "
          f"gauche gagne {100 * w1 / decided:5.1f} %")
print(f"({time.time()-t0:.1f}s)")
