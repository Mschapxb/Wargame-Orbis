import sys
import os
import unittest

# Ajouter src/ au path pour les imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import Arme, SpellFireball, SpellHeal
from unit import Unit
from unit_library import create_unit, build_army, UNIT_DATABASE
from battle import Battle


class TestArme(unittest.TestCase):
    def test_lancer_degats_fixe(self):
        arme = Arme("Epée", nb_attaque=2, toucher=3, blesser=3, perforation=0, degats="1", porte=1)
        self.assertEqual(arme.lancer_degats(), 1)

    def test_lancer_degats_de(self):
        arme = Arme("Arc", nb_attaque=1, toucher=3, blesser=3, perforation=0, degats="1d6", porte=9)
        for _ in range(20):
            self.assertIn(arme.lancer_degats(), range(1, 7))

    def test_lancer_degats_bonus(self):
        arme = Arme("Catapulte", nb_attaque=1, toucher=5, blesser=5, perforation=-3, degats="2+1d4", porte=24)
        for _ in range(20):
            self.assertIn(arme.lancer_degats(), range(3, 7))


class TestSpell(unittest.TestCase):
    def test_cooldown(self):
        spell = SpellFireball(porte=9, toucher=3, blesser=1, perforation=-2, degats="1d4", aoe_size=3, cooldown=2)
        self.assertTrue(spell.is_ready())
        spell.use()
        self.assertFalse(spell.is_ready())
        spell.tick_cooldown()
        self.assertFalse(spell.is_ready())
        spell.tick_cooldown()
        self.assertTrue(spell.is_ready())

    def test_heal_ready(self):
        spell = SpellHeal(porte=6, cooldown=3)
        self.assertTrue(spell.is_ready())


class TestUnit(unittest.TestCase):
    def _make_unit(self, pv=5):
        return Unit("Test", pv=pv, vitesse=3, morale=3, sauvegarde=5, color=(255, 0, 0))

    def test_hp_max_hp_sont_alias(self):
        u = self._make_unit(pv=5)
        self.assertEqual(u.hp, u.pv)
        self.assertEqual(u.max_hp, u.max_pv)

    def test_hp_setter_met_a_jour_pv(self):
        u = self._make_unit(pv=5)
        u.hp = 3
        self.assertEqual(u.pv, 3)

    def test_max_hp_setter_met_a_jour_max_pv(self):
        u = self._make_unit(pv=5)
        u.max_hp = 10
        self.assertEqual(u.max_pv, 10)

    def test_take_damage(self):
        u = self._make_unit(pv=5)
        u.take_damage(2)
        self.assertEqual(u.pv, 3)
        self.assertEqual(u.hp, 3)

    def test_take_damage_mort(self):
        u = self._make_unit(pv=2)
        u.take_damage(5)
        self.assertFalse(u.is_alive)

    def test_morale_check_impossible_si_zero(self):
        u = self._make_unit()
        u.base_morale = 0
        self.assertFalse(u.morale_check())

    def test_get_effective_morale(self):
        u = self._make_unit()
        u.morale_bonus = 1
        u.morale_malus = 2
        self.assertEqual(u.get_effective_morale(), max(0, 3 + 1 - 2))


class TestUnitLibrary(unittest.TestCase):
    def test_create_unit_skaldienne(self):
        faction = UNIT_DATABASE["Armée Skaldienne"]
        u_def = next(u for u in faction["units"] if u["nom"] == "Infanterie régulière")
        u = create_unit(u_def, faction["color"])
        self.assertEqual(u.vitesse, u_def["deplacement"])
        self.assertEqual(u.pv, u_def["blessure"])
        self.assertTrue(len(u.armes) > 0)

    def test_build_army(self):
        army = build_army("Armée Skaldienne", [("Infanterie régulière", 3)])
        self.assertEqual(len(army), 3)
        for u in army:
            self.assertIsInstance(u, Unit)

    def test_unite_avec_sorts(self):
        army = build_army("Armée Skaldienne", [("Mage de guerre", 1)])
        self.assertEqual(len(army), 1)
        self.assertTrue(len(army[0].spells) > 0)


class TestBattle(unittest.TestCase):
    def _make_battle(self):
        a1 = build_army("Armée Skaldienne", [("Infanterie régulière", 2)])
        a2 = build_army("Armée Orlandar", [("Fantassin covaliir", 2)])
        return Battle(a1, a2, battlefield_width=20, battlefield_height=15, map_name="Prairie")

    def test_creation_battle(self):
        b = self._make_battle()
        self.assertEqual(b.round, 1)
        self.assertIsNotNone(b.battlefield)
        self.assertEqual(b.cell_size, 32)

    def test_simulate_round_ne_plante_pas(self):
        b = self._make_battle()
        b.simulate_round()
        self.assertEqual(b.round, 2)

    def test_is_battle_over_debut(self):
        b = self._make_battle()
        self.assertIsNone(b.is_battle_over())

    def test_battle_report_structure(self):
        b = self._make_battle()
        report = b.get_battle_report()
        self.assertIn('winner', report)
        self.assertIn('army1', report)
        self.assertIn('army2', report)
        self.assertIn('rounds', report)


