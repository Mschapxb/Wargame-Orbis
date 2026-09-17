# Lot B — Environnement destructible, incendies et cartes de siège

Date: 2026-09-17
Statut: relue et validée (décisions en fin de document); plan B1 à écrire

## Contexte

Feuille de route validée le 2026-09-17 (ordre choisi par l'utilisateur):

- **A** Fondations — fait (branche `lot-a-fondations`): cartes symétriques,
  obstacles qui coupent la ligne de tir, méthodes d'IA dédoublonnées,
  estimation du rempart corrigée. Biais de côté mesuré: 50 % ± 2.
- **B** Environnement destructible + cartes (ce document)
- **C** IA « plan de bataille » (objectifs de terrain, plans multi-rounds,
  intentions visibles)
- **D** Visuel et interface (zoom, mini-carte, fiche d'unité, HUD, ambiance)

Choix utilisateur: la destruction est **mécanique ET visuelle**. Une maison
effondrée, un bois brûlé ou un mur percé changent la manière de se battre,
et l'IA en tient compte.

### État actuel (vérifié dans le code)

- Seules les **portes** sont destructibles (`bf.gate_hp`, `Battle._attack_gate`,
  `renderer.repaint_gates`).
- `grid == 1` mélange des objets de nature très différente: rocher (Prairie,
  Siège), maison et haie (Village), cœur de bosquet (Forêt), masse rocheuse
  (Défilé), mur de force temporaire. Rien ne les distingue.
- La boule de feu (`Unit._cast_fireball`) ne touche que les unités; sa trace
  (`decal "scorch"`) s'efface au bout de ~30 s.
- Les armes de siège (`Baliste` portée 18 dégâts `1d4`, `Scorpion` 13 `1d2`,
  `Catapulte covaliir` 24 `2+1d4`) ne visent que les unités et les portes.
- La surface de terrain est pré-rendue une fois (`build_grid_surface`, ~90 ms
  sur une grande carte); seules les portes sont repeintes à la volée.
- La carte Siège n'a **aucun** terrain à effets.

### Découpage en livraisons

| Livraison | Contenu |
|---|---|
| **B1** | Structures destructibles, incendie, ruines, terrain brûlé; rendu incrémental; IA consciente du feu |
| **B2** | Siège enrichi: fossé, palissades, brèches de mur à la catapulte |
| **B3** | Carte Citadelle à double enceinte — spec existante, `2026-09-16-terrain-design.md` §1b, complétée par les structures et brèches de B1/B2 |

Chaque livraison a son plan, ses tests et sa mesure d'équilibre avant fusion.

### Hors périmètre

- Recherche active de couvert (se poster dans des ruines, tenir une lisière),
  plans multi-rounds → lot C.
- Météo, éclairage de nuit, zoom → lot D (le rendu de B1 reste proportionnel
  à la taille de case, donc prêt pour un zoom).
- Destruction par la mêlée (abattre une haie à la hache): non. Seuls le feu,
  les sorts de zone et les machines de guerre détruisent.
- Masses rocheuses du Défilé: indestructibles (ce sont des montagnes).

---

## B1 — Structures, incendie, ruines

### Modèle de données

Nouveau module `src/structures.py`, **sans dépendance à Pygame**, seule source
de vérité des règles de destruction (même principe que `terrain.py`: moteur et
IA appellent les mêmes fonctions).

```python
HOUSE, HEDGE, GROVE, ROCK, PALISADE = (
    "maison", "haie", "bosquet", "rocher", "palissade")

KINDS = {
    #            PV     svg     inflammabilité  combustion   devient          machine lourde seule
    HOUSE:    dict(hp=14, save=4, flammable=0.15, burn=4, leaves=tr.RUBBLE, heavy_only=False),
    HEDGE:    dict(hp=4,  save=6, flammable=0.35, burn=2, leaves=tr.BURNT,  heavy_only=False),
    GROVE:    dict(hp=6,  save=5, flammable=0.25, burn=3, leaves=tr.BURNT,  heavy_only=False),
    ROCK:     dict(hp=16, save=3, flammable=0.0,  burn=0, leaves=tr.RUBBLE, heavy_only=True),
    PALISADE: dict(hp=8,  save=5, flammable=0.20, burn=3, leaves=tr.RUBBLE, heavy_only=False),
}
```

- `Battlefield.structures`: `{(x, y): (kind, group_id)}`. Les PV sont portés
  **par groupe**: `Battlefield.structure_hp[group_id]`. Une maison de 3×2 est
  **une** structure de 6 cases: la frapper n'importe où l'entame toute, et elle
  s'effondre d'un bloc (des maisons à trous seraient illisibles et absurdes).
  Haies et bosquets: un groupe par case (ils brûlent de proche en proche).
- `grid` reste la vérité physique: une case de structure vaut `1` tant qu'elle
  tient. À la destruction: `grid → 0` et `terrain → leaves`.
- Les générateurs de cartes renseignent `map_data['structures']`
  (`{(x, y): kind}`); `Battlefield.__init__` l'extrait **avant** `siege_data`,
  comme `terrain` et `decor`, et calcule les groupes (composantes 4-connexes
  pour `HOUSE` et `PALISADE`, une case sinon).
- Une case `grid == 1` sans structure (mur de force, masse rocheuse du Défilé)
  se comporte exactement comme aujourd'hui.

Affectation par carte:

| Carte | Structures |
|---|---|
| Prairie | rochers → `ROCK` |
| Forêt | cœurs de bosquet → `GROVE` |
| Village | blocs pleins ≥ 2×2 → `HOUSE`; le reste (anneau, alignements) → `HEDGE` (règle aujourd'hui dans `draw_village_buildings`, déplacée dans `structures.classify_village` pour que moteur et rendu la partagent) |
| Défilé | aucune (falaises) |
| Siège | couverts de l'assaillant → `PALISADE` (B2) |

### Nouveaux terrains (`terrain.py`)

| Terrain | Déplacement | Vue | Combat | Charge |
|---|---|---|---|---|
| **Décombres** (`RUBBLE`) | ×2 | ne bloque pas | tirs reçus: +1 au seuil de toucher (couvert) | non |
| **Brûlé** (`BURNT`) | ×1 | ne bloque pas | — | oui |

Le bois brûlé perd tout ce qui faisait le bois: il ne ralentit plus, ne couvre
plus, ne masque plus. Les ruines deviennent un couvert franchissable: une
maison qui barrait une rue devient une position de tir.

### Incendie

État: `Battlefield.fires = {(x, y): rounds_restants}`. Évalué **une fois par
round** dans `Battle.simulate_round`, juste après la régénération: le feu agit
entre deux rounds, les commandants le voient au round suivant.

1. **Allumage**
   - Boule de feu: chaque case inflammable de la zone 3×3 (structure
     inflammable ou `WOOD`) prend feu avec une probabilité de **50 %**; la
     structure touchée subit aussi `1d4` dégâts (jet de sauvegarde de la
     structure).
   - Case de `WOOD` sans structure (sous-bois): inflammabilité **0,20**,
     brûle 2 rounds, devient `BURNT`.
2. **Combustion**: une case en feu inflige à son groupe **2** dégâts par round,
   sans sauvegarde. Au bout de `burn` rounds, ou à 0 PV, la structure est
   détruite (voir *Effondrement*); un sous-bois devient `BURNT`.
3. **Propagation**: chaque case en feu tente d'allumer ses 4 voisines
   inflammables, avec l'inflammabilité de la **cible**. Jamais à travers
   `RIVER`, `FORD`, `MARSH`, `BRIDGE`, ni une case sans structure ni `WOOD`:
   sentiers, rues et clairières sont des coupe-feu naturels.
4. **Plafond**: au plus **8** nouveaux allumages par round sur toute la carte.
   Les candidats sont **mélangés** par le `random` global avant le tirage (un
   tri par position favoriserait systématiquement l'ouest et recréerait un
   biais de côté). Un feu de forêt doit rester un événement de bataille, pas
   la fin de la carte.
5. **Unités**: une unité dont une case est en feu subit **1** dégât par round
   (jet de sauvegarde normal) et +1 de *suppression* (réutilise `_suppression`,
   lu par la phase de moral).
6. **Fumée**: une case en feu compte comme **une case de bois** pour la ligne
   de vue (`WOODS_BLOCKING`): trois cases enfumées masquent un tir.

Tout le hasard du moteur passe par le `random` global dans l'ordre du round:
une graine rejoue le même incendie. Le rendu garde sa propre RNG.

### Effondrement

À 0 PV (tir, sort, feu), pour toutes les cases du groupe:

- `grid → 0`, `terrain → leaves`, retrait de `structures` et de `fires`,
  ajout à `Battlefield.dirty_cells`;
- événement de journal d'importance 2 (« Une maison s'effondre »,
  « Le bosquet est réduit en cendres »), donc bannière comme aujourd'hui;
- une unité adjacente à une **maison** qui s'effondre subit `1d3` dégâts
  (sauvegarde normale): rester collé à un bâtiment en feu a un coût;
- événement visuel `collapse` (voir Rendu).

### Qui détruit quoi

- **Boule de feu**: dégâts + allumage (ci-dessus).
- **Machines de guerre** (`is_artillery`): une structure peut être **ciblée**.
  Résolution calquée sur `_attack_gate`: pas de jet de toucher (cible
  immobile), sauvegarde de la structure modifiée par la perforation, dégâts de
  l'arme. `ROCK` (`heavy_only`) n'encaisse que des armes de dégâts moyens ≥ 3
  (la catapulte).
- **Tirs ordinaires, mêlée**: n'endommagent pas les structures.

Quand une machine vise-t-elle une structure ? Règle unique, dans
`ai_commander` (ordre `demolish`):

> une machine sans cible **visible** à portée, dont la cible prioritaire
> (`focus_target`, sinon la meilleure de `_rank_targets`) est à portée mais
> masquée par une structure destructible, tire sur **la première structure du
> tracé**: elle dégage son champ de tir.

Le moteur exécute l'ordre dans `Battle`, à l'emplacement de `_attack_gate`
(nouvelle `_attack_structure`, même horodatage d'action).

### IA consciente du feu (minimum de B1)

- **Déplacement**: `step_cost` d'une case en feu = ×4 (traversable mais
  évitée); l'A* la contourne dès qu'un détour raisonnable existe.
- **Carte de menace** (`tactics.ThreatField`): une case en feu ajoute `1.5` de
  menace, ses voisines `0.5`. Replis, kiting et décrochages n'y reculent plus.
- **Évacuation**: une unité dont la case est en feu reçoit un ordre `withdraw`
  vers la case sûre la plus proche (`ThreatField.safest`), priorité 6.
- **Boule de feu**: `_cast_fireball` ajoute au score d'une zone `+1` par
  ennemi posté en `WOOD`, `HEDGE` ou `GROVE` (il va perdre son couvert) et
  `-2` par allié à 1 case d'une case inflammable de la zone (pas d'incendie
  sur ses propres lignes).
- **Estimation**: `tactics.expected_damage` et le moteur restent alignés sur
  `RUBBLE` (même test de convergence que le bois dans `test_terrain.py`).

### Rendu

#### Rendu incrémental (prérequis)

`build_grid_surface` sépare deux couches:

1. **Sol** (`ground_layer`): fond, grain, taches organiques et **traces
   permanentes** (cratères, voir ci-dessous). Construit une fois.
2. **Composition** (`grid_surface`, blittée à l'écran): sol + terrain +
   structures + murs/portes + décor.

Nouvelle fonction `repaint_region(grid_surface, ground_layer, battle, cells)`:
rectangle englobant des cases modifiées **+ 1 case de marge**, clip, recopie
du sol de ce rectangle, puis dans le clip: terrain des cases, **structures
entières qui intersectent** le rectangle (une maison est dessinée d'un bloc),
décor. `repaint_gates` devient un cas particulier. Le moteur remplit
`Battlefield.dirty_cells`; le renderer le vide une fois par round.

Budget: repeindre 20 cases ≤ **4 ms** (test de fumée, comme
`test_render_terrain_smoke`).

#### Nouveaux visuels

| Élément | Rendu |
|---|---|
| **Feu** | Par case en feu, dans `FxRenderer.draw_overlay`: 2–3 langues de flamme animées (`sprites.flame_frames`, en cache), halo additif orangé qui pulse, braises qui montent, colonne de fumée qui dérive dans le sens des nuages (particules `smoke`, plafonnées). |
| **Maison endommagée** | À 66 % puis 33 % des PV: toit percé (trous sombres), poutres visibles, tuiles tombées au pied du mur. Trois états, donc trois repeints au plus par maison. |
| **Effondrement** | Nuage de poussière qui s'étend (`dust`), débris projetés, onde de choc discrète, légère secousse de caméra (≤ `SHAKE_MAX`). |
| **Décombres** | Pans de mur brisés, poutres calcinées croisées, tas de pierres et de tuiles, dans la teinte de la maison d'origine (on reconnaît encore le village). Motif non chromatique: blocs anguleux. |
| **Brûlé** | Sol noirci à bords irréguliers, souches et troncs morts noirs (bosquet), cendres grises. Motif: petits traits croisés. |
| **Cratères** | Boule de feu et catapulte laissent une trace **permanente**, cuite dans `ground_layer` (le sang, lui, reste temporaire). |
| **Palissade** | Pieux taillés en pointe reliés, ombre portée; fendue puis éventrée selon les PV. |
| **Légende (L)** | + Décombres, Brûlé, En feu. |

Performance: la médiane de rendu ne dépasse pas **+1 ms** avec 20 cases en feu
à l'écran (mesure à 79 unités, comme le README).

### Tests B1 (`src/test_destruction.py`, style exécutable du projet)

- groupes: une maison 3×2 = un groupe; une haie = un groupe par case;
- effondrement: `grid`, `terrain`, `structures`, `fires`, `dirty_cells`
  cohérents; unités adjacentes blessées;
- propagation: jamais à travers rivière, gué, marais ou case sans combustible;
  plafond de 8 allumages; un feu isolé s'éteint;
- déterminisme: même graine → mêmes feux au round 20 (`test_determinism.py`
  étendu à une Forêt avec mages);
- ligne de vue: `BURNT` ne masque plus, fumée = bois, `RUBBLE` ne masque pas;
- estimation IA = moteur sur `RUBBLE` (tolérance 10 %);
- A*: contourne une case en feu quand un détour de 2 pas au plus existe;
- IA: une machine sans cible visible tire sur la structure qui masque sa cible;
  une unité dans les flammes évacue;
- rendu: `repaint_region` ne modifie aucun pixel hors du rectangle; fumée de
  rendu avec feux et décombres; budget 4 ms;
- symétrie: structures en miroir comme la grille (étend `test_fondations.py`).

### Équilibre B1

- Les affrontements **sans mage ni machine** ne bougent pas de plus de
  **5 points**.
- Les autres affrontements de `bench_balance.py` / `bench_maps.py` ne bougent
  pas de plus de **10 points**.
- Biais de côté (`bench_sides.py 300`): **50 % ± 5** par carte.
- Nouveau banc `bench_fire.py` (Forêt et Village, 2 mages par camp, 60
  graines): part moyenne des cases combustibles brûlées en fin de bataille
  **≤ 25 %**; aucune bataille au-delà de 90 rounds.
- Durée d'un round headless: **+20 %** au plus.

---

## B2 — Siège enrichi

### Géographie

- **Fossé boueux** (`MARSH`, 2 cases) au pied du mur côté assaillant,
  interrompu devant la porte (chaussée de 4 cases en `PLAIN`).
- **Palissades** (`PALISADE`): les deux lignes de couverts actuelles deviennent
  des palissades de 2 à 4 cases. Elles couvrent l'approche, mais brûlent.
- **Glacis**: bande de `HILL` d'une case derrière le mur (côté défenseur): face
  à une brèche, la mêlée des défenseurs garde l'avantage de la hauteur.

### Brèches

- Les cases de mur (`grid == 2`) reçoivent des PV par **segment vertical de 3
  cases**: `hp=24`, `save=2`. Seules les machines de guerre les entament:
  - la **catapulte** (dégâts moyens ≥ 3) inflige ses dégâts pleins;
  - la **baliste** (dégâts moyens ≥ 2) inflige la **moitié** de ses dégâts,
    arrondie à l'inférieur: elle perce, mais lentement;
  - le **scorpion** et les tireurs ordinaires ne font rien au mur.
- Segment détruit: `grid → 0`, `terrain → RUBBLE`, cases retirées de
  `bf.walls`; les cases de rempart (`4`) et d'escalier (`5`) des mêmes rangées
  s'écroulent aussi (`grid → 0`, `RUBBLE`, retirées de `ramparts`/`stairs`).
  Une unité qui s'y trouvait chute: `1d3` dégâts, perte du bonus de rempart,
  elle reste sur sa case.
- Une brèche est une **entrée**: `CommanderAI._pick_assault_gate` considère les
  brèches ouvertes comme des portes détruites (danger évalué de la même
  manière); l'assaut les préfère si elles sont moins battues.
- IA des machines de brèche (catapulte, et baliste sans cible visible): tant
  qu'aucune brèche n'est ouverte et que la porte tient, elles visent le segment
  de mur **le moins couvert** par les tireurs
  ennemis à portée (même mesure de danger que le choix de porte), choix
  verrouillé 4 rounds.
- IA de défense: une brèche ouverte est traitée comme une porte détruite
  (`_siege_defense` y envoie la mêlée).
- Bannière « BRÈCHE DANS LE MUR ! ».

### Rendu B2

Mur fissuré en 3 états (lézardes, pierres manquantes, crénelage éboulé),
effondrement avec gros nuage de poussière et blocs projetés, brèche en éboulis
de moellons (teinte du mur) qui déborde dans le fossé.

### Tests et équilibre B2

- brèche: `walls`, `ramparts`, `stairs`, `grid`, `terrain` cohérents; unités du
  rempart écroulé blessées et privées de bonus;
- l'assaut passe par une brèche moins défendue que la porte (scénario
  headless dans `test_ai_headless.py`);
- `test_edge_cases.py`: siège sans catapulte, siège où tout le mur tombe;
- équilibre: « Siege » de `bench_balance.py` (sans catapulte) **20 %–45 %** de
  victoires assaillant (23 % aujourd'hui); nouvel affrontement « Siege
  catapulte » (assaillant + 1 catapulte) **35 %–60 %**.

---

## B3 — Citadelle

Reprend la section **1b** de `docs/superpowers/specs/2026-09-16-terrain-design.md`
(double enceinte, `siege_data['rings']`, bascule d'enceinte, posture
`fall_back`), avec en plus:

- les structures de B1 dans la basse-cour (maisons, jardins en `GROVE`/`HEDGE`);
- les brèches de B2 sur les deux enceintes;
- le fossé de B2 devant le mur extérieur.

Le plan B3 sera écrit après la fusion de B2, en relisant la section 1b à la
lumière du code d'alors.

---

## Documentation

`README.md`: section « Environnement destructible » (structures, incendie,
ruines, brèches), terrains Décombres et Brûlé dans le tableau de terrain,
cartes Siège et Citadelle mises à jour, nouvelles lignes de tests et de bancs,
mesures de performance.

## Décisions de relecture (2026-09-17)

1. **Incendie contenu**: plafond de 8 allumages par round conservé.
2. **Brèches**: catapulte à dégâts pleins **et** baliste à demi-dégâts (voir
   B2 › Brèches). Le banc « Siege » sans machine reste dans 20 %–45 %; ajouter
   un affrontement « Siege baliste » (assaillant + 1 baliste) dans 25 %–50 %.
3. **Effondrement d'une maison**: `1d3` dégâts aux unités adjacentes, conservé.
