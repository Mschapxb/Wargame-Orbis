"""Déploiement des armées sur le champ de bataille.

`deploy_armies(bf, army1, army2, center_y)` place l'armée 1 à gauche et
l'armée 2 en miroir à droite (bataille rangée), ou l'armée 2 en garnison
derrière l'enceinte extérieure (siège).

Tout le hasard passe par rng_scope.RNG, dans un ordre fixe: une graine de
carte redonne le même déploiement.
"""
import maps
from rng_scope import RNG

ROLES = ('front', 'mid', 'back')
RAMPART = 4   # code de case du rempart
GATE = 3      # code de case de la porte


def effective_role(u):
    """Les unités fragiles (tireurs, mages) sont TOUJOURS placées à
    l'arrière, protégées par la mêlée — quel que soit leur rôle déclaré
    dans la base."""
    if u._max_range >= 4 or u.spells:
        return 'back'
    return u.role


def find_free_near(bf, x, y, unit, min_x=0, back=-1):
    """Position libre la plus proche de (x, y) pour l'unité (multi-cases
    supporté), en anneaux carrés croissants; None si la carte est pleine.

    `back`: sens de l'arrière du camp (-1 armée 1, +1 armée 2). À distance
    égale, on recule plutôt qu'on n'avance. Un parcours toujours ouest →
    est reculait les tireurs de l'armée 1 et poussait ceux de l'armée 2
    DEVANT leur infanterie."""
    for radius in range(0, max(bf.width, bf.height)):
        dxs = range(-radius, radius + 1) if back < 0 else range(radius, -radius - 1, -1)
        for dx in dxs:
            for dy in range(-radius, radius + 1):
                if abs(dx) != radius and abs(dy) != radius:
                    continue
                nx, ny = x + dx, y + dy
                if nx < min_x:
                    continue
                if bf.can_place_unit(nx, ny, unit):
                    return (nx, ny)
    return None


def _put(bf, u, pos):
    u.position = pos
    bf.place_unit(u)


def _place_or_nearby(bf, u, pos, min_x, back=-1):
    """Place u en pos, sinon sur la case libre la plus proche (vers
    l'arrière du camp à distance égale)."""
    if not bf.can_place_unit(*pos, u):
        pos = find_free_near(bf, pos[0], pos[1], u, min_x=min_x, back=back)
    if pos is not None:
        _put(bf, u, pos)


# ─── Bataille rangée: rangs par groupe ───

