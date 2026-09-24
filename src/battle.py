import combat
import copy
import deployment
import weather as weather_mod
import unit as unit_mod
import facing
import math
import random

import rng_scope

import siege_engines
import spatial
import structures as st
import tactics
import terrain as tr

from battlefield import Battlefield
from unit import reassign_uid
from effects import (FloatingText, AttackLine, Projectile,
                     AoeExplosion, HealBeam, ArmorShimmer, WallEffect,
                     ImpactBurst, ShockWave, SlashEffect, ThrustEffect,
                     DeathAnimation, FX_CLOCK)
from ai_commander import CommanderAI

# RNG dédiée aux effets visuels (délais de volée, dispersion...)
# — flux séparé pour ne JAMAIS influencer les dés de la simulation
_FX_RNG = random.Random(20260610)

# Plafond de la file d'effets visuels (sécurité hors rendu — voir fin de round)
_FX_MAX_QUEUE = 600


# Couleur du trait d'attaque selon la nature du coup: l'oeil distingue
# instantanement un echange ordinaire d'une reaction ou d'un enchainement.
_KIND_COLORS = {
    'normal': (255, 100, 100),
    'charge': (255, 200, 50),
    'opportunity': (255, 240, 150),
    'momentum': (255, 140, 255),
    'reaction': (120, 210, 255),
}

# Decoupage temporel d'un round (fractions): mouvement, puis choc des
# charges, puis l'echange general. Les fenetres se CHEVAUCHENT - c'est ce
# chevauchement qui donne l'impression de temps reel.
T_MOVE_START, T_MOVE_END = 0.02, 0.46

# Teinte des lames selon la nature du coup (arc de taille / estoc)
_BLADE_COLORS = {
    'normal': (255, 240, 225),
    'charge': (255, 215, 110),
    'opportunity': (255, 250, 170),
    'momentum': (255, 160, 255),
    'reaction': (170, 225, 255),
}
T_CHARGE = 0.26

# ─── Fortification (niveaux 2-3, cf. maps/fortification.py) ───
# Baliste de tour: l'arme de la bibliothèque, mais immobile (vitesse 0: elle
# ne descend pas de sa plateforme), fragile (2 PV: on l'abat en quelques
# volées) et lente à repointer depuis sa plateforme (2 rounds). Mesuré:
# la baliste de bibliothèque (4 PV, recharge 1) faisait tomber l'assaillant
# du Siège de 22 % à 0 %; ce réglage le laisse à ~8 %.
TOWER_BALLISTA = {
    "nom": "Baliste de tour",
    "deplacement": 0,
    "blessure": 2,
    "bravoure": 3,
    "sauvegarde": 7,
    "role": "back",
    "size": 2,
    "unit_type": "Artillerie",
    "armes": [("Carreaux de baliste", 18, 1, 4, 2, -2, "1d4")],
    "traits": ["Rechargement (2)"],
}
# Porte piégée: huile bouillante et pierres sur qui se presse au pied du
# battant qui cède (distance ≤ TRAP_REACH), puis flaque en feu quelques rounds
TRAP_REACH = 2
TRAP_PERFORATION = -1
TRAP_DAMAGE = "1d2"
TRAP_BURN = 2
T_ACTION_START, T_ACTION_END = 0.34, 0.96


