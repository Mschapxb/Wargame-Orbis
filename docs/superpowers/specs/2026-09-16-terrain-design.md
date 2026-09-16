# Chantier 1 — Terrain à effets, cartes enrichies et double enceinte

Date: 2026-09-16
Statut: validé en conversation, en attente de relecture de la spec

## Contexte

Wargame-Orbis est un simulateur de batailles au tour par tour (Python/Pygame).
Le terrain est aujourd'hui une grille binaire (`0` vide, `1` obstacle, `2` mur,
`3` porte, `4` rempart, `5` escalier): les cartes changent la *forme* du champ
de bataille mais jamais la *manière* de s'y battre. Aucun terrain n'influence
le déplacement, la vue ou le combat.

Ce chantier est le premier d'une série de quatre, dans cet ordre:

1. **Terrain & cartes** (ce document)
2. Combat (flancs, formations, prises de dos)
3. IA stratégique (plan de bataille, réserves, objectifs de terrain; nettoyage
   des méthodes définies deux fois dans `ai_commander.py`)
4. Accessibilité

Il est découpé en deux livraisons successives: **1a** (terrain + cartes
existantes enrichies) puis **1b** (carte Citadelle à double enceinte).

### Hors périmètre

- Flancs, formations, orientation des unités → chantier 2.
- Plan stratégique de l'IA, prise d'objectifs de terrain → chantier 3.
  (1a rend seulement l'IA *consciente* des coûts et modificateurs via les
  fonctions partagées; elle ne cherche pas encore à tenir une colline.)
- Légende complète, options de lisibilité → chantier 4 (1a pose seulement les
  motifs non chromatiques et la touche `L`).

---

## 1a — Modèle de terrain

### Donnée

Nouveau module `src/terrain.py`, sans dépendance vers Pygame:

```python
PLAIN, HILL, WOOD, RIVER, FORD, BRIDGE, MARSH = (
    "plaine", "colline", "bois", "riviere", "gue", "pont", "marais")

TERRAINS = {
    PLAIN:  dict(move=1.0, passable=True,  charge=True,  save_mod=0, cover=0, blocks_los=0),
    HILL:   dict(move=1.0, passable=True,  charge=True,  save_mod=0, cover=0, blocks_los=0, elevated=True),
    WOOD:   dict(move=2.0, passable=True,  charge=False, save_mod=0, cover=1, blocks_los=1),
    RIVER:  dict(move=None, passable=False, charge=False, save_mod=0, cover=0, blocks_los=0),
    FORD:   dict(move=2.0, passable=True,  charge=False, save_mod=-1, cover=0, blocks_los=0),
    BRIDGE: dict(move=1.0, passable=True,  charge=True,  save_mod=0, cover=0, blocks_los=0),
    MARSH:  dict(move=3.0, passable=True,  charge=False, save_mod=-1, cover=0, blocks_los=0),
}
```

- `Battlefield.terrain`: grille `[x][y]` parallèle à `grid`, initialisée à
  `PLAIN`. Fournie par les générateurs via `map_data['terrain']` et extraite
  dans `Battlefield.__init__` **avant** `siege_data` (même précaution que
  `decor`: sinon `bool(siege_data)` deviendrait vrai sur toutes les cartes).
- Une carte sans `map_data['terrain']` se comporte **exactement** comme
  aujourd'hui (toutes les cases en plaine, tous les modificateurs à 0).
- `grid` n'est pas modifié: on n'ajoute aucun code de cellule (29 sites
  comparent `grid[x][y]` à des entiers).

### Effets

