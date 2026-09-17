"""Banc des plans de bataille (lot C): l'IA AVEC plans affronte la même armée
commandée SANS plan, les plans passant d'un camp à l'autre à chaque graine
(annule le biais de côté). La version avec plans doit gagner ≥ 50 % des
parties décidées: elle ne doit pas jouer moins bien.

    python src/bench_plans.py [N=40] [OFF=7000] [W=60] [H=40]
"""
import os, sys, random, time
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle

MATCHES = [
    ("Mixte Prairie", "Prairie",
     ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 3, "Officier": 1, "Mage de guerre": 1})),
    ("Cavalerie Prairie", "Prairie",
     ("Armée Orlandar", {"Fantassin covaliir": 6, "Archer covaliir": 3, "Cavalier covaliir": 3, "Officier covaliir": 1})),
    ("Infanterie Forêt", "Forêt",
     ("Armée Skaldienne", {"Infanterie régulière": 8, "Arbaletrier régulier": 3, "Housecarl": 2})),
    ("Mixte Village", "Village",
     ("Armée Orlandar", {"Fantassin covaliir": 8, "Archer covaliir": 4, "Cavalier covaliir": 2})),
    ("Tir Défilé", "Défilé",
     ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 5, "Officier": 1})),
]

EVENTS = (("frappe", "marteau frappe"), ("brisé", "marteau brisé"),
          ("réserve", "réserve engagée"), ("assaut principal", "feinte puis assaut"),
          ("contre-attaque", "contre-attaque colline"), ("aile refusée", "aile refusée engagée"))

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
OFF = int(sys.argv[2]) if len(sys.argv) > 2 else 7000
W = int(sys.argv[3]) if len(sys.argv) > 3 else 60
H = int(sys.argv[4]) if len(sys.argv) > 4 else 40

t0 = time.time()
total_win = total_dec = 0
for label, mapname, (faction, comp) in MATCHES:
    plan_wins = plan_losses = draws = 0
    kinds, phases = Counter(), Counter()
    for seed in range(N):
        random.seed(OFF + seed)
        b = Battle(ul.build_army(faction, list(comp.items())),
                   ul.build_army(faction, list(comp.items())), W, H, 8, map_name=mapname)
        planner_is_1 = seed % 2 == 0
        planner = b.commander1 if planner_is_1 else b.commander2
        other = b.commander2 if planner_is_1 else b.commander1
        other.use_plans = False
        side = "Armée 1 :" if planner_is_1 else "Armée 2 :"
        first_kind = None
        while not b.is_battle_over() and b.round <= 90:
            b.simulate_round()
            if first_kind is None and planner.plan.kind is not None:
                first_kind = planner.plan.kind
            for txt, _, _ in b.round_events:
                if txt.startswith(side):
                    for key, name in EVENTS:
                        if key in txt:
                            phases[name] += 1
                            break
        kinds[first_kind or "?"] += 1
        res = b.is_battle_over()
        if res in ("Armée 1", "Armée 2"):
            won = res == ("Armée 1" if planner_is_1 else "Armée 2")
            plan_wins += won
            plan_losses += not won
        else:
            draws += 1
    dec = max(1, plan_wins + plan_losses)
    total_win += plan_wins
    total_dec += plan_wins + plan_losses
    detail = ", ".join(f"{k} {v}" for k, v in sorted(phases.items()))
    print(f"{label:18s} plans gagnent {100 * plan_wins / dec:5.1f} % ({plan_wins}/{dec}, nuls {draws}) | "
          f"plans: {dict(kinds)} | {detail}")
print(f"TOTAL: plans gagnent {100 * total_win / max(1, total_dec):.1f} % des parties décidées "
      f"({time.time() - t0:.0f}s)")
