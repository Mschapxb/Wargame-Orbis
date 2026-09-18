"""Couches de thème posées sur une carte: rivière, collines, biome."""

import procgen
import structures as st
import terrain as tr

from .catalog import NATURAL_RELIEF, SIEGE_MAPS, THEMED_MAPS, natural_biome
from .common import _bfs_path, deploy_front


# ═══════════════════════════════════════════════════════════════
#                 COUCHES DE THÈME (relief, biome)
# ═══════════════════════════════════════════════════════════════

def _field_x_range(map_name, width, data):
    """Bande de terrain où les couches procédurales ont le droit de peindre:
    entre le front de l'armée 1 et le centre (cartes symétriques), ou entre
    le front de l'assaillant et le fossé (sièges)."""
    if map_name in SIEGE_MAPS:
        wall_x = data['rings'][0]['wall_x'] if data.get('rings') else data['wall_x']
        return deploy_front(width, siege=True) + 3, wall_x - 6
    return deploy_front(width, data.get('deploy_gap')) + 3, width // 2 - 2


def _gate_rows(data):
    return list(data.get('gate_positions', ()))


def _clear_village_houses_near(grid, width, height, cells):
    """Une maison coupée par la rivière n'est plus une maison: on retire
    les blocs d'obstacles qui touchent le lit (le miroir est préservé,
    le lit étant symétrique)."""
    near = {(x + dx, y) for (x, y) in cells for dx in (-1, 0, 1)}
    obstacles = [(x, y) for x in range(width) for y in range(height) if grid[x][y] == 1]
    for comp in st._components(obstacles):
        if any(c in near for c in comp):
            for (x, y) in comp:
                grid[x][y] = 0


def _add_river(map_name, grid, data, width, height, biome):
    terr = data['terrain']
    cy = height // 2
    if map_name in SIEGE_MAPS:
        x_lo, x_hi = _field_x_range(map_name, width, data)
        if x_hi - x_lo < 3:
            return
        spans = procgen.river_spans_meander(height, (x_lo + x_hi) // 2, x_lo, x_hi,
                                            width_cells=2 if width < 90 else 3)
        gates = _gate_rows(data)
        crossings = procgen.pick_rows(height, 1 if height < 40 else 2, forced=gates)
        _, approach = procgen.paint_river(grid, terr, width, height, spans, crossings,
                                          bridge_rows=gates)
        # Les palissades ne se dressent pas au milieu de l'eau
        structs = data.get('structures')
        if structs:
            for c in [c for c in structs if grid[c[0]][c[1]] == 0]:
                del structs[c]
        if biome == "Forêt":
            procgen.paint_banks(grid, terr, width, height, spans, tr.WOOD, 0.3, skip=approach)
        return

    amp = 1 if width < 90 else 2
    spans = procgen.river_spans_symmetric(width, height, amp)
    if map_name == "Village":
        bed = {(x, y) for y, v in spans.items()
               for x0, x1 in procgen._segs(v) for x in range(x0, x1 + 1)}
        _clear_village_houses_near(grid, width, height, bed)
    # Un pont là où l'on marche déjà (grand-rue du village, couloir central)
    forced = [cy]
    crossings = procgen.pick_rows(height, 2 if height < 40 else 3, margin=4, forced=forced)
    _, approach = procgen.paint_river(grid, terr, width, height, spans, crossings,
                                      bridge_rows=forced)
    bank = {"Forêt": (tr.WOOD, 0.35), "Désert": (tr.WOOD, 0.45),
            "Prairie": (tr.WOOD, 0.12)}[biome]
    procgen.paint_banks(grid, terr, width, height, spans, bank[0], bank[1],
                        skip=approach, symmetric=True)


def _remove_river(map_name, data, width, height):
    """Le ruisseau de la Forêt redevient sous-bois; ses gués, des sentiers."""
    terr = data['terrain']
    procgen.strip(terr, width, height, (tr.RIVER,), to=tr.WOOD)
    procgen.strip(terr, width, height, (tr.FORD, tr.BRIDGE), to=tr.PLAIN)


