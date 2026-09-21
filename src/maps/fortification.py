"""Niveaux de fortification des cartes de siège (Siège, Citadelle).

    Niveau 1  la place historique: portes à 10 PV, rien d'autre
    Niveau 2  portes renforcées + une TOUR portant une baliste de garnison
              sur le chemin de ronde de l'enceinte extérieure
    Niveau 3  portes encore plus solides, tour à baliste, réserves de
              munitions doublées pour la garnison, portes PIÉGÉES (huile
              bouillante et chute de pierres quand une porte cède)

La tour est une plateforme 2×2 prise sur le chemin de ronde (cases rempart):
elle reste marchable et la baliste qui l'occupe est une unité ordinaire de
l'armée défenseure — on peut la tuer au tir ou en montant l'escalier.

Le niveau 1 ne touche à rien (aucun tirage): la carte et l'équilibre mesuré
restent ceux d'avant les niveaux.
"""

LEVELS = ("Niveau 1", "Niveau 2", "Niveau 3")
DESCRIPTIONS = {
    1: "Place ordinaire: portes de bois, garnison sur le rempart.",
    2: "Portes renforcées, tour à baliste au-dessus de la porte.",
    3: "Portes bardées de fer et piégées, tour à baliste, réserves doublées.",
}
GATE_HP = {1: 10, 2: 16, 3: 22}
# Rangées entre le haut de la tour et la première porte
TOWER_OFFSET = 2
# Réserves de traits de la garnison (×, cf. Unit.refill_ammo)
GARRISON_AMMO = {1: 1, 2: 1, 3: 2}


def level_of(options):
    """Niveau (1-3) demandé par map_options: 'fortification' vaut 1, 2, 3
    ou un libellé de LEVELS. Sans option: 1."""
    raw = (options or {}).get('fortification', 1)
    if raw in LEVELS:
        return LEVELS.index(raw) + 1
    try:
        return max(1, min(3, int(raw)))
    except (TypeError, ValueError):
        return 1


def _gate_groups(gates):
    """Portes d'une enceinte groupées en battants contigus (même colonne)."""
    groups, run = [], []
    for g in sorted(gates):
        if run and (g[0] != run[-1][0] or g[1] != run[-1][1] + 1):
            groups.append(run)
            run = []
        run.append(g)
    if run:
        groups.append(run)
    return groups


def _tower_site(wall_x, gate_groups, ramparts, stairs, height):
    """Coin haut-gauche d'une plateforme 2×2 entièrement sur le chemin de
    ronde, au plus près de la rangée idéale: TOWER_OFFSET rangées au-dessus
    de la première porte (tour-porche). Plus loin sur la courtine, elle
    prend l'assaut en enfilade (mesuré: assaillant 8 % → 2,5 %)."""
    if not gate_groups:
        return None
    ideal = gate_groups[0][0][1] - TOWER_OFFSET
    x = wall_x + 1
    for off in range(height):
        for y in (ideal - off, ideal + off):
            cells = [(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)]
            if all(c in ramparts and c not in stairs for c in cells):
                return (x, y)
    return None


def apply_fortification(map_data, level):
    """Renforce une carte de siège en place selon le niveau.

    Ajoute à map_data: 'fortification' (niveau), 'towers' [{'anchor',
    'cells', 'ring'}], 'gate_trap' (bool), 'garrison_ammo' (facteur)."""
    map_data['fortification'] = level
    if level <= 1:
        return map_data
    hp = GATE_HP[level]
    map_data['gates'] = {pos: hp for pos in map_data.get('gates', {})}
    rings = map_data.get('rings') or [{'wall_x': map_data['wall_x'],
                                       'gates': list(map_data['gates'])}]
    ramparts = {tuple(c) for c in map_data.get('ramparts', [])}
    stairs = {tuple(c) for c in map_data.get('stairs', [])}
    height = 2 + max((c[1] for c in ramparts), default=0)
    towers = []
    outer = rings[0]
    anchor = _tower_site(outer['wall_x'], _gate_groups(outer['gates']), ramparts, stairs, height)
    if anchor is not None:
        ax, ay = anchor
        towers.append({'anchor': anchor, 'ring': 0,
                       'cells': [(ax + dx, ay + dy) for dx in (0, 1) for dy in (0, 1)]})
    map_data['towers'] = towers
    map_data['gate_trap'] = level >= 3
    map_data['garrison_ammo'] = GARRISON_AMMO[level]
    return map_data
