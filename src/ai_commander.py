"""
AI Commander — Système de commandement tactique.

Chaque armée a un CommanderAI qui analyse le champ de bataille 
et assigne des objectifs tactiques aux unités.

Tactiques disponibles:
- Focus fire: concentrer le feu sur les cibles prioritaires
- Flanquement: cavalerie contourne par les côtés
- Protection: CaC forme un écran devant les tireurs
- Ciblage prioritaire: artillerie→archers, cavalerie→artillerie
"""

import random


# Priorités de ciblage par type d'unité
# Chaque type préfère attaquer certains types ennemis
TARGET_PRIORITY = {
    # role attaquant → [(role cible, bonus priorité), ...]
    "cavalry": [("artillery", 3), ("back", 2), ("mid", 1)],
    "artillery": [("back", 3), ("mid", 2), ("front", 1)],
    "back": [("front", 2), ("cavalry", 2), ("mid", 1)],
    "front": [("front", 1), ("cavalry", 1), ("mid", 1)],
    "mid": [("front", 1), ("mid", 1), ("back", 1)],
}


class TacticalOrder:
    """Ordre tactique assigné à une unité."""
    __slots__ = ['order_type', 'target_unit', 'target_pos', 'priority']
    
    def __init__(self, order_type, target_unit=None, target_pos=None, priority=0):
        self.order_type = order_type    # "attack", "flank", "protect", "hold"
        self.target_unit = target_unit  # Unité ennemie ciblée
        self.target_pos = target_pos    # Position objective (flanquement)
        self.priority = priority        # Plus haut = plus important


