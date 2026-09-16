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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        sys.stdout.buffer.write(run_once().encode("utf-8"))
        sys.exit(0)
    runs = [subprocess.run([sys.executable, __file__, "--child"], capture_output=True).stdout
            for _ in range(3)]
    if runs[0] and runs[0] == runs[1] == runs[2]:
        print("OK   3 exécutions identiques")
        sys.exit(0)
    print("ECHEC: résultats différents d'une exécution à l'autre")
    for i, r in enumerate(runs):
        print(f"--- run {i}\n{r.decode('utf-8', 'replace')}")
    sys.exit(1)
