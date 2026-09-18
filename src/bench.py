"""Banc d'essai unifié: rejoue des affrontements types sur N graines et
rapporte taux de victoire, durée et survivants.

    python src/bench.py SUITE [N] [options]

Suites:
    balance   affrontements de référence (Prairie, sièges, Citadelle, Forêt)
    maps      Village et Défilé
    sides     biais de côté: une armée contre son double, par carte
              (l'armée de gauche doit gagner ~50 %)
    themes    sièges avec biome/relief non historiques (rivière, bois…)
    all       balance + maps

Options:
    --only TXT      ne joue que les affrontements dont le libellé contient TXT
    --off K         décalage des graines (défaut: 1000, 5000 pour sides)
    --size W H      taille de carte (défaut 40 30; 178 64 = partie réelle)
    --save FICHIER  écrit aussi le résultat dans FICHIER
    --compare FICH  compare à un résultat sauvegardé (écart en victoires A1)
    --weather M     impose une météo (cf. weather.py) à toutes les parties
"""
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle

SKALD_MIXTE = ("Armée Skaldienne", {"Infanterie régulière": 6, "Arbaletrier régulier": 3,
                                     "Housecarl": 2})
ORLANDAR_MIXTE = ("Armée Orlandar", {"Fantassin covaliir": 6, "Archer covaliir": 3,
                                      "Cavalier covaliir": 2})
SIEGE_ATT = ("Armée Skaldienne", {"Infanterie régulière": 8, "Arbaletrier régulier": 4,
                                   "Officier": 1})
SIEGE_DEF = ("Armée Skaldienne", {"Infanterie régulière": 5, "Arbaletrier régulier": 4,
                                   "Officier": 1})
MIXTE = ("Armée Skaldienne", {"Infanterie régulière": 5, "Arbaletrier régulier": 3,
                               "Officier": 1, "Mage de guerre": 1})

# (libellé, carte, options de carte, armée 1, armée 2)
SUITES = {
    "balance": [
        ("Melee vs Archers", "Prairie", None,
         ("Armée Skaldienne", {"Infanterie régulière": 8, "Hallbardier": 4}),
         ("Armée Skaldienne", {"Arbaletrier régulier": 8, "Infanterie régulière": 3})),
        ("Mixte miroir", "Prairie", None, MIXTE, MIXTE),
        ("Skald vs Orlandar", "Prairie", None, MIXTE,
         ("Armée Orlandar", {"Fantassin covaliir": 5, "Archer covaliir": 3,
                             "Cavalier covaliir": 2, "Officier covaliir": 1})),
        ("Cavalerie vs Tir", "Prairie", None,
         ("Armée Orlandar", {"Cavalier covaliir": 4, "Fantassin covaliir": 5}),
         ("Armée Orlandar", {"Archer covaliir": 6, "Fantassin covaliir": 4})),
        ("Siege", "Siège", None, SIEGE_ATT, SIEGE_DEF),
        ("Siege baliste", "Siège", None,
         ("Armée Skaldienne", {"Infanterie régulière": 8, "Arbaletrier régulier": 4,
                               "Officier": 1, "Baliste": 1}),
         SIEGE_DEF),
        ("Siege Orlandar", "Siège", None,
         ("Armée Orlandar", {"Fantassin covaliir": 8, "Archer covaliir": 4,
                             "Officier covaliir": 1}),
         SIEGE_DEF),
        ("Siege catapulte", "Siège", None,
         ("Armée Orlandar", {"Fantassin covaliir": 8, "Archer covaliir": 4,
                             "Officier covaliir": 1, "Catapulte covaliir": 1}),
         SIEGE_DEF),
        ("Citadelle", "Citadelle", None, SIEGE_ATT, SIEGE_DEF),
        ("Foret mixte", "Forêt", None, SKALD_MIXTE, ORLANDAR_MIXTE),
    ],
    "maps": [
        ("Village mixte", "Village", None, SKALD_MIXTE, ORLANDAR_MIXTE),
        ("Defile mixte", "Défilé", None, SKALD_MIXTE, ORLANDAR_MIXTE),
    ],
    "sides": [
        (m, m, None, SKALD_MIXTE, SKALD_MIXTE)
        for m in ("Prairie", "Forêt", "Village", "Défilé", "Désert")
    ],
    "themes": [
        (f"Siege {tag}", "Siège", opts, SIEGE_ATT, SIEGE_DEF)
        for tag, opts in (("riviere", {'relief': "Rivière"}),
                          ("collines", {'relief': "Collines"}),
                          ("foret", {'biome': "Forêt", 'relief': "Plat"}),
                          ("desert", {'biome': "Désert", 'relief': "Plat"}))
    ] + [
        (f"Citadelle {tag}", "Citadelle", opts, SIEGE_ATT, SIEGE_DEF)
        for tag, opts in (("riviere", {'relief': "Rivière"}),
                          ("foret", {'biome': "Forêt", 'relief': "Plat"}))
    ],
}
SUITES["all"] = SUITES["balance"] + SUITES["maps"]

