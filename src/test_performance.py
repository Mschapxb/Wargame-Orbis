"""Tests des optimisations de performance: elles ne doivent RIEN changer.

Chaque structure rapide est confrontée à la version naïve qu'elle remplace
(plus proche voisin, A* à indices plats), sur des tirages aléatoires. Plus
les correctifs trouvés en chemin (listes d'armée partagées avec les
commandants, jeton recopié à chaque import). Script exécutable:
    python test_performance.py            # tout
    python test_performance.py astar      # seulement les tests dont le nom contient 'astar'
"""
import heapq, os, sys, random, tempfile, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import spatial
import terrain as tr
import unit_library as ul
from battle import Battle
from battlefield import Battlefield
from models import Arme
from unit import Unit

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


class Pos:
    __slots__ = ('position',)

    def __init__(self, p):
        self.position = p


def soldier(pos):
    u = Unit("Soldat", pv=1, vitesse=4, morale=5, sauvegarde=7, color=(1, 1, 1),
             armes=[Arme("Epee", 1, 4, 4, 0, "1", porte=1)])
    u.position = pos
    return u


class Sides(spatial.Neighbourhood):
    """Bataille minimale: deux camps posés sur le champ de bataille."""

    def __init__(self, bf, army1, army2):
        self.battlefield = bf
        self.army1, self.army2 = army1, army2
        for u in army1 + army2:
            bf.place_unit(u)

    def get_enemies(self, unit):
        return self.army2 if any(u is unit for u in self.army1) else self.army1

    def get_allies(self, unit):
        return self.army1 if any(u is unit for u in self.army1) else self.army2


# ── Plus proche voisin (spatial.NearestDistance / NearestUnit) ──


@test
def test_distance_au_plus_proche_exacte():
    rnd = random.Random(7)
    for _ in range(1500):
        w, h = rnd.randint(1, 180), rnd.randint(1, 64)
        pts = [(rnd.randrange(w), rnd.randrange(h)) for _ in range(rnd.randint(0, 40))]
        nd = spatial.NearestDistance(pts)
        for _ in range(20):
            x, y = rnd.randrange(-5, w + 5), rnd.randrange(-5, h + 5)
            attendu = min((abs(px - x) + abs(py - y) for px, py in pts), default=99)
            assert nd.dist(x, y, 99) == attendu, (pts, x, y)


@test
def test_unite_la_plus_proche_comme_min():
    """Même unité que min(): la première de la liste à égalité, doublons de
    position compris."""
    rnd = random.Random(11)
    for _ in range(2000):
        w, h = rnd.randint(1, 30), rnd.randint(1, 20)
        units = [Pos((rnd.randrange(w), rnd.randrange(h))) for _ in range(rnd.randint(0, 30))]
        nu = spatial.NearestUnit(units)
        for _ in range(15):
            x, y = rnd.randrange(-3, w + 3), rnd.randrange(-3, h + 3)
            attendu = (min(units, key=lambda e: abs(x - e.position[0]) + abs(y - e.position[1]))
                       if units else None)
            assert nu.nearest(x, y) is attendu, (x, y)


# ── A* des unités d'une case: la version plate refait la recherche d'origine ──


OCTILE = 1.414 - 1.0


def octile(dx, dy):
    dx, dy = abs(dx), abs(dy)
    return dy + dx * OCTILE if dy > dx else dx + dy * OCTILE


