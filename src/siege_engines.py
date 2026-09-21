"""Engins de siège de l'assaillant: le bélier et la tour de siège.

Comme structures.py, ce module ne dépend pas de Pygame: le moteur, l'IA et
les tests appellent les mêmes fonctions.

Les engins ne suivent pas les ordres tactiques ordinaires: ils marchent
seuls vers leur objectif (cf. engine_move, appelé en tête de
Battlefield.compute_move).

    Bélier (2×2)   se colle à une porte intacte de l'enceinte active et
                   l'enfonce (×RAM_GATE_FACTOR, cf. Battle._attack_gate). Ne
                   frappe jamais les troupes. L'huile d'une porte piégée le
                   brûle sans sauvegarde.
    Tour (2×4)     se colle au mur, hors des portes. Ses archers tirent à
                   hauteur du rempart (ligne de tir surélevée, pas de bonus
                   de rempart pour la cible). Accolée, elle devient une RAMPE
                   (ses 8 cases, praticables) et une PASSERELLE (deux cases du
                   mur, praticables) enregistrée comme brèche: l'IA
                   d'assaut, la chute d'enceinte et le repli de la garnison
                   la traitent comme n'importe quelle brèche.
"""

import terrain as tr

RAM, TOWER = "ram", "tower"
RAM_GATE_FACTOR = 3
# Servants: une machine de tir (Artillerie) ne tire ni ne bouge sans
# CREW_NEEDED artilleurs au contact; un engin de contact n'avance (et le
# bélier ne cogne) qu'avec PUSHERS_NEEDED guerriers au contact.
CREW_NEEDED = 2
PUSHERS_NEEDED = {RAM: 2, TOWER: 2}
# Une tour ne s'accole pas à moins de ces rangées d'une porte: elle
# boucherait l'approche du bélier et de l'infanterie
TOWER_GATE_CLEARANCE = 3
# Un engin servi qui n'avance plus depuis N rounds (chemin bouché) libère
# ses pousseurs: ils valent mieux au combat que figés à côté d'une épave
ENGINE_STALL_ROUNDS = 4

GRID_RAMPART, GRID_STAIRS, GRID_WALL = 4, 5, 2


def is_engine(unit):
    return getattr(unit, 'siege_engine', None) is not None


# ═══════════════════════════════════════════════════════════════
#                     SERVANTS ET POUSSEURS
# ═══════════════════════════════════════════════════════════════

def needs_crew(unit):
    """Machine de tir qu'il faut servir (baliste, scorpion, catapulte...)."""
    return getattr(unit, 'is_artillery', False) and not is_engine(unit)


def is_crew(unit):
    return getattr(unit, 'artilleur', False)


def can_push(unit):
    """Simple guerrier capable de pousser un engin: fantassin de mêlée, ni
    tireur, ni mage, ni officier, ni artilleur, ni machine."""
    return (unit.unit_type == "Infanterie" and unit._max_range < 4 and not unit.spells
            and unit.encouragement_range <= 0 and not is_crew(unit)
            and not getattr(unit, 'is_artillery', False) and not is_engine(unit))


def is_machine(unit):
    return needs_crew(unit) or is_engine(unit)


def _touch(bf, a, apos, b, bpos):
    """Empreintes de a (en apos) et b (en bpos) au contact (côté ou coin)."""
    ax, ay = apos
    bx, by = bpos
    aw, ah = bf.get_unit_dims(a)
    bw, bh = bf.get_unit_dims(b)
    gx = max(0, bx - (ax + aw - 1), ax - (bx + bw - 1))
    gy = max(0, by - (ay + ah - 1), ay - (by + bh - 1))
    return max(gx, gy) == 1


def _allies(battle, unit):
    return [a for a in battle.get_allies(unit)
            if a is not unit and a.is_alive and not a.fleeing and a.position is not None]


def crew_count(bf, battle, machine):
    """Artilleurs au contact d'une machine de tir."""
    return sum(1 for a in _allies(battle, machine)
               if is_crew(a) and _touch(bf, a, a.position, machine, machine.position))


def pusher_count(bf, battle, engine):
    """Guerriers au contact d'un engin de contact."""
    return sum(1 for a in _allies(battle, engine)
               if can_push(a) and _touch(bf, a, a.position, engine, engine.position))


def manned(bf, battle, unit):
    """La machine a-t-elle ses servants (vrai pour toute autre unité) ?
    Sans bataille (appel hors moteur), on ne peut pas savoir: vrai."""
    if battle is None:
        return True
    if needs_crew(unit):
        return crew_count(bf, battle, unit) >= CREW_NEEDED
    if is_engine(unit):
        return pusher_count(bf, battle, unit) >= PUSHERS_NEEDED[unit.siege_engine]
    return True


