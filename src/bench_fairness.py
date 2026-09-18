"""Banc d'équité: à armées ÉGALES, aucun camp ne doit être avantagé.

Chaque « situation » (carte × relief × biome × composition × météo × taille)
oppose une armée à son double exact. Sans avantage de terrain choisi, le camp
de gauche doit gagner ~50 % des parties décidées. Une situation est signalée
quand l'écart dépasse 3 erreurs types (|z| > 3): au-delà du hasard.

    python src/bench_fairness.py [N=200] [--quick] [--full-size] [--jobs 12]
                                 [--off K] [--only "forêt · cavalerie,prairie · mages"]

Les sièges sont exclus: un camp y défend une forteresse, par construction.
"""
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ARMIES = {
    "mixte": ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 3,
                                   "Housecarl": 2}),
    "infanterie": ("Armée Skaldienne", {"Infanterie régulière": 8, "Hallbardier": 3}),
    "tireurs": ("Armée Skaldienne", {"Arbaletrier régulier": 6, "Infanterie régulière": 4}),
    "cavalerie": ("Armée Orlandar", {"Fantassin covaliir": 5, "Archer covaliir": 3,
                                     "Cavalier covaliir": 3}),
    "mages": ("Armée Skaldienne", {"Infanterie régulière": 5, "Arbaletrier régulier": 2,
                                   "Mage de guerre": 2, "Officier": 1}),
}
OPEN_MAPS = ("Prairie", "Forêt", "Désert", "Village", "Défilé")
RELIEFS = ("Plat", "Rivière", "Collines", "Rivière + collines")
WEATHERS = ("Pluie", "Brouillard", "Vent", "Crépuscule", "Chaleur")


def situations(quick=False, full_size=False):
    """[(libellé, carte, options, armée, largeur, hauteur)]"""
    out = []
    size = (178, 64) if full_size else (40, 30)
    comps = ("mixte",) if quick else tuple(ARMIES)
    for m in OPEN_MAPS:
        for c in comps:
            out.append((f"{m} · {c}", m, None, c) + size)
    if not quick:
        for m in ("Prairie", "Forêt", "Désert", "Village"):
            for r in RELIEFS:
                out.append((f"{m} · relief {r}", m, {'relief': r}, "mixte") + size)
        for b in ("Forêt", "Désert"):
            out.append((f"Village · biome {b}", "Village", {'biome': b}, "mixte") + size)
        for w in WEATHERS:
            out.append((f"Prairie · {w}", "Prairie", {'weather': w}, "mixte") + size)
            out.append((f"Forêt · {w}", "Forêt", {'weather': w}, "mixte") + size)
    return out


def _chunk(args):
    """Joue les graines [a, b) d'une situation (processus séparé)."""
    label, mapname, opts, comp, w, h, a, b = args
    import unit_library as ul
    from battle import Battle
    army = ARMIES[comp]
    w1 = w2 = draw = 0
    for seed in range(a, b):
        random.seed(seed)
        a1 = ul.build_army(army[0], list(army[1].items()))
        a2 = ul.build_army(army[0], list(army[1].items()))
        bt = Battle(a1, a2, w, h, 8, map_name=mapname, map_options=opts)
        while not bt.is_battle_over() and bt.round <= 90:
            bt.simulate_round()
        res = bt.is_battle_over()
        if res == "Armée 1":
            w1 += 1
        elif res == "Armée 2":
            w2 += 1
        else:
            draw += 1
    return label, w1, w2, draw


def main(argv):
    n = next((int(a) for a in argv if a.isdigit()), 200)
    quick = "--quick" in argv
    full = "--full-size" in argv
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else (os.cpu_count() or 4)
    off = int(argv[argv.index("--off") + 1]) if "--off" in argv else 20000
    sits = situations(quick, full)
    if "--only" in argv:
        wanted = argv[argv.index("--only") + 1].lower().split(",")
        sits = [x for x in sits if any(w.strip() in x[0].lower() for w in wanted)]
    step = max(10, n // 4)
    tasks = []
    for i, (label, m, opts, comp, w, h) in enumerate(sits):
        base = off + i * 100000
        for a in range(0, n, step):
            tasks.append((label, m, opts, comp, w, h, base + a, base + min(n, a + step)))
    t0 = time.time()
    agg = {}
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for label, w1, w2, d in pool.map(_chunk, tasks):
            r = agg.setdefault(label, [0, 0, 0])
            r[0] += w1
            r[1] += w2
            r[2] += d
    tot1 = tot = 0
    flagged = []
    print(f"{'situation':34s} {'gauche':>7s} {'droite':>7s} {'nuls':>5s} {'gauche %':>9s} {'z':>6s}")
    for label, *_ in sits:
        w1, w2, d = agg[label]
        dec = max(1, w1 + w2)
        p = w1 / dec
        z = (p - 0.5) / (0.5 / dec ** 0.5)
        mark = "  <-- biais" if abs(z) > 3 else ("  ?" if abs(z) > 2 else "")
        print(f"{label:34s} {w1:7d} {w2:7d} {d:5d} {100 * p:8.1f}% {z:6.2f}{mark}")
        if abs(z) > 3:
            flagged.append(label)
        tot1 += w1
        tot += w1 + w2
    p = tot1 / max(1, tot)
    z = (p - 0.5) / (0.5 / max(1, tot) ** 0.5)
    print(f"\nTOTAL: gauche {100 * p:.1f}% sur {tot} parties décidées (z={z:.2f})")
    print(f"situations signalées (|z|>3): {flagged or 'aucune'}")
    print(f"({time.time() - t0:.0f}s, {len(sits)} situations × {n} parties)")
    return flagged


if __name__ == "__main__":
    main(sys.argv[1:])