MAX_ROUNDS = 90


def play(mapname, options, army1, army2, seed, width, height, weather=None):
    """Joue une bataille jusqu'au bout. Renvoie la Battle terminée."""
    random.seed(seed)
    a1 = ul.build_army(army1[0], list(army1[1].items()))
    a2 = ul.build_army(army2[0], list(army2[1].items()))
    kwargs = {'map_name': mapname, 'map_options': options}
    if weather is not None:
        kwargs['weather'] = weather
    b = Battle(a1, a2, width, height, 8, **kwargs)
    while not b.is_battle_over() and b.round <= MAX_ROUNDS:
        b.simulate_round()
    return b


def run_match(match, n, off, width, height, weather=None):
    label, mapname, options, army1, army2 = match
    w1 = w2 = draw = 0
    rounds = []
    surv1 = surv2 = 0
    for seed in range(n):
        b = play(mapname, options, army1, army2, off + seed, width, height, weather)
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
    return dict(label=label, w1=w1, w2=w2, draw=draw,
                rounds=sum(rounds) / len(rounds), surv1=surv1 / n, surv2=surv2 / n)


def format_row(r, sides=False):
    line = (f"{r['label']:22s} A1={r['w1']:3d} A2={r['w2']:3d} nul={r['draw']:3d} | "
            f"rounds moy={r['rounds']:5.1f} | surv A1={r['surv1']:4.1f} A2={r['surv2']:4.1f}")
    if sides:
        decided = max(1, r['w1'] + r['w2'])
        line += f" | gauche gagne {100 * r['w1'] / decided:5.1f} %"
    return line


_ROW = re.compile(r"^(.{22}) A1=\s*(\d+) A2=\s*(\d+)")


def load_rows(path):
    """{libellé: (victoires A1, victoires A2)} d'un résultat sauvegardé."""
    rows = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _ROW.match(line)
            if m:
                rows[m.group(1).strip()] = (int(m.group(2)), int(m.group(3)))
    return rows


def main(argv):
    args = list(argv)
    opts = {'--only': None, '--off': None, '--save': None, '--compare': None,
            '--weather': None}
    size = (40, 30)
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--size':
            size = (int(args[i + 1]), int(args[i + 2]))
            i += 3
        elif a in opts:
            opts[a] = args[i + 1]
            i += 2
        else:
            positional.append(a)
            i += 1
    suite = positional[0] if positional else "balance"
    if suite not in SUITES:
        sys.exit(f"Suite inconnue: {suite} (choix: {', '.join(SUITES)})")
    n = int(positional[1]) if len(positional) > 1 else 12
    off = int(opts['--off']) if opts['--off'] else (5000 if suite == "sides" else 1000)
    matches = [m for m in SUITES[suite]
               if not opts['--only'] or opts['--only'].lower() in m[0].lower()]
    reference = load_rows(opts['--compare']) if opts['--compare'] else {}

    t0 = time.time()
    lines = []
    for match in matches:
        r = run_match(match, n, off, size[0], size[1], opts['--weather'])
        line = format_row(r, sides=(suite == "sides"))
        ref = reference.get(r['label'])
        if ref:
            line += f" | avant A1={ref[0]:3d} ({r['w1'] - ref[0]:+d})"
        print(line, flush=True)
        lines.append(line)
    footer = f"({time.time() - t0:.1f}s, N={n}, off={off}, {size[0]}x{size[1]})"
    print(footer)
    if opts['--save']:
        with open(opts['--save'], "w", encoding="utf-8") as f:
            f.write("\n".join(lines + [footer]) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
