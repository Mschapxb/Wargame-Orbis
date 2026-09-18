"""Tests de la météo (weather.py, weather_render.py, lot 1F).

    python test_weather.py            # tout
    python test_weather.py vent       # seulement les tests dont le nom contient 'vent'
"""
import os, sys, random, traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import structures as st
import terrain as tr
import unit_library as ul
import weather as W
from battle import Battle
from battlefield import Battlefield
from models import Arme
from unit import Unit

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def flat_bf(w=20, h=8, sky=None):
    grid = [[0] * h for _ in range(w)]
    bf = Battlefield(w, h, 0, "Prairie", grid, {'terrain': tr.make_grid(w, h)})
    bf.weather = sky
    return bf


def shooter(pos, porte=9):
    u = Unit("Tireur", pv=1, vitesse=4, morale=5, sauvegarde=7, color=(1, 1, 1),
             armes=[Arme("Arbalète", 1, 3, 3, 0, "1", porte=porte)], role="back")
    u.position = pos
    return u


@test
def test_clair_ne_tire_aucun_de():
    random.seed(9)
    before = random.getstate()
    assert W.resolve(None).name == W.CLEAR
    assert W.resolve(W.CLEAR).name == W.CLEAR
    assert random.getstate() == before


@test
def test_aleatoire_de_siege_sans_brouillard_ni_crepuscule():
    rng = random.Random(3)
    seen = {W.resolve(W.RANDOM_WEATHER, "Forêt", rng, siege=True).name for _ in range(400)}
    assert W.FOG not in seen and W.DUSK not in seen, seen
    seen_open = {W.resolve(W.RANDOM_WEATHER, "Forêt", rng).name for _ in range(400)}
    assert W.FOG in seen_open


@test
def test_brouillard_et_crepuscule_raccourcissent_les_armes():
    u = shooter((0, 0), porte=9)
    W.Weather(W.FOG).apply_to_unit(u)
    assert u.armes[0].porte == W.FOG_RANGE and u._max_range == W.FOG_RANGE
    assert u.armes[0].base_porte == 9                 # contre un mur: portée nominale
    v = shooter((0, 0), porte=5)
    W.Weather(W.DUSK).apply_to_unit(v)
    assert v.armes[0].porte == 4                      # jamais sous 4
    m = Unit("Fantassin", 1, 4, 3, 7, (0, 0), armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    W.Weather(W.FOG).apply_to_unit(m)
    assert m.armes[0].porte == 1


@test
def test_brouillard_la_hauteur_ne_fait_plus_voir_plus_loin():
    bf = flat_bf()
    bf.terrain[0][1] = tr.HILL
    a, t = shooter((0, 1)), shooter((9, 1))
    assert tr.range_bonus(bf, a, t) == 1
    bf.weather = W.Weather(W.FOG)
    assert tr.range_bonus(bf, a, t) == 0


@test
def test_vent_porte_dans_son_sens_et_gene_contre():
    bf = flat_bf(sky=W.Weather(W.WIND, wind=1))       # souffle vers l'est
    west, east = shooter((2, 1)), shooter((12, 1))
    assert tr.range_bonus(bf, west, east) == 1        # tir porté par le vent
    assert tr.range_bonus(bf, east, west) == 0
    assert tr.combat_mods(bf, east, west, True)['toucher'] == 1   # contre le vent
    assert tr.combat_mods(bf, west, east, True)['toucher'] == 0
    assert tr.combat_mods(bf, east, west, False)['toucher'] == 0  # mêlée: sans effet


@test
def test_pluie_gene_le_tir_et_le_feu():
    bf = flat_bf(sky=W.Weather(W.RAIN))
    a, t = shooter((2, 1)), shooter((8, 1))
    assert tr.combat_mods(bf, a, t, True)['toucher'] == 1
    assert W.Weather(W.RAIN).ignite_factor() == 0.5
    assert W.Weather(W.RAIN).extra_burn() == 1


@test
def test_vent_pousse_le_feu():
    w = W.Weather(W.WIND, wind=-1)                    # souffle vers l'ouest
    assert w.ignite_factor(-1) > 1 > w.ignite_factor(1)
    assert w.ignite_factor(0) == 1.0


@test
def test_feu_sous_la_pluie_s_eteint_plus_vite():
    def burn_rounds(sky):
        w, h = 8, 3
        grid = [[0] * h for _ in range(w)]
        bf = Battlefield(w, h, 0, "Prairie", grid,
                         {'terrain': tr.make_grid(w, h), 'structures': {(3, 1): st.HOUSE}})
        bf.weather = sky
        st.ignite(bf, 3, 1)
        n = 0
        while bf.fires and n < 20:
            st.fire_step(bf, random.Random(1))
            n += 1
        return n
    assert burn_rounds(W.Weather(W.RAIN)) < burn_rounds(None)


@test
def test_chaleur_double_la_fatigue():
    random.seed(1)
    a1 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 1)])
    a2 = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 1)])
    b = Battle(a1, a2, 40, 30, 8, map_name="Désert", weather=W.HEAT)
    u = b.army1[0]
    assert u.fatigue_rate == 2.0
    u.start_round(); u._melee_this_round = True; u.end_round()
    assert u.fatigue == 2


@test
def test_meteo_du_menu_et_redemarrage():
    random.seed(2)
    a1 = ul.build_army("Armée Skaldienne", [("Arbaletrier régulier", 1)])
    a2 = ul.build_army("Armée Skaldienne", [("Arbaletrier régulier", 1)])
    b = Battle(a1, a2, 40, 30, 8, map_name="Prairie",
               map_options={'relief': "Plat", 'weather': W.FOG})
    assert b.battlefield.weather.name == W.FOG
    assert all(u._max_range == W.FOG_RANGE for u in b.army1 + b.army2)
    # Les armées d'origine ne sont pas touchées (le redémarrage repart d'elles)
    assert a1[0].armes[0].porte == a1[0].armes[0].base_porte


@test
def test_rendu_de_chaque_meteo_et_pause():
    import pygame
    import weather_render as WR
    pygame.init()
    screen = pygame.Surface((320, 200))
    for name in W.WEATHERS:
        fx = WR.WeatherFx(W.Weather(name, 1))
        fx.draw(screen, 320, 200)
        fx.update()
        fx.draw(screen, 320, 200)
    fx = WR.WeatherFx(W.Weather(W.RAIN))
    fx.draw(screen, 320, 200)
    frozen = [list(d) for d in fx._drops]
    fx.update(paused=True)
    assert fx._drops == frozen
    fx.update()
    assert fx._drops != frozen
    assert WR.label(W.Weather(W.WIND, -1)) == "Vent d'est"
    assert WR.label(W.Weather()) is None


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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests météo passent.")
    sys.exit(1 if fails else 0)
