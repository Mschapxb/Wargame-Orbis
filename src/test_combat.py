"""Tests de la résolution commune des attaques (combat.py) et des règles
qui en dépendent: convention de signe de la perforation, sauvegarde
effective (armure magique, phalange), bonus d'armée du menu, peur, traits.

    python test_combat.py            # tout
    python test_combat.py armure     # seulement les tests dont le nom contient 'armure'
"""
import os, sys, random, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import combat
import tactics
import terrain as tr
import unit_library as ul
from battlefield import Battlefield
from models import Arme, SpellMagicArmor
from unit import Unit

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def soldier(pos=(0, 0), save=6, morale=3, armes=None, unit_type="Infanterie", pv=3):
    u = Unit("Soldat", pv=pv, vitesse=3, morale=morale, sauvegarde=save, color=(1, 1, 1),
             armes=armes if armes is not None else [Arme("Epee", 1, 3, 3, 0, "1", porte=1)],
             unit_type=unit_type)
    u.position = pos
    return u


def flat_bf(w=12, h=12):
    grid = [[0] * h for _ in range(w)]
    return Battlefield(w, h, 0, "Prairie", grid, {'terrain': tr.make_grid(w, h)})


# ── Conventions de signe ──

@test
def test_perforation_negative_degrade_la_sauvegarde():
    assert combat.save_threshold(4, -2) == 6
    assert combat.save_threshold(6, -2) == combat.NO_SAVE     # plafonné à 7
    assert combat.save_threshold(4, 1) == 3                   # perforation positive: aide la cible
    assert combat.save_threshold(4, 0, mod=-2) == 2           # rempart


@test
def test_boule_de_feu_perce_les_armures():
    """Régression: la perforation -2 de la boule de feu AIDAIT la cible."""
    random.seed(3)
    heavy = soldier(save=3)
    saved = sum(combat.saves(combat.save_threshold(heavy.sauvegarde, -2)) for _ in range(6000))
    # seuil 5: 2 chances sur 6 (et non 100 % comme avant la correction)
    assert 1700 < saved < 2300, saved


@test
def test_probabilites_coherentes_avec_les_jets():
    random.seed(11)
    n, hits = 20000, 0
    for _ in range(n):
        hits += combat.roll(3, 4, 5) == combat.HIT
    expected = combat.p_hit(3, 4, 5)
    assert abs(hits / n - expected) < 0.015, (hits / n, expected)


# ── Profil d'attaque partagé moteur / IA / interface ──

@test
def test_profil_anti_type_et_charge():
    a = soldier()
    a.anti_large = True
    a.charge_montee = True
    big = soldier(unit_type="Monstre")
    p = combat.attack_profile(a, big, a.armes[0], charging=True)
    assert (p.toucher, p.blesser, p.dmg_bonus) == (2, 2, 1), (p.toucher, p.blesser, p.dmg_bonus)
    labels = {label for label, _, _ in p.details}
    assert {"Anti-Large", "Charge montée"} <= labels, labels


@test
def test_profil_flanc_libelle():
    bf = flat_bf()
    t = soldier((5, 5))
    t.facing = (1.0, 0.0)                 # regarde vers l'est
    a = soldier((5, 4))                   # arrive par le nord: flanc
    p = combat.attack_profile(a, t, a.armes[0], bf)
    assert p.toucher == 2, p.toucher
    assert ("Flanc", combat.TOUCHER, -1) in p.details, p.details
    assert "Toucher 2+ (Flanc -1)" in combat.describe(p), combat.describe(p)


@test
def test_ia_et_moteur_memes_chiffres():
    bf = flat_bf()
    a = soldier((5, 4))
    a.afraid = True
    t = soldier((5, 5), save=4)
    t.facing = (1.0, 0.0)
    prof = combat.attack_profile(a, t, a.armes[0], bf)
    assert abs(tactics.expected_damage(a, t, 1, bf) - prof.expected_damage()) < 1e-9


@test
def test_fiche_apercu_attaque():
    import ui

    class _Battle:
        def __init__(self, bf, a, t):
            self.battlefield, self.army1, self.army2 = bf, [a], [t]
            self.commander1 = self.commander2 = None

        def get_closest_enemy(self, u):
            return self.army2[0]

    bf = flat_bf()
    a = soldier((5, 4))
    t = soldier((5, 5), save=5)
    t.facing = (1.0, 0.0)
    b = _Battle(bf, a, t)
    target, dist, prof, in_reach = ui.attack_preview(a, b)
    assert target is t and dist == 1 and in_reach
    lines = [x for x, _ in ui.unit_card_lines(a, b)]
    assert any(x.startswith("Contre Soldat (1 cases)") and "dégâts/round" in x for x in lines), lines
    assert any("Toucher 2+ (Flanc -1)" in x and "Svg 5+" in x for x in lines), lines
    t.position = (5, 11)                              # hors de portée
    lines = [x for x, _ in ui.unit_card_lines(a, b)]
    assert any("hors de portée" in x for x in lines), lines
    assert not any("Toucher " in x for x in lines), lines


