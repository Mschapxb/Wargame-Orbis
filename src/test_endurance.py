"""Tests des munitions et de la fatigue (unit.py, lot 1E).

    python test_endurance.py            # tout
    python test_endurance.py fatigue    # seulement les tests dont le nom contient 'fatigue'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import terrain as tr
import unit as U
import unit_library as ul
from battle import Battle
from battlefield import Battlefield
from models import Arme
from unit import Unit

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def flat_bf(w=14, h=8, **data):
    grid = [[0] * h for _ in range(w)]
    return Battlefield(w, h, 0, "Prairie", grid, dict(terrain=tr.make_grid(w, h), **data))


def archer(pos, melee=False):
    armes = [Arme("Arc", 1, 3, 3, 0, "1", porte=8)]
    if melee:
        armes.append(Arme("Epee", 1, 4, 4, 0, "1", porte=1))
    u = Unit("Archer", pv=1, vitesse=4, morale=5, sauvegarde=7, color=(1, 1, 1),
             armes=armes, role="back")
    u.position = pos
    return u


def dummy(pos, pv=100000, save=7):
    u = Unit("Cible", pv=pv, vitesse=4, morale=5, sauvegarde=save, color=(2, 2, 2),
             armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    u.position = pos
    return u


# ── Munitions ──

@test
def test_carquois_par_defaut_et_trait_ammo():
    assert archer((0, 0)).max_ammo == U.DEFAULT_AMMO
    assert dummy((0, 0)).max_ammo is None                     # mêlée: illimité
    bal = ul.make_unit("Armée Skaldienne", "Baliste")
    assert bal.max_ammo is None                               # machine: rechargement
    u = Unit("X", 1, 4, 3, 7, (0, 0), armes=[Arme("Arc", 1, 3, 3, 0, "1", porte=8)],
             special={"ammo:4": True})
    assert u.max_ammo == 4


@test
def test_chaque_volee_consomme_puis_passage_a_la_melee():
    bf = flat_bf()
    a, t = archer((0, 1), melee=True), dummy((6, 1))
    bf.place_unit(a); bf.place_unit(t)
    for i in range(U.DEFAULT_AMMO):
        a.perform_attacks(t, bf)
        assert a.ammo == U.DEFAULT_AMMO - i - 1
    assert a._max_range == 1 and [w.name for w in a.armes] == ["Epee"]
    assert a.role == "front" and a.attack_type == "melee"
    before = t.hp
    a.perform_attacks(t, bf)                                 # plus rien à tirer
    assert t.hp == before


@test
def test_tireur_sans_arme_de_melee_prend_un_coutelas():
    bf = flat_bf()
    a, t = archer((0, 1)), dummy((6, 1))
    bf.place_unit(a); bf.place_unit(t)
    a.ammo = 1
    a.perform_attacks(t, bf)
    assert [w.name for w in a.armes] == ["Coutelas"] and a._max_range == 1


@test
def test_garnison_sur_le_rempart_ne_consomme_pas():
    random.seed(5)
    a1 = ul.build_army("Armée Skaldienne", [("Arbaletrier régulier", 1)])
    a2 = ul.build_army("Armée Skaldienne", [("Arbaletrier régulier", 3)])
    b = Battle(a1, a2, 40, 30, 8, map_name="Siège")
    bf = b.battlefield
    gar = next(u for u in b.army2 if bf.on_active_rampart(*u.position, u, b))
    att = b.army1[0]
    spot = next((bf.wall_x - d, gar.position[1] + dy) for d in range(3, 8) for dy in (0, 1, -1, 2, -2)
                if bf.is_valid(bf.wall_x - d, gar.position[1] + dy)
                and (bf.wall_x - d, gar.position[1] + dy) not in bf.units)
    bf.move_unit(att, spot)
    assert bf.has_line_of_fire(gar, att) and bf.has_line_of_fire(att, gar)
    gar_before, att_before = gar.ammo, att.ammo
    gar.perform_attacks(att, bf, b)
    assert gar.ammo == gar_before                  # réserves de la place
    att.is_alive = True
    att.perform_attacks(gar, bf, b)
    assert att.ammo == att_before - 1              # l'assaillant, lui, consomme


@test
def test_train_de_siege_double_les_carquois_de_l_assaillant():
    random.seed(2)
    a1 = ul.build_army("Armée Skaldienne", [("Arbaletrier régulier", 2)])
    a2 = ul.build_army("Armée Skaldienne", [("Arbaletrier régulier", 2)])
    b = Battle(a1, a2, 40, 30, 8, map_name="Siège")
    assert all(u.ammo == U.DEFAULT_AMMO * U.SIEGE_TRAIN_FACTOR for u in b.army1)
    assert all(u.ammo == U.DEFAULT_AMMO for u in b.army2)


@test
def test_tir_econome_quand_le_carquois_est_presque_vide():
    bf = flat_bf()
    a = archer((0, 1))
    a.armes[0].blesser = 6                        # trait faible: blesse sur 6
    tough = dummy((6, 1), save=2)                 # mur de boucliers
    soft = dummy((6, 3))
    for u in (a, tough, soft):
        bf.place_unit(u)
    assert not a.spares_ammo(tough, bf)           # carquois plein: on tire
    a.ammo = U.AMMO_SPARING
    assert a.spares_ammo(tough, bf)               # presque vide: pas sur lui
    a.armes[0].blesser = 3
    assert not a.spares_ammo(soft, bf)            # une cible qui en vaut la peine


# ── Fatigue ──

@test
def test_fatigue_monte_en_melee_et_redescend_au_repos():
    u = dummy((0, 0))
    for _ in range(U.FATIGUE_TIRED):
        u.start_round()
        u._melee_this_round = True
        u.end_round()
    assert u.fatigue == U.FATIGUE_TIRED and u.tired and not u.exhausted
    u.start_round(); u.end_round()          # un round sans combat
    assert u.fatigue == U.FATIGUE_TIRED - 1
    u._calm_rounds = 1
    u.start_round(); u.end_round()          # au calme: récupère plus vite
    assert u.fatigue == U.FATIGUE_TIRED - 3


@test
def test_charge_fatigue_davantage():
    u = dummy((0, 0))
    u.start_round()
    u._melee_this_round = True
    u._charged_this_round = True
    u.end_round()
    assert u.fatigue == 3


@test
def test_effets_fatigue_et_epuisement():
    bf = flat_bf()
    a, t = dummy((3, 3)), dummy((4, 3))
    a.fatigue = U.FATIGUE_TIRED
    assert tr.combat_mods(bf, a, t, False)['toucher'] == 1   # mêlée
    assert tr.combat_mods(bf, a, t, True)['toucher'] == 0    # tir: pas encore
    a.fatigue = U.FATIGUE_EXHAUSTED
    assert tr.combat_mods(bf, a, t, True)['toucher'] == 1
    a.start_round()
    assert a.vitesse == 3                    # 4 - 1
    a.fatigue = 0
    a.start_round()
    assert a.vitesse == 4


@test
def test_epuise_ne_charge_pas():
    random.seed(4)
    a1 = ul.build_army("Armée Orlandar", [("Cavalier covaliir", 1)])
    a2 = ul.build_army("Armée Orlandar", [("Fantassin covaliir", 1)])
    b = Battle(a1, a2, 30, 12, 0, map_name="Prairie", map_options={'relief': "Plat"})
    bf = b.battlefield
    cav, foe = b.army1[0], b.army2[0]
    bf.remove_unit(cav); bf.remove_unit(foe)
    cav.position, foe.position = (10, 6), (14, 6)
    bf.place_unit(cav); bf.place_unit(foe)
    cav.fatigue = U.FATIGUE_EXHAUSTED
    b._charge_phase([cav, foe])
    assert not getattr(cav, '_charged_this_round', False)


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests munitions et fatigue passent.")
    sys.exit(1 if fails else 0)
