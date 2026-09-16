"""Banc d'essai d'équilibrage pour Village et Défilé: même structure que
bench_balance.py (qui ne couvrait que Prairie/Siège/Forêt), pour vérifier
qu'aucune carte ne fait basculer l'équilibre de plus de 10 points (>6
victoires d'écart sur 60 graines) — cf. le principe d'équilibrage du spec
terrain."""
import os, sys, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle

MATCHES = [
    ("Village mixte", "Village",
     ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 3, "Housecarl": 2}),
     ("Armée Orlandar", {"Fantassin covaliir": 6, "Archer covaliir": 3, "Cavalier covaliir": 2})),
    ("Defile mixte", "Défilé",
     ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 3, "Housecarl": 2}),
     ("Armée Orlandar", {"Fantassin covaliir": 6, "Archer covaliir": 3, "Cavalier covaliir": 2})),
]

N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
OFF = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
# Taille de carte (défaut: la petite grille historique, rapide; passer
# 178 64 pour la taille réelle d'une partie sur écran 1920 px)
W = int(sys.argv[3]) if len(sys.argv) > 3 else 40
H = int(sys.argv[4]) if len(sys.argv) > 4 else 30
t0 = time.time()
for label, mapname, (f1, c1), (f2, c2) in MATCHES:
    w1 = w2 = draw = 0
    rounds = []
    surv1 = surv2 = 0
    for seed in range(N):
        random.seed(OFF + seed)
        a1 = ul.build_army(f1, list(c1.items()))
        a2 = ul.build_army(f2, list(c2.items()))
        b = Battle(a1, a2, W, H, 8, map_name=mapname)
        while not b.is_battle_over() and b.round <= 90:
            b.simulate_round()
        res = b.is_battle_over()
        rounds.append(b.round - 1)
        surv1 += sum(1 for u in b.army1 if u.is_alive)
        surv2 += sum(1 for u in b.army2 if u.is_alive)
        if res == "Armée 1":
            w1 += 1
        elif res == "Armée 2":
            w2 += 1
        else:
            draw += 1
    print(f"{label:22s} A1={w1:2d} A2={w2:2d} nul={draw:2d} | "
          f"rounds moy={sum(rounds)/len(rounds):5.1f} | surv A1={surv1/N:4.1f} A2={surv2/N:4.1f}")
print(f"({time.time()-t0:.1f}s)")