| Terrain | Déplacement | Ligne de vue | Combat |
|---|---|---|---|
| Colline | coût ×1,5 pour un pas qui **monte** (plaine → colline), ×1 sinon | un tireur en colline voit par-dessus les bois; une cible derrière une colline (colline strictement entre les deux, tireur pas en colline) n'est pas visible | tireur en colline visant une cible hors colline: **+1 portée**; attaquant de mêlée hors colline frappant une cible en colline: **+1 au seuil de toucher** |
| Bois | ×2 | la ligne de tir traverse au plus **2** cases de bois intermédiaires; 3 ou plus bloquent (sauf tireur en colline) | tir reçu par une cible en bois: **+1 au seuil de toucher**; charge impossible si le chargeur part d'un bois ou si la case d'impact est en bois |
| Rivière | infranchissable | ne bloque pas | — |
| Gué | ×2 | — | cible en gué: **sauvegarde -1**; charge impossible |
| Pont | ×1 | — | — (le goulet vient de la géométrie: 1 à 2 cases de large) |
| Marais | ×3 | — | cible en marais: **sauvegarde -1**; charge impossible |

Convention du projet: un seuil de toucher plus **haut** est plus **difficile**
(le README note `-1` = plus facile). « Sauvegarde -1 » signifie que la
sauvegarde de la cible est dégradée d'un cran (seuil +1).

### API partagée (un seul endroit fait foi)

```python
def at(bf, x, y) -> str
def is_passable(bf, x, y) -> bool
def step_cost(bf, from_xy, to_xy) -> float        # multiplicateur, >= 1
def can_charge(bf, from_xy, to_xy) -> bool
def range_bonus(bf, shooter, target) -> int       # 0 ou +1
def combat_mods(bf, attacker, target, ranged) -> dict
    # {'toucher': int, 'save': int}  (valeurs à ajouter aux seuils)
def blocks_line(bf, x0, y0, x1, y1, shooter_elevated) -> bool
```

`combat_mods` est appelé **à la fois** par la résolution réelle
(`Unit.perform_attacks`) et par l'estimation de l'IA
(`tactics.expected_damage`). L'IA et le moteur voient donc les mêmes chiffres.

### Points de branchement

| Où | Changement |
|---|---|
| `Battlefield.__init__` | extraire `terrain` de `map_data` |
| `Battlefield.is_valid` | `False` si `not terrain.is_passable` (rivière) |
| `Battlefield.a_star_path` | coût de pas × `step_cost`; heuristique inchangée (Chebyshev, coût min 1 → reste admissible). Garder le style inliné: lire `self.terrain` dans une variable locale et un dict `move` pré-calculé |
| `Battlefield.has_line_of_fire` / `_los_clear` | ajouter le test bois/colline; supprimer le court-circuit « pas de fortifications → True » quand la carte a du terrain bloquant |
| `Battlefield.compute_move` et mouvement cohésif (`battle.py`) | le budget de déplacement d'un round (= vitesse) consomme `step_cost` par case le long du chemin; l'unité s'arrête avant le pas qui dépasserait le budget, mais fait toujours **au moins 1 pas** si elle en a un (sinon une unité de vitesse 2 resterait bloquée en marais). Ex.: vitesse 4 → 2 cases en bois, 1 en marais |
| `Unit.perform_attacks` | portée effective `_max_range + range_bonus`; appliquer `combat_mods` au toucher et à la sauvegarde |
| `tactics.expected_damage` | appliquer `combat_mods` et `range_bonus` |
| `Battle._charge_phase` | ignorer les proies pour lesquelles `can_charge` est faux; le budget d'élan consomme `step_cost` |
| `Battle._reaction_fire` | utiliser la portée effective |

Toute comparaison de portée `dist <= u._max_range` dans l'IA qui décide d'un
tir passe par une aide `effective_range(bf, shooter, target)` pour rester
cohérente avec le moteur. Les autres usages de `_max_range` (classification
tireur/mêlée, `>= 4`) ne changent pas.

### Rendu

- `renderer.build_grid_surface`: teinte de sol par terrain **et motif
  distinct** dessiné une fois dans la surface statique:
  colline = courbes de niveau + ombrage côté bas-droite; bois = sous-bois
  sombre + petites cimes; rivière = eau avec ondes animables (statique en 1a);
  gué = eau claire + galets; pont = planches; marais = hachures + touffes.
  La lisibilité ne dépend jamais de la seule couleur.
- `maps.generate_decor`: les arbres se concentrent sur les cases `WOOD`, rien
  n'est semé sur `RIVER`/`BRIDGE`.