def reference_a_star(bf, start, goal, unit, battle, reserved, max_nodes, partial):
    """L'A* à tuples de la branche 1×1, écrit sans indices plats: même
    heuristique octile, même objectif de repli (case libre la plus proche
    d'un objectif occupé ou emmuré)."""
    if start == goal:
        return [goal]
    enemy_cells, ally_positions = bf._occupancy_split(unit, battle)
    sx, sy = start
    gx, gy = goal
    grid, width, height = bf.grid, bf.width, bf.height
    gate_hp = bf.gate_hp
    open_cells = bf.gate_cells_open_for(unit)
    terr = bf.terrain
    fires = getattr(bf, 'fires', None)

    def static_ok(x, y):
        return (0 <= x < width and 0 <= y < height and grid[x][y] not in (1, 2)
                and (terr is None or tr.MOVE[terr[x][y]] is not None))

    def blocked(x, y):
        return ((x, y) in reserved or (x, y) in enemy_cells
                or (grid[x][y] == 3 and (x, y) not in open_cells and gate_hp.get((x, y), 0) > 0))

    def walled_in(x, y):
        return not any(static_ok(x + dx, y + dy) and not blocked(x + dx, y + dy)
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)

    xs = -1 if gx >= sx else 1
    goal_blocked = not bf.is_valid(gx, gy) or goal in reserved or goal in enemy_cells
    if partial and max(abs(gx - sx), abs(gy - sy)) > 1 and (goal_blocked or walled_in(gx, gy)):
        alt = None
        for r in range(1, 4):
            cands = [(max(abs(x - sx), abs(y - sy)), abs(x - sx) + abs(y - sy), xs * x, y, (x, y))
                     for x in range(gx - r, gx + r + 1) for y in range(gy - r, gy + r + 1)
                     if max(abs(x - gx), abs(y - gy)) == r and static_ok(x, y)
                     and not blocked(x, y) and (x, y) not in ally_positions
                     and not walled_in(x, y)]
            if cands:
                alt = min(cands)[-1]
                break
        if alt is not None:
            if alt == start:
                return []
            gx, gy = goal = alt
            goal_blocked = False
            xs = -1 if gx >= sx else 1
    dist_to_goal = max(abs(gx - sx), abs(gy - sy))
    ally_penalty = 1.5 if dist_to_goal > 8 else 2.5
    open_set = [(octile(gx - sx, gy - sy), 0.0, xs * sx, sy, sx)]
    g_score = {start: 0.0}
    came_from = {}
    best_node, best_h = start, dist_to_goal
    if goal_blocked:
        if not partial:
            return []
        max_nodes = min(max_nodes, 40 + 6 * (dist_to_goal + 3) ** 2)
    explored = 0
    cur_el = False
    while open_set:
        _, g, _xk, cy, cx = heapq.heappop(open_set)
        explored += 1
        if explored > max_nodes:
            break
        if cx == gx and cy == gy:
            path, cur = [], (gx, gy)
            while cur in came_from:
                path.append(cur)
                cur = came_from[cur]
            return path[::-1]
        current = (cx, cy)
        if g > g_score.get(current, 1e9):
            continue
        if partial:
            hc = max(abs(gx - cx), abs(gy - cy))
            if hc < best_h:
                best_h, best_node = hc, current
        if terr is not None:
            cur_el = tr.MOVE_ELEV[terr[cx][cy]][1]
        for dx, dy in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
            nx, ny = cx + dx, cy + dy
            nb = (nx, ny)
            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            cell = grid[nx][ny]
            if cell == 1 or cell == 2:
                continue
            if cell == 3 and nb not in open_cells and gate_hp.get(nb, 0) > 0:
                continue
            if nb in reserved or nb in enemy_cells:
                continue
            cost = 1.414 if (dx and dy) else 1.0
            if terr is not None:
                mc, n_el = tr.MOVE_ELEV[terr[nx][ny]]
                if mc is None:
                    continue
                if n_el and not cur_el:
                    mc *= tr.UPHILL_FACTOR
                cost *= mc
            if fires and nb in fires:
                cost *= tr.FIRE_MOVE_FACTOR
            if dx and dy and enemy_cells and (
                    (cx + dx, cy) in enemy_cells and (cx, cy + dy) in enemy_cells):
                continue
            if nb in ally_positions and nb != goal:
                new_g = g + cost + ally_penalty
            else:
                new_g = g + cost
            if new_g < g_score.get(nb, 1e9):
                came_from[nb] = current
                g_score[nb] = new_g
                heapq.heappush(open_set, (new_g + octile(gx - nx, gy - ny), new_g,
                                          xs * nx, ny, nx))
    if partial and best_node != start:
        path, cur = [], best_node
        while cur in came_from:
            path.append(cur)
            cur = came_from[cur]
        return path[::-1]
    return []


def random_field(rnd):
    """Champ de bataille tiré au sort: obstacles, murs, portes (fermées,
    ouvertes, détruites), remparts, terrain varié ou absent, feux."""
    w, h = rnd.randint(6, 26), rnd.randint(5, 18)
    grid = [[0] * h for _ in range(w)]
    for x in range(w):
        for y in range(h):
            r = rnd.random()
            grid[x][y] = (1 if r < 0.08 else 2 if r < 0.11 else 3 if r < 0.14
                          else 4 if r < 0.17 else 5 if r < 0.19 else 0)
    data = {}
    if rnd.random() < 0.8:
        kinds = [tr.PLAIN] * 6 + [tr.HILL, tr.HILL, tr.WOOD, tr.RIVER, tr.FORD, tr.MARSH,
                                  tr.RUBBLE, tr.BURNT]
        data['terrain'] = [[rnd.choice(kinds) for _ in range(h)] for _ in range(w)]
    bf = Battlefield(w, h, 0, "Prairie", grid, data)
    gates = [(x, y) for x in range(w) for y in range(h) if grid[x][y] == 3]
    bf.gate_hp = {g: rnd.choice([0, 5, 5]) for g in gates}
    bf.open_gate_cells = {g for g in gates if rnd.random() < 0.3}
    if gates and rnd.random() < 0.5:
        # Citadelle: la garnison a ses propres portes (gate_cells_open_for)
        wx = rnd.randrange(w)
        bf.rings = [{'wall_x': wx, 'gates': gates[::2]}, {'wall_x': w - 1, 'gates': gates[1::2]}]
    if rnd.random() < 0.5:
        bf.fires = {(rnd.randrange(w), rnd.randrange(h)): 2 for _ in range(rnd.randint(1, 8))}
    free = [(x, y) for x in range(w) for y in range(h) if grid[x][y] in (0, 4, 5)]
    rnd.shuffle(free)
    return bf, free


