"""Test headless des nouveaux comportements IA (sans pygame display)."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle

def run(army1, army2, map_name, max_rounds=120, verbose_events=True, label=""):
    b = Battle(army1, army2, map_name=map_name)
    events = []
    prev_open = b.battlefield.gates_open
    prev_posture2 = b.commander2.posture
    prev_posture1 = b.commander1.posture
    while not b.is_battle_over() and b.round <= max_rounds:
        b.simulate_round()
        if b.battlefield.gates_open != prev_open:
            events.append(f"  R{b.round-1}: portes {'OUVERTES' if b.battlefield.gates_open else 'REFERMÉES'}")
            prev_open = b.battlefield.gates_open
        if b.commander2.posture != prev_posture2:
            events.append(f"  R{b.round-1}: posture défenseurs -> {b.commander2.posture}")
            prev_posture2 = b.commander2.posture
        if b.commander1.posture != prev_posture1:
            events.append(f"  R{b.round-1}: posture armée 1 -> {b.commander1.posture}")
            prev_posture1 = b.commander1.posture
    winner = b.is_battle_over() or "timeout"
    a1 = sum(1 for u in b.army1 if u.is_alive)
    a2 = sum(1 for u in b.army2 if u.is_alive)
    print(f"[{label}] vainqueur={winner} en {b.round-1} rounds (A1 vivants={a1}, A2 vivants={a2})")
    if verbose_events:
        for e in events:
            print(e)
    return winner

random.seed(42)

print("=" * 70)
print("TEST 1 — SIÈGE: défenseurs SANS archers vs attaquants AVEC archers")
print("Attendu: posture 'sortie', portes ouvertes, les défenseurs sortent")
print("=" * 70)
atk = ul.build_army("Armée Skaldienne", list({"Infanterie régulière": 6, "Arbaletrier régulier": 6, "Officier": 1}.items()))
def_ = ul.build_army("Armée Skaldienne", list({"Infanterie régulière": 8, "Hallbardier": 4, "Officier": 1}.items()))
run(atk, def_, "Siège", label="Siège sortie")

print()
print("=" * 70)
print("TEST 2 — SIÈGE: défenseurs AVEC archers (défense classique attendue)")
print("=" * 70)
atk = ul.build_army("Armée Skaldienne", list({"Infanterie régulière": 8, "Arbaletrier régulier": 3, "Officier": 1}.items()))
def_ = ul.build_army("Armée Skaldienne", list({"Infanterie régulière": 4, "Arbaletrier régulier": 5, "Officier": 1}.items()))
run(atk, def_, "Siège", label="Siège hold")

print()
print("=" * 70)
print("TEST 3 — PRAIRIE: armée sans archers vs armée d'archers (rush attendu)")
print("=" * 70)
a1 = ul.build_army("Armée Skaldienne", list({"Infanterie régulière": 8, "Hallbardier": 4}.items()))
a2 = ul.build_army("Armée Skaldienne", list({"Arbaletrier régulier": 8, "Infanterie régulière": 3}.items()))
run(a1, a2, "Prairie", label="Rush")

print()
print("=" * 70)
print("TEST 4 — PRAIRIE: supériorité de tir (hold_line attendu côté A1)")
print("=" * 70)
a1 = ul.build_army("Armée Skaldienne", list({"Arbaletrier régulier": 8, "Infanterie régulière": 4}.items()))
a2 = ul.build_army("Armée Skaldienne", list({"Infanterie régulière": 10}.items()))
run(a1, a2, "Prairie", label="Hold line")

print()
print("=" * 70)
print("TEST 5 — Régression: armées mixtes équilibrées sur 3 cartes")
print("=" * 70)
for m in ["Prairie", "Forêt", "Village"]:
    a1 = ul.build_army("Armée Skaldienne", list({"Infanterie régulière": 5, "Arbaletrier régulier": 3, "Officier": 1, "Mage de guerre": 1}.items()))
    a2 = ul.build_army("Armée Orlandar", list({"Fantassin covaliir": 5, "Archer covaliir": 3, "Cavalier covaliir": 2, "Officier covaliir": 1}.items()))
    run(a1, a2, m, verbose_events=False, label=m)

print()
print("Tous les tests terminés.")