class CommanderAI:
    """IA de commandement pour une armée."""
    
    def __init__(self, army, enemy_army, battlefield, is_army1=True):
        self.army = army
        self.enemy_army = enemy_army
        self.battlefield = battlefield
        self.is_army1 = is_army1
        
        # Analyser la composition une fois
        self.composition = self._analyze_composition(army)
        self.enemy_composition = self._analyze_composition(enemy_army)
        
        # Déterminer le style basé sur la composition
        self.style = self._determine_style()
    
    def _analyze_composition(self, army):
        """Analyse la composition d'une armée."""
        comp = {
            'total': len(army),
            'front': [], 'mid': [], 'back': [],
            'cavalry': [],    # vitesse >= 6
            'artillery': [],  # vitesse == 0
            'ranged': [],     # portée >= 4
            'melee': [],      # portée < 4
            'heroes': [],     # encouragement ou awe
        }
        
        for u in army:
            comp[u.role].append(u)
            if u.vitesse >= 6:
                comp['cavalry'].append(u)
            if u.vitesse <= 0:
                comp['artillery'].append(u)
            if u._max_range >= 4:
                comp['ranged'].append(u)
            else:
                comp['melee'].append(u)
            if u.encouragement_range > 0 or u.awe > 0:
                comp['heroes'].append(u)
        
        return comp
    
    def _determine_style(self):
        """Détermine le style tactique basé sur la composition."""
        comp = self.composition
        total = max(1, comp['total'])
        
        ranged_ratio = len(comp['ranged']) / total
        cavalry_ratio = len(comp['cavalry']) / total
        melee_ratio = len(comp['melee']) / total
        
        # Style adaptatif
        if cavalry_ratio >= 0.25:
            return "flanker"       # Beaucoup de cavalerie → flanquement
        elif ranged_ratio >= 0.4:
            return "ranged_heavy"  # Beaucoup de tireurs → défensif, protéger les archers
        elif melee_ratio >= 0.7:
            return "aggressive"    # Masse CaC → rush direct
        else:
            return "balanced"      # Équilibré → tactiques mixtes
    
    def issue_orders(self, battle):
        """Phase de commandement: assigne un ordre tactique à chaque unité vivante."""
        alive_units = [u for u in self.army if u.is_alive and not u.fleeing]
        alive_enemies = [e for e in self.enemy_army if e.is_alive]
        
        if not alive_units or not alive_enemies:
            return
        
        # Analyser la situation actuelle
        enemy_center = self._get_center(alive_enemies)
        my_center = self._get_center(alive_units)
        
        # Identifier les cibles prioritaires ennemies
        priority_targets = self._identify_priority_targets(alive_enemies)
        
        # Assigner les ordres selon le style
        for unit in alive_units:
            order = self._decide_order(unit, alive_enemies, priority_targets,
                                       enemy_center, my_center, battle)
            unit._tactical_order = order
    
    def _get_center(self, units):
        """Centre de masse d'un groupe d'unités."""
        if not units:
            return (0, 0)
        cx = sum(u.position[0] for u in units) / len(units)
        cy = sum(u.position[1] for u in units) / len(units)
        return (cx, cy)
    
    def _identify_priority_targets(self, enemies):
        """Identifie les cibles ennemies les plus dangereuses."""
        targets = []
        for e in enemies:
            danger = 0
            # Artillerie/archers = haute priorité
            if e._max_range >= 8:
                danger += 3
            elif e._max_range >= 4:
                danger += 2
            # Officiers/encourageurs
            if e.encouragement_range > 0:
                danger += 4  # Tuer les officiers est critique
            # Mages
            if e.spells:
                danger += 3
            # Unités blessées = plus facile à achever
            if e.hp < e.max_hp * 0.5:
                danger += 1
            targets.append((danger, e))
        
        targets.sort(key=lambda x: (-x[0], id(x[1])))
        return targets
    
    def _decide_order(self, unit, enemies, priority_targets, enemy_center, my_center, battle):
        """Décide l'ordre pour une unité spécifique."""
        bf = self.battlefield
        
        # === Cavalerie: flanquement ou chasse aux archers/artillerie ===
        if unit.vitesse >= 6 and self.style in ("flanker", "balanced"):
            return self._cavalry_order(unit, enemies, priority_targets, enemy_center, my_center)
        
        # === Tireurs: focus fire sur la cible la plus dangereuse à portée ===
        if unit._max_range >= 4:
            return self._ranged_order(unit, enemies, priority_targets)
        
        # === CaC front: protéger les tireurs ou attaquer ===
        if unit.role == "front":
            if self.style == "ranged_heavy":
                return self._protect_order(unit, enemies, my_center)
            else:
                return self._melee_order(unit, enemies, priority_targets, enemy_center)
        
        # === Mid/officiers: rester groupés, suivre le front ===
        if unit.encouragement_range > 0:
            return self._officer_order(unit, enemies, my_center)
        
        # === Défaut: attaquer la cible la plus proche mais en tenant compte des priorités ===
        return self._melee_order(unit, enemies, priority_targets, enemy_center)
    
    def _cavalry_order(self, unit, enemies, priority_targets, enemy_center, my_center):
        """Cavalerie: flanquer ou chasser les cibles prioritaires."""
        bf = self.battlefield
        
        # Chercher artillerie/archers ennemis à chasser
        high_value = [e for _, e in priority_targets if e._max_range >= 4 or e.vitesse <= 0]
        
        if high_value:
            # Cibler le tireur/artillerie le plus proche
            target = min(high_value, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=target, priority=3)
        
        # Sinon flanquer: aller sur le côté de l'ennemi
        flank_y = 3 if unit.position[1] < bf.height // 2 else bf.height - 4
        flank_x = int(enemy_center[0])
        return TacticalOrder("flank", target_pos=(flank_x, flank_y), priority=2)
    
    def _ranged_order(self, unit, enemies, priority_targets):
        """Tireurs: focus fire sur cible prioritaire à portée."""
        bf = self.battlefield
        
        # Chercher la cible la plus dangereuse à portée
        for danger, enemy in priority_targets:
            dist = bf.manhattan_distance(unit.position, enemy.position)
            if dist <= unit._max_range:
                return TacticalOrder("attack", target_unit=enemy, priority=danger)
        
        # Hors portée: cibler le plus proche
        closest = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
        return TacticalOrder("attack", target_unit=closest, priority=1)
    
    def _melee_order(self, unit, enemies, priority_targets, enemy_center):
        """CaC: attaquer en tenant compte des priorités."""
        bf = self.battlefield
        
        # Officiers ennemis proches? Les cibler en priorité
        officers = [e for _, e in priority_targets[:5] 
                    if bf.manhattan_distance(unit.position, e.position) <= unit.vitesse * 3]
        if officers:
            target = min(officers, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=target, priority=3)
        
        # Cible blessée proche? L'achever
        wounded = [e for e in enemies if e.hp < e.max_hp * 0.4 
                   and bf.manhattan_distance(unit.position, e.position) <= unit.vitesse * 2]
        if wounded:
            target = min(wounded, key=lambda e: e.hp)
            return TacticalOrder("attack", target_unit=target, priority=2)
        
        # Sinon: le plus proche
        closest = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
        return TacticalOrder("attack", target_unit=closest, priority=1)
    
    def _protect_order(self, unit, enemies, my_center):
        """CaC protecteur: se placer entre les tireurs alliés et l'ennemi."""
        bf = self.battlefield
        
        # Trouver nos tireurs
        my_ranged = [u for u in self.army if u.is_alive and u._max_range >= 4]
        if not my_ranged:
            # Pas de tireurs à protéger → attaquer normalement
            closest = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=closest, priority=1)
        
        # Se positionner entre le centre des tireurs et l'ennemi le plus proche
        ranged_center = self._get_center(my_ranged)
        closest_enemy = min(enemies, key=lambda e: bf.manhattan_distance(
            (int(ranged_center[0]), int(ranged_center[1])), e.position))
        
        # Position d'écran: entre les tireurs et l'ennemi
        shield_x = int((ranged_center[0] + closest_enemy.position[0]) / 2)
        shield_y = int((ranged_center[1] + closest_enemy.position[1]) / 2)
        
        # Si un ennemi est trop proche des tireurs, l'intercepter
        for e in enemies:
            dist_to_ranged = bf.manhattan_distance(e.position, (int(ranged_center[0]), int(ranged_center[1])))
            if dist_to_ranged <= 5:
                return TacticalOrder("attack", target_unit=e, priority=4)
        
        return TacticalOrder("protect", target_pos=(shield_x, shield_y), priority=2)
    
    def _officer_order(self, unit, enemies, my_center):
        """Officier: rester au milieu des alliés pour l'aura."""
        bf = self.battlefield
        
        # Trouver le groupe d'alliés le plus dense
        alive_allies = [u for u in self.army if u.is_alive and u != unit]
        if not alive_allies:
            closest = min(enemies, key=lambda e: bf.manhattan_distance(unit.position, e.position))
            return TacticalOrder("attack", target_unit=closest, priority=1)
        
        # Rester au centre des alliés
        ally_center = self._get_center(alive_allies)
        return TacticalOrder("hold", target_pos=(int(ally_center[0]), int(ally_center[1])), priority=2)