@test
def test_astar_plat_identique_a_la_reference():
    rnd = random.Random(2026)
    compared = 0
    for trial in range(700):
        bf, free = random_field(rnd)
        if len(free) < 6:
            continue
        n1, n2 = rnd.randint(1, len(free) // 4 + 1), rnd.randint(0, len(free) // 4)
        army1 = [soldier(p) for p in free[:n1]]
        army2 = [soldier(p) for p in free[n1:n1 + n2]]
        b = Sides(bf, army1, army2)
        for u in rnd.sample(army1 + army2, min(3, len(army1 + army2))):
            if rnd.random() < 0.2:
                u.is_alive = False          # mort encore sur la grille
        unit = army1[0]
        unit.garrison = rnd.random() < 0.5
        window = trial % 2 == 1             # dans la fenêtre de planification
        if window:
            bf.occupancy_cache(True)
        reserved = set()
        try:
            for _ in range(4):
                # Les réservations ne font que grossir pendant une passe
                reserved.update(rnd.choice(free) for _ in range(rnd.randint(0, 4)))
                if rnd.random() < 0.2:
                    reserved.add((rnd.randint(-3, bf.width + 3), rnd.randint(-3, bf.height + 3)))
                if rnd.random() < 0.15:
                    goal = (rnd.randint(-2, bf.width + 1), rnd.randint(-2, bf.height + 1))
                else:
                    goal = rnd.choice(free)
                max_nodes = rnd.choice((3, 20, 80, 300, 1200))
                partial = rnd.random() < 0.6
                attendu = reference_a_star(bf, unit.position, goal, unit, b, reserved,
                                           max_nodes, partial)
                rendu = bf.a_star_path(unit.position, goal, unit, b, reserved,
                                       max_nodes=max_nodes, partial=partial)
                assert rendu == attendu, (trial, unit.position, goal, max_nodes, partial,
                                          attendu, rendu)
                compared += 1
        finally:
            bf.occupancy_cache(False)
    assert compared > 1500, compared


# ── Correctifs ──


@test
def test_commandants_voient_les_listes_de_la_bataille():
    """Les armées sont filtrées EN PLACE: les commandants gardent les mêmes
    listes que la bataille. Une tour accostée quittait battle.army1 mais
    restait, vivante, dans la liste du commandant adverse — qui en faisait
    sa cible de tir prioritaire."""
    attack = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 8),
                                                ("Arbaletrier régulier", 4), ("Officier", 1)])
    attack += ul.build_army("Engins de siège", [("Tour de siège", 1)])
    defense = ul.build_army("Armée Skaldienne", [("Infanterie régulière", 5),
                                                 ("Arbaletrier régulier", 4), ("Officier", 1)])
    docked_seen = 0
    for seed in (1, 2, 3):
        random.seed(seed)
        b = Battle(attack, defense, 40, 30, 8, map_name="Siège")
        while not b.is_battle_over() and b.round <= 60:
            b.simulate_round()
            assert b.commander1.army is b.army1 and b.commander1.enemy_army is b.army2
            assert b.commander2.army is b.army2 and b.commander2.enemy_army is b.army1
            tower = next(u for u in b.army1_roster if u.siege_engine == "tower")
            if tower.docked:
                docked_seen += 1
                assert all(e is not tower for e in b.commander2.enemy_army)
    assert docked_seen, "aucune tour accostée: le test ne vérifie rien"


@test
def test_jeton_pas_recopie_s_il_est_deja_en_place():
    """install_token ne réécrit pas un jeton identique (deux processus qui
    importaient ensemble se bloquaient sur le fichier sous Windows)."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "source.png")
        with open(src, "wb") as f:
            f.write(b"\x89PNG-factice")
        saved = ul.TOKENS_DIR
        ul.TOKENS_DIR = os.path.join(tmp, "tokens")
        try:
            assert ul.install_token(src, "Essai")
            dest = os.path.join(ul.TOKENS_DIR, "Essai.png")
            os.utime(dest, (1_000_000, 1_000_000))
            assert ul.install_token(src, "Essai")
            assert os.stat(dest).st_mtime == 1_000_000       # pas recopié
            with open(src, "wb") as f:
                f.write(b"\x89PNG-autre")
            assert ul.install_token(src, "Essai")
            with open(dest, "rb") as f:
                assert f.read() == b"\x89PNG-autre"            # contenu changé: recopié
            assert not [n for n in os.listdir(ul.TOKENS_DIR) if n.endswith(".tmp")]
        finally:
            ul.TOKENS_DIR = saved


# ── Runner (ajouter les nouveaux tests AU-DESSUS de cette ligne) ──

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
    print(f"{len(fails)} ECHEC(S)" if fails else "Tous les tests performance passent.")
    sys.exit(1 if fails else 0)