def engine_active(bf, unit):
    """Un engin de contact a-t-il encore besoin de ses pousseurs ?"""
    if not unit.is_alive or unit.docked or not bf.is_siege:
        return False
    if getattr(unit, '_stalled', 0) >= ENGINE_STALL_ROUNDS:
        return False                     # bloqué: on l'abandonne
    goal = engine_goal(bf, unit)
    if unit.siege_engine == RAM and not passage_open(bf):
        return True                      # il marche vers la porte ou la bat
    return goal is not None and goal != unit.position


def assign_attendants(battle):
    """Chaque round: 2 artilleurs par machine de tir, 2 guerriers par engin
    de contact en marche. Les plus proches, affectation stable (on garde
    ses servants tant qu'ils vivent). Pose `_attends` sur les servants."""
    bf = battle.battlefield
    for army in (battle.army1, battle.army2):
        alive = [u for u in army if u.is_alive and u.position is not None]
        machines = sorted((u for u in alive if needs_crew(u)
                           or (is_engine(u) and engine_active(bf, u))), key=lambda u: u.uid)
        live_ids = {id(m) for m in machines}
        for u in alive:
            m = getattr(u, '_attends', None)
            if m is not None and (id(m) not in live_ids or u.fleeing):
                u._attends = None
        for m in machines:
            need = CREW_NEEDED if needs_crew(m) else PUSHERS_NEEDED[m.siege_engine]
            ok = is_crew if needs_crew(m) else can_push
            have = [u for u in alive if getattr(u, '_attends', None) is m]
            free = [u for u in alive if ok(u) and not u.fleeing
                    and getattr(u, '_attends', None) is None]
            mx, my = m.position
            free.sort(key=lambda u: (abs(u.position[0] - mx) + abs(u.position[1] - my), u.uid))
            for u in free[:max(0, need - len(have))]:
                u._attends = m


def staffing_warning(army):
    """Avertissement pour le menu si une armée n'a pas de quoi servir ses
    machines, sinon None."""
    machines = sum(1 for u in army if needs_crew(u))
    crew = sum(1 for u in army if is_crew(u))
    engines = [u for u in army if is_engine(u)]
    pushers = sum(1 for u in army if can_push(u))
    need_push = sum(PUSHERS_NEEDED[u.siege_engine] for u in engines)
    parts = []
    if crew < machines * CREW_NEEDED:
        parts.append(f"{machines} machine(s) de tir pour {crew} artilleur(s) "
                     f"(il en faut {CREW_NEEDED} par machine)")
    if pushers < need_push:
        parts.append(f"{len(engines)} engin(s) pour {pushers} guerrier(s) de mêlée "
                     f"(il en faut {need_push} pour les pousser)")
    return "; ".join(parts) or None


def gather_attendants(battle):
    """Déploiement: chaque servant (artilleur, pousseur) commence au contact
    de sa machine, du côté de son camp. Sans cela, une catapulte perdait
    ses premières volées à attendre ses artilleurs (brèches avant le round
    25: 23/40 → 11/40)."""
    bf = battle.battlefield
    assign_attendants(battle)
    for army in (battle.army1, battle.army2):
        home = -1 if army is battle.army1 else 1
        for u in sorted((u for u in army if getattr(u, '_attends', None) is not None),
                        key=lambda u: u.uid):
            m = u._attends
            if _touch(bf, u, u.position, m, m.position):
                continue
            mx, my = m.position
            mw, mh = bf.get_unit_dims(m)
            spots = [(x, y) for x in range(mx - 1, mx + mw + 1) for y in range(my - 1, my + mh + 1)
                     if _touch(bf, u, (x, y), m, m.position)]
            # Côté de son camp d'abord, puis le plus près du centre de la machine
            spots.sort(key=lambda c: ((c[0] - mx) * -home, abs(c[1] - my - mh / 2), c))
            bf.remove_unit(u)
            for pos in spots:
                if bf.can_place_unit(*pos, u):
                    u.position = pos
                    break
            bf.place_unit(u)