def select_tactical_target(unit, battle, battlefield):
    """Sélectionne la cible en utilisant l'ordre tactique si disponible.
    
    Retourne l'ennemi ciblé (ou None).
    """
    order = getattr(unit, '_tactical_order', None)
    enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
    
    if not enemies:
        return None
    
    if order is None:
        # Pas d'ordre → comportement par défaut (plus proche)
        return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))
    
    # === ATTACK: cibler l'unité assignée si elle vit encore ===
    if order.order_type == "attack" and order.target_unit:
        if order.target_unit.is_alive:
            return order.target_unit
        # Cible morte → plus proche
        return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))
    
    # === FLANK: cibler l'ennemi le plus proche de la position de flanquement ===
    if order.order_type == "flank" and order.target_pos:
        # Pendant le déplacement vers le flanc, attaquer ce qui est à portée
        in_range = [e for e in enemies 
                    if battlefield.manhattan_distance(unit.position, e.position) <= unit._max_range]
        if in_range:
            return min(in_range, key=lambda e: e.hp)  # Achever les blessés
        # Sinon cibler l'ennemi le plus proche du point de flanc
        return min(enemies, key=lambda e: battlefield.manhattan_distance(e.position, order.target_pos))
    
    # === PROTECT: intercepter l'ennemi qui menace nos tireurs ===
    if order.order_type == "protect":
        # Cibler l'ennemi le plus proche (intercepter)
        return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))
    
    # === HOLD: attaquer ce qui est à portée, sinon le plus proche ===
    if order.order_type == "hold":
        in_range = [e for e in enemies 
                    if battlefield.manhattan_distance(unit.position, e.position) <= unit._max_range]
        if in_range:
            return min(in_range, key=lambda e: e.hp)
        return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))
    
    # Fallback
    return min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))


def select_tactical_move_target(unit, battle, battlefield):
    """Détermine vers où l'unité doit se déplacer selon son ordre tactique.
    
    Retourne (target_pos_or_unit, move_towards_pos).
    Pour flank/protect/hold, retourne une position au lieu d'une unité.
    """
    order = getattr(unit, '_tactical_order', None)
    enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
    
    if not enemies:
        return None, None
    
    if order is None:
        target = min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))
        return target, None
    
    # ATTACK → aller vers la cible assignée
    if order.order_type == "attack" and order.target_unit and order.target_unit.is_alive:
        return order.target_unit, None
    
    # FLANK → se déplacer vers la position de flanc, puis attaquer
    if order.order_type == "flank" and order.target_pos:
        dist_to_flank = battlefield.manhattan_distance(unit.position, order.target_pos)
        if dist_to_flank <= 3:
            # Arrivé au flanc → attaquer le plus proche
            target = min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))
            return target, None
        else:
            # En transit → se déplacer vers le point de flanc
            return None, order.target_pos
    
    # PROTECT → se déplacer vers la position d'écran
    if order.order_type == "protect" and order.target_pos:
        dist = battlefield.manhattan_distance(unit.position, order.target_pos)
        if dist <= 2:
            # En position → intercepter le plus proche
            target = min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))
            return target, None
        else:
            return None, order.target_pos
    
    # HOLD → rester en position, attaquer ce qui est à portée
    if order.order_type == "hold" and order.target_pos:
        in_range = [e for e in enemies 
                    if battlefield.manhattan_distance(unit.position, e.position) <= unit._max_range + 2]
        if in_range:
            target = min(in_range, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))
            return target, None
        return None, order.target_pos
    
    target = min(enemies, key=lambda e: battlefield.manhattan_distance(unit.position, e.position))
    return target, None