# ── Sauvegarde effective: plus de dérive ──

@test
def test_armure_magique_ne_derive_pas():
    """Régression: sauvegarde 2 → plancher 1 pendant l'armure, puis +2
    rendus à la fin: 3 au lieu de 2."""
    u = soldier(save=2)
    u._armor_buff, u._armor_buff_rounds, u._armor_buff_amount = True, 1, 2
    assert u.sauvegarde == 1
    u.tick_armor_buff()
    assert u.sauvegarde == 2 and u.base_sauvegarde == 2, u.sauvegarde


@test
def test_phalange_ne_derive_pas():
    u = soldier(save=1)
    u._phalange_bonus_active = True
    assert u.sauvegarde == 1
    u._phalange_bonus_active = False
    assert u.sauvegarde == 1, u.sauvegarde


@test
def test_armure_et_phalange_cumulent():
    u = soldier(save=6)
    u._armor_buff, u._armor_buff_rounds, u._armor_buff_amount = True, 3, 2
    u._phalange_bonus_active = True
    assert u.sauvegarde == 3, u.sauvegarde


@test
def test_armure_magique_vise_le_moins_protege():
    """Régression: le sort visait la MEILLEURE sauvegarde (le lanceur lui-même)."""
    class _BF:
        def manhattan_distance(self, a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

    class _Battle:
        battlefield = _BF()

        def __init__(self, allies):
            self.allies = allies

        def get_allies(self, u):
            return self.allies

    mage = soldier((0, 0), save=2)
    tank = soldier((1, 0), save=3)
    naked = soldier((2, 0), save=7)
    mage._cast_armor(SpellMagicArmor(), _Battle([mage, tank, naked]), [])
    assert naked._armor_buff and not mage._armor_buff and not tank._armor_buff
    assert naked.sauvegarde == 5


# ── Bonus d'armée du menu: +1 est toujours un avantage ──

@test
def test_bonus_menu_dans_le_bon_sens():
    from menu import ArmyState
    st = ArmyState(0)
    st.add_unit("Armée Skaldienne", "Officier", 1)
    base = st.build()[0]
    for k in ("toucher", "blesser", "sauvegarde", "perforation"):
        st.bonuses[k] = 1
    u = st.build()[0]
    assert u.sauvegarde == base.sauvegarde - 1
    for a0, a1 in zip(base.armes, u.armes):
        assert a1.toucher == a0.toucher - 1
        assert a1.blesser == a0.blesser - 1
        assert a1.perforation == a0.perforation - 1


# ── Peur: pèse tant qu'on est dans l'aura, selon son niveau ──

@test
def test_peur_temporaire_et_graduee():
    u = soldier(morale=4)
    u.morale_bonus = 0
    u.apply_fear_effect(2, 3)                 # Effroi
    assert u.get_effective_morale() == 2
    u.morale_bonus = 0                         # nouvelle phase de moral, hors de l'aura
    assert u.get_effective_morale() == 4
    u.apply_fear_effect(2, 3)                  # de retour dans l'aura: même malus, pas cumulé
    assert u.get_effective_morale() == 2


@test
def test_immunite_mentale():
    u = soldier(morale=2)
    u.immune_mind = True
    assert u.apply_fear_effect(3, 1) is None
    assert u.get_effective_morale() == 2


# ── Traits lisibles → mécaniques du moteur ──

@test
def test_traits_speciaux():
    d = {"nom": "Bête", "deplacement": 4, "blessure": 10, "bravoure": 3, "sauvegarde": 5,
         "armes": [("Arc", 12, 1, 3, 3, 0, "1"), ("Griffes", 1, 2, 3, 3, -1, "1d2")],
         "traits": ["Terreur", "Régénération (20)", "Munitions [4]", "Rechargement (2)",
                    "Intimidant", "Immunité mentale", "Vengeance de sang (2)"]}
    u = ul.create_unit(d, (0, 0, 0))
    assert u.fear_aura == 3
    assert u.regeneration == 20
    assert u.max_ammo == 4 and u.ammo == 4
    assert u.reload_rounds == 2
    assert u.awe == 1
    assert u.immune_mind
    assert u.blood_vengeance == 2
    peur = ul.create_unit(dict(d, traits=["peur"]), (0, 0, 0))
    assert peur.fear_aura == 1 and peur.regeneration == 0 and peur.max_ammo == 10


@test
def test_regeneration_releve_l_unite():
    random.seed(5)
    u = soldier(pv=4)
    u.regeneration = 25
    u.take_damage(5)                            # -1 PV: à terre, pas mort
    assert not u.is_alive and u.down_timer > 0
    for _ in range(10):
        u.regenerate()
        if u.is_alive:
            break
    assert u.is_alive and u.pv >= 1


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests combat passent.")
    sys.exit(1 if fails else 0)