class TestArmyStateGroupes(unittest.TestCase):
    """Composition par groupes dans le menu (logique pure, sans pygame)."""

    def setUp(self):
        from menu import ArmyState
        self.ArmyState = ArmyState

    def test_ajout_dans_le_groupe_actif(self):
        st = self.ArmyState(0)
        st.add_unit("Armée Skaldienne", "Infanterie régulière", 3)
        st.add_group()
        st.add_unit("Armée Skaldienne", "Infanterie régulière", 2)
        self.assertEqual(st.group_size(0), 3)
        self.assertEqual(st.group_size(1), 2)
        self.assertEqual(st.composition[("Armée Skaldienne", "Infanterie régulière")], 5)
        self.assertEqual(st.total_units, 5)

    def test_libelles_uniques_meme_faction(self):
        st = self.ArmyState(0)
        st.add_unit("Armée Skaldienne", "Infanterie régulière", 2)
        st.add_group()
        st.add_unit("Armée Skaldienne", "Hallbardier", 2)
        self.assertNotEqual(st.group_label(0), st.group_label(1))

    def test_build_estampille_les_groupes(self):
        st = self.ArmyState(0)
        st.add_unit("Armée Skaldienne", "Infanterie régulière", 2)
        st.add_group()
        st.add_unit("Armée Skaldienne", "Arbaletrier régulier", 3)
        units = st.build()
        self.assertEqual(len(units), 5)
        self.assertEqual(len({u.contingent for u in units}), 2)

    def test_copie_vers_autre_camp(self):
        # Régression: « Copier » écrivait dans une propriété en lecture seule
        a, b = self.ArmyState(0), self.ArmyState(1)
        a.add_unit("Armée Skaldienne", "Infanterie régulière", 4)
        a.add_group()
        a.add_unit("Armée Skaldienne", "Hallbardier", 1)
        a.bonuses["pv"] = 2
        b.copy_from(a)
        self.assertEqual(b.total_units, 5)
        self.assertEqual(len(b.groups), 2)
        self.assertEqual(b.bonuses["pv"], 2)
        # Copie indépendante: modifier la source ne touche pas la cible
        a.add_unit("Armée Skaldienne", "Hallbardier", 3)
        self.assertEqual(b.total_units, 5)

    def test_suppression_groupe_et_vider(self):
        st = self.ArmyState(0)
        st.add_group()
        st.add_group()
        st.remove_group(2)
        self.assertEqual(len(st.groups), 2)
        self.assertLess(st.active, len(st.groups))
        st.remove_group(0)
        st.remove_group(0)  # le dernier groupe ne se supprime pas
        self.assertEqual(len(st.groups), 1)
        st.add_unit("Armée Skaldienne", "Infanterie régulière", 2)
        st.clear()
        self.assertEqual(st.total_units, 0)
        self.assertEqual(len(st.groups), 1)


class TestReglesDeCombat(unittest.TestCase):
    """Garde-fous sur les règles corrigées lors de la revue."""

    def _battle(self, a1, a2, seed=3):
        import random
        random.seed(seed)
        return Battle(a1, a2, 60, 40, 8, map_name="Prairie")

    def test_deplacement_plafonne_a_1_5_vitesse(self):
        # Une charge ne s'ajoute plus au mouvement du round
        a1 = build_army("Armée Orlandar", [("Cavalier covaliir", 4), ("Fantassin covaliir", 4)])
        a2 = build_army("Armée Orlandar", [("Archer covaliir", 6)])
        b = self._battle(a1, a2)
        for _ in range(12):
            if b.is_battle_over():
                break
            b.simulate_round()
            for u in b.army1 + b.army2:
                if u.is_alive and u.vitesse > 0:
                    self.assertLessEqual(u._cells_moved, int(u.vitesse * 1.5))

    def test_pression_lue_avant_d_etre_vieillie(self):
        # Les compteurs de pression doivent survivre jusqu'à la phase de moral
        u = Unit("T", pv=5, vitesse=3, morale=2, sauvegarde=5, color=(1, 1, 1))
        u._under_fire = 6
        u._witnessed_deaths = 2
        u.start_round()
        self.assertEqual(u._under_fire, 6)
        self.assertEqual(u._witnessed_deaths, 2)
        u.end_round()
        self.assertLess(u._under_fire, 6)

    def test_deploiement_dans_la_carte(self):
        a1 = build_army("Armée Skaldienne", [("Infanterie régulière", 40)])
        a2 = build_army("Armée Skaldienne", [("Infanterie régulière", 40)])
        b = self._battle(a1, a2)
        positions = [u.position for u in b.army1 + b.army2]
        self.assertEqual(len(positions), len(set(positions)))
        for x, y in positions:
            self.assertTrue(0 <= y < b.battlefield.height)

    def test_decor_hors_donnees_de_siege(self):
        # Régression: le décor dans siege_data faisait croire à un siège
        b = self._battle(build_army("Armée Skaldienne", [("Infanterie régulière", 2)]),
                         build_army("Armée Skaldienne", [("Infanterie régulière", 2)]))
        self.assertFalse(b.battlefield.siege_data)
        self.assertTrue(b.battlefield.decor)


