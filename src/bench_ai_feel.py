"""Banc du « ressenti » de l'IA: agressivité et cohésion visuelle des troupes.
Deux armées miroir s'affrontent sur chaque carte; on mesure:

  contact  — round médian du premier corps-à-corps (Chebyshev ≤ 1)
  durée    — rounds moyens de la bataille
  paquet   — part des unités (mobiles, hors machines) ayant ≥ 2 alliés à
             ≤ 2 cases: plus c'est haut, plus l'armée marche en blocs
  traînard — part des unités dont l'allié le plus proche est à > 4 cases
  attente  — part des unités immobiles SANS ennemi à portée + 2 (piétinement)
  gauche   — victoires de l'armée 1 parmi les parties décidées (biais de côté)

paquet/traînard/attente sont moyennés sur tous les rounds où l'armée compte
au moins 3 unités mobiles; « marche » = mêmes mesures avant le premier contact.

    python src/bench_ai_feel.py [N=16] [OFF=8000] [W=60] [H=40]
"""
import os, sys, random, statistics, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle

MAPS = ["Prairie", "Forêt", "Désert", "Village", "Défilé"]
ARMIES = [
    ("Armée Skaldienne", {"Infanterie régulière": 7, "Arbaletrier régulier": 3,
                          "Housecarl": 2, "Officier": 1}),
    ("Armée Orlandar", {"Fantassin covaliir": 6, "Archer covaliir": 3,
                        "Cavalier covaliir": 3, "Officier covaliir": 1}),
]

N = int(sys.argv[1]) if len(sys.argv) > 1 else 16
OFF = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
W = int(sys.argv[3]) if len(sys.argv) > 3 else 60
H = int(sys.argv[4]) if len(sys.argv) > 4 else 40


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def formation_stats(army, enemies, prev):
    mob = [u for u in army if u.is_alive and not u.fleeing and u.vitesse > 0
           and not getattr(u, 'is_artillery', False)]
    if len(mob) < 3:
        return None
    packed = strag = idle = 0
    foes = [e for e in enemies if e.is_alive]
    for u in mob:
        ds = sorted(cheb(u.position, a.position) for a in mob if a is not u)
        packed += len(ds) >= 2 and ds[1] <= 2
        strag += ds[0] > 4
        if prev.get(id(u)) == u.position and not any(
                cheb(u.position, e.position) <= u._max_range + 2 for e in foes):
            idle += 1
    n = len(mob)
    return packed / n, strag / n, idle / n


t0 = time.time()
tot = {'paquet': [], 'trainard': [], 'attente': [], 'contact': [], 'duree': []}
for mapname in MAPS:
    contacts, rounds = [], []
    march, fight = [], []
    w1 = w2 = 0
    for seed in range(N):
        random.seed(OFF + seed)
        faction, comp = ARMIES[seed % len(ARMIES)]
        b = Battle(ul.build_army(faction, list(comp.items())),
                   ul.build_army(faction, list(comp.items())), W, H, 8, map_name=mapname)
        contact = None
        while not b.is_battle_over() and b.round <= 90:
            prev = {id(u): u.position for u in b.army1 + b.army2}
            b.simulate_round()
            if contact is None and any(
                    u.is_alive and e.is_alive and cheb(u.position, e.position) <= 1
                    for u in b.army1 for e in b.army2):
                contact = b.round - 1
            for army, en in ((b.army1, b.army2), (b.army2, b.army1)):
                st = formation_stats(army, en, prev)
                if st is not None:
                    (march if contact is None else fight).append(st)
        contacts.append(contact if contact is not None else 99)
        rounds.append(b.round - 1)
        res = b.is_battle_over()
        w1 += res == "Armée 1"
        w2 += res == "Armée 2"

    def avg(rows, i):
        return 100 * sum(r[i] for r in rows) / max(1, len(rows))

    allrows = march + fight
    tot['paquet'].append(avg(allrows, 0))
    tot['trainard'].append(avg(allrows, 1))
    tot['attente'].append(avg(allrows, 2))
    tot['contact'].append(statistics.median(contacts))
    tot['duree'].append(sum(rounds) / len(rounds))
    print(f"{mapname:8s} contact {statistics.median(contacts):4.1f} | durée {sum(rounds)/len(rounds):5.1f} | "
          f"paquet {avg(allrows, 0):5.1f} % (marche {avg(march, 0):5.1f}) | "
          f"traînard {avg(allrows, 1):4.1f} % | attente {avg(allrows, 2):4.1f} % "
          f"(marche {avg(march, 2):4.1f}) | gauche {100 * w1 / max(1, w1 + w2):5.1f} % "
          f"({w1}/{w1 + w2})")
print("MOYENNE  " + " | ".join(f"{k} {sum(v)/len(v):.1f}" for k, v in tot.items())
      + f"  ({time.time() - t0:.0f}s)")