- Touche `L` en bataille: bascule un encart listant les terrains présents sur
  la carte, avec motif et effets en une ligne chacun.

---

## 1a — Cartes existantes enrichies

Principes: aucune carte ne perd son identité; terrain **symétrique en miroir
gauche/droite**; zones de déploiement en plaine (on ne place aucun terrain à
coût > 1 dans les colonnes de déploiement).

| Carte | Ajouts |
|---|---|
| **Prairie** | Les deux crêtes deviennent des bandes de **colline** (épaisseur 2–3), quelques rochers `1` conservés dessus comme couvert. **Colline centrale basse** (rayon ~3) au milieu du couloir principal. Deux **bosquets de broussailles** (`WOOD`) sur chaque flanc. |
| **Forêt** | Pour chaque bosquet: les cases dont tous les voisins sont obstacles restent `1` (cœur), les autres deviennent `0` + `WOOD` (pourtour traversable). La lisière clairsemée devient `WOOD`. **Ruisseau** nord-sud dans la clairière centrale avec **2 gués**. |
| **Village** | **Jardins/vergers** (`WOOD`) sur une partie des cases libres entre maisons de l'anneau extérieur. **Mare** (`MARSH`, rayon ~2) adjacente à la place, sur un côté (répliquée en miroir). Le disque du bourg est en **colline** (butte). |
| **Défilé** | Les 2 rangées bordant chaque paroi deviennent **colline** (pentes). **Éboulis** (`MARSH`) en taches dans le goulet. **Torrent** nord-sud à l'étranglement avec **un pont** (2 cases) et **un gué** (2 cases). |

Contraintes vérifiées par test pour chaque carte et plusieurs graines:

- au moins **2 chemins** disjoints en largeur (cases distinctes) d'une zone de
  déploiement à l'autre, rivière bloquante, gués/ponts passants;
- au moins **1 chemin sans marais**;
- aucun terrain à coût > 1 dans les zones de déploiement.

`maps._connected` est étendu pour accepter la grille de terrain.

Rythme: le premier contact en Prairie est aujourd'hui vers le round 7. S'il
recule de plus de 2 rounds, on réduit l'emprise des terrains lents.

---

## 1b — Carte « Citadelle » (double enceinte)

### Géographie

- **Mur extérieur** à `x ≈ 0,55 × width`, **2 portes** (vers 1/3 et 2/3 de la
  hauteur), remparts et escaliers comme le siège actuel.
- **Donjon** à `x ≈ 0,80 × width`, **1 porte** centrale, remparts sur 2 rangs.
- **Basse-cour** entre les deux: quelques bâtiments (`1`), jardins (`WOOD`),
  **butte** (`HILL`) devant le donjon.
- Approche assaillante: couverts `1` comme le siège actuel, **fossé boueux**
  (`MARSH`, 1–2 cases) au pied du mur extérieur, interrompu devant les portes.

### Modèle de siège généralisé

- `siege_data['rings']`: liste ordonnée de l'extérieur vers l'intérieur, chaque
  élément `{wall_x, walls, gates, ramparts, stairs, gate_positions}`.
- `generate_siege` (carte « Siège » actuelle) produit `rings` à **un seul**
  élément. Les clés plates historiques restent fournies pour compatibilité
  pendant la migration, puis sont retirées une fois tous les appelants migrés.
- `Battlefield`:
  - `is_siege` (remplace les 3 tests `map_name == "Siège"` de `battle.py`);
  - `active_ring` (index), `wall_x` (propriété → `wall_x` de l'enceinte
    active);
  - `walls`, `ramparts`, `stairs`, `gate_hp` restent des ensembles **globaux**
    (toutes enceintes), car ils décrivent la géométrie physique;
  - `active_gates` → portes de l'enceinte active (utilisé par l'IA et le
    déploiement);
  - `advance_ring()` → passe à l'enceinte suivante.
- Les 44 lectures de `siege_data.get('wall_x')` passent par `bf.wall_x`.

### Bascule d'enceinte