def place_rank(bf, units, x_start, step_x, band_top, band_h, min_x=0):
    """Range des unités en RANGS dans la bande qui leur est allouée.

    Une colonne ne dépasse jamais la hauteur de bande: au-delà, on ouvre
    une colonne supplémentaire en arrière. Sans cela, une armée nombreuse
    formait une file unique plus haute que la carte, et tout le monde
    finissait tassé contre le bord inférieur.

    Une unité large (cavalerie 2×2) déborde de sa colonne vers l'ARRIÈRE
    de son camp: à l'ouest pour l'armée 1 (step_x = -1), à l'est pour
    l'armée 2. Ancrée partout au coin haut-gauche, elle débordait vers
    l'avant chez l'une et vers l'arrière chez l'autre: chez l'armée 2, la
    cavalerie mordait sur la colonne des tireurs, repoussés DEVANT
    l'infanterie (Forêt · cavalerie: 64 % pour la gauche).

    Retourne la largeur occupée, en cases (pour décaler la suite).
    """
    if not units:
        return 0
    units = sorted(units, key=lambda u: -u.size)
    band_h = max(1, band_h)

    columns = []
    cur, cur_h = [], 0
    for u in units:
        uh = bf.get_unit_dims(u)[1]
        if cur and cur_h + uh > band_h:
            columns.append((cur, cur_h))
            cur, cur_h = [], 0
        cur.append(u)
        cur_h += uh
    if cur:
        columns.append((cur, cur_h))

    offset = 0
    for col_units, col_h in columns:
        x_col = x_start + offset * step_x
        y = band_top + max(0, (band_h - col_h) // 2)
        for u in col_units:
            w, h = bf.get_unit_dims(u)
            ax = _anchor_x(bf, x_col, w, step_x, min_x)
            _place_or_nearby(bf, u, (ax, max(1, min(bf.height - 1 - h, y))), min_x,
                             back=step_x)
            y += h
        offset += max(bf.get_unit_dims(u)[0] for u in col_units)
    return offset


def _anchor_x(bf, x_col, w, step_x, min_x):
    """Ancre (coin gauche) d'une unité de largeur w dont la colonne de
    déploiement est x_col: elle s'étend vers l'arrière de son camp."""
    ax = x_col - (w - 1) if step_x < 0 else x_col
    return max(min_x, min(bf.width - w, ax))


def place_support(bf, units, x_start, step_x, band_top, band_h, min_x=0):
    """Arrière du groupe: tireurs et machines de guerre.

    Les pièces volumineuses (balistes, catapultes) sont espacées dans la
    bande — elles ont besoin d'angle de tir — le reste s'aligne en rangs
    derrière la mêlée.
    """
    if not units:
        return 0
    large = [u for u in units if u.size >= 2]
    normal = [u for u in units if u.size < 2]
    used = 0
    if large:
        spacing = max(2, band_h // (len(large) + 1))
        for i, u in enumerate(large):
            w, h = bf.get_unit_dims(u)
            ty = max(1, min(bf.height - 1 - h, band_top + spacing * (i + 1) - h // 2))
            _place_or_nearby(bf, u, (_anchor_x(bf, x_start, w, step_x, min_x), ty), min_x,
                             back=step_x)
        used = max(bf.get_unit_dims(u)[0] for u in large)
    if normal:
        used = max(used, place_rank(bf, normal, x_start, step_x, band_top, band_h, min_x))
    return max(1, used)


def deploy_span(bf, base_x):
    """(haut, hauteur) du tronçon praticable de la colonne de déploiement
    où ranger l'armée: le plus long, de préférence celui qui passe par le
    centre. Dans un défilé, déployer sur toute la hauteur jetait la moitié
    des unités dans les parois rocheuses."""
    col = max(0, min(bf.width - 1, base_x))
    mid_y = bf.height // 2

    def walkable(yy):
        if bf.is_valid(col, yy):
            return True
        # Un obstacle ISOLÉ (arbre de lisière, rocher) ne coupe pas la
        # colonne: l'unité qui y tomberait est simplement décalée.
        return (0 < yy < bf.height - 1 and bf.is_valid(col, yy - 1)
                and bf.is_valid(col, yy + 1))

    best, best_score = (1, max(4, bf.height - 2)), None
    y = 1
    while y < bf.height - 1:
        if walkable(y):
            y0 = y
            while y < bf.height - 1 and walkable(y):
                y += 1
            length = y - y0
            # Le tronçon le plus proche du centre l'emporte: un long tronçon
            # excentré enverrait l'armée au bord de la carte
            dist = 0 if y0 <= mid_y < y else min(abs(mid_y - y0), abs(mid_y - (y - 1)))
            score = length - 4 * dist
            if best_score is None or score > best_score:
                best, best_score = (y0, length), score
        else:
            y += 1
    return best


def band_heights(weights, avail):
    """Hauteur de bande de chaque groupe: sa hauteur naturelle si tout
    tient, sinon une part au prorata (≥ 3) — les rangs s'épaississent."""
    total_w = sum(weights)
    if total_w <= avail:
        return list(weights)
    bands = [max(3, int(avail * w / total_w)) for w in weights]
    over = sum(bands) - avail
    i = 0
    while over > 0 and any(b > 3 for b in bands):
        j = i % len(bands)
        if bands[j] > 3:
            bands[j] -= 1
            over -= 1
        i += 1
    return bands


def deploy_contingents(bf, units, base_x, step_x, min_x=0):
    """Déploie une armée GROUPE PAR GROUPE, en rangs.

    Une armée peut être articulée en plusieurs groupes: chacun forme un
    corps distinct (sa ligne de front, son centre, ses tireurs), occupe une
    bande de terrain proportionnelle à son effectif, et reste séparé du
    voisin par un intervalle. L'ensemble est centré sur la carte et ne peut
    plus déborder: si les effectifs ne tiennent pas sur une seule ligne, les
    rangs s'épaississent au lieu de s'entasser contre un bord.
    """
    if not units:
        return
    order, groups = [], {}
    for u in units:
        key = u.contingent or ""
        if key not in groups:
            groups[key] = {role: [] for role in ROLES}
            order.append(key)
        groups[key][effective_role(u)].append(u)
    for key in order:
        for role_list in groups[key].values():
            RNG.shuffle(role_list)

    top_margin, usable = deploy_span(bf, base_x)
    usable = max(4, usable)
    gap = 2 if len(order) > 1 else 0
    avail = max(len(order) * 3, usable - gap * (len(order) - 1))

    # Hauteur "naturelle" d'un groupe = sa colonne de rôle la plus fournie
    weights = [max(1, max(sum(bf.get_unit_dims(u)[1] for u in groups[key][role])
                          for role in ROLES))
               for key in order]
    bands = band_heights(weights, avail)

    total_h = sum(bands) + gap * (len(order) - 1)
    # Centré sur le MILIEU DE LA CARTE, borné au tronçon praticable (et non
    # centré dans le tronçon, qui peut être excentré)
    lo = top_margin
    hi = max(lo, top_margin + usable - total_h)
    cur_y = max(lo, min(hi, bf.height // 2 - total_h // 2))

    for key, band_h in zip(order, bands):
        g = groups[key]
        # Un rôle vide ne consomme pas de colonne: sans cela, un groupe sans
        # unité de « front » laissait un trou béant dans la ligne, son
        # centre planté un rang en arrière.
        x_cursor = base_x
        x_cursor += place_rank(bf, g['front'], x_cursor, step_x, cur_y, band_h, min_x) * step_x
        x_cursor += place_rank(bf, g['mid'], x_cursor, step_x, cur_y, band_h, min_x) * step_x
        place_support(bf, g['back'], x_cursor, step_x, cur_y, band_h, min_x)
        cur_y += band_h + gap


def push_machines_forward(bf, army, gap=1):
    """Siège: les machines de l'assaillant (bélier, tour, balistes...)
    passent DEVANT la ligne de ses troupes. Déployées dans les rangs, elles
    butaient sur l'infanterie qui marchait devant elles (une tour 2×4 ne se
    faufile pas entre deux files). Leurs servants les rejoignent ensuite
    (siege_engines.gather_attendants)."""
    import siege_engines as se
    machines = sorted((u for u in army if se.is_machine(u) and u.position is not None),
                      key=lambda u: u.uid)
    troops = [u for u in army if not se.is_machine(u) and u.position is not None]
    if not machines or not troops:
        return
    front = max(u.position[0] + bf.get_unit_dims(u)[0] - 1 for u in troops) + 1 + gap
    for m in machines:
        w, h = bf.get_unit_dims(m)
        mx, my = m.position
        bf.remove_unit(m)
        spot = None
        for dx in range(0, 4):
            for dy in sorted(range(-bf.height, bf.height), key=lambda d: (abs(d), d)):
                pos = (front + dx, my + dy)
                if 0 < pos[1] and pos[1] + h < bf.height and bf.can_place_unit(*pos, m):
                    spot = pos
                    break
            if spot:
                break
        m.position = spot or (mx, my)
        bf.place_unit(m)


# ─── Siège: garnison de l'enceinte extérieure ───

def _rampart_rows(bf, wall_x, gate_zone, gate_center):
    """Rangées de rempart hors de la zone de porte, de la plus proche de la
    porte à la plus lointaine, en alternant bas/haut pour étaler les
    tireurs symétriquement."""
    slots = [y for y in range(1, bf.height - 1)
             if y not in gate_zone and bf.grid[wall_x + 1][y] == RAMPART]
    above = sorted([y for y in slots if y < gate_center], reverse=True)
    below = sorted([y for y in slots if y >= gate_center])
    rows = []
    i_a = i_b = 0
    while i_a < len(above) or i_b < len(below):
        if i_b < len(below):
            rows.append(below[i_b])
            i_b += 1
        if i_a < len(above):
            rows.append(above[i_a])
            i_a += 1
    return rows


def _place_on_ramparts(bf, units, wall_x, rows, gate_center, min_x):
    """Tireurs et mages sur le rempart, étalés autour de la porte; au-delà,
    un 2e rang (wall_x + 2), en dernier recours la case libre la plus
    proche."""
    taken = set()
    for u in units:
        row = next((ry for ry in rows
                    if ry not in taken and bf.can_place_unit(wall_x + 1, ry, u)), None)
        if row is not None:
            _put(bf, u, (wall_x + 1, row))
            taken.add(row)
            continue
        row = next((ry for ry in rows if bf.can_place_unit(wall_x + 2, ry, u)), None)
        if row is not None:
            _put(bf, u, (wall_x + 2, row))
            continue
        pos = find_free_near(bf, wall_x + 2, gate_center, u, min_x=min_x)
        if pos:
            _put(bf, u, pos)


def _gate_slot(bf, u, pos, taken):
    """Vrai si u peut tenir en pos: dans la carte, hors rempart (pas de
    mêlée sur le rempart) et case pas déjà prise par la garnison."""
    x, y = pos
    if not (0 <= x < bf.width and 0 <= y < bf.height):
        return False
    return bf.grid[x][y] != RAMPART and pos not in taken and bf.can_place_unit(x, y, u)


def _place_behind_gate(bf, units, wall_x, gate_rows, gate_center):
    """Mêlée et officiers derrière la porte, PAS sur le rempart: d'abord
    dans l'axe des portes, puis en débordement autour du centre de porte."""
    taken = set()
    for u in units:
        pos = next(((wall_x + dx, gy) for dx in range(1, 6) for gy in gate_rows
                    if _gate_slot(bf, u, (wall_x + dx, gy), taken)), None)
        if pos is None:
            pos = next(((wall_x + dx, gate_center + off * sign)
                        for dx in range(1, 8) for off in range(0, bf.height // 2)
                        for sign in (1, -1)
                        if _gate_slot(bf, u, (wall_x + dx, gate_center + off * sign), taken)),
                       None)
        if pos is not None:
            _put(bf, u, pos)
            taken.add(pos)


def deploy_garrison(bf, defenders, center_y):
    """Garnison de siège sur l'enceinte EXTÉRIEURE, répartie par CAPACITÉ
    et non par rôle: tireurs (portée ≥ 4) et mages au rempart, tout le
    reste (y compris les officiers sans arme à distance) derrière la porte.

    L'ouverture des portes n'est pas décidée ici: le CommanderAI (posture
    « sortie ») les ouvre en cours de bataille si les défenseurs se font
    canarder sans pouvoir répliquer."""
    wall_x = bf.rings[0]['wall_x']
    gate_positions = bf.siege_data.get('gate_positions', [])
    gate_center = gate_positions[0] if gate_positions else center_y
    gate_rows = sorted(y for y in range(bf.height) if bf.grid[wall_x][y] == GATE)
    # Zone porte élargie (±2 cases) pour garder la mêlée proche
    gate_zone = {gy + dy for gy in gate_rows for dy in range(-2, 3)}

    wall_units = [u for u in defenders if u._max_range >= 4 or u.spells]
    gate_units = [u for u in defenders if not (u._max_range >= 4 or u.spells)]
    _place_on_ramparts(bf, wall_units, wall_x,
                       _rampart_rows(bf, wall_x, gate_zone, gate_center),
                       gate_center, wall_x + 1)
    _place_behind_gate(bf, gate_units, wall_x, gate_rows, gate_center)


# ─── Entrée ───

def deploy_armies(bf, army1, army2, center_y):
    # Rôles de l'armée 2 mélangés AVANT tout placement, même en bataille
    # rangée où ils ne servent pas: l'ordre des tirages fixe le déploiement
    # d'une graine donnée.
    army2_roles = {role: [] for role in ROLES}
    for u in army2:
        army2_roles[effective_role(u)].append(u)
    for role_list in army2_roles.values():
        RNG.shuffle(role_list)

    # Front de l'armée 1, à gauche du centre. Demi-écart entre les fronts:
    # les armées marchent un peu avant le choc (~7 rounds pour l'infanterie
    # en terrain découvert); forêt et village imposent le leur, le siège
    # garde son placement historique. Formule partagée avec la génération
    # des cartes (rien de procédural ne doit tomber dans les zones de
    # déploiement).
    a1_front = maps.deploy_front(bf.width, bf.deploy_gap, bf.is_siege)
    deploy_contingents(bf, army1, a1_front, -1)
    if bf.is_siege:
        deploy_garrison(bf, army2_roles['front'] + army2_roles['mid'] + army2_roles['back'],
                        center_y)
    else:
        # Reflet exact de l'armée 1 (le terrain est en miroir x → width-1-x)
        deploy_contingents(bf, army2, bf.width - 1 - a1_front, +1)
