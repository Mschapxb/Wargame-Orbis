"""Une graine doit rejouer EXACTEMENT la même bataille, d'un processus à
l'autre. Sans cela, impossible de mesurer l'effet d'un changement."""
import os, sys, random, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def run_once():
    import unit_library as ul
    from battle import Battle
    out = []
    for m in ("Prairie", "Siège", "Forêt"):
        for seed in range(4):
            random.seed(1000 + seed)
            a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 8), ("Arbaletrier régulier", 4)])
            a2 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 5), ("Arbaletrier régulier", 4)])
            b = Battle(a1, a2, 40, 30, 8, map_name=m)
            while not b.is_battle_over() and b.round <= 90:
                b.simulate_round()
            hp = sum(u.hp for u in b.army1 + b.army2 if u.is_alive)
            out.append(f"{m}|{seed}|{b.is_battle_over()}|{b.round}|{hp}")
    return "\n".join(out)


def seed_is_isolated():
    """Graine de carte: même carte et même déploiement quel que soit le
    random global, et la génération ne consomme pas le random global (deux
    graines de carte différentes le laissent dans le même état; seules les
    IA y tirent leur propre graine, comme sans graine de carte)."""
    import unit_library as ul
    from battle import Battle
    errors = []
    for m in ("Prairie", "Village", "Siège", "Citadelle"):
        seen = []
        after = []
        for glob, map_seed in ((1, 4242), (2, 4242), (1, 99)):
            random.seed(glob)
            before = random.getstate()
            a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 6), ("Arbaletrier régulier", 3)])
            a2 = ul.build_army("Armée Orlandar", [("Fantassin covaliir", 6), ("Archer covaliir", 3)])
            random.setstate(before)
            b = Battle(a1, a2, 40, 30, 8, map_name=m,
                       map_options={'relief': "Aléatoire", 'weather': "Aléatoire", 'seed': map_seed})
            bf = b.battlefield
            seen.append((repr(bf.grid), repr(vars(bf.weather)),
                         [u.position for u in b.army1 + b.army2]))
            after.append(random.getstate())
        if seen[0] != seen[1]:
            errors.append(f"{m}: la carte graînée dépend du random global")
        if after[0] != after[2]:
            errors.append(f"{m}: la génération graînée consomme le random global")
    return errors


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        sys.stdout.buffer.write(run_once().encode("utf-8"))
        sys.exit(0)
    errors = seed_is_isolated()
    if errors:
        print("ECHEC: " + "\n       ".join(errors))
        sys.exit(1)
    print("OK   graine de carte isolée du random global")
    runs = [subprocess.run([sys.executable, __file__, "--child"], capture_output=True).stdout
            for _ in range(3)]
    if runs[0] and runs[0] == runs[1] == runs[2]:
        print("OK   3 exécutions identiques")
        sys.exit(0)
    print("ECHEC: résultats différents d'une exécution à l'autre")
    for i, r in enumerate(runs):
        print(f"--- run {i}\n{r.decode('utf-8', 'replace')}")
    sys.exit(1)
