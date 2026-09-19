"""Tests de l'import du livre de règles (livre_import.py → armees_livre.json)
et de son chargement dans la bibliothèque d'unités.

    python test_livre.py            # tout
    python test_livre.py portee     # seulement les tests dont le nom contient 'portee'
"""
import json, os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import livre_import as li
import unit_library as ul

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def lib_unit(army, name):
    return next(u for u in ul.get_library()[army]["units"] if u["nom"] == name)


# ── Conversions de cellules ──

@test
def test_nombres_du_livre():
    assert li.num("3M") == 3 and li.num("4m") == 4
    assert li.num("0/-2*") == 0 and li.num("5 /3*") == 5
    assert li.num("4 —> 2²") == 4
    assert li.num("44593.0") == 1          # « 1/2 » changé en date par Excel
    assert li.num("44259.0") == 4          # « 4/3 »
    for blank in ("—", "—*", "...", "**", "-", "*1"):
        assert li.num(blank) is None, blank


@test
def test_degats_du_livre():
    assert li.dice("1.0") == "1"
    assert li.dice("1D2") == "1d2"
    assert li.dice("1/1D3*") == "1"
    assert li.dice("2+1D4") == "2+1d4"
    assert li.dice("44256.0") == "1"
    assert li.dice("—") is None


@test
def test_portees_converties():
    assert li.game_range("18.0", "Arbalète", 4) == 9            # tir: moitié
    assert li.game_range("3.0", "Lance", None) == 2             # allonge
    assert li.game_range("2.0", "Lance", None) == 2             # lance de cavalerie
    assert li.game_range("2.0", "Hache à deux mains", None) == 1
    assert li.game_range("7.0", "Pique", None) == 3             # mêlée plafonnée
    assert li.game_range("6.0", "Couteau de lancer", None) == 4  # arme de jet
    assert li.game_range("10-50", "Carreaux de baliste", None) == 25


@test
def test_munitions_dans_le_nom():
    assert li.split_ammo("Arbalète [4]") == ("Arbalète", 4)
    assert li.split_ammo("Arc (x5)") == ("Arc", 5)
    assert li.split_ammo("Arbalette (4x)") == ("Arbalette", 4)
    assert li.split_ammo("Epée") == ("Epée", None)


# ── Le livre complet ──

@test
def test_json_a_jour_avec_le_livre():
    """armees_livre.json doit être régénéré après chaque modification du
    livre ou du script: python src/livre_import.py"""
    armies, _ = li.parse_livre()
    with open(li.OUT, encoding="utf-8") as f:
        saved = json.load(f)["armies"]
    assert saved == json.loads(json.dumps(armies)), "relancer: python src/livre_import.py"


@test
def test_armees_du_livre_presentes():
    armies = ul.list_armies()
    for a in ("Arkkar", "Armée Muhr", "Armée Huǒ shé", "Armée Marcheurs Jaunes",
              "Armée Aïdatienne", "Ordre Eternel", "Armée Erast", "Ordre de Chevalerie",
              "Collège de magie", "Al-Athar"):
        assert a in armies, a
    assert lib_unit("Armée Skaldienne", "Baliste de Tartaglia")["source"] == "livre"
    assert lib_unit("Héros", "Diane, La Reine Dieu")["source"] == "livre"


@test
def test_unites_reglees_a_la_main_intactes():
    arb = lib_unit("Armée Skaldienne", "Arbaletrier régulier")
    assert "source" not in arb and arb["traits"] == []       # pas de Munitions (4)
    ed = lib_unit("Héros", "Edolion")
    assert ed["unit_type"] == "Monstre" and ed["size"] == 3
    names = [u["nom"] for u in ul.get_library()["Armée Orlandar"]["units"]]
    assert len(names) == len(set(names)), "aucun doublon"


@test
def test_types_deduits():
    assert lib_unit("Armée Marcheurs Jaunes", "Zarog le Géant")["unit_type"] == "Héros"
    assert lib_unit("Armée Marcheurs Jaunes", "Behemoth")["unit_type"] == "Monstre"
    assert lib_unit("Armée Muhr", "Eléphant de guerre")["unit_type"] == "Large"
    assert lib_unit("Armée Muhr", "Cavalier")["unit_type"] == "Cavalerie"
    assert lib_unit("Armée Skaldienne", "Baliste de Tartaglia")["unit_type"] == "Artillerie"


@test
def test_toutes_les_unites_se_construisent():
    lib = ul.get_library()
    for army in ul.list_armies():
        for d in lib[army]["units"]:
            u = ul.create_unit(d, lib[army]["color"])
            assert u.armes and u.max_pv >= 1 and 1 <= u.sauvegarde <= 7, (army, d["nom"])


@test
def test_traits_du_livre_reconnus():
    mage = ul.create_unit(lib_unit("Armée Marcheurs Jaunes", "Mage Jaune"), (0, 0, 0))
    assert mage.spells_per_round == 2 and mage.spells       # « Sortilèges (2) »
    garde = ul.create_unit(lib_unit("Armée Aïdatienne", "Garde de l'archipel"), (0, 0, 0))
    assert garde.charge_aida and not garde.charge_montee    # « Charge Aïdatienne »
    squelette = ul.create_unit(lib_unit("Ordre Eternel", "Guerrier Squelette"), (0, 0, 0))
    assert squelette.immune_mind                             # « Mort vivant »
    behemoth = ul.create_unit(lib_unit("Armée Marcheurs Jaunes", "Behemoth"), (0, 0, 0))
    assert behemoth.fear_aura == 1 and behemoth.charge_montee  # Peur, Charge du minotaure
    tir = ul.create_unit(lib_unit("Armée Muhr", "Tirailleur"), (0, 0, 0))
    assert tir.max_ammo == 3                                 # « Javelots [3] »


@test
def test_bataille_avec_une_armee_du_livre():
    from battle import Battle
    random.seed(4)
    a1 = ul.build_army("Arkkar", [("Infanterie", 4), ("Citoyen du par-delà", 3),
                                  ("Monteur de Rhino", 1), ("Occultiste", 1)])
    a2 = ul.build_army("Armée Muhr", [("Lancier", 4), ("Archer", 3), ("Chars", 1)])
    b = Battle(a1, a2, 40, 30, 8, map_name="Prairie")
    while not b.is_battle_over() and b.round <= 90:
        b.simulate_round()
    assert b.is_battle_over(), "la bataille se termine"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests livre passent.")
    sys.exit(1 if fails else 0)
