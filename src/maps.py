"""Système de cartes — génère différents terrains pour le champ de bataille.

Types de cellules dans la grille:
    0 = vide (traversable)
    1 = obstacle (infranchissable, bloque vision)
    2 = mur (infranchissable, unités dessus = +2 svg, CaC ne passe pas)
    3 = porte (destructible, a des PV)
"""

import random


# ═══════════════════════════════════════════════════════════════
#                    DÉFINITIONS DES MAPS
# ═══════════════════════════════════════════════════════════════

MAP_TYPES = {
    "Prairie": {
        "description": "Terrain ouvert avec peu d'obstacles",
        "bg_color": (45, 65, 35),
        "obstacle_color": (70, 90, 55),
        "grid_color": (55, 75, 45),
    },
    "Forêt": {
        "description": "Dense forêt avec de nombreux arbres",
        "bg_color": (30, 55, 25),
        "obstacle_color": (20, 70, 15),
        "grid_color": (35, 60, 30),
    },
    "Village": {
        "description": "Village avec bâtiments en obstacles",
        "bg_color": (55, 50, 40),
        "obstacle_color": (90, 70, 50),
        "grid_color": (60, 55, 45),
    },
    "Siège": {
        "description": "Forteresse avec murs et portes défensives",
        "bg_color": (40, 45, 50),
        "obstacle_color": (80, 80, 80),
        "grid_color": (50, 55, 60),
        "wall_color": (100, 100, 110),
        "gate_color": (140, 100, 50),
    },
}


def get_map_names():
    return list(MAP_TYPES.keys())


def get_map_info(name):
    return MAP_TYPES.get(name, MAP_TYPES["Prairie"])


# ═══════════════════════════════════════════════════════════════
#                      GÉNÉRATEURS
# ═══════════════════════════════════════════════════════════════

def generate_prairie(width, height):
    """Prairie: 3-5 petits obstacles éparpillés."""
    grid = [[0] * height for _ in range(width)]
    count = random.randint(3, 5)
    obstacles = []
    margin_x = width // 4
    
    for _ in range(count * 30):
        if len(obstacles) >= count:
            break
        x = random.randint(margin_x, width - margin_x - 1)
        y = random.randint(3, height - 4)
        if grid[x][y] == 0 and all(abs(x-ox)+abs(y-oy) > 8 for ox,oy in obstacles):
            grid[x][y] = 1
            obstacles.append((x, y))
    
    return grid, {}


def generate_forest(width, height):
    """Forêt: dense avec de nombreux clusters d'arbres."""
    grid = [[0] * height for _ in range(width)]
    
    # Zone de sécurité au centre pour le combat
    mid_x = width // 2
    
    # Placer de nombreux clusters d'arbres
    num_clusters = random.randint(12, 20)
    for _ in range(num_clusters):
        cx = random.randint(5, width - 6)
        cy = random.randint(3, height - 4)
        cluster_size = random.randint(4, 10)
        
        for _ in range(cluster_size):
            ox = cx + random.randint(-3, 3)
            oy = cy + random.randint(-3, 3)
            if 0 < ox < width - 1 and 0 < oy < height - 1:
                # Laisser un couloir central libre (±3 cases)
                if abs(ox - mid_x) > 4:
                    grid[ox][oy] = 1
    
    return grid, {}


def generate_village(width, height):
    """Village avec de nombreux bâtiments."""
    grid = [[0] * height for _ in range(width)]
    
    # Placer 8-14 bâtiments sur toute la carte
    num_buildings = random.randint(8, 14)
    buildings = []
    
    for _ in range(num_buildings * 30):
        if len(buildings) >= num_buildings:
            break
        bw = random.randint(2, 5)
        bh = random.randint(2, 4)
        bx = random.randint(5, width - 6 - bw)
        by = random.randint(3, height - 4 - bh)
        
        overlap = False
        for (ox, oy, ow, oh) in buildings:
            if (bx < ox + ow + 2 and bx + bw + 2 > ox and
                by < oy + oh + 2 and by + bh + 2 > oy):
                overlap = True
                break
        
        if not overlap:
            for x in range(bx, bx + bw):
                for y in range(by, by + bh):
                    if 0 <= x < width and 0 <= y < height:
                        grid[x][y] = 1
            buildings.append((bx, by, bw, bh))
    
    return grid, {}


def generate_siege(width, height):
    """Siège: mur vertical avec une porte de 6 cases, remparts et escaliers."""
    grid = [[0] * height for _ in range(width)]
    
    # Mur vertical au 2/3 de la map (défenseur = armée 2 à droite)
    wall_x = width * 2 // 3
    
    # Une seule porte de 6 cases, centrée
    gate_center = height // 2
    gate_half = 3  # 6 cases: de center-3 à center+2
    gate_positions = [gate_center]  # Y central pour le placement des défenseurs
    
    # Construire le mur
    walls = []
    gates = []
    ramparts = []
    stairs = []
    
    for y in range(1, height - 1):
        is_gate = (gate_center - gate_half <= y < gate_center + gate_half)
        if is_gate:
            grid[wall_x][y] = 3  # Porte
            gates.append((wall_x, y))
        else:
            grid[wall_x][y] = 2  # Mur
            walls.append((wall_x, y))
            # Remparts: 2 cases marchables derrière le mur
            for dx in [1, 2]:
                rx = wall_x + dx
                if 0 <= rx < width and grid[rx][y] == 0:
                    grid[rx][y] = 4
                    ramparts.append((rx, y))
            # Escalier derrière les remparts
            sx = wall_x + 3
            if 0 <= sx < width and grid[sx][y] == 0:
                grid[sx][y] = 5
                stairs.append((sx, y))
    
    # Tours aux coins du mur
    for dy in [-1, 0, 1]:
        for y_anchor in [1, height - 2]:
            tx, ty = wall_x - 1, y_anchor + dy
            if 0 <= ty < height:
                grid[tx][ty] = 2
                walls.append((tx, ty))
            tx2 = wall_x + 1
            if 0 <= tx2 < width and 0 <= ty < height and grid[tx2][ty] != 4:
                grid[tx2][ty] = 2
                walls.append((tx2, ty))
    
    # Quelques obstacles devant le mur (côté attaquant)
    for _ in range(3):
        ox = random.randint(width // 4, wall_x - 5)
        oy = random.randint(3, height - 4)
        if grid[ox][oy] == 0:
            grid[ox][oy] = 1
    
    siege_data = {
        'walls': walls,
        'ramparts': ramparts,
        'stairs': stairs,
        'gates': {pos: 10 for pos in gates},  # Chaque porte a 10 PV
        'gate_save': 3,  # Sauvegarde des portes
        'gate_positions': gate_positions,  # Y centraux des portes
        'wall_x': wall_x,
    }
    
    return grid, siege_data


# ═══════════════════════════════════════════════════════════════
#                    FONCTION PRINCIPALE
# ═══════════════════════════════════════════════════════════════

def generate_map(map_name, width, height):
    """Génère la grille et les données spéciales pour un type de map.
    
    Retourne (grid, map_data) où:
        grid: [[int]] — grille 2D (0=vide, 1=obstacle, 2=mur, 3=porte)
        map_data: dict — données spéciales (siege_data, etc.)
    """
    generators = {
        "Prairie": generate_prairie,
        "Forêt": generate_forest,
        "Village": generate_village,
        "Siège": generate_siege,
    }
    
    gen = generators.get(map_name, generate_prairie)
    return gen(width, height)