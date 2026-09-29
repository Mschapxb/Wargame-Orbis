"""Vidéo de bataille (video_export): fichier AVI bien formé, bataille rejouée
à l'identique, export complet dans un autre processus. Script exécutable:
    python test_video.py
"""
import os, sys, random, struct, tempfile, traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("WARGAME_ORBIS_SETTINGS", "memory")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pygame
pygame.init()
pygame.display.set_mode((1, 1))

import battle_pipeline as BP
import unit_library as ul
import video_export as VE
from battle import Battle

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def small_battle(seed=5, mapname="Prairie"):
    random.seed(seed)
    a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 6), ("Arbaletrier régulier", 3)])
    a2 = ul.build_army("Armée Orlandar", [("Fantassin covaliir", 6), ("Cavalier covaliir", 2)])
    return Battle(a1, a2, 40, 30, 8, map_name=mapname)


def state(b):
    return [(u.position, u.hp, u.is_alive) for u in b.army1_roster + b.army2_roster]


def read_avi(path):
    """(images annoncées par l'en-tête, entrées d'index, données des images)."""
    data = open(path, "rb").read()
    assert data[:4] == b"RIFF" and data[8:12] == b"AVI "
    assert struct.unpack("<I", data[4:8])[0] == len(data) - 8
    avih = data.index(b"avih")
    total = struct.unpack("<14I", data[avih + 8:avih + 64])[4]
    idx = data.rindex(b"idx1")
    n = struct.unpack("<I", data[idx + 4:idx + 8])[0] // 16
    movi = data.index(b"movi")
    frames = []
    for i in range(n):
        ck, _flags, off, size = struct.unpack("<4sIII", data[idx + 8 + 16 * i:idx + 24 + 16 * i])
        assert ck == b"00dc"
        assert data[movi + off:movi + off + 4] == b"00dc"
        frames.append(data[movi + off + 8:movi + off + 8 + size])
    return total, n, frames


@test
def test_avi_mjpeg_bien_forme():
    with tempfile.TemporaryDirectory() as tmp:
        w = VE.AviWriter(os.path.join(tmp, "t.avi"), 64, 48, 12)
        for i in range(5):
            s = pygame.Surface((64, 48))
            s.fill((40 * i, 80, 120))
            w.add_frame(s)
        total, n, frames = read_avi(w.close())
        assert total == n == 5
        assert all(f[:2] == b"\xff\xd8" and f[-2:] == b"\xff\xd9" for f in frames)


@test
def test_bataille_rejouee_a_l_identique():
    """Le kit (bataille au départ + état du hasard) rejoue EXACTEMENT la
    bataille, ailleurs — identités d'unités recalées au passage."""
    b = small_battle()
    kit = BP.pack_battle(b, random.getstate())
    expected = []
    for _ in range(6):
        b.simulate_round()
        expected.append(state(b))
    replay, rng = BP.unpack_battle(kit)
    random.setstate(rng)
    for k in range(6):
        replay.simulate_round()
        assert state(replay) == expected[k], f"round {k + 1}"


@test
def test_export_dans_le_processus_meme_bataille():
    """L'export dessine chaque round de la bataille rejouée: la dernière
    image correspond à la bataille jouée à la main."""
    b = small_battle(seed=8)
    kit = BP.pack_battle(b, random.getstate())
    rounds = 3
    for _ in range(rounds):
        b.simulate_round()
    with tempfile.TemporaryDirectory() as tmp:
        kit_path = os.path.join(tmp, "kit.bin")
        open(kit_path, "wb").write(kit)
        seen = []
        path, view = VE.export({'kit': kit_path, 'base': os.path.join(tmp, "v"),
                                'video': {'resolution': "720p", 'fps': 12,
                                          'seconds_per_round': 0.5},
                                'title': "Essai", 'max_rounds': rounds, 'ffmpeg': False},
                               on_round=seen.append)
        assert path.endswith(".avi") and seen[-1] == rounds
        total, n, _frames = read_avi(path)
        assert total == n >= rounds * 6
        assert view.screen.get_size() == (1280, 720)
        assert state(view.battle) == state(b)


@test
def test_export_en_arriere_plan():
    """ExportJob: autre processus, avancement lisible, fichier produit."""
    b = small_battle(seed=2)
    kit = BP.pack_battle(b, random.getstate())
    with tempfile.TemporaryDirectory() as tmp:
        job = VE.ExportJob(kit, {'resolution': "720p", 'fps': 12, 'seconds_per_round': 0.5},
                           title="Essai", out_dir=tmp, max_rounds=2, ffmpeg=False)
        final = job.wait(timeout=180)
        assert final['state'] == "done", final
        assert os.path.exists(final['path']) and os.path.getsize(final['path']) > 10_000
        assert not os.path.exists(job.work)          # dossier de travail nettoyé


# ── Runner (ajouter les nouveaux tests AU-DESSUS de cette ligne) ──

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    fails = []
    for fn in TESTS:
        if only and only not in fn.__name__:
            continue
        try:
            random.seed(7)
            fn()
            print(f"  OK    {fn.__name__}")
        except Exception:
            fails.append(fn.__name__)
            print(f"  ECHEC {fn.__name__}")
            traceback.print_exc()
    print()
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests vidéo passent.")
    sys.exit(1 if fails else 0)
