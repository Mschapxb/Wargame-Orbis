"""Outils partagés des générateurs: miroir, chemins, déploiement."""

import math

import terrain as tr


def _carve(grid, x, y, r, width, height):
    """Dégage un disque de rayon r (sentiers, clairières)."""
    ri = int(math.ceil(r))
    for dx in range(-ri, ri + 1):
        for dy in range(-ri, ri + 1):
            if dx * dx + dy * dy <= r * r:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    grid[nx][ny] = 0


def _connected(grid, width, height, start, goal, terrain=None, avoid=()):
    """Vrai si goal est atteignable depuis start (8-voisinage, cases libres).
    Avec `terrain`: la rivière bloque, et les terrains de `avoid` aussi."""
    return _bfs_path(grid, width, height, [start], [goal], terrain, avoid) is not None


def _bfs_path(grid, width, height, starts, goals, terrain=None, avoid=(), blocked=()):
    """Plus court chemin (en cases, 8-voisinage) d'une case de `starts` à une
    case de `goals`, ou None. `blocked`: cases interdites en plus."""
    goals = set(goals)
    blocked = set(blocked)

    def ok(x, y):
        if grid[x][y] != 0 or (x, y) in blocked:
            return False
        if terrain is not None:
            name = terrain[x][y]
            if tr.MOVE[name] is None or name in avoid:
                return False
        return True

    from collections import deque
    came = {}
    queue = deque()
    for s in starts:
        if ok(*s) and s not in came:
            came[s] = None
            queue.append(s)
    while queue:
        cur = queue.popleft()
        if cur in goals:
            path = []
            while cur is not None:
                path.append(cur)
                cur = came[cur]
            return path[::-1]
        cx, cy = cur
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = cx + dx, cy + dy
                if (0 <= nx < width and 0 <= ny < height and (nx, ny) not in came
                        and ok(nx, ny)):
                    came[(nx, ny)] = cur
                    queue.append((nx, ny))
    return None


def _mirror_grid(grid, width, height):
    """Recopie la moitié ouest de la grille bâtie sur l'est (x → width-1-x).
    Sans cela, les tirages aléatoires (rochers, maisons, saillies) donnent
    à un camp plus de couverts qu'à l'autre."""
    for x in range(width // 2):
        for y in range(height):
            grid[width - 1 - x][y] = grid[x][y]


def _mirror_terrain(terr, width, height):
    """Recopie la moitié ouest sur l'est (x → width-1-x): aucun camp n'est
    avantagé par le terrain."""
    for x in range(width // 2):
        for y in range(height):
            terr[width - 1 - x][y] = terr[x][y]


def _paint_disc(terr, cx, cy, r, name, width, height):
    """Peint un disque de terrain (centre réel autorisé)."""
    ri = int(math.ceil(r)) + 1
    for x in range(int(cx) - ri, int(cx) + ri + 2):
        for y in range(int(cy) - ri, int(cy) + ri + 2):
            if 0 <= x < width and 0 <= y < height and (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                terr[x][y] = name


def deploy_front(width, deploy_gap=None, siege=False):
    """Colonne de front de l'armée 1 (source unique: Battle._place_armies
    l'utilise aussi). Rien de procédural ne doit tomber à sa gauche
    (principe « zones de déploiement en plaine »)."""
    mid_x = width // 2
    if siege:
        gap = 12
    elif deploy_gap:
        gap = int(deploy_gap)
    else:
        gap = max(12, int(width * 0.12))
    return mid_x - max(4, min(gap, mid_x - 8))