class TestEffetsDeCombat(unittest.TestCase):
    """Données d'effets produites par le moteur (sans pygame)."""

    def _battle(self, a1, a2, seed=5):
        import random
        random.seed(seed)
        return Battle(a1, a2, 50, 30, 8, map_name="Prairie")

    def test_position_de_depart_suit_le_round(self):
        # Régression: une unité arrêtée rejouait son ancien déplacement
        a1 = build_army("Armée Skaldienne", [("Infanterie régulière", 2)])
        a2 = build_army("Armée Skaldienne", [("Infanterie régulière", 2)])
        b = self._battle(a1, a2)
        u = b.army1[0]
        u.position = (5, 5)
        u._prev_position = (2, 5)   # déplacement d'un round précédent
        u.start_round()
        self.assertEqual(u._prev_position, (5, 5))
        self.assertEqual(u._last_step, (3, 0))

    def test_mort_produit_une_animation(self):
        a1 = build_army("Armée Skaldienne", [("Infanterie régulière", 8), ("Arbaletrier régulier", 4)])
        a2 = build_army("Armée Skaldienne", [("Infanterie régulière", 3)])
        b = self._battle(a1, a2)
        for _ in range(30):
            if b.is_battle_over():
                break
            b.simulate_round()
        deaths = b.visual_effects.get('deaths', [])
        self.assertTrue(deaths, "aucune animation de mort générée")
        d = deaths[0]
        self.assertEqual(len(d.to_pos), 2)
        self.assertGreaterEqual(d.delay, 0)

    def test_types_de_projectiles(self):
        a1 = build_army("Armée Skaldienne", [("Arbaletrier régulier", 4), ("Baliste", 1)])
        a1 += build_army("Engins de siège", [("Artilleur", 2)])   # ses servants
        a2 = build_army("Armée Skaldienne", [("Infanterie régulière", 6)])
        b = self._battle(a1, a2)
        kinds = set()
        for _ in range(12):
            if b.is_battle_over():
                break
            b.simulate_round()
            kinds |= {p.projectile_type for p in b.visual_effects['projectiles']}
        self.assertIn("bolt", kinds)
        self.assertIn("ballista", kinds)

    def test_trajectoire_en_cloche(self):
        from effects import Projectile
        p = Projectile((0, 0), (300, 0), (0, 0, 0), 34, "arrow", 28, delay=0)
        p.age = int(34 * 0.7 / 2)             # mi-course
        x, y = p.get_current_pos()
        self.assertLess(y, -10)                # le trait monte au-dessus de la ligne
        p.age = int(34 * 0.7 * 0.9)            # fin de course: il redescend
        import math
        self.assertGreater(math.sin(p.get_heading()), 0)


class TestCartes(unittest.TestCase):
    """Terrains centraux (forêt, village) et déploiement sur grande carte."""

    def test_passage_garanti_entre_les_camps(self):
        import random
        from maps import generate_map, _connected
        for m in ("Forêt", "Village"):
            for seed in range(8):
                random.seed(seed)
                g, d = generate_map(m, 178, 64)
                gap = d['deploy_gap']
                left, right = (89 - gap, 32), (89 + gap, 32)
                self.assertTrue(_connected(g, 178, 64, left, right), f"{m} graine {seed}")

    def test_ecart_de_deploiement_ne_passe_pas_pour_un_siege(self):
        import random
        random.seed(1)
        b = Battle(build_army("Armée Skaldienne", [("Infanterie régulière", 4)]),
                   build_army("Armée Skaldienne", [("Infanterie régulière", 4)]),
                   178, 64, 8, map_name="Village")
        self.assertFalse(b.battlefield.siege_data)
        self.assertTrue(b.battlefield.deploy_gap)

    def test_armees_centrees_et_hors_du_terrain_central(self):
        import random
        for m in ("Forêt", "Village", "Prairie"):
            random.seed(4)
            b = Battle(build_army("Armée Skaldienne", [("Infanterie régulière", 12), ("Arbaletrier régulier", 6)]),
                       build_army("Armée Orlandar", [("Fantassin covaliir", 12), ("Archer covaliir", 6)]),
                       178, 64, 8, map_name=m)
            for army in (b.army1, b.army2):
                ys = [u.position[1] for u in army]
                self.assertLess(abs((min(ys) + max(ys)) / 2 - 32), 8, m)
            front1 = max(u.position[0] for u in b.army1)
            front2 = min(u.position[0] for u in b.army2)
            self.assertGreaterEqual(front2 - front1, 36, m)   # un peu de marche avant le choc

    def test_village_maisons_rectangulaires_et_haie(self):
        import random
        from maps import generate_village
        random.seed(2)
        g, d = generate_village(178, 64)
        cells = sum(sum(col) for col in g)
        self.assertGreater(cells, 250)


if __name__ == '__main__':
    unittest.main()
