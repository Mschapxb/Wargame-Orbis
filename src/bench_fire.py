"""Banc incendie (lot B1): Forêt et Village avec deux mages par camp.

Vérifie que le feu reste un événement de bataille et non la fin de la
carte: part moyenne du combustible consumé (≤ 25 %), batailles bornées
(aucune au-delà de 90 rounds), et équilibre des victoires.

    python src/bench_fire.py [N=60] [OFF=3000] [W=40] [H=30]
"""
import os, sys, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import structures as st
import terrain as tr
import unit_library as ul
from battle import Battle

MAPS = ["Forêt", "Village"]
ARMY = ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 2,
                             "Mage de guerre": 2})

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
OFF = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
W = int(sys.argv[3]) if len(sys.argv) > 3 else 40
H = int(sys.argv[4]) if len(sys.argv) > 4 else 30


def fuel_cells(bf):
    return {(x, y) for x in range(bf.width) for y in range(bf.height)
            if st.flammability(bf, x, y) > 0}


t0 = time.time()
for mapname in MAPS:
    w1 = w2 = draw = 0
    burnt_share, rounds, peak_fires, collapses, over = [], [], [], 0, 0
    for seed in range(N):
        random.seed(OFF + seed)
        a1 = ul.build_army(ARMY[0], list(ARMY[1].items()))
        a2 = ul.build_army(ARMY[0], list(ARMY[1].items()))
        b = Battle(a1, a2, W, H, 8, map_name=mapname)
        bf = b.battlefield
        fuel = fuel_cells(bf)
        peak = 0
        while not b.is_battle_over() and b.round <= 90:
            b.simulate_round()
            peak = max(peak, len(bf.fires))
            collapses += sum(1 for txt, _, _ in b.round_events
                             if "effondre" in txt or "cendres" in txt or "fumée" in txt)
        res = b.is_battle_over()
        w1 += res == "Armée 1"
        w2 += res == "Armée 2"
        draw += res not in ("Armée 1", "Armée 2")
        over += b.round > 90
        rounds.append(b.round - 1)
        peak_fires.append(peak)
        gone = sum(1 for (x, y) in fuel if bf.terrain[x][y] in (tr.BURNT, tr.RUBBLE))
        burnt_share.append(gone / max(1, len(fuel)))
    print(f"{mapname:8s} A1={w1:2d} A2={w2:2d} nul={draw:2d} | "
          f"combustible consumé moy={100 * sum(burnt_share) / N:5.1f} % "
          f"max={100 * max(burnt_share):5.1f} % | feux simultanés max={max(peak_fires):3d} | "
          f"destructions={collapses:3d} | rounds moy={sum(rounds) / N:5.1f} | >90 rounds: {over}")
print(f"({time.time() - t0:.1f}s)")
