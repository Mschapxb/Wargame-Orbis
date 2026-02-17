"""
AI Commander v2 — Commandement tactique avec défense de siège et coordination.
"""
import random


class TacticalOrder:
    __slots__ = ['order_type', 'target_unit', 'target_pos', 'priority', 'lane']
    def __init__(self, order_type, target_unit=None, target_pos=None, priority=0, lane=0):
        self.order_type = order_type
        self.target_unit = target_unit
        self.target_pos = target_pos
        self.priority = priority
        self.lane = lane


class CommanderAI:
    def __init__(self, army, enemy_army, battlefield, is_army1=True):
        self.army = army
        self.enemy_army = enemy_army
        self.battlefield = battlefield
        self.is_army1 = is_army1
        self.style = self._determine_style()
    
    def _determine_style(self):
        alive = [u for u in self.army if u.is_alive]
        total = max(1, len(alive))
        ranged = sum(1 for u in alive if u._max_range >= 4)
        cavalry = sum(1 for u in alive if u.vitesse >= 6)
        if cavalry / total >= 0.25:
            return "flanker"
        elif ranged / total >= 0.4:
            return "ranged_heavy"
        elif ranged / total <= 0.1:
            return "aggressive"
        return "balanced"
    
    def issue_orders(self, battle):
        alive = [u for u in self.army if u.is_alive and not u.fleeing]
        enemies = [e for e in self.enemy_army if e.is_alive]
        if not alive or not enemies:
            return
        
        bf = self.battlefield
        is_siege = bool(bf.siege_data)
        is_defender = is_siege and not self.is_army1
        
        prio = self._rank_targets(enemies)
        ec = self._center(enemies)
        mc = self._center(alive)
        lanes = self._assign_lanes(alive, enemies)
        
        for unit in alive:
            lane = lanes.get(id(unit), 0)
            if is_defender and is_siege:
                order = self._siege_defense(unit, enemies, prio, battle)
            else:
                order = self._standard(unit, enemies, prio, ec, mc, battle)
            order.lane = lane
            unit._tactical_order = order
    
    def _center(self, units):
        if not units:
            return (0, 0)
        return (sum(u.position[0] for u in units) / len(units),
                sum(u.position[1] for u in units) / len(units))
    
    def _rank_targets(self, enemies):
        scored = []
        for e in enemies:
            d = 0
            if e.encouragement_range > 0: d += 5
            if e.spells: d += 4
            if e._max_range >= 8: d += 3
            elif e._max_range >= 4: d += 2
            if e.hp < e.max_hp * 0.4: d += 2
            if e.awe > 0: d += 1
            scored.append((d, e))
        scored.sort(key=lambda x: (-x[0], id(x[1])))
        return scored
    
    def _assign_lanes(self, alive, enemies):
        bf = self.battlefield
        h = bf.height
        # Assigner des lanes à TOUTES les unités mobiles (pas seulement CaC)
        # pour que l'approche se fasse en front large
        mobile = [u for u in alive if u.vitesse > 0]
        if not mobile:
            return {}
        
        ec_y = sum(e.position[1] for e in enemies) / max(1, len(enemies))
        # Plus de lanes = front plus large = moins de bouchon
        num_lanes = max(3, min(h - 4, len(mobile)))
        spacing = max(1, (h - 6) / max(1, num_lanes))
        
        lanes = {}
        for i, u in enumerate(mobile):
            offset = ((i % num_lanes) - num_lanes // 2) * spacing
            ty = int(ec_y + offset)
            ty = max(2, min(h - 3, ty))
            lanes[id(u)] = ty
        return lanes
    
    # ─── Standard ───
    
    def _standard(self, unit, enemies, prio, ec, mc, battle):
        bf = self.battlefield
        
        if unit.vitesse >= 6 and self.style in ("flanker", "balanced"):
            return self._cav_order(unit, enemies, prio, ec)
        if unit._max_range >= 4:
            return self._ranged_order(unit, enemies, prio)
        if unit.encouragement_range > 0:
            return self._officer_order(unit, enemies, mc)
        if self.style == "ranged_heavy" and unit.role == "front":
            return self._screen_order(unit, enemies, mc)
        return self._melee_order(unit, enemies, prio)
    
    def _cav_order(self, unit, enemies, prio, ec):
        bf = self.battlefield
        hv = [e for _, e in prio if e._max_range >= 4 or e.vitesse <= 0]
        if hv:
            t = min(hv, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=t, priority=4)
        fy = 3 if unit.position[1] < bf.height // 2 else bf.height - 4
        return TacticalOrder("flank", target_pos=(int(ec[0]), fy), priority=3)
    
    def _ranged_order(self, unit, enemies, prio):
        bf = self.battlefield
        for _, e in prio:
            if bf.manhattan_distance(unit.position, e.position) <= unit._max_range:
                return TacticalOrder("attack", target_unit=e, priority=3)
        c = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
        return TacticalOrder("attack", target_unit=c, priority=1)
    
    def _melee_order(self, unit, enemies, prio):
        bf = self.battlefield
        # Achever blessés proches
        wounded = [e for e in enemies if e.hp < e.max_hp * 0.4
                   and bf.manhattan_distance(unit.position, e.position) <= unit.vitesse * 2]
        if wounded:
            return TacticalOrder("attack", target_unit=min(wounded, key=lambda e: e.hp), priority=3)
        # Officier proche
        off = [e for _, e in prio[:3] if e.encouragement_range > 0
               and bf.manhattan_distance(unit.position, e.position) <= unit.vitesse * 3]
        if off:
            return TacticalOrder("attack", target_unit=off[0], priority=4)
        c = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
        return TacticalOrder("attack", target_unit=c, priority=1)
    
    def _screen_order(self, unit, enemies, mc):
        bf = self.battlefield
        my_r = [u for u in self.army if u.is_alive and u._max_range >= 4]
        if not my_r:
            c = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=c, priority=1)
        rc = self._center(my_r)
        ce = min(enemies, key=lambda e: bf.manhattan_distance((int(rc[0]), int(rc[1])), e.position))
        if bf.manhattan_distance(ce.position, (int(rc[0]), int(rc[1]))) <= 6:
            return TacticalOrder("attack", target_unit=ce, priority=4)
        sx = int(rc[0] * 0.4 + ce.position[0] * 0.6)
        sy = int(rc[1] * 0.4 + ce.position[1] * 0.6)
        return TacticalOrder("protect", target_pos=(sx, sy), priority=2)
    
    def _officer_order(self, unit, enemies, mc):
        bf = self.battlefield
        fighters = [u for u in self.army if u.is_alive and u != unit and u._max_range < 4 and not u.fleeing]
        if fighters:
            c = self._center(fighters)
            return TacticalOrder("hold", target_pos=(int(c[0]), int(c[1])), priority=2)
        c = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
        return TacticalOrder("attack", target_unit=c, priority=1)
    
    # ─── Défense siège ───
    
    def _siege_defense(self, unit, enemies, prio, battle):
        bf = self.battlefield
        wall_x = bf.siege_data.get('wall_x', 0)
        gates_intact = any(hp > 0 for hp in bf.gate_hp.values())
        on_ramp = bf.is_rampart(*unit.position)
        
        # Ennemis ayant passé le mur
        inside = [e for e in enemies if e.position[0] > wall_x]
        # Ennemis proches du mur
        near_wall = [e for e in enemies if e.position[0] >= wall_x - 10]
        # Ennemis aux portes
        gate_ys = set()
        for (gx, gy), hp in bf.gate_hp.items():
            if hp > 0:
                gate_ys.add(gy)
        at_gate = [e for e in enemies if any(abs(e.position[1] - gy) <= 2 for gy in gate_ys)
                   and e.position[0] >= wall_x - 2]
        
        # === PRIORITÉ 1: Ennemis à l'intérieur → intercepter ===
        if inside:
            t = min(inside, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=t, priority=6)
        
        # === Portes intactes: défense positionnelle ===
        if gates_intact:
            # Tireurs sur rempart: focus les ennemis près du mur/portes
            if on_ramp and unit._max_range >= 4:
                if at_gate:
                    t = min(at_gate, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                    return TacticalOrder("attack", target_unit=t, priority=5)
                if near_wall:
                    t = min(near_wall, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                    return TacticalOrder("attack", target_unit=t, priority=4)
                t = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                return TacticalOrder("attack", target_unit=t, priority=3)
            
            # CaC sur rempart: bloquer les escaliers
            if on_ramp and unit._max_range < 4:
                stair_e = [e for e in enemies if (e.position in bf.stairs)
                           or bf.manhattan_distance(unit.position, e.position) <= 2]
                if stair_e:
                    t = min(stair_e, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                    return TacticalOrder("attack", target_unit=t, priority=5)
                return TacticalOrder("hold", target_pos=unit.position, priority=3)
            
            # CaC derrière la porte
            if unit._max_range < 4:
                if at_gate:
                    t = min(at_gate, key=lambda e: bf.manhattan_distance(unit.position, e.position))
                    return TacticalOrder("attack", target_unit=t, priority=4)
                return TacticalOrder("hold", target_pos=unit.position, priority=2)
            
            # Tireurs pas sur rempart → y monter
            if unit._max_range >= 4 and not on_ramp:
                for y in range(1, bf.height - 1):
                    if bf.grid[wall_x + 1][y] == 4 and not bf.is_occupied(wall_x + 1, y):
                        return TacticalOrder("protect", target_pos=(wall_x + 1, y), priority=3)
        
        # === Portes détruites: combat ouvert ===
        c = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
        return TacticalOrder("attack", target_unit=c, priority=2)


# ─── Intégration ───

def select_tactical_target(unit, battle, battlefield):
    order = getattr(unit, '_tactical_order', None)
    enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
    if not enemies:
        return None
    
    if order and order.order_type == "attack" and order.target_unit and order.target_unit.is_alive:
        dist = battlefield.manhattan_distance(unit.position, order.target_unit.position)
        if dist <= unit._max_range:
            return order.target_unit
        # Hors portée → attaquer blessé à portée
        in_r = [e for e in enemies if battlefield.manhattan_distance(unit.position, e.position) <= unit._max_range]
        if in_r:
            return min(in_r, key=lambda e: (e.hp / max(1, e.max_hp), id(e)))
    
    if order and order.order_type in ("flank", "hold", "protect"):
        in_r = [e for e in enemies if battlefield.manhattan_distance(unit.position, e.position) <= unit._max_range]
        if in_r:
            return min(in_r, key=lambda e: e.hp)
    
    return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))


def select_tactical_move_target(unit, battle, battlefield):
    order = getattr(unit, '_tactical_order', None)
    enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
    if not enemies:
        return None, None
    
    if order is None:
        return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position)), None
    
    if order.order_type == "attack":
        t = order.target_unit
        if t and t.is_alive:
            return t, None
        return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position)), None
    
    if order.order_type == "flank" and order.target_pos:
        if battlefield.manhattan_distance(unit.position, order.target_pos) <= 4:
            return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position)), None
        return None, order.target_pos
    
    if order.order_type == "protect" and order.target_pos:
        if battlefield.manhattan_distance(unit.position, order.target_pos) <= 2:
            return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position)), None
        return None, order.target_pos
    
    if order.order_type == "hold":
        in_r = [e for e in enemies if battlefield.manhattan_distance(unit.position, e.position) <= unit._max_range + 3]
        if in_r:
            return min(in_r, key=lambda e: battlefield.manhattan_distance(unit.position, e.position)), None
        if order.target_pos:
            return None, order.target_pos
        return None, None
    
    return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position)), None


def get_lane_offset(unit, battlefield):
    order = getattr(unit, '_tactical_order', None)
    if order and order.lane:
        return order.lane
    return unit.position[1]