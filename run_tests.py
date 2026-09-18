"""Lance toutes les suites de tests en parallèle et résume.

    python run_tests.py              # tout
    python run_tests.py terrain ui   # seulement les suites dont le nom contient l'un des mots
    python run_tests.py -v           # affiche aussi la sortie des suites qui passent

Chaque src/test_*.py est un script autonome (code de sortie 0 = succès).
Aucune dépendance hors bibliothèque standard.
"""
import glob
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")


def suites():
    return [(os.path.basename(p)[:-3], [sys.executable, p])
            for p in sorted(glob.glob(os.path.join(SRC, "test_*.py")))]


def run(cmd):
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy",
               PYTHONIOENCODING="utf-8")
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout + p.stderr, time.time() - t0


def main(argv):
    verbose = "-v" in argv
    words = [a for a in argv if not a.startswith("-")]
    todo = [(n, c) for n, c in suites() if not words or any(w in n for w in words)]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        results = list(pool.map(lambda nc: (nc[0],) + run(nc[1]), todo))
    failed = [r for r in results if r[1] != 0]
    for name, code, output, dt in results:
        mark = "OK   " if code == 0 else "ECHEC"
        print(f"{mark} {name:28s} {dt:5.1f}s")
        if code != 0 or verbose:
            print("    " + output.strip().replace("\n", "\n    ")[-4000:])
    print(f"\n{len(results) - len(failed)}/{len(results)} suites vertes "
          f"en {time.time() - t0:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
