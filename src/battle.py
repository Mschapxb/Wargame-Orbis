import copy
import random

from battlefield import Battlefield
from effects import FloatingText


class Battle:
    def __init__(self, army1, army2, battlefield_width=40, battlefield_height=30, obstacle_count=8):
        self.army1 = copy.deepcopy(army1)
        self.army2 = copy.deepcopy(army2)
        self.battlefield = Battlefield(battlefield_width, battlefield_height, obstacle_count)
        self.round = 1
        self.visual_effects = {'projectiles': [], 'attack_lines': [], 'target_indicators': []}
        
        self._alive_cache = {'army1': [], 'army2': [], 'dirty': True}
        
        center_y = self.battlefield.height // 2
        self._place_armies(center_y)

    def _place_armies(self, center_y):
        """Place les armées. Espacement 1 (collé, pas de case vide entre).
        Si trop d'unités pour une colonne, débordement sur la colonne derrière.
        """
        bf = self.battlefield
        usable_height = bf.height - 2
        max_per_col = max(1, usable_height)  # Espacement 1 = 1 unité par case
        
        def place_role_units(units, base_x, center_y, step_x):
            """step_x: -1 armée gauche (déborde à gauche), +1 armée droite."""
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
                x_col = max(0, min(bf.width - 1, x_col))
                self._place_column(col_units, x_col, center_y, bf)
        
        # Trier par rôle
        army1_roles = {'front': [], 'mid': [], 'back': []}
        army2_roles = {'front': [], 'mid': [], 'back': []}
        
        for u in self.army1:
            army1_roles[u.role].append(u)
        for u in self.army2:
            army2_roles[u.role].append(u)
        
        # Armée 1 (gauche) : front=8, mid=5, back=2. Déborde vers la gauche.
        place_role_units(army1_roles['front'], 8, center_y, -1)
        place_role_units(army1_roles['mid'],   5, center_y, -1)
        place_role_units(army1_roles['back'],  2, center_y, -1)
        
        # Armée 2 (droite) : front=W-9, mid=W-6, back=W-3. Déborde vers la droite.
        place_role_units(army2_roles['front'], bf.width - 9, center_y, +1)
        place_role_units(army2_roles['mid'],   bf.width - 6, center_y, +1)
        place_role_units(army2_roles['back'],  bf.width - 3, center_y, +1)
    
    def _place_column(self, units, x_col, center_y, bf):
        """Place les unités sur une colonne, centrées, espacement 1 (collé)."""
        if not units:
            return
        
        n = len(units)
        start_y = center_y - n // 2
        
        for i, u in enumerate(units):
            target_y = start_y + i
            target_y = max(1, min(bf.height - 2, target_y))
            
            pos = (x_col, target_y)
            
            if not bf.is_valid(*pos) or bf.is_occupied(*pos):
                pos = self._find_free_near(x_col, target_y, bf)
            
            if pos is not None:
                u.position = pos
                bf.units[pos] = u

    def _find_free_near(self, x, y, bf):
        """Trouve la position libre la plus proche en spirale."""
        for radius in range(0, max(bf.width, bf.height)):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) != radius and abs(dy) != radius:
                        continue
                    nx, ny = x + dx, y + dy
                    if bf.is_valid(nx, ny) and not bf.is_occupied(nx, ny):
                        return (nx, ny)
        return None

    def get_all_alive(self):
        if self._alive_cache['dirty']:
            self._alive_cache['army1'] = [u for u in self.army1 if u.is_alive]
            self._alive_cache['army2'] = [u for u in self.army2 if u.is_alive]
            self._alive_cache['all'] = self._alive_cache['army1'] + self._alive_cache['army2']
            self._alive_cache['dirty'] = False
        return self._alive_cache['all']

    def get_enemies(self, unit):
        return self.army2 if unit in self.army1 else self.army1

    def get_allies(self, unit):
        return self.army1 if unit in self.army1 else self.army2

    def get_closest_enemy(self, unit):
        enemies = self.get_enemies(unit)
        alive_enemies = [e for e in enemies if e.is_alive]
        if not alive_enemies:
            return None
        return min(alive_enemies, key=lambda e: self.battlefield.manhattan_distance(unit.position, e.position))

    def get_units_in_radius(self, center_pos, radius, unit_list):
        result = []
        for unit in unit_list:
            if unit.is_alive and self.battlefield.manhattan_distance(center_pos, unit.position) <= radius:
                result.append(unit)
        return result

    def fear_phase(self):
        for army in [self.army1, self.army2]:
            alive_count = sum(1 for u in army if u.is_alive)
            total_count = len(army)
            
            if total_count > 0 and alive_count <= total_count // 2:
                for unit in army:
                    if unit.is_alive and not hasattr(unit, '_half_army_malus_applied'):
                        unit.morale_malus += 1
                        unit._half_army_malus_applied = True
                        unit.floating_texts.append(FloatingText("-1 Moral (Pertes)", (255, 100, 60), 80))
                        
                        if unit.get_effective_morale() == 0 and not unit.fleeing:
                            unit.fleeing = True
                            unit.status_text = "FUITE!"
        
        for unit in self.get_all_alive():
            if unit.fleeing:
                continue
            unit.afraid = False
            if unit.status_text in ["DOWN", "REVIVED"]:
                continue
            
            max_aura, min_dist = 0, 99
            for enemy in self.get_enemies(unit):
                if not enemy.is_alive or enemy.fear_aura == 0:
                    continue
                dist = self.battlefield.manhattan_distance(unit.position, enemy.position)
                if dist <= enemy.fear_aura and (dist < min_dist or enemy.fear_aura > max_aura):
                    max_aura, min_dist = enemy.fear_aura, dist
            
            if max_aura > 0:
                unit.apply_fear_effect(max_aura, min_dist)

    def simulate_round(self, cell_size):
        self._alive_cache['dirty'] = True
        self.visual_effects['target_indicators'] = []
        alive = self.get_all_alive()
        
        alive.sort(key=lambda u: (u.vitesse, random.random()), reverse=True)
        
        reserved = set()
        moves = {}
        
        for unit in alive:
            new_pos, target = self.battlefield.compute_move(unit, self, reserved)
            unit.current_target = target
            if target:
                self.visual_effects['target_indicators'].append((unit, target))
            if new_pos and self.battlefield.is_free(*new_pos, unit) and new_pos not in reserved:
                moves[unit] = new_pos
                reserved.add(new_pos)
        
        for unit, new_pos in moves.items():
            old = unit.position
            if old in self.battlefield.units:
                del self.battlefield.units[old]
            unit.position = new_pos
            self.battlefield.units[new_pos] = unit
        
        self.fear_phase()
        
        for unit in alive:
            if unit.spells and unit.is_alive:
                unit.cast_random_spell(self, self.visual_effects, cell_size)
        
        for unit in alive:
            if unit.is_alive:
                target = self.get_closest_enemy(unit)
                if target:
                    unit.perform_attacks(target, self.battlefield, self.visual_effects, cell_size)
        
        for unit in self.army1 + self.army2:
            unit.regenerate()
        
        # Nettoyer les unités mortes de la grille (libérer leurs cases)
        dead_positions = []
        for pos, unit in list(self.battlefield.units.items()):
            if not unit.is_alive and unit.down_timer <= 0:
                dead_positions.append(pos)
        for pos in dead_positions:
            del self.battlefield.units[pos]
        
        self.army1 = [u for u in self.army1 if u.is_alive or u.down_timer > 0]
        self.army2 = [u for u in self.army2 if u.is_alive or u.down_timer > 0]
        self.round += 1
        self._alive_cache['dirty'] = True