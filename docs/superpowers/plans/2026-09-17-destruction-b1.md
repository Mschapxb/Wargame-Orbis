# Lot B1 — Structures destructibles, incendie, ruines — Plan d'implémentation

**Goal:** Rendre maisons, haies, bosquets et rochers destructibles (feu, sorts,
machines de guerre), avec incendie qui se propage, ruines et terrain brûlé qui
changent la manière de se battre, une IA consciente du feu, et un rendu
spectaculaire mais incrémental.

**Spec:** `docs/superpowers/specs/2026-09-17-destruction-design.md` (section B1
et décisions de relecture).

**Branche:** `lot-a-fondations` (travail par-dessus le lot A, non commité —
choix utilisateur du 2026-09-17).

**Architecture:** un module pur `src/structures.py` détient la table des
structures et toutes les règles (groupes, dégâts, effondrement, incendie).
`Battlefield` porte `structures`, `structure_hp`, `fires` et `dirty_cells`.
Moteur (`battle.py`, `unit.py`) et IA (`tactics.py`, `ai_commander.py`)
appellent `structures.py`. Le rendu garde une couche de sol pristine et ne
repeint que les rectangles modifiés.

## Contraintes globales

- Aucune nouvelle dépendance.
- `grid` garde ses codes `0..5`; une structure est une case `1` tant qu'elle
  tient, `0` ensuite.
- Carte sans `map_data['structures']` → `bf.structures == {}` → comportement
  identique à aujourd'hui (Défilé, Siège avant B2, cartes de test).
- Tout hasard du moteur passe par le `random` global dans l'ordre du round;
  jamais d'itération sur un `set` ou un `dict` non trié quand l'ordre influe
  sur un tirage. Candidats d'allumage **mélangés** (pas triés par position:
  biais ouest).
- Structures en miroir comme la grille (x ↔ width-1-x) sur les 4 cartes de
  bataille rangée.
- Équilibre (60 graines): affrontements sans mage ni machine ±5 points;
  autres ±10; `bench_sides.py 300` 50 % ± 5; `bench_fire.py` ≤ 25 % de
  combustible brûlé, aucune bataille > 90 rounds.
- Performance: `bench_balance.py 60` ≤ +20 % de durée; repeindre 20 cases
  ≤ 4 ms; rendu +1 ms médian avec 20 cases en feu.
- Tests: scripts exécutables sans pytest, lancés depuis `src/`.
- Pas de commit sans demande explicite de l'utilisateur.

## Structure des fichiers

| Fichier | Rôle |
|---|---|
| `src/structures.py` (créer) | Table `KINDS`, classification Village, groupes, `damage`, `collapse`, `ignite`, `fire_step` |
| `src/test_destruction.py` (créer) | Tests du lot B1 |
| `src/bench_fire.py` (créer) | Banc incendie (Forêt, Village, 2 mages par camp) |
| `src/terrain.py` | `RUBBLE`, `BURNT`; coût ×4 et fumée des cases en feu |
| `src/battlefield.py` | Extraction des structures, groupes, PV, `fires`, `dirty_cells` |
| `src/maps.py` | `map_data['structures']` pour Prairie, Forêt, Village |
| `src/unit.py` | Boule de feu: allumage, dégâts aux structures, score de zone |
| `src/battle.py` | Phase d'incendie, `_attack_structure`, événements visuels |
| `src/tactics.py` | Menace des cases en feu |
| `src/ai_commander.py` | Évacuation, ordre `demolish` des machines |
| `src/renderer.py` | Couche de sol, `repaint_region`, maisons endommagées |
| `src/terrain_render.py` | Motifs Décombres / Brûlé, légende « En feu » |
| `src/sprites.py`, `src/fx_render.py` | Flammes, fumée, effondrement, cratères permanents |
| `src/test_fondations.py`, `src/test_determinism.py` | Symétrie des structures, déterminisme avec incendie |
| `README.md` | Section « Environnement destructible », tests, bancs |

---

### Tâche 1 — Terrains Décombres et Brûlé, feu dans les règles de terrain

**Fichiers:** `src/terrain.py`, `src/battlefield.py`, `src/test_destruction.py`

- `RUBBLE = "decombres"`: `move=2.0, passable, charge=False, save_mod=0, cover=1, blocks_los=0`.
- `BURNT = "brule"`: `move=1.0, passable, charge=True, save_mod=0, cover=0, blocks_los=0`.
- `FIRE_MOVE_FACTOR = 4.0`: `step_cost` multiplie par ce facteur si
  `to in bf.fires` (lu par `getattr(bf, 'fires', None)`).
- `blocks_line`: une case intermédiaire en feu compte comme une case de bois.
- A* (`battlefield.a_star_path`): même facteur, inliné via `fires` local.

**Tests:** coûts `RUBBLE`/`BURNT`; `combat_mods` à distance sur `RUBBLE` = +1;
fumée: 3 cases en feu bloquent, 2 non; A* contourne une case en feu si un
détour ≤ 2 pas existe; carte sans `fires` inchangée.

### Tâche 2 — Module `structures.py` (règles pures)

**Fichiers:** `src/structures.py`, `src/test_destruction.py`

API:

```python
HOUSE, HEDGE, GROVE, ROCK, PALISADE
KINDS = {...}                                   # table de la spec
classify_village(grid, w, h) -> {(x, y): kind}  # blocs pleins ≥2×2 → HOUSE, sinon HEDGE
build_groups(structs) -> (cells, hp, members)   # {(x,y): (kind, gid)}, {gid: pv}, {gid: [(x,y)]}
flammability(bf, x, y) -> float                 # 0 si non combustible
damage(bf, gid, amount, heavy=False) -> bool    # True si effondrée
collapse(bf, gid) -> list[(x, y)]               # grid/terrain/fires/dirty_cells
ignite(bf, x, y) -> bool
fire_step(bf, rng) -> dict                      # {'ignited', 'collapsed', 'burnt'}
```