def attendant_move(bf, unit, battle, reserved_positions):
    """Un servant reste collé à sa machine: vers une case au contact de la
    destination prévue de la machine ce round, côté opposé à l'ennemi."""
    m = unit._attends
    planned = getattr(battle, '_planned_moves', {}) or {}
    mpos = planned.get(m, m.position)
    enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
    if _touch(bf, unit, unit.position, m, mpos):
        return None, None
    mw, mh = bf.get_unit_dims(m)
    ex = (sum(e.position[0] for e in enemies) / len(enemies)) if enemies else mpos[0]
    back = -1 if ex >= mpos[0] else 1
    cells = []
    for x in range(mpos[0] - 1, mpos[0] + mw + 1):
        for y in range(mpos[1] - 1, mpos[1] + mh + 1):
            if mpos[0] <= x < mpos[0] + mw and mpos[1] <= y < mpos[1] + mh:
                continue
            if not _touch(bf, unit, (x, y), m, mpos):
                continue
            if not bf._can_move_to(unit, (x, y), reserved_positions):
                continue
            if any(mpos[0] <= cx < mpos[0] + mw and mpos[1] <= cy < mpos[1] + mh
                   for (cx, cy) in bf._get_reserved_cells(unit, (x, y))):
                continue
            ux, uy = unit.position
            side = (x - (mpos[0] + (mw - 1) / 2)) * back   # > 0: derrière la machine
            cells.append((abs(x - ux) + abs(y - uy) - 0.5 * side, (x, y)))
    if not cells:
        return None, None
    for _cost, goal in sorted(cells):
        path = bf.a_star_path(unit.position, goal, unit, battle, reserved_positions, partial=True)
        if path:
            step = bf._advance_along(unit, path, unit.vitesse, reserved_positions, battle)
            if step is not None:
                return step, None
    return None, None


# ═══════════════════════════════════════════════════════════════
#                     BÉLIER
# ═══════════════════════════════════════════════════════════════

def ram_target_gate(bf, unit):
    """Porte intacte de l'enceinte active à enfoncer (celle de l'axe
    d'assaut si possible, sinon la plus proche), ou None."""
    intact = [g for g, hp in bf.active_gates.items() if hp > 0]
    if not intact or bf.gates_open:
        return None
    wanted = getattr(unit, '_assault_gate', None)
    if wanted in intact:
        return wanted
    ux, uy = unit.position
    return min(intact, key=lambda g: (abs(g[0] - ux) + abs(g[1] - uy), g))


def passage_open(bf):
    """L'enceinte active a-t-elle déjà une ouverture (porte brisée ou
    ouverte, brèche) ? Le bélier a alors fini son travail sur ce mur."""
    return (bf.gates_open or bool(bf.active_breaches)
            or any(hp <= 0 for hp in bf.active_gates.values()))


def ram_park_anchor(bf, unit):
    """Une fois le passage ouvert, le bélier se range contre le mur, au-dessus
    ou au-dessous des portes: planté devant, il bouchait l'entrée à sa propre
    infanterie (mesuré: Citadelle 54 % → 50 % AVEC un bélier)."""
    gates = sorted(bf.active_gates)
    if not gates:
        return None
    gx = gates[0][0]
    rows = [g[1] for g in gates]
    ux, uy = unit.position
    options = []
    for y0 in (min(rows) - 4, max(rows) + 3):
        for x0 in (gx - 2, gx - 3, gx - 4):
            if all(bf.is_valid(x0 + dx, y0 + dy) for dx in (0, 1) for dy in (0, 1)):
                options.append((abs(x0 - ux) + abs(y0 - uy), (x0, y0)))
                break
    return min(options)[1] if options else None


def ram_dock_anchors(gate):
    """Coins haut-gauche où un bélier 2×2 touche `gate` par sa face droite."""
    gx, gy = gate
    return [(gx - 2, gy - 1), (gx - 2, gy)]


def gate_distance(bf, unit, gate):
    """Distance de l'empreinte de l'unité à une case de porte."""
    gx, gy = gate
    return min(abs(cx - gx) + abs(cy - gy) for (cx, cy) in bf.get_unit_cells(unit))


# ═══════════════════════════════════════════════════════════════
#                     TOUR DE SIÈGE
# ═══════════════════════════════════════════════════════════════

def tower_site_ok(bf, anchor, clearance=TOWER_GATE_CLEARANCE, unit=None):
    """Un emplacement d'accostage (coin haut-gauche 2×4) est-il valable ?
    Mur intact sur les 4 rangées, chemin de ronde derrière la passerelle,
    cases de la tour praticables et libres de tout AUTRE engin (un bélier
    rangé contre le mur bloquait la tour à jamais), à `clearance` rangées
    des portes."""
    wall_x = bf.wall_x
    x0, y0 = anchor
    if wall_x is None or x0 != wall_x - 2 or y0 < 1 or y0 + 3 > bf.height - 2:
        return False
    for y in range(y0, y0 + 4):
        if bf.grid[wall_x][y] != GRID_WALL:
            return False
        if not (bf.is_valid(x0, y) and bf.is_valid(x0 + 1, y)):
            return False
        for x in (x0, x0 + 1):
            occ = bf.units.get((x, y))
            if occ is not None and occ is not unit and is_engine(occ):
                return False
    if not all((wall_x + 1, y) in bf.ramparts for y in (y0 + 1, y0 + 2)):
        return False
    return not any(y0 - clearance <= gy <= y0 + 3 + clearance
                   for (_gx, gy) in bf.active_gates)


