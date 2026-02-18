import copy
import random

from battlefield import Battlefield
from effects import FloatingText, AttackLine
from ai_commander import CommanderAI


class Battle:
    def __init__(self, army1, army2, battlefield_width=40, battlefield_height=30, 
                 obstacle_count=8, map_name="Prairie"):
        self.army1 = copy.deepcopy(army1)
        self.army2 = copy.deepcopy(army2)
        self.map_name = map_name
        
        # Générer la map
        from maps import generate_map
        grid, map_data = generate_map(map_name, battlefield_width, battlefield_height)
        self.battlefield = Battlefield(battlefield_width, battlefield_height, 
                                        obstacle_count, map_name, grid, map_data)
        self.round = 1
        self.visual_effects = {'projectiles': [], 'attack_lines': [], 'target_indicators': []}
        
        self.army1_initial_size = len(self.army1)
        self.army2_initial_size = len(self.army2)
        
        self.army1_roster = list(self.army1)
        self.army2_roster = list(self.army2)
        
        self.army1_fled = []
        self.army2_fled = []
        
        self._alive_cache = {'army1': [], 'army2': [], 'dirty': True}
        
        center_y = self.battlefield.height // 2
        self._place_armies(center_y)
        
        # Commandants IA
        self.commander1 = CommanderAI(self.army1, self.army2, self.battlefield, is_army1=True)
        self.commander2 = CommanderAI(self.army2, self.army1, self.battlefield, is_army1=False)
        
        # Initialiser les positions d'animation (pas de transition au premier frame)
        for u in self.army1 + self.army2:
            u._prev_position = u.position

    def _place_armies(self, center_y):
        bf = self.battlefield
        usable_height = bf.height - 2
        max_per_col = max(1, usable_height)
        
        def place_role_units(units, base_x, center_y, step_x, min_x=0):
            if not units:
                return
            columns = []
            remaining = list(units)
            while remaining:
                chunk = remaining[:max_per_col]
                remaining = remaining[max_per_col:]
                columns.append(chunk)
            for col_idx, col_units in enumerate(columns):
                x_col = base_x + col_idx * step_x
                x_col = max(min_x, min(bf.width - 1, x_col))
                self._place_column(col_units, x_col, center_y, bf, min_x=min_x)
        
        def place_back_spread(units, base_x, center_y, step_x, min_x=0):
            """Place les unités back en les étalant sur toute la hauteur.
            Les unités large (size >= 2) sont espacées uniformément."""
            if not units:
                return
            # Séparer large et normal
            large = [u for u in units if u.size >= 2]
            normal = [u for u in units if u.size < 2]
            
            # Étaler les large uniformément sur la hauteur
            if large:
                usable = bf.height - 4
                spacing = max(4, usable // (len(large) + 1))
                for i, u in enumerate(large):
                    target_y = 2 + spacing * (i + 1)
                    target_y = max(2, min(bf.height - 3 - bf.get_unit_dims(u)[1], target_y))
                    pos = (base_x, target_y)
                    if not bf.can_place_unit(*pos, u):
                        pos = self._find_free_near_unit(base_x, target_y, u, bf, min_x=min_x)
                    if pos is not None:
                        u.position = pos
                        bf.place_unit(u)
            
            # Placer le reste normalement
            if normal:
                self._place_column(normal, base_x, center_y, bf, min_x=min_x)
        
        army1_roles = {'front': [], 'mid': [], 'back': []}
        army2_roles = {'front': [], 'mid': [], 'back': []}
        
        for u in self.army1:
            army1_roles[u.role].append(u)
        for u in self.army2:
            army2_roles[u.role].append(u)
        
        import random as _rng
        for roles in (army1_roles, army2_roles):
            for role_list in roles.values():
                _rng.shuffle(role_list)
        
        # Placement attaquant (armée 1) — à gauche du centre
        # Lignes resserrées pour que l'armée avance de manière cohésive
        mid_x = bf.width // 2
        gap = 12  # demi-écart: 12 cases de chaque côté = 24-25 cases entre fronts
        
        a1_front = mid_x - gap
        a1_mid   = a1_front - 1   # mid juste derrière front (1 case)
        a1_back  = a1_front - 2   # back 2 cases derrière (au lieu de 4)
        
        place_role_units(army1_roles['front'], a1_front, center_y, -1)
        place_role_units(army1_roles['mid'],   a1_mid,   center_y, -1)
        place_back_spread(army1_roles['back'],  a1_back,  center_y, -1)
        
        if self.map_name == "Siège":
            wall_x = bf.siege_data.get('wall_x', bf.width * 2 // 3)
            defender_min_x = wall_x + 1
            gate_positions = bf.siege_data.get('gate_positions', [])
            gate_center = gate_positions[0] if gate_positions else center_y
            
            # Trouver les Y des portes (cases type 3 sur wall_x)
            gate_y_set = set()
            for y in range(bf.height):
                if bf.grid[wall_x][y] == 3:
                    gate_y_set.add(y)
            # Zone porte élargie (±2 cases) pour garder les CaC proches
            gate_zone = set()
            for gy in gate_y_set:
                for dy in range(-2, 3):
                    gate_zone.add(gy + dy)
            
            # === Séparer les unités par CAPACITÉ, pas par rôle ===
            # Tireurs = unités avec arme portée >= 4 OU mage avec sorts
            # CaC = tout le reste (y compris officiers sans arme à distance)
            wall_units = []    # Vont sur les remparts (tireurs + mages)
            gate_units = []    # Vont derrière la porte (CaC + officiers)
            
            all_defenders = army2_roles['front'] + army2_roles['mid'] + army2_roles['back']
            for u in all_defenders:
                if u._max_range >= 4 or u.spells:
                    wall_units.append(u)
                else:
                    gate_units.append(u)
            
            # === Cases rempart disponibles, triées par distance à la porte ===
            # Alterner haut/bas de la porte pour étaler les tireurs
            rampart_slots = []
            for y in range(1, bf.height - 1):
                if y not in gate_zone and bf.grid[wall_x + 1][y] == 4:
                    rampart_slots.append(y)
            
            # Trier par distance au centre de la porte (les plus proches d'abord)
            # en alternant haut et bas pour un étalement symétrique
            rampart_above = sorted([y for y in rampart_slots if y < gate_center], reverse=True)
            rampart_below = sorted([y for y in rampart_slots if y >= gate_center])
            rampart_sorted = []
            i_a, i_b = 0, 0
            while i_a < len(rampart_above) or i_b < len(rampart_below):
                if i_b < len(rampart_below):
                    rampart_sorted.append(rampart_below[i_b])
                    i_b += 1
                if i_a < len(rampart_above):
                    rampart_sorted.append(rampart_above[i_a])
                    i_a += 1
            
            # === TIREURS/MAGES → remparts étalés autour de la porte ===
            placed_wall = set()
            for u in wall_units:
                placed = False
                for ry in rampart_sorted:
                    if ry in placed_wall:
                        continue
                    pos = (wall_x + 1, ry)
                    if bf.can_place_unit(*pos, u):
                        u.position = pos
                        bf.place_unit(u)
                        placed_wall.add(ry)
                        placed = True
                        break
                if not placed:
                    # Débordement: 2e rang de rempart (wall_x + 2)
                    for ry in rampart_sorted:
                        pos = (wall_x + 2, ry)
                        if bf.can_place_unit(*pos, u):
                            u.position = pos
                            bf.place_unit(u)
                            placed = True
                            break
                if not placed:
                    # Dernier recours
                    pos = self._find_free_near_unit(wall_x + 2, gate_center, u, bf, min_x=defender_min_x)
                    if pos:
                        u.position = pos
                        bf.place_unit(u)
            
            # === CaC → derrière la porte (PAS sur le rempart) ===
            # Cases valides: juste derrière la porte (wall_x+1 sur les Y de porte)
            # puis débordement sur wall_x+2, wall_x+3 etc.
            gate_ys_sorted = sorted(gate_y_set)
            
            placed_gate_positions = set()
            for u in gate_units:
                placed = False
                # D'abord: cases directement derrière la porte (non-rempart)
                for dx in range(1, 6):
                    for gy in gate_ys_sorted:
                        pos = (wall_x + dx, gy)
                        if pos in placed_gate_positions:
                            continue
                        cell = bf.grid[pos[0]][pos[1]] if 0 <= pos[0] < bf.width and 0 <= pos[1] < bf.height else -1
                        # Éviter les remparts pour les CaC
                        if cell == 4:
                            continue
                        if bf.can_place_unit(*pos, u):
                            u.position = pos
                            bf.place_unit(u)
                            placed_gate_positions.add(pos)
                            placed = True
                            break
                    if placed:
                        break
                
                if not placed:
                    # Débordement: chercher une case libre proche de la porte, pas sur rempart
                    for dx in range(1, 8):
                        for dy_offset in range(0, bf.height // 2):
                            for sign in [1, -1]:
                                ny = gate_center + dy_offset * sign
                                pos = (wall_x + dx, ny)
                                if not (0 <= pos[0] < bf.width and 0 <= pos[1] < bf.height):
                                    continue
                                cell = bf.grid[pos[0]][pos[1]]
                                if cell == 4:  # Pas de CaC sur rempart
                                    continue
                                if pos in placed_gate_positions:
                                    continue
                                if bf.can_place_unit(*pos, u):
                                    u.position = pos
                                    bf.place_unit(u)
                                    placed_gate_positions.add(pos)
                                    placed = True
                                    break
                            if placed:
                                break
                        if placed:
                            break
            
            # Ouvrir les portes si l'armée 2 n'a aucune unité à distance
            has_ranged = any(u._max_range >= 4 for u in self.army2 if u.is_alive)
            if not has_ranged:
                for pos in bf.gate_hp:
                    bf.gate_hp[pos] = 0
        else:
            a2_front = mid_x + gap
            a2_mid   = a2_front + 1
            a2_back  = a2_front + 2
            
            place_role_units(army2_roles['front'], a2_front, center_y, +1)
            place_role_units(army2_roles['mid'],   a2_mid,   center_y, +1)
            place_back_spread(army2_roles['back'],  a2_back,  center_y, +1)
    
    def _place_column(self, units, x_col, center_y, bf, min_x=0):
        if not units:
            return
        units_sorted = sorted(units, key=lambda u: -u.size)
        total_h = sum(bf.get_unit_dims(u)[1] for u in units_sorted)
        start_y = center_y - total_h // 2
        
        cur_y = start_y
        for u in units_sorted:
            w, h = bf.get_unit_dims(u)
            target_y = max(1, min(bf.height - 1 - h, cur_y))
            pos = (x_col, target_y)
            if not bf.can_place_unit(*pos, u):
                pos = self._find_free_near_unit(x_col, target_y, u, bf, min_x=min_x)
            if pos is not None:
                u.position = pos
                bf.place_unit(u)
            cur_y += h

    def _find_free_near_unit(self, x, y, unit, bf, min_x=0):
        """Cherche une position libre pour une unité (multi-cases supporté)."""
        for radius in range(0, max(bf.width, bf.height)):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) != radius and abs(dy) != radius:
                        continue
                    nx, ny = x + dx, y + dy
                    if nx < min_x:
                        continue
                    if bf.can_place_unit(nx, ny, unit):
                        return (nx, ny)
        return None

    def get_all_alive(self):
        if self._alive_cache['dirty']:
            self._alive_cache['army1'] = [u for u in self.army1 if u.is_alive]
            self._alive_cache['army2'] = [u for u in self.army2 if u.is_alive]
            self._alive_cache['all'] = self._alive_cache['army1'] + self._alive_cache['army2']
            self._alive_cache['dirty'] = False
        return self._alive_cache['all']

    def _refresh_army_sets(self):
        """Met à jour les sets d'appartenance pour O(1) lookup."""
        if not hasattr(self, '_army1_ids') or self._alive_cache['dirty']:
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

    def _get_initial_size(self, unit):
        """Retourne la taille initiale de l'armée de cette unité."""
        if unit in self.army1:
            return self.army1_initial_size
        return self.army2_initial_size

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
        
        # --- 0b) Siège: défenseurs derrière le mur intact → +1 bravoure ---
        if self.map_name == "Siège":
            wall_x = self.battlefield.siege_data.get('wall_x', 0)
            has_intact_gates = any(hp > 0 for hp in self.battlefield.gate_hp.values())
            if has_intact_gates:
                for unit in self.army2:
                    if unit.is_alive and not unit.fleeing and unit.position[0] >= wall_x:
                        unit.morale_bonus = max(unit.morale_bonus, unit.morale_bonus + 1)
        
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
                        unit.morale_malus += 1
                        unit.floating_texts.append(
                            FloatingText("-1 Moral (Pertes!)", (255, 100, 60), 90))
                        
                        if unit.get_effective_morale() <= 0:
                            unit.fleeing = True
                            unit.status_text = "FUITE!"
                            unit.floating_texts.append(
                                FloatingText("FUITE!", (255, 50, 50), 100))
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
                        unit.morale_malus += 1
                        unit.floating_texts.append(
                            FloatingText("-1 Moral (Déroute!)", (255, 50, 50), 90))
                        
                        if unit.get_effective_morale() <= 0:
                            unit.fleeing = True
                            unit.status_text = "FUITE!"
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
                unit.apply_fear_effect(max_aura, min_dist)
            else:
                if unit.afraid and not unit.fleeing:
                    unit.afraid = False
                    unit.status_text = ""
        
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

    def _charge_phase(self, alive, cell_size):
        """Phase de charge: les unités avec charge se ruent sur un ennemi à distance de charge.
        
        Nerfé: portée réduite (vitesse à 1.5x au lieu de 2x), nécessite un chemin libre,
        et seule la PREMIÈRE arme est utilisée lors de l'attaque de charge.
        """
        for unit in alive:
            if not unit.is_alive or unit.fleeing:
                continue
            if not unit.charge_montee and not unit.charge_aida:
                continue
            
            # Distance de charge réduite: entre vitesse et 1.5x vitesse (au lieu de 2x)
            min_dist = unit.vitesse
            max_dist = int(unit.vitesse * 1.5)
            
            # Trouver un ennemi dans la zone de charge
            best_target = None
            best_dist = 999
            for enemy in self.get_enemies(unit):
                if not enemy.is_alive:
                    continue
                d = self.battlefield.manhattan_distance(unit.position, enemy.position)
                if min_dist <= d <= max_dist and d < best_dist:
                    best_target = enemy
                    best_dist = d
            
            if not best_target:
                continue
            
            # Trouver une case adjacente à la cible pour charger
            tx, ty = best_target.position
            charge_pos = None
            charge_dist = 999
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = tx + dx, ty + dy
                    if self.battlefield._can_move_to(unit, (nx, ny), set()):
                        d = self.battlefield.manhattan_distance(unit.position, (nx, ny))
                        if d < charge_dist:
                            charge_pos = (nx, ny)
                            charge_dist = d
            
            if not charge_pos:
                continue
            
            # Vérifier qu'il y a un chemin libre (pas de téléportation à travers les alliés)
            path = self.battlefield.a_star_path(unit.position, charge_pos, unit, self)
            if not path or len(path) > max_dist:
                continue
            
            # Déplacer l'unité vers la cible (charge!)
            self.battlefield.move_unit(unit, charge_pos)
            unit.has_charged = True
            
            # Effet visuel: ligne de charge
            start_px = (unit.position[0] * cell_size + cell_size // 2,
                        unit.position[1] * cell_size + cell_size // 2)
            end_px = (best_target.position[0] * cell_size + cell_size // 2,
                      best_target.position[1] * cell_size + cell_size // 2)
            
            charge_color = (255, 200, 50) if unit.charge_montee else (100, 200, 255)
            self.visual_effects['attack_lines'].append(
                AttackLine(start_px, end_px, charge_color, 35)
            )
            
            label = "CHARGE!" if unit.charge_montee else "CHARGE D'AÏDA!"
            unit.floating_texts.append(FloatingText(label, charge_color, 70))
            
            # Attaque de charge: seulement la première arme CaC (pas toutes les armes)
            if unit.armes:
                melee_armes = [a for a in unit.armes if a.porte <= 2]
                if melee_armes:
                    saved_armes = unit.armes
                    unit.armes = [melee_armes[0]]
                    unit.perform_attacks(best_target, self.battlefield, self.visual_effects, cell_size)
                    unit.armes = saved_armes
                else:
                    unit.perform_attacks(best_target, self.battlefield, self.visual_effects, cell_size)

    def simulate_round(self, cell_size):
        self._alive_cache['dirty'] = True
        self.visual_effects['target_indicators'] = []
        
        # Déroute: si une armée n'a plus de combattants, tous les restants fuient
        for army in [self.army1, self.army2]:
            fighters = sum(1 for u in army if u.is_alive and not u.fleeing)
            if fighters == 0:
                for u in army:
                    if u.is_alive and not u.fleeing:
                        u.fleeing = True
                        u.status_text = "DÉROUTE"
                        u.floating_texts.append(FloatingText("Déroute!", (255, 100, 50), 80))
        
        # === PHASE DE COMMANDEMENT: les IA assignent les ordres ===
        self.commander1.issue_orders(self)
        self.commander2.issue_orders(self)
        
        alive = self.get_all_alive()
        
        # === MOUVEMENT COHÉSIF EN 3 PASSES ===
        # Pass 1: fuyards et artillerie (statiques)
        # Pass 2: unités engagées (déjà au contact) — micro-ajustent
        # Pass 3: unités en approche — avancent en formation avec étalement
        #   - Triées du FOND vers l'AVANT pour que les arrières ne soient pas
        #     bloqués par les unités de front qui réservent tout devant elles
        
        bf = self.battlefield
        
        static_units = []   # Fuyards, artillerie
        engaged = []        # Au contact (distance ≤ portée+1)
        approaching = []    # En approche (pas encore au contact)
        
        for u in alive:
            if u.fleeing or u.vitesse <= 0:
                static_units.append(u)
                continue
            # Siège: tireurs/mages sur rempart → toujours "engaged" (ne bougent pas)
            if bf.gate_hp and bf.is_rampart(*u.position) and (u._max_range >= 4 or bool(u.spells)):
                engaged.append(u)
                continue
            enemies = self.get_enemies(u)
            alive_enemies = [e for e in enemies if e.is_alive]
            if alive_enemies:
                min_d = min(bf.manhattan_distance(u.position, e.position) for e in alive_enemies)
                if min_d <= u._max_range + 1:
                    engaged.append(u)
                else:
                    approaching.append(u)
            else:
                static_units.append(u)
        
        # === Pass 1: statiques — réservent leur position ===
        reserved = set()
        moves = {}
        
        for unit in static_units:
            new_pos, target = bf.compute_move(unit, self, reserved)
            unit.current_target = target
            if target:
                self.visual_effects['target_indicators'].append((unit, target))
            if new_pos and bf._can_move_to(unit, new_pos, reserved):
                moves[unit] = new_pos
                reserved.update(bf._get_reserved_cells(unit, new_pos))
            elif unit.position:
                reserved.update(bf._get_reserved_cells(unit, unit.position))
        
        # === Pass 2: engagées — se déplacent, triées par proximité ===
        engaged.sort(key=lambda u: min(
            (bf.manhattan_distance(u.position, e.position)
             for e in self.get_enemies(u) if e.is_alive), default=999))
        
        for unit in engaged:
            new_pos, target = bf.compute_move(unit, self, reserved)
            unit.current_target = target
            if target:
                self.visual_effects['target_indicators'].append((unit, target))
            if new_pos and bf._can_move_to(unit, new_pos, reserved):
                moves[unit] = new_pos
                reserved.update(bf._get_reserved_cells(unit, new_pos))
            elif unit.position:
                reserved.update(bf._get_reserved_cells(unit, unit.position))
        
        # === Pass 3: en approche — avance cohésive ===
        # Trier les approchants du PLUS LOIN au PLUS PROCHE de l'ennemi
        # Ainsi les unités de derrière réservent d'abord leur destination
        # et les unités de devant s'adaptent (au lieu de tout bloquer)
        approaching.sort(key=lambda u: min(
            (bf.manhattan_distance(u.position, e.position)
             for e in self.get_enemies(u) if e.is_alive), default=999),
            reverse=True)
        
        # Calculer la distance min de l'ennemi parmi les approchants
        # pour limiter la vitesse des plus rapides (cohésion)
        if approaching:
            approach_dists = []
            for u in approaching:
                ae = [e for e in self.get_enemies(u) if e.is_alive]
                if ae:
                    approach_dists.append(
                        min(bf.manhattan_distance(u.position, e.position) for e in ae))
            if approach_dists:
                median_dist = sorted(approach_dists)[len(approach_dists) // 2]
            else:
                median_dist = 999
        
        for unit in approaching:
            # Cohésion: les unités très en avance ralentissent pour ne pas
            # se retrouver isolées. On limite la vitesse effective si l'unité
            # est significativement plus proche que la médiane de son armée.
            ae = [e for e in self.get_enemies(unit) if e.is_alive]
            if ae:
                my_dist = min(bf.manhattan_distance(unit.position, e.position) for e in ae)
            else:
                my_dist = 999
            
            # Si l'unité est > 6 cases en avance de la médiane, elle ralentit
            orig_speed = unit.vitesse
            advance_gap = median_dist - my_dist
            if advance_gap > 6 and unit._max_range < 4:
                # Unité très en avance: ralentir (vitesse min 1)
                unit.vitesse = max(1, orig_speed - 1)
            
            new_pos, target = bf.compute_move(unit, self, reserved)
            unit.current_target = target
            if target:
                self.visual_effects['target_indicators'].append((unit, target))
            if new_pos and bf._can_move_to(unit, new_pos, reserved):
                moves[unit] = new_pos
                reserved.update(bf._get_reserved_cells(unit, new_pos))
            elif unit.position:
                # Bloqué: essayer un mouvement latéral SEULEMENT si pas d'ennemi au contact
                # (sinon on risque de s'éloigner d'un ennemi qu'on devrait combattre)
                ux, uy = unit.position
                enemy_in_range = any(
                    abs(ux - e.position[0]) + abs(uy - e.position[1]) <= unit._max_range
                    for e in self.get_enemies(unit) if e.is_alive
                )
                if not enemy_in_range:
                    alt_pos = bf.find_lateral_advance(unit, self, reserved)
                    if alt_pos and bf._can_move_to(unit, alt_pos, reserved):
                        moves[unit] = alt_pos
                        reserved.update(bf._get_reserved_cells(unit, alt_pos))
                    else:
                        reserved.update(bf._get_reserved_cells(unit, unit.position))
                else:
                    reserved.update(bf._get_reserved_cells(unit, unit.position))
            
            # Restaurer la vitesse originale
            unit.vitesse = orig_speed
        
        for unit, new_pos in moves.items():
            bf.move_unit(unit, new_pos)
        
        # Phase de moral (pertes lourdes + auras + stress au combat)
        self.morale_phase()
        
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
                dist = self.battlefield.manhattan_distance(unit.position, ally.position)
                if dist <= 1:
                    if not unit._phalange_bonus_active:
                        unit._phalange_bonus_active = True
                        unit.sauvegarde = max(1, unit.sauvegarde - 1)
                    break  # Un seul bonus suffit
        
        # Phase de Charge (avant les attaques normales)
        self._charge_phase(alive, cell_size)
        
        # Sorts
        for unit in alive:
            if unit.spells and unit.is_alive:
                unit.cast_random_spell(self, self.visual_effects, cell_size)
        
        # Attaques
        _units_attacked_gate = set()
        
        # Phase de siège: attaque des portes (AVANT attaques normales)
        if self.battlefield.gate_hp and any(h > 0 for h in self.battlefield.gate_hp.values()):
            gate_save = self.battlefield.gate_save
            for unit in self.army1:
                if not unit.is_alive or unit.fleeing:
                    continue
                ux, uy = unit.position
                
                best_gate = None
                best_gate_dist = 999
                for gpos, ghp in self.battlefield.gate_hp.items():
                    if ghp <= 0:
                        continue
                    d = self.battlefield.manhattan_distance((ux, uy), gpos)
                    if d < best_gate_dist:
                        best_gate = gpos
                        best_gate_dist = d
                
                if best_gate is None:
                    continue
                
                gx, gy = best_gate
                is_artillery = (unit.vitesse <= 0)
                
                total_dmg = 0
                for arme in unit.armes:
                    if arme.porte < 4 and best_gate_dist > 1:
                        continue
                    if arme.porte >= 4 and best_gate_dist > arme.porte:
                        continue
                    # Arbalétriers/archers mobiles: priorité ennemis
                    # Artillerie (vitesse 0): tire sur portes même s'il y a des ennemis
                    if arme.porte >= 4 and not is_artillery:
                        enemies_in_range = any(
                            e.is_alive and self.battlefield.manhattan_distance((ux, uy), e.position) <= arme.porte
                            for e in self.army2
                        )
                        if enemies_in_range:
                            continue
                    
                    for _ in range(arme.nb_attaque):
                        gate_save_mod = min(7, gate_save - arme.perforation)
                        save_roll = random.randint(1, 6)
                        if save_roll >= gate_save_mod:
                            continue
                        total_dmg += max(1, arme.lancer_degats())
                
                if total_dmg > 0:
                    destroyed = self.battlefield.damage_gate(gx, gy, total_dmg)
                    hp_left = self.battlefield.gate_hp.get((gx, gy), 0)
                    unit.floating_texts.append(
                        FloatingText(f"-{total_dmg} Porte ({hp_left})", (200, 150, 50), 40))
                    _units_attacked_gate.add(id(unit))
                    if destroyed:
                        unit.floating_texts.append(
                            FloatingText("PORTE DÉTRUITE!", (255, 200, 50), 90))
                elif best_gate_dist <= 1 and unit._max_range < 4:
                    unit.floating_texts.append(
                        FloatingText("Porte résiste!", (150, 130, 80), 30))
                    _units_attacked_gate.add(id(unit))
        
        # Attaques normales (unités qui n'ont pas tapé une porte)
        from ai_commander import select_tactical_target
        for unit in alive:
            if unit.is_alive and id(unit) not in _units_attacked_gate:
                target = select_tactical_target(unit, self, self.battlefield)
                ux, uy = unit.position
                
                # Si la cible tactique est hors de portée, chercher un ennemi à portée
                if target:
                    td = abs(ux - target.position[0]) + abs(uy - target.position[1])
                    if td > unit._max_range:
                        # Cible IA hors de portée: fallback sur l'ennemi à portée le plus blessé
                        enemies = self.get_enemies(unit)
                        in_range = [e for e in enemies if e.is_alive and
                                    abs(ux - e.position[0]) + abs(uy - e.position[1]) <= unit._max_range]
                        if in_range:
                            target = min(in_range, key=lambda e: (e.hp / max(1, e.max_hp), abs(ux - e.position[0]) + abs(uy - e.position[1])))
                else:
                    # Pas de cible tactique: chercher l'ennemi le plus proche à portée
                    enemies = self.get_enemies(unit)
                    in_range = [e for e in enemies if e.is_alive and
                                abs(ux - e.position[0]) + abs(uy - e.position[1]) <= unit._max_range]
                    if in_range:
                        target = min(in_range, key=lambda e: abs(ux - e.position[0]) + abs(uy - e.position[1]))
                
                if target:
                    unit.perform_attacks(target, self.battlefield, self.visual_effects, cell_size)
        
        # Reset phalange bonus en fin de round
        for unit in alive:
            if unit._phalange_bonus_active:
                unit.sauvegarde += 1
                unit._phalange_bonus_active = False
        
        # Régénération + tick buffs
        for unit in self.army1 + self.army2:
            unit.regenerate()
            unit.tick_armor_buff()
        
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
                    self.battlefield.grid[wx][wy] = original  # Restaurer la case originale
                else:
                    remaining.append((wx, wy, dur - 1, original))
            self.battlefield._temp_walls = remaining
        
        # Nettoyer les unités mortes de la grille
        dead_units_seen = set()
        for pos, unit in list(self.battlefield.units.items()):
            if not unit.is_alive and unit.down_timer <= 0 and id(unit) not in dead_units_seen:
                dead_units_seen.add(id(unit))
                self.battlefield.remove_unit(unit)
        
        # Fuyards qui atteignent le bord → quittent la map
        bf = self.battlefield
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
        
        self.army1 = [u for u in self.army1 if u.is_alive or u.down_timer > 0]
        self.army2 = [u for u in self.army2 if u.is_alive or u.down_timer > 0]
        self.round += 1
        self._alive_cache['dirty'] = True

    def is_battle_over(self):
        """La bataille est finie quand une armée n'a plus personne sur la map."""
        a1_on_map = sum(1 for u in self.army1 if u.is_alive)
        a2_on_map = sum(1 for u in self.army2 if u.is_alive)
        
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
            all_fled_off = fled_list[:]
            # Fuyards encore sur la map
            for u in roster:
                if u.fleeing and u.is_alive and not u.fled:
                    all_fled_off.append(u)
            
            if is_winner:
                # Gagnant: vivants = ceux qui ne fuient pas, fuyants = ceux qui fuient
                alive = [u for u in all_alive if not u.fleeing]
                fled = [u for u in all_alive if u.fleeing] + all_fled_off
            else:
                # Perdant: tous les survivants sont des fuyants
                alive = []
                fled = all_alive + all_fled_off
            
            return {
                'name': name,
                'total': len(roster),
                'alive': count_by_name(alive),
                'alive_count': len(alive),
                'dead': count_by_name(all_dead),
                'dead_count': len(all_dead),
                'fled': count_by_name(fled),
                'fled_count': len(fled),
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