def _add_hills(map_name, grid, data, width, height):
    terr = data['terrain']
    x_lo, x_hi = _field_x_range(map_name, width, data)
    n = max(2, (width * height) // 1100)
    size = (1.6, max(2.2, height * 0.06))
    if map_name in SIEGE_MAPS:
        procgen.scatter_blobs(terr, grid, width, height, n, (x_lo, x_hi), (2, height - 3),
                              size, tr.HILL, avoid_rows=_gate_rows(data))
    else:
        if map_name == "Forêt":
            x_lo = max(x_lo, width // 2 - int(width * 0.16))
        procgen.scatter_blobs(terr, grid, width, height, n, (x_lo, x_hi), (2, height - 3),
                              size, tr.HILL, symmetric=True)


def _apply_biome(map_name, grid, data, width, height, biome):
    """Végétation d'une disposition bâtie hors de sa prairie natale."""
    terr = data['terrain']
    x_lo, x_hi = _field_x_range(map_name, width, data)
    cy = height // 2
    if biome == "Forêt":
        n = max(3, (width * height) // 450)
        size = (1.4, max(2.0, height * 0.06))
        if map_name in SIEGE_MAPS:
            procgen.scatter_blobs(terr, grid, width, height, n, (x_lo, x_hi), (1, height - 2),
                                  size, tr.WOOD, avoid_rows=_gate_rows(data))
        else:
            procgen.scatter_blobs(terr, grid, width, height, n, (x_lo, x_hi), (1, height - 2),
                                  size, tr.WOOD, avoid_rows=[cy], symmetric=True)
    elif biome == "Désert":
        # Plus de jardins ni de vergers: seuls restent les palmiers au bord
        # de l'eau. Règle déterministe → la symétrie est préservée.
        wet = set(procgen.WET)
        for x in range(width):
            for y in range(height):
                if terr[x][y] != tr.WOOD:
                    continue
                if not any(0 <= x + dx < width and 0 <= y + dy < height
                           and terr[x + dx][y + dy] in wet
                           for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)):
                    terr[x][y] = tr.PLAIN
        if map_name == "Village":
            # La mare du village devient une oasis: palmiers tout autour
            for x in range(width):
                for y in range(1, height - 1):
                    if (terr[x][y] == tr.PLAIN and grid[x][y] == 0 and abs(y - cy) > 2
                            and any(0 <= x + dx < width and terr[x + dx][y + dy] == tr.MARSH
                                    for dx in (-1, 0, 1) for dy in (-1, 0, 1))):
                        terr[x][y] = tr.WOOD


def _ensure_crossing(map_name, grid, data, width, height):
    """Filet de sécurité: si les couches ont coupé le passage d'un bord à
    l'autre (ou jusqu'au fossé), on ouvre un gué sur la rangée centrale."""
    terr = data['terrain']
    cy = height // 2
    x_end = _field_x_range(map_name, width, data)[1] + 3 if map_name in SIEGE_MAPS else width - 2
    left = [(1, y) for y in range(1, height - 1) if grid[1][y] == 0 and tr.MOVE[terr[1][y]] is not None]
    right = [(x_end, y) for y in range(1, height - 1)
             if grid[x_end][y] == 0 and tr.MOVE[terr[x_end][y]] is not None]
    if _bfs_path(grid, width, height, left, right, terr):
        return
    for x in range(1, x_end + 1):
        for y in (cy - 1, cy, cy + 1):
            if grid[x][y] == 1:
                grid[x][y] = 0
            if terr[x][y] == tr.RIVER:
                terr[x][y] = tr.FORD
    structs = data.get('structures')
    if structs:
        for c in [c for c in structs if grid[c[0]][c[1]] == 0]:
            del structs[c]


def apply_theme(map_name, grid, data, width, height, opts):
    """Pose les couches de thème sur une carte générée. Ne fait RIEN (et ne
    tire aucun dé) quand `opts` est le thème naturel de la carte."""
    if map_name not in THEMED_MAPS or data.get('terrain') is None:
        return
    nat_river, nat_hills = NATURAL_RELIEF[map_name]
    changed = False
    if opts['biome'] != natural_biome(map_name):
        _apply_biome(map_name, grid, data, width, height, opts['biome'])
        changed = True
    if opts['hills'] != nat_hills:
        if opts['hills']:
            _add_hills(map_name, grid, data, width, height)
        else:
            procgen.strip(data['terrain'], width, height, (tr.HILL,))
        changed = True
    if opts['river'] != nat_river:
        if opts['river']:
            _add_river(map_name, grid, data, width, height, opts['biome'])
        else:
            _remove_river(map_name, data, width, height)
        changed = True
    if changed:
        _ensure_crossing(map_name, grid, data, width, height)