Évaluée une fois par round dans `Battle.simulate_round`, après le moral:
l'enceinte active tombe si **l'une** des conditions est vraie:

- toutes ses portes sont détruites **et** au moins 3 unités assaillantes (ou
  la moitié des assaillants vivants) sont au-delà de son `wall_x`;
- plus aucun défenseur non fuyard n'est entre son `wall_x` et le `wall_x` de
  l'enceinte suivante.

Un événement de journal « L'enceinte extérieure est tombée » est émis.

### IA de défense

- Nouvelle posture `fall_back`, choisie quand l'enceinte active est sur le
  point de tomber (portes à ≤ 30 % des PV totaux et ennemis au contact des
  portes, ou bascule déjà déclenchée alors que des défenseurs sont dehors).
- Ordres: tireurs et mages d'abord vers les remparts de l'enceinte suivante;
  une **arrière-garde** (mêlée la plus robuste, ~1/3 de la mêlée) tient la
  porte extérieure 1–2 rounds (`hold`), puis rentre; les portes du donjon se
  ferment derrière les derniers (logique `recall` / `_try_close_gates`
  adaptée à l'enceinte active).
- `sortie` n'est proposée que depuis l'enceinte active.
- `_siege_defense`, `_recall_order`, `_sortie_order` lisent `bf.wall_x` et
  `bf.active_gates`.

### IA d'assaut

- `_pick_assault_gate` choisit parmi `bf.active_gates`; le verrou est remis à
  zéro à la bascule.
- Les tireurs assaillants dont la cible n'est plus à portée avancent dans la
  basse-cour (pas de station devant le premier mur).

### Déploiement

Le placement défenseur actuel (`battle.py` l.417–558) est paramétré par
l'enceinte **extérieure** (index 0). Sur Citadelle, les tireurs occupent les
remparts extérieurs; la mêlée se place derrière les portes extérieures; le
surplus éventuel va sur les remparts du donjon.

---

## Tests et validation

Nouveau fichier `src/test_terrain.py` (même style exécutable que
`test_edge_cases.py`, sans dépendance à pytest):

- `step_cost`, `is_passable`, `can_charge` pour chaque terrain;
- `combat_mods` / `range_bonus`: colline, bois, gué, marais, cas cumulés;
- ligne de vue: 2 bois passent, 3 bloquent, tireur en colline voit par-dessus,
  colline intermédiaire masque;
- A*: préfère un détour court en plaine à une traversée de marais; traverse
  le gué quand c'est le seul passage; ne traverse jamais la rivière;
- estimation IA = résolution moteur: sur N tirs simulés en bois, la moyenne
  des dégâts converge vers `expected_damage` (tolérance 10 %);
- connexité et symétrie des 4 cartes enrichies sur 20 graines;
- carte sans `terrain` → résultats identiques à l'état actuel sur graines
  fixes (non-régression).

Siège / Citadelle:

- Siège actuel: mêmes vainqueurs et même nombre de rounds qu'avant sur graines
  fixes;
- scénario headless Citadelle (ajouté à `test_ai_headless.py`): la bascule
  d'enceinte se produit, des défenseurs rejoignent le donjon, la bataille se
  termine sans blocage;
- `test_edge_cases.py`: ajouter « Citadelle » à la boucle des cartes.

Équilibre (`bench_balance.py`), avant/après, 60 graines:

- aucune carte existante ne voit le taux de victoire d'un affrontement type
  varier de plus de **10 points**;
- assaut équilibré sur Citadelle: défenseur vainqueur entre **40 % et 65 %**.

Performance: le README mesure 7 ms/image médiane; l'ajout du terrain ne doit
pas dépasser **+1 ms** en rendu, ni **+20 %** sur la durée d'un round simulé
headless (mesurée sur `bench_balance`).

## Documentation

Mettre à jour `README.md`: section « Cartes disponibles » (Citadelle, terrains
des cartes enrichies), nouvelle section « Terrain » (tableau des effets),
touche `L`, et la ligne de test qui cite `tests/test_main.py` (répertoire
ignoré par git) remplacée par `src/test_terrain.py`.