Règles (spec): PV par groupe; maisons et palissades = composantes 4-connexes,
le reste une case par groupe; `heavy_only` (ROCK) ignore les armes < 3 de
dégâts moyens; combustion 2 PV/round sans sauvegarde; fin au bout de `burn`
rounds; sous-bois `WOOD` sans structure: inflammabilité 0,20, 2 rounds, devient
`BURNT`; propagation 4-voisins, jamais à travers rivière, gué, marais, pont ni
case sans combustible; plafond 8 allumages par round, candidats mélangés.

`damage`/`collapse` ne connaissent pas les unités: les blessures des unités
adjacentes sont appliquées par `battle.py` à partir de ce qu'ils renvoient.

**Tests:** classification (maison 3×2 → un groupe `HOUSE`; anneau → `HEDGE`);
effondrement cohérent; propagation bornée et arrêtée par l'eau; feu isolé
éteint; plafond; `ROCK` insensible aux armes légères.

### Tâche 3 — Battlefield et cartes

**Fichiers:** `src/battlefield.py`, `src/maps.py`, `src/renderer.py`,
`src/test_fondations.py`

- `Battlefield.__init__`: extrait `structures` avant `siege_data`; construit
  `structures`, `structure_hp`, `structure_max_hp`, `structure_members`;
  `fires = {}`, `dirty_cells = set()`. Si des structures existent et
  `terrain is None`, crée une grille de plaine (neutre).
- `maps.py`: Prairie → rochers `ROCK`; Forêt → cœurs `GROVE`; Village →
  `classify_village` (que `draw_village_buildings` réutilise). Calculé après le
  miroir de la grille.

**Tests:** chaque carte a des structures cohérentes avec `grid == 1`; Défilé
n'en a pas; symétrie des structures.

### Tâche 4 — Moteur: boule de feu, phase d'incendie, machines

**Fichiers:** `src/unit.py`, `src/battle.py`, `src/test_destruction.py`

- `_cast_fireball`: pour chaque case 3×3: structure touchée → `1d4` dégâts
  (sauvegarde de la structure); case combustible → allumage à 50 %. Événement
  `crater`. Score de zone: +1 par ennemi sur `WOOD` ou au contact d'une
  structure combustible, −2 par allié à 1 case d'une case combustible de la zone.
- `Battle._fire_phase()` (après régénération): `structures.fire_step`; unités
  sur une case en feu: 1 dégât (sauvegarde), `_suppression += 1`; effondrement
  d'une maison: `1d3` aux unités adjacentes; `log_event` importance 2; effet
  visuel `collapses`.
- `Battle._attack_structure(unit)`: si l'ordre est `demolish`, résolution
  calquée sur `_attack_gate`; appelée juste après `_attack_gate`.

**Tests:** boule de feu sur un bosquet l'allume; unité dans les flammes
blessée; maison effondrée blesse l'adjacent; baliste en `demolish` entame la
maison; déterminisme étendu (Forêt avec mages).

### Tâche 5 — IA consciente du feu

**Fichiers:** `src/tactics.py`, `src/ai_commander.py`, `src/battlefield.py`

- `ThreatField.at`: +1,5 si la case est en feu, +0,5 si une voisine l'est.
- `CommanderAI._standard`: unité sur une case en feu → `withdraw` vers la case
  la plus sûre à portée de pas, priorité 6.
- Ordre `demolish` pour les machines: pas de cible visible à portée; cible
  prioritaire à portée masquée par une structure destructible → la première
  structure du tracé. `compute_move` le traite comme `hold`.

**Tests:** évacuation; `demolish` émis quand une maison masque la cible, pas
quand la cible est visible.

### Tâche 6 — Rendu incrémental et décor détruit

**Fichiers:** `src/renderer.py`, `src/terrain_render.py`

- `build_grid_surface` conserve `ground_layer` (sol + grain + taches).
- `repaint_region(surface, battle, cell_size, cells)`: rectangle + 1 case,
  clip, sol, terrain, structures intersectées (maisons entières), murs/portes,
  décor. Appelée chaque round sur `bf.dirty_cells`, puis vidage.
- Maisons endommagées en 3 états; repeint seulement quand l'état change.
- `terrain_render.draw_cell`: `RUBBLE` et `BURNT`; légende + « En feu ».

**Tests:** `repaint_region` ne modifie aucun pixel hors rectangle; 20 cases
≤ 4 ms; fumée de rendu Village après effondrement.

### Tâche 7 — Effets: flammes, fumée, effondrement, cratères

**Fichiers:** `src/sprites.py`, `src/fx_render.py`, `src/renderer.py`

- `sprites.flame_frames(cs)` en cache.
- `FxRenderer.draw_fires`: flammes animées par case visible, halo additif,
  braises; fumée plafonnée.
- `collapses`: poussière, débris, onde de choc, secousse ≤ `SHAKE_MAX`.
- Cratères permanents cuits dans la couche de sol et la composition.

**Tests:** fumée de rendu d'une frame avec feux; mesure du coût de rendu.

### Tâche 8 — Validation, bancs, documentation

- `bench_fire.py`; `bench_balance.py 60`, `bench_maps.py 60`,
  `bench_sides.py 300` → `docs/superpowers/baselines/bench-after-B1.txt`.
- Toutes les suites de tests vertes.
- Lancement réel (Village et Forêt avec mages): capture d'un incendie et d'une
  maison effondrée.
- `README.md`: « Environnement destructible », terrains, tests, bancs.
- Mémoire projet mise à jour.
