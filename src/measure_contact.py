"""Round du premier corps-à-corps, par carte (taille réelle 178x64)."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle

N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
for m in ("Prairie", "Forêt", "Village", "Défilé"):
    rounds = []
    for seed in range(N):
        random.seed(300 + seed)
        a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 10), ("Arbaletrier régulier", 4)])
        a2 = ul.build_army("Armée Orlandar", [("Fantassin covaliir", 10), ("Archer covaliir", 4)])
        b = Battle(a1, a2, 178, 64, 8, map_name=m)
        contact = None
        while not b.is_battle_over() and b.round <= 40 and contact is None:
            b.simulate_round()
            for u in b.army1:
                if u.is_alive and any(e.is_alive and abs(u.position[0] - e.position[0])
                                      + abs(u.position[1] - e.position[1]) <= 1 for e in b.army2):
                    contact = b.round - 1
                    break
        rounds.append(contact if contact is not None else 99)
    print(f"{m:10s} premier contact moyen: round {sum(rounds) / len(rounds):.1f}  {rounds}")
