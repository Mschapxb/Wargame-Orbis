"""Round du premier corps-à-corps, par carte (taille réelle 178x64).

Contact = un vivant de l'armée 1 à distance de Chebyshev <= 1 d'un vivant
de l'armée 2 (max(|dx|, |dy|) <= 1, ce qui couvre aussi l'adjacence en
diagonale), vérifié après chaque round. Si la bataille se termine avant
qu'une telle adjacence n'ait été observée mais que les DEUX camps ont
subi des pertes (affrontement resté à distance, sans jamais se toucher),
le round de fin de bataille compte quand même comme contact: sinon le
critère raterait tout affrontement purement au tir.

Affiche par carte: le round médian de contact (parmi les batailles qui en
ont eu un), le taux de contact (k/N) et la liste brute par graine (99 =
pas de contact observé avant le plafond de rounds).
"""
import os, statistics, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
CAP = 80
SENTINEL = 99  # pas de contact observé avant le plafond de rounds

for m in ("Prairie", "Forêt", "Village", "Défilé"):
    raw = []
    contacts = []
    for seed in range(N):
        random.seed(300 + seed)
        a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 10), ("Arbaletrier régulier", 4)])
        a2 = ul.build_army("Armée Orlandar", [("Fantassin covaliir", 10), ("Archer covaliir", 4)])
        b = Battle(a1, a2, 178, 64, 8, map_name=m)
        contact = None
        while not b.is_battle_over() and b.round <= CAP and contact is None:
            b.simulate_round()
            r = b.round - 1
            if any(u.is_alive and any(
                    e.is_alive and max(abs(u.position[0] - e.position[0]), abs(u.position[1] - e.position[1])) <= 1
                    for e in b.army2)
                   for u in b.army1):
                contact = r
            elif b.is_battle_over():
                a1_casualties = any(not u.is_alive for u in b.army1)
                a2_casualties = any(not u.is_alive for u in b.army2)
                if a1_casualties and a2_casualties:
                    contact = r
        if contact is not None:
            contacts.append(contact)
            raw.append(contact)
        else:
            raw.append(SENTINEL)
    k = len(contacts)
    median = statistics.median(contacts) if k else float('nan')
    print(f"{m:10s} contact médian: round {median:.1f}  taux contact: {k}/{N}  {raw}")
