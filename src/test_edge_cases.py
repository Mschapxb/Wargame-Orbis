"""Cas limites du moteur: on vérifie qu'aucune configuration tordue ne
casse la simulation (armée vide, unité sans arme, carte minuscule,
effectifs démesurés, sorts sans cible, siège dégénéré...)."""
import os, sys, random, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_library as ul
from battle import Battle
from unit import Unit

FAILS = []


def run_case(label, a1, a2, w=60, h=40, map_name="Prairie", rounds=40, setup=None):
    try:
        b = Battle(a1, a2, w, h, 8, map_name=map_name)
        if setup is not None:
            setup(b)
        # Aucune unité ne doit être hors carte ni empilée
        for army in (b.army1, b.army2):
            for u in army:
                x, y = u.position
                assert 0 <= x < b.battlefield.width, f"{u.name} hors carte en x={x}"
                assert 0 <= y < b.battlefield.height, f"{u.name} hors carte en y={y}"
        n = 0
        while not b.is_battle_over() and n < rounds:
            b.simulate_round()
            n += 1
        rep = b.get_battle_report()
        assert 'winner' in rep and 'army1' in rep and 'army2' in rep
        for key in ('army1', 'army2'):
            a = rep[key]
            assert a['alive_count'] + a['dead_count'] + a['fled_count'] == a['total'], \
                f"{key}: comptes incohérents {a['alive_count']}+{a['dead_count']}+{a['fled_count']} != {a['total']}"
            for c in a['contingents']:
                assert c['alive_count'] + c['dead_count'] + c['fled_count'] == c['total']
        print(f"  OK   {label:42s} ({n} rounds, {rep['winner']})")
    except Exception as exc:
        FAILS.append((label, traceback.format_exc()))
        print(f"  ECHEC {label:42s} -> {type(exc).__name__}: {exc}")


def sk(comp):
    return ul.build_army("Armée Skaldienne", list(comp.items()))


random.seed(1)
print("=== Cas limites ===")

run_case("armée 1 vide", [], sk({"Infanterie régulière": 3}))
run_case("les deux vides", [], [])
run_case("1 contre 1", sk({"Infanterie régulière": 1}), sk({"Infanterie régulière": 1}))

# Battle(a, a, ...) deep-copie la MÊME armée des deux côtés: sans réattribution
# d'uid après les deepcopy, les deux camps auraient des unités aux uids
# identiques et un tri comme (-score, uid, u) pourrait comparer deux Unit
# directement en cas d'égalité totale, ce qui lève un TypeError.
_ident_army = sk({"Infanterie régulière": 5, "Arbaletrier régulier": 3})
try:
    _b = Battle(_ident_army, _ident_army, 40, 30, 8, map_name="Prairie")
    _uids = [u.uid for u in _b.army1 + _b.army2]
    assert len(_uids) == len(set(_uids)), f"uids dupliqués: {_uids}"
    print(f"  OK   {'Battle(a, a, ...) -> uids tous distincts':42s}")
except Exception as _exc:
    FAILS.append(("Battle(a, a, ...) -> uids tous distincts", traceback.format_exc()))
    print(f"  ECHEC {'Battle(a, a, ...) -> uids tous distincts':42s} -> {type(_exc).__name__}: {_exc}")

run_case("armées identiques (Battle(a, a, ...))", _ident_army, _ident_army)

sans_arme = Unit("Manchot", pv=3, vitesse=3, morale=2, sauvegarde=5, color=(1, 2, 3))
sans_arme.token_name = ""
run_case("unité sans arme", [sans_arme], sk({"Infanterie régulière": 2}))

run_case("carte minuscule", sk({"Infanterie régulière": 4}),
         sk({"Infanterie régulière": 4}), w=20, h=12)
run_case("effectifs vs petite carte", sk({"Infanterie régulière": 30}),
         sk({"Infanterie régulière": 30}), w=30, h=16)

run_case("artillerie seule", sk({"Baliste": 3}), sk({"Scorpion": 3}))
run_case("mages seuls", sk({"Mage de guerre": 3}), sk({"Mage de guerre": 3}))
run_case("artillerie vs mêlée", sk({"Baliste": 2}), sk({"Infanterie régulière": 6}))

run_case("siège sans défenseurs", sk({"Infanterie régulière": 5}), [], map_name="Siège")
run_case("siège attaquants vides", [], sk({"Infanterie régulière": 5}), map_name="Siège")
run_case("siège normal", sk({"Infanterie régulière": 6, "Arbaletrier régulier": 3}),
         sk({"Infanterie régulière": 4, "Arbaletrier régulier": 3}), map_name="Siège")


def _raze_walls(b):
    """Tout le mur s'écroule d'emblée: plus que des brèches."""
    import structures as st
    bf = b.battlefield
    for gid, kind in list(bf.structure_kind.items()):
        if kind == st.WALL:
            cells = list(bf.structure_members[gid])
            if st.damage(bf, gid, 999, heavy=True):
                b._structure_collapsed(gid, kind, cells)


run_case("siège où tout le mur tombe", sk({"Infanterie régulière": 6, "Arbaletrier régulier": 3}),
         sk({"Infanterie régulière": 4, "Arbaletrier régulier": 3}), map_name="Siège",
         setup=_raze_walls)
run_case("siège avec catapulte",
         ul.build_army("Armée Orlandar", [("Fantassin covaliir", 6), ("Catapulte covaliir", 2)]),
         sk({"Infanterie régulière": 4, "Arbaletrier régulier": 3}), map_name="Siège", rounds=60)

# Groupes: 4 corps, dont un vide de mêlée
g = []
for gi, comp in enumerate([{"Infanterie régulière": 6}, {"Arbaletrier régulier": 6},
                           {"Baliste": 2}, {"Officier": 2}]):
    part = sk(comp)
    for u in part:
        u.contingent = f"G{gi + 1}"
    g += part
run_case("4 groupes hétérogènes", g, sk({"Infanterie régulière": 10}))

# Unités volumineuses
large = sk({"Baliste": 4})
for u in large:
    u.size = 3
run_case("unités size 3", large, sk({"Infanterie régulière": 6}))

run_case("citadelle sans défenseurs", sk({"Infanterie régulière": 5}), [], map_name="Citadelle")
run_case("citadelle minuscule", sk({"Infanterie régulière": 4}),
         sk({"Infanterie régulière": 3}), w=24, h=16, map_name="Citadelle")

for m in ("Prairie", "Forêt", "Village", "Siège", "Défilé", "Citadelle"):
    run_case(f"carte {m}", sk({"Infanterie régulière": 5, "Arbaletrier régulier": 3}),
             ul.build_army("Armée Orlandar", [("Fantassin covaliir", 5), ("Archer covaliir", 3)]),
             map_name=m)

print()
if FAILS:
    print(f"{len(FAILS)} ECHEC(S)")
    for label, tb in FAILS:
        print(f"\n--- {label} ---\n{tb}")
    sys.exit(1)
print("Tous les cas limites passent.")