def tower_dock_site(bf, unit):
    """Meilleur emplacement d'accostage pour la tour: le plus proche de sa
    rangée actuelle. Mémorisé sur l'unité tant qu'il reste valable."""
    wall_x = bf.wall_x
    if wall_x is None:
        return None
    kept = getattr(unit, '_dock_site', None)
    if kept is not None and tower_site_ok(bf, kept, 0, unit):
        return kept
    uy = unit.position[1] + 1.5
    best = None
    # La marge aux portes cède si le mur est trop court pour elle (Citadelle
    # 40×30: deux portes, aucun tronçon à 3 rangées de l'une et de l'autre)
    for clearance in range(TOWER_GATE_CLEARANCE, -1, -1):
        sites = [(wall_x - 2, y0) for y0 in range(1, bf.height - 4)
                 if tower_site_ok(bf, (wall_x - 2, y0), clearance, unit)]
        if sites:
            best = min(sites, key=lambda a: (abs(a[1] + 1.5 - uy), a[1]))
            break
    unit._dock_site = best
    return best


def tower_docked(bf, unit):
    """La tour est-elle à son poste d'accostage ?"""
    site = getattr(unit, '_dock_site', None)
    return site is not None and unit.position == site and tower_site_ok(bf, site, 0, unit)


def dock_tower(bf, unit):
    """Accostage: la tour quitte la grille des unités et devient une rampe
    (8 cases praticables) plus une passerelle (2 cases du mur). Retourne
    (rampe, passerelle). L'appelant retire l'unité de son armée."""
    x0, y0 = unit.position
    wall_x = x0 + 2
    ramp = bf.get_unit_cells(unit)
    bf.remove_unit(unit)
    for (x, y) in ramp:
        bf.grid[x][y] = GRID_STAIRS
        if bf.terrain is not None:
            bf.terrain[x][y] = tr.PLAIN
        bf.siege_ramp_cells.add((x, y))
        bf.dirty_cells.add((x, y))
    bridge = [(wall_x, y0 + 1), (wall_x, y0 + 2)]
    for (x, y) in bridge:
        bf.grid[x][y] = GRID_RAMPART
        bf.walls.discard((x, y))
        bf.structures.pop((x, y), None)
        bf.bridge_cells.add((x, y))
        bf.dirty_cells.add((x, y))
    bf.breaches.add(bridge[0])
    unit.docked = True
    return ramp, bridge


# ═══════════════════════════════════════════════════════════════
#                     MOUVEMENT
# ═══════════════════════════════════════════════════════════════

def engine_goal(bf, unit):
    """Coin haut-gauche visé par l'engin, ou None."""
    if unit.siege_engine == RAM:
        if passage_open(bf):
            return ram_park_anchor(bf, unit)
        gate = ram_target_gate(bf, unit)
        if gate is None:
            return None
        anchors = [a for a in ram_dock_anchors(gate)
                   if all(bf.is_valid(a[0] + dx, a[1] + dy) for dx in (0, 1) for dy in (0, 1))]
        if not anchors:
            return None
        ux, uy = unit.position
        return min(anchors, key=lambda a: (abs(a[0] - ux) + abs(a[1] - uy), a))
    if unit.siege_engine == TOWER:
        return tower_dock_site(bf, unit)
    return None


def engine_move(bf, unit, battle, reserved_positions):
    """(case où aller ou None, cible de tir ou None) pour un engin."""
    target = None
    if unit._max_range >= 4:
        enemies = [e for e in battle.get_enemies(unit) if e.is_alive]
        in_range = bf._in_range(unit, enemies)
        if in_range:
            target = bf._weakest_then_closest(unit, in_range)
    if unit.fleeing or not bf.is_siege:
        return None, target
    if not manned(bf, battle, unit):
        unit.status_text = "SANS POUSSEURS"
        return None, target              # personne pour le pousser
    if unit.siege_engine == RAM and not passage_open(bf):
        gate = ram_target_gate(bf, unit)
        if gate is not None and gate_distance(bf, unit, gate) <= 1:
            return None, target          # au contact: il frappe
    goal = engine_goal(bf, unit)
    if goal is None or goal == unit.position:
        return None, target
    path = bf.a_star_path(unit.position, goal, unit, battle, reserved_positions, partial=True)
    step = bf._advance_along(unit, path, unit.vitesse, reserved_positions, battle) if path else None
    unit._stalled = 0 if step not in (None, unit.position) else getattr(unit, '_stalled', 0) + 1
    return step, target