class Battle(spatial.Neighbourhood):
    def __init__(self, army1, army2, battlefield_width=40, battlefield_height=30, 
                 obstacle_count=8, map_name="Prairie", map_options=None, weather=None):
        self.army1 = copy.deepcopy(army1)
        self.army2 = copy.deepcopy(army2)
        # Des uids frais après le deepcopy: `Battle(a, a, …)` copierait sinon
        # les mêmes uids des deux côtés (voir reassign_uid). army1 garde des
        # uids plus petits que army2, donc l'ordre relatif ne change pas.
        for u in self.army1:
            reassign_uid(u)
        for u in self.army2:
            reassign_uid(u)
        self.map_name = map_name
        # Thème demandé (biome, relief), rejoué tel quel par un redémarrage
        self.map_options = map_options
        
        self.round = 1
        self.visual_effects = {'projectiles': [], 'attack_lines': [], 'target_indicators': []}
        
        self.army1_initial_size = len(self.army1)
        self.army2_initial_size = len(self.army2)
        
        self.army1_roster = list(self.army1)
        self.army2_roster = list(self.army2)
        
        self.army1_fled = []
        self.army2_fled = []
        
        self._alive_cache = {'army1': [], 'army2': [], 'dirty': True}
        self._army1_ids = self._army2_ids = None
        # Distance au plus proche ennemi, calculée une fois par passe de
        # planification (cf. _plan_moves) — None hors de cette fenêtre.
        self._near_enemy_cache = None

        self._restart_army1 = copy.deepcopy(self.army1)
        self._restart_army2 = copy.deepcopy(self.army2)

        # Graine de carte (écran « Champ de bataille »): la carte, la météo
        # tirée au sort et le déploiement sont ceux de l'aperçu, et R rejoue
        # la même carte. Ils tirent leur hasard d'un générateur à part: le
        # random global de la bataille n'est ni lu ni réinitialisé.
        map_seed = (map_options or {}).get('seed')
        gen_rng = random.Random(map_seed) if map_seed is not None else random
        with rng_scope.using(gen_rng):
            self._build_field(battlefield_width, battlefield_height, obstacle_count,
                              map_name, map_options, weather)
        if self.battlefield.is_siege:
            for u in self.army1:
                u.refill_ammo(unit_mod.SIEGE_TRAIN_FACTOR)
        for u in self.army1 + self.army2:
            self.battlefield.weather.apply_to_unit(u)
        # Chaque armée regarde l'autre au déploiement
        for u in self.army1:
            u.facing = (1.0, 0.0)
        for u in self.army2:
            u.facing = (-1.0, 0.0)
        
        # Commandants IA
        self.commander1 = CommanderAI(self.army1, self.army2, self.battlefield, is_army1=True)
        self.commander2 = CommanderAI(self.army2, self.army1, self.battlefield, is_army1=False)
        
        # Taille de cellule en pixels (définie par le renderer avant le premier round)
        self.cell_size = 32

        # Duree d'un round en frames d'affichage (le renderer la synchronise
        # avec la vitesse de simulation). Sert a repartir les actions dans
        # le temps: sans elle, tout se produirait au meme instant.
        self.fx_frames_per_round = 48
        # Fil d'evenements notables du round (reactions, ruptures, exploits)
        self.round_events = []
        # Cache du rapport de forces (une evaluation par round suffit)
        self._force_cache = (0.0, 0.0)
        self._force_cache_round = -1
        # Destruction → rendu, horodatés dans le round comme les autres effets:
        # repeints de cases [(délai, {cases})], instant d'apparition des
        # flammes {case: délai}, cratères permanents [(délai, x, y, rayon)].
        # Le renderer les consomme; simulate_round les remet à zéro.
        self.pending_repaints = []
        self.fire_reveal = {}
        self.pending_craters = []

        # Initialiser les positions d'animation (pas de transition au premier frame)
        for u in self.army1 + self.army2:
            u._prev_position = u.position

    # ─── Rythme du round: chaque action est estampillée dans le temps ───

    def _build_field(self, battlefield_width, battlefield_height, obstacle_count,
                     map_name, map_options, weather):
        """Carte, météo et déploiement: tout le hasard passe par rng_scope.RNG."""
        # Générer la map
        from maps import generate_map
        grid, map_data = generate_map(map_name, battlefield_width, battlefield_height,
                                      map_options)
        self.battlefield = Battlefield(battlefield_width, battlefield_height, 
                                        obstacle_count, map_name, grid, map_data)
        # Météo: argument explicite, sinon choix du menu (map_options)
        if weather is None and map_options:
            weather = map_options.get('weather')
        theme = getattr(self.battlefield, 'theme', None) or {}
        self.battlefield.weather = weather_mod.resolve(
            weather, theme.get('biome', "Prairie"), rng=rng_scope.RNG,
            siege=self.battlefield.is_siege)
        self._place_armies(self.battlefield.height // 2)

    def _set_action_time(self, t01):
        """Positionne l'horloge d'effets: t01 ∈ [0,1] = instant de l'action
        dans le round. Tous les effets créés ensuite (textes, traits, tirs,
        impacts) hériteront de cette estampille → le round se joue comme un
        échange continu au lieu d'un flash simultané."""
        FX_CLOCK.at(max(0.0, min(1.05, t01)) * self.fx_frames_per_round)

    def _apply_combat_events(self, events, base_delay=None):
        """Convertit les événements grid-coords produits par unit.py en
        effets visuels pixels, à l'instant prévu par l'horloge d'action."""
        if not events:
            return
        cs = self.cell_size
        base = FX_CLOCK.current_delay if base_delay is None else int(base_delay)

        def to_px(gpos):
            return (gpos[0] * cs + cs // 2, gpos[1] * cs + cs // 2)

        strikes = {}  # coups successifs sur la même cible: décalés et alternés
        for evt in events:
            t = evt['type']
            d = base + int(evt.get('at', 0))
            kind = evt.get('kind', 'normal')

            if t == 'arrow':
                proj = evt.get('proj', 'arrow')
                dur = {"arrow": 34, "bolt": 26, "ballista": 30}.get(proj, 34)
                # Petite dispersion: les volées partent en cascade
                self.visual_effects['projectiles'].append(
                    Projectile(to_px(evt['from_grid']), to_px(evt['to_grid']),
                               (200, 180, 100), dur, proj, cs,
                               delay=d + _FX_RNG.randint(0, 6)))
            elif t in ('reach', 'melee'):
                fp = to_px(evt['from_grid'])
                tp = to_px(evt['to_grid'])
                key = (evt['from_grid'], evt['to_grid'])
                n = strikes.get(key, 0)
                strikes[key] = n + 1
                dd = d + n * 5
                col = _BLADE_COLORS.get(kind, _BLADE_COLORS['normal'])
                if t == 'reach':
                    self.visual_effects.setdefault('thrusts', []).append(
                        ThrustEffect(fp, tp, col, 12, delay=dd))
                else:
                    ang = math.atan2(tp[1] - fp[1], tp[0] - fp[0])
                    cx = fp[0] + (tp[0] - fp[0]) * 0.72
                    cy = fp[1] + (tp[1] - fp[1]) * 0.72
                    scale = 1.25 if kind in ('charge', 'momentum') else 1.0
                    self.visual_effects.setdefault('slashes', []).append(
                        SlashEffect((cx, cy), ang, col, mirror=bool(n % 2),
                                    scale=scale, duration=14, delay=dd))
            elif t == 'impact':
                px = to_px(evt['at_grid'])
                fx_from = to_px(evt.get('from_grid', evt['at_grid']))
                ang = math.atan2(px[1] - fx_from[1], px[0] - fx_from[0])
                col = (255, 200, 120) if evt.get('ranged') else (255, 120, 70)
                fxk = evt.get('fx') or ('ranged' if evt.get('ranged') else 'melee')
                self.visual_effects.setdefault('impacts', []).append(
                    ImpactBurst(px, col, evt.get('power', 1.0), ang, 18, delay=d, kind=fxk))
            elif t == 'shockwave':
                px = to_px(evt['at_grid'])
                self.visual_effects.setdefault('shockwaves', []).append(
                    ShockWave(px, cs * (1 + int(evt.get('unit_size', 1))),
                              (255, 190, 120), 26, delay=d))
            elif t == 'fireball':
                fp = to_px(evt['from_grid'])
                tp = to_px(evt['to_grid'])
                self.visual_effects['projectiles'].append(
                    Projectile(fp, tp, (255, 100, 0), 32, "fireball", cs, delay=d))
                aoe_r = (evt['aoe_size'] // 2) * cs + cs // 2
                self.visual_effects.setdefault('aoe_explosions', []).append(
                    AoeExplosion(tp, aoe_r, (255, 120, 0), 35, delay=d + 22))
            elif t == 'heal':
                self.visual_effects.setdefault('heal_beams', []).append(
                    HealBeam(to_px(evt['from_grid']), to_px(evt['to_grid']), 30, delay=d))
            elif t == 'armor':
                px = to_px(evt['at_grid'])
                ur = max(3, cs // 2 - 4) * max(1, evt['unit_size'])
                self.visual_effects.setdefault('armor_shimmers', []).append(
                    ArmorShimmer(px, ur, 40, delay=d))
            elif t == 'magic_projectile':
                sp = to_px(evt['from_grid'])
                ep = to_px(evt['to_grid'])
                for i in range(3):
                    off = (_FX_RNG.randint(-8, 8), _FX_RNG.randint(-8, 8))
                    ep_off = (ep[0] + off[0], ep[1] + off[1])
                    self.visual_effects['projectiles'].append(
                        Projectile(sp, ep_off, (180, 80, 255), 24, "magic", cs,
                                   delay=d + i * 3))
            elif t == 'wall':
                self.visual_effects.setdefault('wall_effects', []).append(
                    WallEffect(evt['positions'], cs, 25, delay=d))
            elif t == 'crater':
                px = to_px(evt['at_grid'])
                self.pending_craters.append((d, px[0], px[1], evt['radius_cells'] * cs))

    def log_event(self, text, color=(230, 220, 180), importance=1):
        """Fil d'événements du round (le HUD y puise ses bandeaux)."""
        self.round_events.append((text, color, importance))

    def _place_armies(self, center_y):
        bf = self.battlefield
        # Fortification: les balistes de tour sont posées AVANT la garnison
        # (qui prendrait sinon leurs cases de rempart) et rejoignent l'armée
        # défenseure; elles ne font pas partie des armées rejouées par R.
        crews = []
        for t in bf.towers:
            ballista = self._man_tower(t)
            if ballista is not None:
                crews.append(ballista)
                crews.extend(self._tower_servants(ballista))
        deployment.deploy_armies(bf, self.army1, self.army2, center_y)
        self.army2.extend(crews)
        self.army2_roster.extend(crews)
        self.army2_initial_size += len(crews)
        self._refresh_army_sets()
        if bf.is_siege:
            deployment.push_machines_forward(bf, self.army1)   # machines devant les troupes
            for u in self.army2:
                u.garrison = True
        siege_engines.gather_attendants(self)     # servants au contact de leur machine
        factor = bf.siege_data.get('garrison_ammo', 1)
        if factor > 1:
            for u in self.army2:
                u.refill_ammo(factor)
        self._alive_cache['dirty'] = True

    def _man_tower(self, tower):
        """Baliste de garnison immobile sur la plateforme d'une tour."""
        import unit_library
        crew = unit_library.create_unit(TOWER_BALLISTA, self._garrison_color())
        crew.token_name = "Baliste"
        crew.contingent = "Garnison"
        crew.position = tower['anchor']
        if not self.battlefield.can_place_unit(*crew.position, crew):
            return None
        self.battlefield.place_unit(crew)
        return crew

    def _tower_servants(self, ballista):
        """Les deux artilleurs de la baliste de tour, sur le chemin de ronde
        au contact de la plateforme. Les tuer réduit la baliste au silence."""
        import unit_library
        bf = self.battlefield
        ax, ay = ballista.position
        # Au-dessus puis au-dessous de la plateforme, sur le chemin de ronde
        spots = [(x, y) for y in (ay - 1, ay + 2) for x in (ax, ax + 1)
                 if bf.is_rampart(x, y) and (x, y) not in bf.units]
        out = []
        for pos in spots[:siege_engines.CREW_NEEDED]:
            crew = unit_library.make_unit("Engins de siège", "Artilleur")
            crew.color = self._garrison_color()
            crew.contingent = "Garnison"
            crew.name = f"Servant{len(out) + 1}"
            crew.position = pos
            bf.place_unit(crew)
            crew._attends = ballista
            out.append(crew)
        return out

    def _garrison_color(self):
        return self.army2[0].color if self.army2 else (160, 160, 170)

    def get_all_alive(self):
        if self._alive_cache['dirty']:
            self._alive_cache['army1'] = [u for u in self.army1 if u.is_alive]
            self._alive_cache['army2'] = [u for u in self.army2 if u.is_alive]
            self._alive_cache['all'] = self._alive_cache['army1'] + self._alive_cache['army2']
            self._alive_cache['dirty'] = False
        return self._alive_cache['all']

    def _refresh_army_sets(self):
        """Met à jour les sets d'appartenance pour O(1) lookup.

        Les tailles servent de garde-fou: un mort retiré d'une liste en
        cours de round (fuyard sorti de la carte) laisserait sinon des sets
        périmés, et l'index spatial rangerait cette unité du mauvais côté."""
        if (self._army1_ids is None or self._alive_cache['dirty']
                or len(self._army1_ids) != len(self.army1)
                or len(self._army2_ids) != len(self.army2)):
            self._army1_ids = {id(u) for u in self.army1}
            self._army2_ids = {id(u) for u in self.army2}

    def get_enemies(self, unit):
        self._refresh_army_sets()
        return self.army2 if id(unit) in self._army1_ids else self.army1

    def get_allies(self, unit):
        self._refresh_army_sets()
        return self.army1 if id(unit) in self._army1_ids else self.army2

    def get_closest_enemy(self, unit):
        enemies = self.get_enemies(unit)
        alive_enemies = [e for e in enemies if e.is_alive]
        if not alive_enemies:
            return None
        ux, uy = unit.position
        return min(alive_enemies, key=lambda e: abs(e.position[0] - ux) + abs(e.position[1] - uy))

    def get_units_in_radius(self, center_pos, radius, unit_list):
        result = []
        for unit in unit_list:
            if unit.is_alive and self.battlefield.manhattan_distance(center_pos, unit.position) <= radius:
                result.append(unit)
        return result

    # ═══════════════════════════════════════════════════════════════
    #   VOISINAGE — répondre « qui est près d'ici » sans tout balayer
    #   (l'essentiel est dans spatial.Neighbourhood)
    # ═══════════════════════════════════════════════════════════════

    def army_ids(self, units):
        """Les sets des deux armées sont déjà tenus à jour: on les rend tels
        quels plutôt que d'en reconstruire un à chaque requête."""
        self._refresh_army_sets()
        if units is self.army1:
            return self._army1_ids
        if units is self.army2:
            return self._army2_ids
        return {id(u) for u in units}

    def _get_initial_size(self, unit):
        """Retourne la taille initiale de l'armée de cette unité."""
        if unit in self.army1:
            return self.army1_initial_size
        return self.army2_initial_size

    # ═══════════════════════════════════════════════════════════════
    #   TENUE AU FEU — qui rompt, et qui se reprend
    # ═══════════════════════════════════════════════════════════════

    def _side_values(self):
        """Valeur restante de chaque camp, calculée UNE fois par round."""
        if self._force_cache_round != self.round:
            v1 = sum(tactics.remaining_value(u) for u in self.army1
                     if u.is_alive and not u.fleeing)
            v2 = sum(tactics.remaining_value(u) for u in self.army2
                     if u.is_alive and not u.fleeing)
            self._force_cache = (v1, v2)
            self._force_cache_round = self.round
        return self._force_cache

    def _force_ratio(self, unit):
        """Rapport de forces vu par cette unité (>1 = son camp domine)."""
        v1, v2 = self._side_values()
        self._refresh_army_sets()
        mine, theirs = (v1, v2) if id(unit) in self._army1_ids else (v2, v1)
        if theirs <= 0.01:
            return 99.0
        return mine / max(0.01, theirs)

    def _resolve_bonus(self, unit):
        """Ascendant moral: une troupe qui domine ne tourne pas les talons.

        C'est ce qui manquait le plus: avec une bravoure de base de 1, le
        moindre échec de test faisait rompre une armée pourtant deux fois
        supérieure en nombre. On tient compte du rapport de forces et de
        l'expérience acquise dans le round (une unité qui vient d'abattre
        un adversaire est galvanisée, pas terrorisée).
        """
        r = self._force_ratio(unit)
        bonus = 0
        if r >= 1.6:
            bonus += 2
        elif r >= 1.15:
            bonus += 1
        if getattr(unit, '_kills', 0) >= 2:
            bonus += 1
        return bonus

    def _can_rout(self, unit):
        """Une unité rompt-elle VRAIMENT, ou se contente-t-elle d'être
        ébranlée ?

        Se faire canarder de loin alors qu'on est en surnombre n'a jamais
        fait fuir une troupe: elle serre les dents et marche au canon. On
        exige donc un danger immédiat (l'ennemi au contact) ou une
        infériorité réelle. Sinon l'unité reste, secouée mais au combat.
        """
        enemies = [e for e in self.get_enemies(unit) if e.is_alive]
        if not enemies:
            return False
        ux, uy = unit.position
        d_min = min(abs(ux - e.position[0]) + abs(uy - e.position[1]) for e in enemies)
        if d_min <= 2:
            return True                       # acculée: la panique est permise
        if unit.hp <= max(1, unit.max_hp // 3) and self._force_ratio(unit) < 1.2:
            return True                       # exsangue et sans ascendant
        if getattr(unit, '_under_fire', 0) >= 3 and unit.hp < unit.max_hp:
            return True                       # clouée sous un feu nourri
        if (getattr(unit, '_witnessed_deaths', 0) >= 2
                and (unit.hp < unit.max_hp or d_min <= 6)):
            return True                       # la ligne se vide autour d'elle
        return self._force_ratio(unit) < 0.85

    def _break_unit(self, unit, label, color=(255, 50, 50)):
        """Applique (ou refuse) la rupture d'une unité au moral épuisé."""
        if self._can_rout(unit):
            unit.fleeing = True
            unit.status_text = "FUITE!"
            unit.floating_texts.append(FloatingText(label, color, 100))
            return True
        # Moral à zéro mais rien qui justifie de rompre: on tient le terrain
        unit.afraid = True
        unit.status_text = "ÉBRANLÉ"
        unit.floating_texts.append(FloatingText("Tient bon!", (255, 190, 90), 70))
        return False

    def _rally_phase(self):
        """Ralliement: une troupe qui a décroché peut se reprendre.

        Sans cela, la moindre panique était définitive et les batailles se
        terminaient par une évaporation générale. On ne se rallie pas sous
        le fer: il faut du champ, et de préférence un officier.
        """
        for unit in list(self.army1) + list(self.army2):
            if not unit.is_alive or not unit.fleeing or unit.fled:
                continue
            if getattr(unit, '_flee_rounds', 0) < 1:
                continue
            ux, uy = unit.position
            enemies = [e for e in self.get_enemies(unit) if e.is_alive]
            if not enemies:
                continue
            if min(abs(ux - e.position[0]) + abs(uy - e.position[1]) for e in enemies) <= 3:
                continue  # on ne se rallie pas le fer dans les reins

            bonus = self._resolve_bonus(unit)
            for a in self.get_allies(unit):
                if (a.is_alive and not a.fleeing and a.encouragement_range > 0
                        and self.battlefield.manhattan_distance(unit.position, a.position)
                        <= max(6, a.encouragement_range)):
                    bonus += 2      # la voix du chef porte
                    break

            seuil = max(1, unit.base_morale + bonus)
            if random.randint(1, 6) <= seuil:
                unit.fleeing = False
                unit.afraid = True
                unit.morale_malus = max(0, unit.morale_malus - 1)
                unit._flee_rounds = 0
                unit.status_text = "RALLIÉ"
                unit.floating_texts.append(FloatingText("RALLIÉ!", (120, 255, 160), 90))
                self.log_event(f"{unit.name} se rallie !", (120, 255, 160), 2)

    def _steady_nerves(self):
        """Récupération: loin du danger et sans pertes, les nerfs se
        remettent. Un malus de moral n'est plus une condamnation."""
        for unit in self.get_all_alive():
            if unit.fleeing or unit.morale_malus <= 0:
                continue
            if unit._damage_taken_round > 0 or getattr(unit, '_damage_prev_round', 0) > 0:
                unit._calm_rounds = 0
                continue
            ux, uy = unit.position
            enemies = [e for e in self.get_enemies(unit) if e.is_alive]
            if enemies and min(abs(ux - e.position[0]) + abs(uy - e.position[1])
                               for e in enemies) <= 4:
                unit._calm_rounds = 0
                continue
            unit._calm_rounds = getattr(unit, '_calm_rounds', 0) + 1
            if unit._calm_rounds >= 2:
                unit._calm_rounds = 0
                unit.morale_malus -= 1
                unit.floating_texts.append(
                    FloatingText("+1 Moral", (150, 220, 255), 60))

    def morale_phase(self):
        """Phase de moral complète.
        
        1) Pertes lourdes: si une armée a perdu >= 50% de son effectif INITIAL,
           toutes les unités vivantes font un test de moral.
           Échec = -1 moral. Si moral tombe à 0 = fuite.
           
        2) Test de moral individuel quand un allié adjacent meurt
           (géré au moment de la mort dans take_damage, pas ici)
        
        3) Auras de peur (des unités avec fear_aura > 0)
        """
        # --- 0) Encouragement: officiers vivants donnent +1 moral à toute l'armée ---
        for unit in self.get_all_alive():
            unit.morale_bonus = 0  # Reset chaque round
        
        for unit in self.get_all_alive():
            if unit.encouragement_range > 0 and unit.is_alive and not unit.fleeing:
                allies = self.get_allies(unit)
                for ally in allies:
                    if ally == unit or not ally.is_alive:
                        continue
                    ally.morale_bonus = max(ally.morale_bonus, 1)  # +1, non cumulable
        
        # --- 0a) Ascendant: le rapport de forces pèse sur les nerfs ---
        for unit in self.get_all_alive():
            unit.morale_bonus += self._resolve_bonus(unit)

        # --- 0b) Siège: défenseurs derrière le mur intact → +1 bravoure ---
        if self.battlefield.is_siege:
            wall_x = self.battlefield.wall_x
            has_intact_gates = (any(hp > 0 for hp in self.battlefield.active_gates.values())
                                and not self.battlefield.gates_open)
            if has_intact_gates:
                for unit in self.army2:
                    if unit.is_alive and not unit.fleeing and unit.position[0] >= wall_x:
                        unit.morale_bonus += 1
        
        # --- 1) Pertes lourdes (seuil 50% de l'effectif initial) ---
        for army, initial_size in [(self.army1, self.army1_initial_size),
                                    (self.army2, self.army2_initial_size)]:
            alive_count = sum(1 for u in army if u.is_alive)
            
            if initial_size > 0 and alive_count <= initial_size // 2:
                for unit in army:
                    if not unit.is_alive or unit.fleeing:
                        continue
                    if hasattr(unit, '_half_army_malus_applied') and unit._half_army_malus_applied:
                        continue
                    
                    # Test de moral : lancer 1d6, réussir si <= bravoure effective
                    unit._half_army_malus_applied = True
                    if not unit.morale_check():
                        unit.morale_malus = min(unit.base_morale + 2, unit.morale_malus + 1)
                        unit.floating_texts.append(
                            FloatingText("-1 Moral (Pertes!)", (255, 100, 60), 90))

                        if unit.get_effective_morale() <= 0:
                            self._break_unit(unit, "FUITE!")
                        else:
                            unit.afraid = True
                            unit.status_text = "PEUR"
            
            # Pertes critiques (75%): deuxième malus
            if initial_size > 0 and alive_count <= initial_size // 4:
                for unit in army:
                    if not unit.is_alive or unit.fleeing:
                        continue
                    if hasattr(unit, '_critical_malus_applied') and unit._critical_malus_applied:
                        continue
                    
                    unit._critical_malus_applied = True
                    if not unit.morale_check():
                        unit.morale_malus = min(unit.base_morale + 2, unit.morale_malus + 1)
                        unit.floating_texts.append(
                            FloatingText("-1 Moral (Déroute!)", (255, 50, 50), 90))

                        if unit.get_effective_morale() <= 0:
                            # Pertes critiques: à ce stade l'armée est
                            # brisée, il n'y a plus d'ascendant qui tienne.
                            # C'est le seul cas où l'on rompt sans avoir
                            # l'ennemi sur le dos.
                            unit.fleeing = True
                            unit.status_text = "DÉROUTE"
                            unit.floating_texts.append(
                                FloatingText("DÉROUTE!", (255, 30, 30), 100))
                        else:
                            unit.afraid = True
        
        # --- 2) Auras de peur (portée 4 cases, ennemis uniquement) ---
        FEAR_RANGE = 4
        for unit in self.get_all_alive():
            if unit.fleeing:
                continue
            if unit.status_text in ["DOWN", "REVIVED"]:
                continue
            
            under_fear = False
            max_aura = 0
            min_dist = 99
            for enemy in self.get_enemies(unit):
                if not enemy.is_alive or enemy.fear_aura == 0:
                    continue
                dist = self.battlefield.manhattan_distance(unit.position, enemy.position)
                if dist <= FEAR_RANGE:
                    if enemy.fear_aura > max_aura or (enemy.fear_aura == max_aura and dist < min_dist):
                        max_aura = enemy.fear_aura
                        min_dist = dist
                    under_fear = True
            
            if under_fear:
                if unit.apply_fear_effect(max_aura, min_dist) == "flee":
                    # La terreur a fait tomber le moral à zéro: reste à
                    # savoir si la troupe a une raison de rompre.
                    unit.fleeing = False
                    self._break_unit(unit, "TERREUR!", (255, 60, 120))
            else:
                if unit.afraid and not unit.fleeing:
                    unit.afraid = False
                    unit.status_text = ""
        
        # --- 2b) Choc et feu nourri: encaisser pèse sur les nerfs ---
        # Un coup qui emporte le tiers des PV ou une volée bien ajustée
        # ébranlent une troupe: elle ne se bat plus aussi bien au round
        # suivant. C'est ce qui donne du poids aux salves et aux gros coups.
        for unit in self.get_all_alive():
            if unit.fleeing or unit.afraid or not unit.is_alive:
                continue
            pressure = unit._shock + (1 if getattr(unit, '_under_fire', 0) >= 3 else 0)
            if pressure >= 2 and not unit.morale_check():
                unit.afraid = True
                unit.status_text = "ÉBRANLÉ"
                unit.floating_texts.append(
                    FloatingText("Ébranlé!", (255, 150, 60), 60))

        # --- 2b bis) Camarades tombés au coude à coude ---
        # Une volée qui fauche le voisin fait plus pour briser une ligne
        # que dix salves tombées dans le vide.
        for unit in self.get_all_alive():
            if unit.fleeing or not unit.is_alive:
                continue
            if getattr(unit, '_witnessed_deaths', 0) <= 0:
                continue
            if not unit.morale_check():
                unit.morale_malus = min(unit.base_morale + 2, unit.morale_malus + 1)
                unit.floating_texts.append(
                    FloatingText("-1 Moral (Camarade!)", (255, 120, 80), 80))
                if unit.get_effective_morale() <= 0:
                    self._break_unit(unit, "FUITE!")
            unit._witnessed_deaths = 0   # testé: on ne le rejoue pas

        # --- 2c) Ralliement et retour au calme ---
        self._rally_phase()
        self._steady_nerves()

        # --- 3) Test de moral au combat (chaque round en mêlée) ---
        for unit in self.get_all_alive():
            if unit.fleeing or unit.afraid or not unit.is_alive:
                continue
            
            # Si au contact d'un ennemi et que l'unité a déjà subi des dégâts
            if unit.hp < unit.max_hp:
                closest = self.get_closest_enemy(unit)
                if closest:
                    dist = self.battlefield.manhattan_distance(unit.position, closest.position)
                    if dist <= 1:  # Au corps à corps
                        # Test seulement si PV < 50% 
                        if unit.hp <= unit.max_hp // 2:
                            if not unit.morale_check():
                                unit.afraid = True
                                unit.status_text = "PEUR"
                                unit.floating_texts.append(
                                    FloatingText("Peur!", (255, 180, 60), 60))

    # ═══════════════════════════════════════════════════════════════
    #   RÉACTIONS — ce qui rend un tour-par-tour vivant
    # ═══════════════════════════════════════════════════════════════

    def _opportunity_attacks(self, mover, new_pos, t01, path=None):
        """Rupture de contact: qui se dérobe au corps à corps s'expose à un
        coup gratuit. Reculer, kiter ou fuir a désormais un prix, et la
        mêlée « mord » au lieu de laisser les unités se décoller sans
        réaction. Retourne False si le fuyard a été abattu sur place.

        Le contact se mesure sur tout le TRAJET (`path`): une cavalerie qui
        déborde (trait Débordement) et longe une ligne sans s'y arrêter
        s'expose au même coup que celle qui s'en dégage."""
        ox, oy = mover.position
        nx, ny = new_pos
        trail = [(ox, oy)] + list(path[:-1] if path else [])
        bf = self.battlefield
        # Seul un ennemi à 2 cases ou moins d'une case du TRAJET peut
        # frapper: on n'interroge que le rectangle du trajet, pas l'armée.
        txs = [c[0] for c in trail]
        tys = [c[1] for c in trail]
        for e in self.enemies_near_box(
                mover, (min(txs), min(tys), max(txs), max(tys)), 2):
            if not e.is_alive or e.fleeing or e._opportunity_used:
                continue
            if e._max_range >= 4:
                continue  # un tireur ne retient personne au contact
            reach = min(2, e._max_range)
            d_old = min(bf.unit_distance(e, mover, b_pos=c) for c in trail)
            d_new = bf.unit_distance(e, mover, b_pos=(nx, ny))
            if d_old > reach or d_new <= d_old:
                continue
            melee = [a for a in e.armes if a.porte <= 2]
            if not melee:
                continue
            e._opportunity_used = True
            self._set_action_time(t01)
            e.floating_texts.append(FloatingText("Opportunité!", (255, 240, 150), 55))
            self._apply_combat_events(
                e.perform_attacks(mover, self.battlefield, self,
                                  weapons=[melee[0]], kind="opportunity"))
            if not mover.is_alive:
                return False
        return True

    def _reaction_fire(self, movers, t01):
        """Tir de réaction: un tireur qui tient sa position lâche sa volée à
        la seconde où un ennemi débouche dans sa zone de feu — pendant le
        mouvement adverse, pas trois phases plus tard."""
        bf = self.battlefield
        for shooter in list(self.get_all_alive()):
            if (not shooter.is_alive or shooter.fleeing
                    or shooter._acted_this_round or shooter.spells
                    or shooter.reloading):
                continue
            if shooter._max_range < 4:
                continue
            if id(shooter) in movers:
                continue  # il s'est déplacé: pas de tir d'arrêt
            sx, sy = shooter.position
            best, best_d = None, 999
            for e in self.enemies_near(shooter, shooter._max_range + tr.MAX_RANGE_BONUS):
                info = movers.get(id(e))
                if info is None:
                    continue
                old_pos, new_pos = info
                mr = tr.effective_range(bf, shooter, e)
                d_old = bf.unit_distance(shooter, e, b_pos=old_pos)
                d_new = bf.unit_distance(shooter, e, b_pos=new_pos)
                if d_old <= mr or d_new > mr:
                    continue  # il était déjà sous le feu, ou toujours hors portée
                if not bf.has_line_of_fire(shooter, e):
                    continue
                if d_new < best_d:
                    best, best_d = e, d_new
            if best is None:
                continue
            shooter._acted_this_round = True
            shooter.mark_fired()
            self._set_action_time(t01)
            shooter.floating_texts.append(
                FloatingText("Tir de réaction!", (120, 210, 255), 55))
            self._apply_combat_events(
                shooter.perform_attacks(best, bf, self, kind="reaction"))

    def _momentum_followup(self, unit, t01):
        """Élan: une unité qui abat son adversaire enchaîne aussitôt sur la
        cible suivante à portée. Les percées se propagent au lieu de
        s'arrêter net à chaque mort."""
        if unit._momentum_used or not unit.is_alive or unit.fleeing:
            return
        if not getattr(unit, '_last_attack_killed', False):
            return
        if unit._max_range >= 4:
            return  # l'élan est une affaire de mêlée: on ne « perce » pas au tir
        bf = self.battlefield
        ux, uy = unit.position
        mr = unit._max_range
        cands = [e for e in self.enemies_near(unit, mr)
                 if bf.unit_distance(unit, e) <= mr]
        if mr >= 4:
            cands = [e for e in cands if bf.has_line_of_fire(unit, e)]
        if not cands:
            return
        target = min(cands, key=lambda e: (e.hp, bf.unit_distance(unit, e)))
        d = bf.unit_distance(unit, target)
        weapon = next((a for a in unit.armes if d <= a.porte), None)
        if weapon is None:
            return
        unit._momentum_used = True
        self._set_action_time(t01)
        unit.floating_texts.append(FloatingText("ÉLAN!", (255, 180, 255), 65))
        if unit._kills >= 3:
            self.log_event(f"{unit.name} taille dans le tas !", (255, 180, 255), 2)
        self._apply_combat_events(
            unit.perform_attacks(target, bf, self, weapons=[weapon], kind="momentum"))

    def _initiative_order(self, units):
        """Ordre d'action du round. Qui frappe en premier compte: un mort
        ne riposte pas. Vitesse, charge et allonge donnent le tempo; une
        part d'aléa empêche toute séquence figée d'un round à l'autre."""
        scored = []
        for u in units:
            score = u.vitesse * 1.15
            if getattr(u, '_charged_this_round', False):
                score += 7.0      # le choc d'une charge précède tout
            if u._max_range >= 4:
                score -= 1.5      # on ajuste avant de lâcher
            if getattr(u, 'is_artillery', False):
                score -= 4.0      # les machines sont longues à servir
            if u.spells:
                score += 1.0
            if u._suppression >= 3:
                score -= 2.0      # sous le feu, on réagit mal
            if u.afraid:
                score -= 1.5
            if u.encouragement_range > 0:
                score += 1.0      # l'officier donne le signal
            score += random.random() * 3.0
            scored.append((-score, u.uid, u))
        scored.sort()
        return [u for _, _, u in scored]


    def _charge_phase(self, alive):
        """Phase de charge: les unités dotées d'une charge se ruent sur une
        proie à distance d'élan.

        La cible n'est plus « la plus proche » mais la plus PAYANTE: une
        machine de guerre, un tireur ou un blessé valent mieux qu'un mur de
        boucliers. Le choc est horodaté tôt dans le round — visuellement,
        la cavalerie percute avant que l'échange général ne commence.
        """
        import tactics
        chargers = [u for u in alive
                    if u.is_alive and not u.fleeing and not u.exhausted
                    and (u.charge_montee or u.charge_aida)]
        if not chargers:
            return

        for ci, unit in enumerate(chargers):
            if not unit.is_alive or unit.fleeing:
                continue

            # Pas d'élan depuis un bois, un gué ou un marais
            if not tr.charge_ok(self.battlefield, *unit.position):
                continue

            # BUDGET de mouvement: la charge porte l'allonge du round à
            # 1,5× la vitesse — elle ne s'AJOUTE pas au déplacement déjà
            # effectué. Sans ce décompte, un cavalier avançait de 8 cases
            # en phase de mouvement puis chargeait 12 cases de plus: 20
            # cases par round pour une vitesse de 8.
            budget = int(unit.vitesse * 1.5) - getattr(unit, '_cells_moved', 0)
            if budget < 2:
                continue
            min_dist = 2
            max_dist = budget

            # ── Choix de la proie: valeur de la cible / résistance attendue ──
            best_target = None
            best_score = -1e9
            for enemy in self.enemies_near(unit, max_dist):
                d = self.battlefield.unit_distance(unit, enemy)
                if not (min_dist <= d <= max_dist):
                    continue
                dmg = tactics.expected_damage(unit, enemy, 1, self.battlefield)
                score = dmg * 2.0 + tactics.remaining_value(enemy) * 0.25
                if enemy._max_range >= 4 or getattr(enemy, 'is_artillery', False):
                    score += 12.0          # briser le tir ennemi: priorité absolue
                if enemy.spells:
                    score += 10.0
                if enemy.hp < enemy.max_hp * 0.45:
                    score += 6.0           # achever plutôt qu'entamer
                if tactics.is_isolated(
                        enemy, self.enemies_near(unit, 4, pos=enemy.position), 4):
                    score += 5.0           # proie sans soutien
                score -= d * 0.4           # à valeur égale, le plus proche
                if score > best_score:
                    best_score = score
                    best_target = enemy

            if not best_target:
                continue

            charge_pos = self._charge_impact(unit, best_target)

            if not charge_pos:
                continue

            path = self.battlefield.a_star_path(unit.position, charge_pos, unit, self)
            if not path:
                continue
            cost = self.battlefield.footprint_path_cost(unit, unit.position, path)
            if cost > budget:
                continue

            start_pos = unit.position
            trail = unit._move_path or [start_pos]
            unit._move_path = trail + [c for c in path if c != trail[-1]]
            self.battlefield.move_unit(unit, charge_pos)
            unit._cells_moved += cost
            unit.has_charged = True
            unit._charged_this_round = True

            # Les charges percutent dans une fenêtre serrée, légèrement
            # décalées les unes des autres.
            t_charge = T_CHARGE + 0.012 * ci
            self._set_action_time(t_charge)

            cs = self.cell_size
            start_px = (start_pos[0] * cs + cs // 2, start_pos[1] * cs + cs // 2)
            end_px = (best_target.position[0] * cs + cs // 2,
                      best_target.position[1] * cs + cs // 2)

            charge_color = (255, 200, 50) if unit.charge_montee else (100, 200, 255)
            self.visual_effects['attack_lines'].append(
                AttackLine(start_px, end_px, charge_color, 30,
                           delay=FX_CLOCK.current_delay))
            self.visual_effects.setdefault('shockwaves', []).append(
                ShockWave(end_px, cs * 2, charge_color, 24,
                          delay=FX_CLOCK.current_delay + 4))

            label = "CHARGE!" if unit.charge_montee else "CHARGE D'AÏDA!"
            unit.floating_texts.append(FloatingText(label, charge_color, 70))

            melee_armes = [a for a in unit.armes if a.porte <= 2]
            weapons = [melee_armes[0]] if melee_armes else None
            self._apply_combat_events(
                unit.perform_attacks(best_target, self.battlefield, self,
                                     weapons=weapons, kind="charge"))
            self._momentum_followup(unit, t_charge + 0.05)

    def _charge_impact(self, unit, target):
        """Case d'arrivée d'une charge: une ancre dont l'empreinte TOUCHE
        celle de la cible (y compris en diagonale), libre et d'où l'on peut
        charger — la plus proche du chargeur. Mesurée en empreintes, et
        départagée en miroir: une grosse cavalerie n'est plus forcée de
        contourner sa proie selon le côté d'où elle vient."""
        bf = self.battlefield
        uw, uh = bf.get_unit_dims(unit)
        tw, th = bf.get_unit_dims(target)
        tx, ty = target.position
        ux, uy = unit.position
        best, best_key = None, None
        for px in range(tx - uw, tx + tw + 1):
            for py in range(ty - uh, ty + th + 1):
                ax0, ax1 = px, px + uw - 1
                ay0, ay1 = py, py + uh - 1
                gx = max(0, tx - ax1, ax0 - (tx + tw - 1))
                gy = max(0, ty - ay1, ay0 - (ty + th - 1))
                if max(gx, gy) != 1:
                    continue                      # ni chevauchement ni écart
                if not bf._can_move_to(unit, (px, py), set()):
                    continue
                if not all(tr.charge_ok(bf, px + i, py + j)
                           for i in range(uw) for j in range(uh)
                           if 0 <= px + i < bf.width and 0 <= py + j < bf.height):
                    continue
                key = (abs(ux - px) + abs(uy - py), gx + gy, abs(py - uy), abs(px - ux))
                if best_key is None or key < best_key:
                    best, best_key = (px, py), key
        return best

    def _attack_gate(self, unit):
        """Siège: l'unité consacre-t-elle son action à enfoncer une porte ?
        Retourne True si elle a frappé (ou tenté de frapper) la porte."""
        bf = self.battlefield
        if not bf.gate_hp or bf.gates_open:
            return False
        gates_now = bf.active_gates
        if not any(h > 0 for h in gates_now.values()):
            return False
        if not unit.is_alive or unit.fleeing:
            return False
        if id(unit) not in self._army1_ids:
            return False

        ux, uy = unit.position
        engine = getattr(unit, 'siege_engine', None)
        best_gate, best_gate_dist = None, 999
        for gpos, ghp in gates_now.items():
            if ghp <= 0:
                continue
            # Engin (2×2 et plus): distance de son empreinte, pas de son coin
            d = (siege_engines.gate_distance(bf, unit, gpos) if engine
                 else bf.manhattan_distance((ux, uy), gpos))
            if d < best_gate_dist:
                best_gate, best_gate_dist = gpos, d
        if best_gate is None:
            return False

        gx, gy = best_gate
        is_artillery = getattr(unit, 'is_artillery', False)
        gate_save = bf.gate_save
        total_dmg = 0
        for arme in unit.armes:
            if arme.porte < 4 and best_gate_dist > 1:
                continue
            if arme.porte >= 4 and best_gate_dist > arme.base_porte:
                continue
            # Archers mobiles: priorité aux ennemis VISIBLES; s'il n'y en a
            # pas, autant marteler la porte.
            if arme.porte >= 4 and not is_artillery:
                if any(e.is_alive
                       and bf.manhattan_distance((ux, uy), e.position) <= arme.porte
                       and bf.has_line_of_fire(unit, e)
                       for e in self.army2):
                    continue
            for _ in range(arme.nb_attaque):
                if combat.saves(combat.save_threshold(gate_save, arme.perforation)):
                    continue
                total_dmg += max(1, arme.lancer_degats())
        if engine == siege_engines.RAM:
            total_dmg *= siege_engines.RAM_GATE_FACTOR

        if total_dmg > 0:
            destroyed = bf.damage_gate(gx, gy, total_dmg)
            hp_left = bf.gate_hp.get((gx, gy), 0)
            unit.floating_texts.append(
                FloatingText(f"-{total_dmg} Porte ({hp_left})", (200, 150, 50), 40))
            cs = self.cell_size
            self.visual_effects.setdefault('impacts', []).append(
                ImpactBurst((gx * cs + cs // 2, gy * cs + cs // 2),
                            (220, 170, 90), 1.4,
                            math.atan2(gy - uy, gx - ux), 18,
                            delay=FX_CLOCK.current_delay + 2, kind="gate"))
            if destroyed:
                unit.floating_texts.append(
                    FloatingText("PORTE DÉTRUITE!", (255, 200, 50), 90))
                self.log_event("La porte cède !", (255, 160, 60), 3)
                self._spring_gate_trap(gx, gy)
            return True
        if best_gate_dist <= 1 and unit._max_range < 4:
            unit.floating_texts.append(
                FloatingText("Porte résiste!", (150, 130, 80), 30))
            return True
        return False


    def _dock_siege_towers(self):
        """Une tour de siège arrivée à son poste s'accole au mur: rampe et
        passerelle (une brèche pour l'assaut). La tour cesse d'être une
        unité sur la carte; elle reste au rôle de l'armée."""
        bf = self.battlefield
        if not bf.is_siege:
            return []
        docked = []
        for u in [u for u in self.army1 if u.is_alive and u.siege_engine == siege_engines.TOWER]:
            if not siege_engines.tower_docked(bf, u):
                continue
            siege_engines.dock_tower(bf, u)
            self.army1.remove(u)
            docked.append(u)
            u.floating_texts.append(FloatingText("À L'ASSAUT !", (255, 210, 120), 90))
            self.log_event("La tour de siège s'accole au rempart !", (255, 180, 90), 3)
        if docked:
            self._alive_cache['dirty'] = True
            self._refresh_army_sets()
            self._flush_structure_changes()
            for cmd in (self.commander1, self.commander2):
                cmd._gate_lock = 0          # une brèche s'ouvre: on reconsidère l'axe
        return docked

    def _spring_gate_trap(self, gx, gy):
        """Porte piégée (fortification niveau 3): quand un battant cède,
        huile bouillante et pierres s'abattent sur les assaillants massés à
        son pied, et la flaque d'huile brûle quelques rounds sur le passage.
        Une fois par battant. Retourne les unités touchées."""
        bf = self.battlefield
        if (gx, gy) not in bf.trapped_gates:
            return []
        group = bf.gate_group(gx, gy)
        bf.trapped_gates.difference_update(group)
        from models import Dice
        dice = Dice.parse(TRAP_DAMAGE)
        hit = []
        for u in sorted((u for u in self.army1 if u.is_alive), key=lambda u: u.uid):
            cells = bf.get_unit_cells(u)
            if not any(abs(cx - x) + abs(cy - y) <= TRAP_REACH
                       for (cx, cy) in cells for (x, y) in group):
                continue
            hit.append(u)
            u._suppression += 1
            # Le toit de peaux d'un engin arrête les flèches, pas l'huile
            if not u.siege_engine and combat.saves(combat.save_threshold(u.sauvegarde, TRAP_PERFORATION)):
                u.floating_texts.append(FloatingText("Esquive!", (200, 200, 160)))
                continue
            u.take_damage(dice.roll())
            u.floating_texts.append(FloatingText("Huile bouillante!", (255, 150, 60), 60))
        # La flaque: le battant et les deux cases devant lui, côté assaillant
        for (x, y) in group:
            for dx in (0, -1, -2):
                c = (x + dx, y)
                if 0 <= c[0] < bf.width and bf.grid[c[0]][c[1]] in (0, 3):
                    bf.fires[c] = max(bf.fires.get(c, 0), TRAP_BURN)
                    bf.dirty_cells.add(c)
        self.log_event("PIÈGE ! L'huile bouillante s'abat sur l'assaillant", (255, 110, 40), 3)
        cs = self.cell_size
        cy = (group[0][1] + group[-1][1] + 1) * cs / 2
        cx = gx * cs + cs / 2
        d = FX_CLOCK.current_delay + 4
        self.visual_effects.setdefault('aoe_explosions', []).append(
            AoeExplosion((cx, cy), cs * (TRAP_REACH + 1), (255, 140, 30), 35, delay=d))
        self._flush_structure_changes()
        return hit

    # ─── Destruction: structures, effondrements, incendie ───

    _COLLAPSE_LABELS = {
        st.HOUSE: ("Une maison s'effondre !", (255, 170, 90), 2),
        st.PALISADE: ("Une palissade cède !", (230, 170, 100), 2),
        st.ROCK: ("Un rocher vole en éclats !", (200, 200, 190), 2),
        st.HEDGE: ("Une haie part en fumée", (200, 150, 90), 1),
        st.GROVE: ("Un bosquet est réduit en cendres", (200, 140, 80), 1),
        st.WALL: ("BRÈCHE DANS LE MUR !", (255, 120, 60), 3),
    }

    def _flush_structure_changes(self):
        """Horodate ce que la destruction a changé depuis le dernier appel:
        le rendu repeint et allume au moment de l'action, pas en début de
        round."""
        bf = self.battlefield
        now = FX_CLOCK.current_delay
        if bf.dirty_cells:
            self.pending_repaints.append((now, set(bf.dirty_cells)))
            bf.dirty_cells.clear()
        for c in bf.fires:
            if c not in self.fire_reveal:
                self.fire_reveal[c] = now
        for c in [c for c in self.fire_reveal if c not in bf.fires]:
            del self.fire_reveal[c]

    def _structure_collapsed(self, gid, kind, cells):
        """Conséquences d'un effondrement: blessures autour d'une maison,
        journal, poussière et onde de choc."""
        bf = self.battlefield
        cset = set(cells)
        if kind == st.HOUSE:
            hit = set()
            for (x, y) in cells:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        u = bf.units.get((x + dx, y + dy))
                        if u is not None and u.is_alive and (x + dx, y + dy) not in cset:
                            hit.add(u)
            for u in sorted(hit, key=lambda u: u.uid):
                if combat.saves(combat.save_threshold(u.sauvegarde)):
                    u.floating_texts.append(FloatingText("Esquive!", (200, 200, 160)))
                    continue
                u.take_damage(random.randint(1, 3))
                u.floating_texts.append(FloatingText("Écrasé!", (255, 150, 90), 50))
        elif kind == st.WALL:
            # Les défenseurs du chemin de ronde chutent avec lui
            fallen = set()
            for (x, y) in cells:
                for dx in (1, 2, 3):
                    u = bf.units.get((x + dx, y))
                    if u is not None and u.is_alive:
                        fallen.add(u)
            for u in sorted(fallen, key=lambda u: u.uid):
                u._on_wall = False
                if combat.saves(combat.save_threshold(u.sauvegarde)):
                    continue
                u.take_damage(random.randint(1, 3))
                u.floating_texts.append(FloatingText("Chute!", (255, 150, 90), 50))
        text, color, importance = self._COLLAPSE_LABELS.get(
            kind, ("Effondrement", (220, 200, 160), 1))
        self.log_event(text, color, importance)
        cs = self.cell_size
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        cx = (min(xs) + max(xs) + 1) * cs / 2
        cy = (min(ys) + max(ys) + 1) * cs / 2
        span = max(max(xs) - min(xs), max(ys) - min(ys)) + 1
        d = FX_CLOCK.current_delay
        if kind in (st.HOUSE, st.PALISADE, st.ROCK, st.WALL):
            self.visual_effects.setdefault('shockwaves', []).append(
                ShockWave((cx, cy), cs * (span + 1), (230, 210, 170), 30, delay=d))
        for (x, y) in cells[::max(1, len(cells) // 4)]:
            self.visual_effects.setdefault('impacts', []).append(
                ImpactBurst((x * cs + cs // 2, y * cs + cs // 2), (200, 180, 140), 1.6,
                            _FX_RNG.uniform(0, math.tau), 20, delay=d, kind="gate"))
        self.visual_effects.setdefault('collapses', []).append((d, cx, cy, span * cs, kind))

    def _attack_structure(self, unit):
        """Machine de guerre sous ordre `demolish`: elle tire sur la
        structure qui masque sa cible. Résolution calquée sur _attack_gate
        (cible immobile: pas de jet de toucher)."""
        order = getattr(unit, '_tactical_order', None)
        if order is None or order.order_type != "demolish" or order.target_pos is None:
            return False
        if not unit.is_alive or unit.fleeing:
            return False
        bf = self.battlefield
        tx, ty = order.target_pos
        gid = st.group_at(bf, tx, ty)
        if gid is None:
            return False
        kind = bf.structure_kind[gid]
        ux, uy = unit.position
        dist = abs(ux - tx) + abs(uy - ty)
        save = st.KINDS[kind]['save']
        total, fired = 0, False
        events = []
        for arme in unit.armes:
            if arme.porte < 4 or dist > arme.base_porte:
                continue
            factor = st.weapon_factor(kind, arme)
            if factor <= 0:
                continue
            fired = True
            for _ in range(arme.nb_attaque):
                events.append({'type': 'arrow', 'from_grid': unit.position,
                               'to_grid': (tx, ty), 'proj': 'ballista', 'at': 0})
                if combat.saves(combat.save_threshold(save, arme.perforation)):
                    continue
                total += int(max(1, arme.lancer_degats()) * factor)
        if not fired:
            return False
        base = FX_CLOCK.current_delay
        self._apply_combat_events(events)
        FX_CLOCK.at(base + 18)
        if total > 0:
            self._apply_combat_events([{'type': 'impact', 'at_grid': (tx, ty),
                                        'from_grid': unit.position, 'power': 1.6,
                                        'ranged': True, 'fx': 'gate', 'at': 0}])
            cells = list(bf.structure_members[gid])
            unit.floating_texts.append(FloatingText(f"-{total} {kind}", (220, 170, 90), 40))
            if st.damage(bf, gid, total, heavy=True):
                self._structure_collapsed(gid, kind, cells)
        else:
            unit.floating_texts.append(FloatingText("Tient bon!", (170, 160, 130), 30))
        self._flush_structure_changes()
        FX_CLOCK.at(base)
        return True

    def _check_ring_fall(self):
        """Chute de l'enceinte active (s'il en reste une derrière):
          (a) ses portes sont tombées ou une brèche y est ouverte, ET au
              moins 3 assaillants (ou la moitié des vivants) sont passés;
          (b) plus aucun défenseur ne tient devant l'enceinte suivante."""
        bf = self.battlefield
        if not bf.is_siege or not bf.has_next_ring:
            return False
        wx = bf.wall_x
        next_x = bf.rings[bf.active_ring + 1]['wall_x']
        attackers = [u for u in self.army1 if u.is_alive and not u.fleeing]
        # Les pièces fixes (baliste de tour) ne se replient pas: elles ne
        # retiennent pas l'enceinte à elles seules
        defenders = [u for u in self.army2 if u.is_alive and not u.fleeing and u.vitesse > 0]
        gates_down = (all(hp <= 0 for hp in bf.active_gates.values())
                      or bool(bf.active_breaches))
        inside = sum(1 for u in attackers if u.position[0] > wx)
        fell_a = gates_down and attackers and (inside >= 3 or inside * 2 >= len(attackers))
        fell_b = bool(defenders) and not any(u.position[0] < next_x for u in defenders)
        if not (fell_a or fell_b):
            return False
        bf.advance_ring()
        self.log_event("L'ENCEINTE EXTÉRIEURE EST TOMBÉE !", (255, 140, 60), 3)
        for cmd in (self.commander1, self.commander2):
            cmd.on_ring_fall()
        return True

    def _fire_phase(self):
        """L'incendie agit entre deux rounds: brûlures, propagation,
        effondrements. Les commandants le verront au round suivant."""
        bf = self.battlefield
        if not bf.fires:
            return
        FX_CLOCK.at(int(self.fx_frames_per_round * 0.92))
        burning = bf.fires
        for u in sorted((u for u in self.army1 + self.army2 if u.is_alive),
                        key=lambda u: u.uid):
            if not any(c in burning for c in bf.get_unit_cells(u)):
                continue
            u._suppression += 1
            if random.randint(1, 6) >= u.sauvegarde:
                continue
            u.take_damage(1)
            u.floating_texts.append(FloatingText("Brûlé!", (255, 140, 40), 45))
        res = st.fire_step(bf, random)
        for gid, kind, cells in res['collapsed']:
            self._structure_collapsed(gid, kind, cells)
        self._flush_structure_changes()

    def _choose_attack_target(self, unit):
        """Choix de la cible de l'action d'attaque.

        L'ordre du commandant pèse lourd, mais une occasion de TUER
        maintenant prime toujours: achever un ennemi vaut mieux qu'entamer
        un adversaire intact, et un tireur n'arrose pas une mêlée déjà
        tenue par les siens.
        """
        from ai_commander import select_tactical_target
        import tactics
        bf = self.battlefield
        ux, uy = unit.position
        mr = unit._max_range
        is_ranged = mr >= 4

        def can_hit(e):
            if bf.unit_distance(unit, e) > tr.effective_range(bf, unit, e):
                return False
            if is_ranged and not bf.has_line_of_fire(unit, e):
                return False
            return True

        reachable = [e for e in self.enemies_near(unit, mr + tr.MAX_RANGE_BONUS)
                     if can_hit(e)]
        if not reachable:
            return None
        if len(reachable) == 1:
            return reachable[0]

        ordered = select_tactical_target(unit, self, bf)

        best, best_score = None, -1e9
        for e in reachable:
            d = bf.unit_distance(unit, e)
            dmg = tactics.expected_damage(unit, e, d, bf)
            score = dmg
            score += tactics.kill_chance(dmg, e) * 14.0   # finir le travail
            score += tactics.remaining_value(e) * 0.12
            if e is ordered:
                score += 8.0                              # ordre du commandant
            if e._max_range >= 4 or e.spells:
                score += 3.0
            if e.encouragement_range > 0:
                score += 2.5
            if is_ranged and any(
                    a._max_range < 4
                    and abs(a.position[0] - e.position[0])
                    + abs(a.position[1] - e.position[1]) <= 1
                    for a in self.allies_near(unit, 1, pos=e.position)):
                score -= 4.0                              # tir fratricide évité
            score -= d * 0.15
            if score > best_score:
                best, best_score = e, score
        return best


    def simulate_round(self):
        """Joue un round complet. Les phases s'enchaînent dans cet ordre (et
        l'ordre des tirages aléatoires en dépend: ne pas le permuter)."""
        self._begin_round()
        self._command_phase()
        siege_engines.assign_attendants(self)   # artilleurs et pousseurs
        alive = self.get_all_alive()
        movers = self._apply_moves(self._plan_moves(alive))
        self._update_facings(movers)
        self._dock_siege_towers()      # tours de siège arrivées au mur
        self.morale_phase()            # pertes lourdes, auras, stress au combat
        self._check_ring_fall()        # Citadelle: l'enceinte active tombe-t-elle ?
        self._position_bonuses(alive)
        # Charge (avant l'échange général)
        charge_pool = [u for u in self.get_all_alive() if u.is_alive]
        random.shuffle(charge_pool)
        self._charge_phase(charge_pool)
        self._exchange_phase()
        self._end_of_round_effects(alive)
        self._remove_casualties()
        self._handle_routers()
        self._close_round()

    def _close_round(self):
        """Vieillissement de la pression subie, plafonds d'effets, compteur."""
        # Lu par la phase de moral du round suivant — d'où le fait de le
        # faire ICI et pas au départ
        for unit in self.army1 + self.army2:
            unit.end_round()

        # Garde-fou: c'est le renderer qui purge les effets visuels au fil
        # des frames. Sans lui (tests headless, simulation accélérée), les
        # listes grossiraient sans fin. On plafonne en jetant les plus vieux.
        for _key, _lst in self.visual_effects.items():
            if _key != 'target_indicators' and len(_lst) > _FX_MAX_QUEUE:
                del _lst[:len(_lst) - _FX_MAX_QUEUE]

        self.army1 = [u for u in self.army1 if u.is_alive or u.down_timer > 0]
        self.army2 = [u for u in self.army2 if u.is_alive or u.down_timer > 0]
        self.round += 1
        self._alive_cache['dirty'] = True
        FX_CLOCK.at(0)

    def _begin_round(self):
        """Remise à zéro des effets du round, déroute des armées sans combattant."""
        self._alive_cache['dirty'] = True
        self.visual_effects['target_indicators'] = []
        self.round_events = []
        # Le renderer a consommé les changements du round précédent: ce qui
        # brûlait est déjà à l'écran.
        self.pending_repaints = []
        self.pending_craters = []
        self.visual_effects['collapses'] = []
        for c in self.fire_reveal:
            self.fire_reveal[c] = 0

        # Horloge du round: toutes les actions vont s'y positionner
        FX_CLOCK.frames_per_round = self.fx_frames_per_round
        FX_CLOCK.at(0)

        for u in self.army1 + self.army2:
            u.start_round()
            u._charged_this_round = False

        # Déroute: si une armée n'a plus de combattants, tous les restants fuient
        for army in [self.army1, self.army2]:
            fighters = sum(1 for u in army if u.is_alive and not u.fleeing)
            if fighters == 0:
                for u in army:
                    if u.is_alive and not u.fleeing:
                        u.fleeing = True
                        u.status_text = "DÉROUTE"
                        u.floating_texts.append(FloatingText("Déroute!", (255, 100, 50), 80))
                        self.log_event("Une armée rompt le combat !", (255, 100, 50), 3)

        # Appartenance d'armée (O(1)) — recalculée explicitement chaque round
        self._army1_ids = {id(u) for u in self.army1}
        self._army2_ids = {id(u) for u in self.army2}

    def _command_phase(self):
        """Les commandants assignent les ordres; bannières des plans."""
        # === PHASE DE COMMANDEMENT: les IA assignent les ordres ===
        self.commander1.issue_orders(self)
        self.commander2.issue_orders(self)
        # Phases des plans de bataille: annoncées (bannières)
        for side, cmd in ((1, self.commander1), (2, self.commander2)):
            for text, color in cmd.plan.pop_events():
                self.log_event(f"Armée {side} : {text}", color, 2)

    def _plan_moves(self, alive):
        """Mouvement cohésif en 3 passes: destinations réservées sans collision.

        Rien ne bouge pendant la planification — les destinations ne sont
        appliquées qu'ensuite par _apply_moves. Le champ de bataille peut
        donc mettre en cache tout ce qui ne dépend que de la disposition
        (cases occupées par camp, distance au plus proche ennemi)."""
        self.battlefield.occupancy_cache(True)
        self._near_enemy_cache = {}
        try:
            return self._plan_moves_pass(alive)
        finally:
            self.battlefield.occupancy_cache(False)
            self._near_enemy_cache = None

    def _plan_moves_pass(self, alive):
        """Les 3 passes proprement dites (statiques, engagées, approchantes)."""
        # Mélanger l'ordre de traitement du mouvement: les tris des passes
        # sont stables, donc à distance égale c'était toujours l'armée 1
        # qui réservait ses cases en premier (avantage cumulatif).
        _move_pool = list(alive)
        random.shuffle(_move_pool)

        # === MOUVEMENT COHÉSIF EN 3 PASSES ===
        bf = self.battlefield

        static_units = []   # Fuyards, artillerie
        engaged = []        # Au contact (distance ≤ portée+1)
        approaching = []    # En approche (pas encore au contact)

        for u in _move_pool:
            # Machines (servies ou non): pas de « pas de côté » des unités
            # bloquées — sans servants, une machine ne bouge pas d'un pouce
            if u.fleeing or u.vitesse <= 0 or siege_engines.is_machine(u):
                static_units.append(u)
                continue
            # Siège: tireurs/mages sur rempart → toujours "engaged" (ne bougent pas)
            if bf.gate_hp and bf.on_active_rampart(*u.position, u, self) and (u._max_range >= 4 or bool(u.spells)):
                engaged.append(u)
                continue
            # 999 = plus aucun ennemi vivant (la carte ne fait jamais
            # 999 cases de diagonale)
            min_d = self.nearest_enemy_dist(u)
            if min_d >= 999:
                static_units.append(u)
            elif min_d <= u._max_range + 1:
                engaged.append(u)
            else:
                approaching.append(u)

        # === Pass 1: statiques — réservent leur position ===
        reserved = set()
        moves = {}
        bf.leaving = set()

        # === Relève: les rangs tournent avant tout le reste ===
        relieved = self._plan_reliefs(_move_pool, reserved, moves)
        if relieved:
            static_units = [u for u in static_units if id(u) not in relieved]
            engaged = [u for u in engaged if id(u) not in relieved]
            approaching = [u for u in approaching if id(u) not in relieved]

        # === Pass 0: machines servies, puis leurs servants ===
        # Les servants visent une case au contact de la DESTINATION de leur
        # machine: elle doit donc être planifiée avant eux.
        crewed = self._plan_machines(_move_pool, reserved, moves, relieved or ())
        if crewed:
            static_units = [u for u in static_units if id(u) not in crewed]
            engaged = [u for u in engaged if id(u) not in crewed]
            approaching = [u for u in approaching if id(u) not in crewed]

        for unit in static_units:
            new_pos, target = bf.compute_move(unit, self, reserved)
            unit.current_target = target
            if target:
                self.visual_effects['target_indicators'].append((unit, target))
            new_pos = self._legal_move(unit, new_pos, reserved)
            if new_pos:
                self._commit_move(unit, new_pos, reserved, moves)
            elif unit.position:
                reserved.update(bf._get_reserved_cells(unit, unit.position))

        # === Pass 2: engagées — se déplacent, triées par proximité ===
        engaged.sort(key=self.nearest_enemy_dist)

        for unit in engaged:
            new_pos, target = bf.compute_move(unit, self, reserved)
            unit.current_target = target
            if target:
                self.visual_effects['target_indicators'].append((unit, target))
            new_pos = self._legal_move(unit, new_pos, reserved)
            if new_pos:
                self._commit_move(unit, new_pos, reserved, moves)
            elif unit.position:
                reserved.update(bf._get_reserved_cells(unit, unit.position))

        # === Pass 3: en approche — avance cohésive ===
        # Trier les approchants du PLUS LOIN au PLUS PROCHE de l'ennemi —
        # sauf les blocs en formation, qui avancent AVANT eux et premier rang
        # en tête: un rang arrière qui bouge d'abord bute sur le rang de
        # devant encore en place, et le bloc se déforme en U.
        def _approach_key(u):
            d = self.nearest_enemy_dist(u)
            o = getattr(u, '_tactical_order', None)
            if o is not None and o.order_type == "form":
                return (0, d)
            return (1, -d)
        approaching.sort(key=_approach_key)

        median_dist = 999
        if approaching:
            approach_dists = []
            for u in approaching:
                d = self.nearest_enemy_dist(u)
                if d < 999:
                    approach_dists.append(d)
            if approach_dists:
                median_dist = sorted(approach_dists)[len(approach_dists) // 2]

        for unit in approaching:
            # Cohésion: les unités très en avance ralentissent pour ne pas
            # se retrouver isolées — sauf ordre de foncer.
            my_dist = self.nearest_enemy_dist(unit)

            orig_speed = unit.vitesse
            advance_gap = median_dist - my_dist
            if advance_gap > 6 and unit._max_range < 4 and not getattr(unit, '_rush', False):
                unit.vitesse = max(1, orig_speed - 1)

            new_pos, target = bf.compute_move(unit, self, reserved)
            unit.current_target = target
            if target:
                self.visual_effects['target_indicators'].append((unit, target))
            new_pos = self._legal_move(unit, new_pos, reserved)
            if new_pos:
                self._commit_move(unit, new_pos, reserved, moves)
            elif unit.position:
                # Bloqué: mouvement latéral seulement si aucun ennemi au contact
                ux, uy = unit.position
                enemy_in_range = any(
                    bf.unit_distance(unit, e) <= tr.effective_range(bf, unit, e)
                    for e in self.enemies_near(unit, unit._max_range + tr.MAX_RANGE_BONUS)
                )
                if not enemy_in_range:
                    alt_pos = self._legal_move(
                        unit, bf.find_lateral_advance(unit, self, reserved), reserved)
                    if alt_pos:
                        self._commit_move(unit, alt_pos, reserved, moves)
                    else:
                        reserved.update(bf._get_reserved_cells(unit, unit.position))
                else:
                    reserved.update(bf._get_reserved_cells(unit, unit.position))

            unit.vitesse = orig_speed
        return moves

    def _plan_machines(self, pool, reserved, moves, skip=()):
        """Planifie les machines qui ont des servants, puis ces servants.
        Retourne les id() des unités planifiées."""
        bf = self.battlefield
        self._planned_moves = moves
        attendants = [u for u in pool if id(u) not in skip and not u.fleeing
                      and getattr(u, '_attends', None) is not None and u._attends.is_alive]
        if not attendants:
            return set()
        masters = {id(u._attends): u._attends for u in attendants}
        machines = [u for u in pool if id(u) in masters and id(u) not in skip]
        done = set()
        for unit in machines + attendants:
            new_pos, target = bf.compute_move(unit, self, reserved)
            unit.current_target = target
            if target:
                self.visual_effects['target_indicators'].append((unit, target))
            new_pos = self._legal_move(unit, new_pos, reserved)
            if new_pos:
                self._commit_move(unit, new_pos, reserved, moves)
            elif unit.position:
                reserved.update(bf._get_reserved_cells(unit, unit.position))
            done.add(id(unit))
        return done

    def _plan_reliefs(self, pool, reserved, moves):
        """RELÈVE: une unité de mêlée fatiguée, au contact, échange sa place
        avec une alliée fraîche de même gabarit, collée à elle (diagonale
        comprise) et hors de tout contact. L'échange est ordonné (pas de coup d'opportunité): la
        fraîche s'avance au moment où la lasse recule. Les rangs tournent
        au lieu de laisser le premier se faire tailler en pièces épuisé.
        Renvoie les id des unités engagées dans une relève."""
        bf = self.battlefield
        taken = set()
        for tired in pool:
            if (id(tired) in taken or not tired.is_alive or tired.fleeing
                    or tired._max_range >= 4 or not tired.tired):
                continue
            foes = [e for e in self.get_enemies(tired) if e.is_alive]
            front = [e for e in foes if bf.unit_distance(tired, e) <= 1]
            if not front:
                continue
            dims = bf.get_unit_dims(tired)
            best = None
            for fresh in self.get_allies(tired):
                if (fresh is tired or id(fresh) in taken or not fresh.is_alive
                        or fresh.fleeing or fresh.vitesse <= 0 or fresh._max_range >= 4
                        or getattr(fresh, 'is_artillery', False)
                        or fresh.tired or fresh.fatigue + 2 > tired.fatigue
                        or bf.get_unit_dims(fresh) != dims
                        or not bf.footprints_touch(tired, fresh)):
                    continue
                if any(bf.unit_distance(fresh, e) <= 1 for e in foes):
                    continue
                key = (fresh.fatigue, -fresh.hp, fresh.uid)
                if best is None or key < best[0]:
                    best = (key, fresh)
            if best is None:
                continue
            fresh = best[1]
            a, b = tired.position, fresh.position
            for u, dest in ((tired, b), (fresh, a)):
                moves[u] = dest
                reserved.update(bf._get_reserved_cells(u, dest))
                u._relief = True
                u._planned_path = None
            fresh.current_target = (tired.current_target if tired.current_target in front
                                    else front[0])
            tired.current_target = None
            fresh.floating_texts.append(FloatingText("Relève!", (170, 220, 255), 55))
            taken.update((id(tired), id(fresh)))
        return taken

    def _legal_move(self, unit, new_pos, reserved):
        """Destination validée par un vrai chemin case par case (cf.
        Battlefield.route_to), ou None."""
        if not new_pos:
            return None
        if new_pos == unit.position:
            # « Rester » est une décision (poste tenu, garde): la case est
            # réservée, et l'unité ne part pas en glissade latérale
            return new_pos if self.battlefield._can_move_to(unit, new_pos, reserved) else None
        budget = max(2, unit.vitesse) if unit.fleeing else unit.vitesse
        return self.battlefield.route_to(unit, self, new_pos, reserved, budget)

    def _commit_move(self, unit, new_pos, reserved, moves):
        """Inscrit le déplacement: la destination est réservée, et la case
        quittée devient disponible pour les unités planifiées ensuite (une
        colonne avance d'un bloc au lieu de piétiner derrière sa tête)."""
        bf = self.battlefield
        moves[unit] = new_pos
        reserved.update(bf._get_reserved_cells(unit, new_pos))
        if new_pos != unit.position:
            bf.leaving.add(id(unit))

    def _apply_moves(self, moves):
        """Applique les déplacements échelonnés dans le temps, avec leurs réactions (opportunité, tir d'arrêt)."""
        bf = self.battlefield
        # === APPLICATION DU MOUVEMENT + RÉACTIONS ===
        # Les déplacements sont échelonnés dans le temps et peuvent
        # DÉCLENCHER des réactions adverses (coups d'opportunité sur rupture
        # de contact, tirs d'arrêt quand on débouche dans une zone de feu).
        movers = {}
        # À vitesse égale, départager au hasard: un départage par uid faisait
        # toujours bouger l'armée 1 d'abord (uids plus petits), ce qui lui
        # offrait les coups d'opportunité et les tirs de réaction — l'armée
        # de gauche gagnait ~65 % des duels miroir.
        ordered_moves = list(moves.items())
        random.shuffle(ordered_moves)
        ordered_moves.sort(key=lambda kv: -kv[0].vitesse)
        n_mv = max(1, len(ordered_moves))
        for i, (unit, new_pos) in enumerate(self._dependency_order(ordered_moves)):
            if not unit.is_alive:
                continue
            t01 = T_MOVE_START + (T_MOVE_END - T_MOVE_START) * (i / n_mv)
            old_pos = unit.position
            if new_pos == old_pos:
                continue  # « rester » réservait la case, rien à jouer
            planned_path = getattr(unit, '_planned_path', None)
            if not (planned_path and planned_path[-1] == new_pos):
                planned_path = None
            unit._backpedal = bool(planned_path) and getattr(unit, '_planned_backpedal', False)
            if not unit._relief and not self._opportunity_attacks(
                    unit, new_pos, t01 + 0.03, planned_path):
                continue  # abattu en se dérobant: il ne part pas
            # Le déplacement se compte en PAS (8 directions, comme l'A*):
            # une diagonale coûte un pas, pas deux. La distance de Manhattan
            # doublait le coût des trajets obliques et vidait le budget de
            # charge des unités arrivées en biais.
            # Le coût planifié par compute_move (somme des step_cost() du
            # CHEMIN réellement suivi) est plus exact que le coût d'un seul
            # saut vers la destination: sur terrain, un vitesse-6 qui
            # traverse un marais puis 3 cases de plaine dépense 6, pas 4.
            # On ne le réutilise que s'il vient bien de la destination
            # appliquée ce round (sinon repli sur le coût du saut direct).
            planned_cost = getattr(unit, '_planned_move_cost', None)
            planned_dest = getattr(unit, '_planned_move_dest', None)
            if (bf.terrain is not None and planned_cost is not None
                    and planned_dest == new_pos):
                cost = planned_cost
            else:
                cost = (max(abs(new_pos[0] - old_pos[0]), abs(new_pos[1] - old_pos[1]))
                        * bf.footprint_step_cost(unit, old_pos, new_pos))
            unit._cells_moved += cost
            if planned_path:
                unit._move_path = [old_pos] + list(planned_path)
            else:
                unit._move_path = [old_pos, new_pos]
            bf.move_unit(unit, new_pos)
            movers[id(unit)] = (old_pos, new_pos)

        self._reaction_fire(movers, T_MOVE_END - 0.06)
        return movers

    def _dependency_order(self, ordered_moves):
        """Ordre d'application: une case libérée par un allié n'est prise
        qu'APRÈS son départ. Un déplacement dont l'arrivée est encore tenue
        attend son tour (l'ordre de vitesse est conservé d'une vague à
        l'autre). Si plus rien ne se libère (échange de places, chaîne
        bloquée), les restants ne bougent pas: jamais deux unités vivantes
        sur une même case."""
        bf = self.battlefield
        occupied = {c: u for c, u in bf.units.items() if u.is_alive}

        def clear(unit, pos):
            w, h = bf.get_unit_dims(unit)
            return all(occupied.get((pos[0] + i, pos[1] + j)) in (None, unit)
                       for i in range(w) for j in range(h))

        order, pending = [], [kv for kv in ordered_moves if kv[0].is_alive]
        while pending:
            now = [kv for kv in pending if clear(*kv)]
            if not now:
                # Relève: les deux partenaires échangent d'un même geste
                now = Battle._relief_swaps(pending)
            if not now:
                break
            for unit, pos in now:
                for c in bf.get_unit_cells(unit):
                    if occupied.get(c) is unit:
                        del occupied[c]
                w, h = bf.get_unit_dims(unit)
                for i in range(w):
                    for j in range(h):
                        occupied[(pos[0] + i, pos[1] + j)] = unit
            order.extend(now)
            pending = [kv for kv in pending if kv not in now]
        bf.leaving = set()
        return order

    @staticmethod
    def _relief_swaps(pending):
        """Paires de relève (échange exact de places) parmi les déplacements
        encore bloqués. Seules les relèves planifiées échangent: toute autre
        boucle reste sur place."""
        at = {kv[0].position: kv for kv in pending if kv[0]._relief}
        out = []
        for unit, dest in pending:
            if not unit._relief or (unit, dest) in out:
                continue
            other = at.get(dest)
            if other is not None and other[1] == unit.position and other[0] is not unit:
                out += [(unit, dest), other]
        return out

    def _update_facings(self, movers):
        """Orientation après le mouvement. Au contact, on fait face à un
        ennemi collé à soi (sa cible s'il en est, sinon le plus dangereux):
        personne ne tourne le dos à qui le touche pour regarder plus loin.
        Sinon on fait face à sa cible à portée, ou on regarde où l'on
        marche. Un fuyard tourne le dos. Sans mouvement ni adversaire,
        l'orientation ne change pas."""
        for u in self.get_all_alive():
            if not u.is_alive or u.position is None:
                continue
            if u.fleeing:
                look = None
            else:
                look = self._facing_target(u)
            if look is not None:
                # Pivot payé: un demi-tour coûte une case (facing.turn_toward)
                facing.turn_to_unit(u, look)
            elif id(u) in movers and not u._backpedal:
                # Le demi-tour éventuel est déjà compté dans le coût de la
                # marche (Battlefield._walk_costs): on regarde où l'on va
                path = u._move_path or list(movers[id(u)])
                d = facing.direction(path[-2], path[-1]) if len(path) > 1 else None
                if d is not None:
                    u.facing = d

    def _facing_target(self, u):
        """Ennemi vers lequel une unité se tourne (None: garder son cap)."""
        ux, uy = u.position
        t = u.current_target
        bf = self.battlefield
        my_cells = bf.get_unit_cells(u) if u.size > 1 else ((ux, uy),)
        adjacent = []
        for e in self.enemies_near(u, 5):
            if abs(e.position[0] - ux) > 5 or abs(e.position[1] - uy) > 5:
                continue
            e_cells = bf.get_unit_cells(e) if e.size > 1 else (e.position,)
            if any(abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1
                   for a in my_cells for b in e_cells):
                adjacent.append(e)
        if adjacent:
            if t in adjacent:
                return t
            return max(adjacent, key=lambda e: (tactics.expected_damage(e, u), -e.uid))
        if (t is not None and t.is_alive and t.position is not None
                and abs(ux - t.position[0]) + abs(uy - t.position[1]) <= u._max_range + 1):
            return t
        return None

    def _position_bonuses(self, alive):
        """Bonus de position du round: rempart et phalange."""
        # Phase Rempart: mettre à jour _on_wall dynamiquement
        for unit in alive:
            unit._on_wall = self.battlefield.is_rampart(*unit.position)

        # Phase Phalange: +1 sauvegarde si adjacent à un allié phalange
        for unit in alive:
            unit._phalange_bonus_active = False
        for unit in alive:
            if not unit.phalange or not unit.is_alive:
                continue
            for ally in self.get_allies(unit):
                if not ally.is_alive or not ally.phalange or ally == unit:
                    continue
                if self.battlefield.manhattan_distance(unit.position, ally.position) <= 1:
                    # Lu par la propriété Unit.sauvegarde (-1 au seuil)
                    unit._phalange_bonus_active = True
                    break

    def _exchange_phase(self):
        """Échange général dans l'ordre d'initiative (sorts, machines, porte, attaque, élan)."""
        # ═══════════════════════════════════════════════════════════
        #   ÉCHANGE GÉNÉRAL — résolu dans l'ORDRE D'INITIATIVE
        # ═══════════════════════════════════════════════════════════
        # Qui frappe en premier compte (un mort ne riposte pas) et chaque
        # action est horodatée: à l'écran, les coups s'enchaînent au lieu
        # de tomber tous ensemble.
        self._alive_cache['dirty'] = True
        act_order = self._initiative_order(
            [u for u in self.get_all_alive() if u.is_alive])
        n_act = max(1, len(act_order))
        span = T_ACTION_END - T_ACTION_START

        for idx, unit in enumerate(act_order):
            if not unit.is_alive:
                continue
            t01 = T_ACTION_START + span * (idx / n_act)
            self._set_action_time(t01)

            # Sorts (le lanceur agit à son tour d'initiative)
            if unit.spells:
                self._apply_combat_events(unit.cast_random_spell(self))
                self._set_action_time(t01)

            if unit._acted_this_round:
                continue  # a déjà tiré en réaction pendant le mouvement
            if not siege_engines.manned(self.battlefield, self, unit):
                # Machine sans ses deux artilleurs, engin sans pousseurs
                unit._acted_this_round = True
                unit.floating_texts.append(
                    FloatingText("Sans servants", (190, 170, 150), 30))
                continue

            # Machine de guerre: percer le mur ou dégager son champ de tir
            # (avant la porte: une machine chargée de percer ne la vise pas).
            # Battre un mur ou une porte garde le même réglage de tir: pas
            # de rechargement, contrairement au tir sur des hommes.
            if self._attack_structure(unit):
                unit._acted_this_round = True
                continue
            # Siège: enfoncer la porte compte comme action du round
            if self._attack_gate(unit):
                unit._acted_this_round = True
                continue
            if unit.siege_engine == siege_engines.RAM:
                continue        # le bélier ne frappe que les portes

            if unit.reloading:
                unit._acted_this_round = True
                unit.floating_texts.append(
                    FloatingText("Recharge…", (170, 170, 190), 30))
                continue
            target = self._choose_attack_target(unit)
            if target and unit._max_range >= 4 and unit.spares_ammo(target, self.battlefield):
                unit._acted_this_round = True
                continue
            if target:
                self._apply_combat_events(
                    unit.perform_attacks(target, self.battlefield, self))
                unit._acted_this_round = True
                unit.mark_fired()
                self._momentum_followup(unit, t01 + 0.05)

    def _end_of_round_effects(self, alive):
        """Fin de round: phalange, régénération, buffs, incendie, murs temporaires."""
        # Reset phalange bonus en fin de round
        for unit in alive:
            unit._phalange_bonus_active = False

        # Régénération + tick buffs
        FX_CLOCK.at(int(self.fx_frames_per_round * 0.9))
        for unit in self.army1 + self.army2:
            unit.regenerate()
            unit.tick_armor_buff()
        self._fire_phase()
        FX_CLOCK.at(0)

        # Murs temporaires: décrémenter et retirer
        if hasattr(self.battlefield, '_temp_walls'):
            remaining = []
            for entry in self.battlefield._temp_walls:
                if len(entry) == 4:
                    wx, wy, dur, original = entry
                else:
                    wx, wy, dur = entry
                    original = 0
                if dur <= 1:
                    self.battlefield.grid[wx][wy] = original
                else:
                    remaining.append((wx, wy, dur - 1, original))
            self.battlefield._temp_walls = remaining

    def _remove_casualties(self):
        """Retire les morts de la grille (animation de chute, camarades témoins)."""
        # Nettoyer les unités mortes de la grille (+ effet de mort en fondu)
        self._refresh_army_sets()
        cs_fx = self.cell_size
        dead_units_seen = set()
        for pos, unit in list(self.battlefield.units.items()):
            if not unit.is_alive and unit.down_timer <= 0 and id(unit) not in dead_units_seen:
                dead_units_seen.add(id(unit))
                # Voir tomber le camarade d'à côté est ce qui ébranle
                # vraiment une troupe — bien plus qu'un tir lointain.
                dx_d, dy_d = unit.position
                for a_w in self.get_allies(unit):
                    if (a_w.is_alive and a_w is not unit
                            and abs(a_w.position[0] - dx_d) + abs(a_w.position[1] - dy_d) <= 2):
                        a_w._witnessed_deaths += 1
                w_u, h_u = self.battlefield.get_unit_dims(unit)
                px_fx = unit.position[0] * cs_fx + (w_u * cs_fx) // 2
                py_fx = unit.position[1] * cs_fx + (h_u * cs_fx) // 2
                pp = unit._prev_position or unit.position
                from_fx = (pp[0] * cs_fx + (w_u * cs_fx) // 2,
                           pp[1] * cs_fx + (h_u * cs_fx) // 2)
                team_c = (60, 120, 220) if id(unit) in self._army1_ids else (220, 60, 60)
                # La victime tombe dans le sens du coup reçu
                killer = getattr(unit, '_last_attacker', None)
                if (killer is not None and killer.position is not None
                        and killer.position != unit.position):
                    fall = math.atan2(unit.position[1] - killer.position[1],
                                      unit.position[0] - killer.position[0])
                else:
                    fall = _FX_RNG.uniform(0, math.tau)
                self.visual_effects.setdefault('deaths', []).append(
                    DeathAnimation(from_fx, (px_fx, py_fx), (w_u, h_u),
                                   unit.token_name, unit.color, team_c, fall,
                                   texts=list(unit.floating_texts), duration=70,
                                   delay=getattr(unit, '_hit_flash_delay', 0),
                                   seed=id(unit) & 0xFFFF))
                self.battlefield.remove_unit(unit)

    def _handle_routers(self):
        """Fuyards qui quittent la carte et fin de partie enlisée."""
        bf = self.battlefield
        # Fuyards qui atteignent le bord → quittent la map
        for army_list, fled_list in [(self.army1, self.army1_fled), (self.army2, self.army2_fled)]:
            for unit in army_list[:]:
                if unit.fleeing and unit.is_alive:
                    if not hasattr(unit, '_flee_rounds'):
                        unit._flee_rounds = 0
                    unit._flee_rounds += 1
                    x, y = unit.position
                    at_border = (x <= 0 or x >= bf.width - 1 or y <= 0 or y >= bf.height - 1)
                    if at_border and unit._flee_rounds >= 2:
                        unit.fled = True
                        unit.is_alive = False
                        bf.remove_unit(unit)
                        fled_list.append(unit)
                        army_list.remove(unit)

        # ── Fin de partie enlisée ──
        # Quelques survivants isolés, sans plus aucun combat depuis
        # longtemps, face à une armée bien plus nombreuse: ils ne tiennent pas
        # le champ de bataille, ils se débandent. Sans cela, un dernier
        # soldat réfugié dans un coin pouvait faire durer la partie sans fin.
        fighting = any(u._damage_taken_round > 0 for u in self.army1 + self.army2)
        self._quiet_rounds = 0 if fighting else getattr(self, '_quiet_rounds', 0) + 1
        if self._quiet_rounds >= 10:
            n1 = sum(1 for u in self.army1 if u.is_alive and not u.fleeing)
            n2 = sum(1 for u in self.army2 if u.is_alive and not u.fleeing)
            for army, mine, theirs in ((self.army1, n1, n2), (self.army2, n2, n1)):
                if mine and theirs and mine * 4 <= theirs:
                    for u in army:
                        if u.is_alive and not u.fleeing:
                            u.fleeing = True
                            u.status_text = "DÉROUTE"
                            u.floating_texts.append(FloatingText("Déroute!", (255, 100, 50), 80))
                    self.log_event("Les derniers survivants abandonnent le terrain !", (255, 120, 60), 2)
                    self._quiet_rounds = 0

    def is_battle_over(self):
        """La bataille est finie quand une armée n'a plus personne sur la map.
        Des engins de siège seuls ne tiennent pas le terrain: leurs servants
        les abandonnent quand il ne reste plus de troupes pour les couvrir."""
        a1_on_map = sum(1 for u in self.army1 if u.is_alive and not u.siege_engine)
        a2_on_map = sum(1 for u in self.army2 if u.is_alive and not u.siege_engine)
        
        if a1_on_map == 0 and a2_on_map == 0:
            return "Égalité"
        if a1_on_map == 0:
            return "Armée 2"
        if a2_on_map == 0:
            return "Armée 1"
        return None

    def get_battle_report(self):
        """Génère le rapport de fin de bataille.
        Les survivants de l'armée perdante sont considérés comme fuyants."""
        winner = self.is_battle_over()
        
        def count_by_name(unit_list):
            """Groupe les unités par token_name → [(name, count), ...]"""
            counts = {}
            for u in unit_list:
                n = u.token_name
                counts[n] = counts.get(n, 0) + 1
            return sorted(counts.items(), key=lambda x: -x[1])
        
        def army_report(roster, fled_list, name, is_winner):
            all_alive = [u for u in roster if u.is_alive and not u.fled]
            all_dead = [u for u in roster if not u.is_alive and not u.fled]
            # Sortis de la carte seulement: les fuyards encore sur la carte
            # sont déjà dans all_alive (les y ajouter les comptait deux fois)
            all_fled_off = fled_list[:]

            if is_winner:
                # Gagnant: vivants = ceux qui ne fuient pas, fuyants = ceux qui fuient
                alive = [u for u in all_alive if not u.fleeing]
                fled = [u for u in all_alive if u.fleeing] + all_fled_off
            else:
                # Perdant: tous les survivants sont des fuyants
                alive = []
                fled = all_alive + all_fled_off

            # ── Détail par contingent ──
            # Une équipe peut aligner plusieurs armées alliées: on rend des
            # comptes séparés, sinon impossible de savoir quel corps a tenu
            # et lequel s'est effondré.
            order, per = [], {}

            def _bucket(unit_list, key_name):
                for u in unit_list:
                    k = u.contingent or name
                    if k not in per:
                        per[k] = {'name': k, 'total': 0, 'alive_count': 0,
                                  'dead_count': 0, 'fled_count': 0}
                        order.append(k)
                    per[k][key_name] += 1
                    per[k]['total'] += 1

            _bucket(alive, 'alive_count')
            _bucket(fled, 'fled_count')
            _bucket(all_dead, 'dead_count')

            return {
                'name': name,
                'total': len(roster),
                'alive': count_by_name(alive),
                'alive_count': len(alive),
                'dead': count_by_name(all_dead),
                'dead_count': len(all_dead),
                'fled': count_by_name(fled),
                'fled_count': len(fled),
                'contingents': [per[k] for k in order],
            }

        w1 = (winner == "Armée 1")
        w2 = (winner == "Armée 2")
        
        r1 = army_report(self.army1_roster, self.army1_fled, "Armée 1", w1)
        r2 = army_report(self.army2_roster, self.army2_fled, "Armée 2", w2)
        
        return {
            'winner': winner or "En cours",
            'rounds': self.round - 1,
            'army1': r1,
            'army2': r2,
        }