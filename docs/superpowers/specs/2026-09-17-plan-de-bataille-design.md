# Lot C — IA « plan de bataille »

Date: 2026-09-17
Statut: rédigée et appliquée sans relecture préalable (l'utilisateur a demandé
de continuer le travail; les choix ouverts sont tranchés en fin de document).

## Contexte

Demande utilisateur: « améliorer l'IA pour des manœuvres et stratégies
intéressantes visuellement en bataille ».

L'IA actuelle (`ai_commander.py`) décide **round par round**: posture avec
inertie, tempérament, manœuvres opportunistes (débordement, concentration,
curée, percée, escorte), couloirs d'avance, discipline de ligne. Elle est
solide mais **réactive**: rien ne se prépare sur plusieurs rounds, rien ne se
lit à l'écran comme une intention, et le terrain (collines) n'est jamais
recherché.

## Objectif

Donner à chaque commandant un **plan de bataille** choisi au début, joué en
**phases** sur plusieurs rounds, abandonné quand il échoue, et **affiché**
(flèches, zones, drapeaux, bannières de phase). Les réflexes existants
restent prioritaires: fuir le feu, décrocher à l'agonie, achever un isolé,
escorter ses tireurs, percer une brèche.

### Hors périmètre

- Siège et Citadelle: leurs IA dédiées restent inchangées (pas de plan).
- Formations et orientation des unités, zoom, mini-carte → lot D.
- Apprentissage, adaptation entre batailles.

## Modèle

Nouveau module pur `src/battle_plan.py` (sans Pygame).

```python
class BattlePlan:
    kind: str            # "marteau", "feinte", "oblique", "colline", "direct"
    phase: str           # dépend du plan
    roles: dict          # id(unit) -> rôle: hammer, lure, refused, hold, reserve
    events: list         # (texte, couleur) à annoncer
    def update(cmd, alive, enemies, s) -> None     # une fois par round
    def order_for(cmd, unit, enemies) -> TacticalOrder | None
    def intents() -> list                          # pour le rendu
```

`CommanderAI.issue_orders` (hors siège) appelle `plan.update` après le calcul
de formation; `_standard` consulte `plan.order_for` **après** les
affectations opportunistes (curée, escorte, percée) et le décrochage, et
**avant** la logique par défaut. Le débordement opportuniste (`envelop`) est
désactivé quand le plan a son propre marteau.

`CommanderAI.use_plans` (attribut de classe, vrai par défaut) permet de
comparer avec l'IA sans plan.

### Choix du plan (au premier round, puis à chaque abandon)

Chaque plan applicable reçoit un score; on tire parmi les deux meilleurs
(poids 2:1) avec la RNG du commandant — deux batailles identiques ne se
jouent donc pas forcément pareil.

| Plan | Applicable si | Score favorisé par |
|---|---|---|
| **Enclume et marteau** | ≥ 2 unités rapides (vitesse ≥ 6), ou ≥ 8 unités de mêlée | cavalerie, audace, ruse |
| **Feinte** | ≥ 6 unités de mêlée | ruse (tempérament manœuvrier) |
| **Ordre oblique** (aile refusée) | ≥ 6 unités de mêlée | prudence, ennemi plus nombreux |
| **Tenir la colline** | une colline « objectif » plus proche de nous que de l'ennemi, ≥ 2 tireurs | patience, supériorité de tir |
| **Direct** | toujours | armée petite (< 6 unités) |

Une **réserve** (≈ 20 % de la mêlée, les unités les plus robustes, au moins
une si ≥ 7 mêlées) existe dans tous les plans sauf Direct.

### Phases et rôles

**Enclume et marteau**
- Marteau: les unités rapides, sinon ≈ 30 % de la mêlée (les plus rapides),
  côté du flanc le moins tenu par l'ennemi.
- `approche`: le marteau gagne un **point d'attente** sur son flanc, hors de
  portée (centre ennemi + perpendiculaire × (demi-front + 7) − axe × 5).
- `enclume`: le reste avance et accroche le centre (comportement par défaut).
- `frappe` — déclenchée quand ≥ 40 % de l'enclume est au contact (ou après
  8 rounds): le marteau passe par un **point de revers** (derrière la ligne
  ennemie, côté flanc) puis attaque tireurs, machines et officiers.
- Abandon: marteau réduit à moins d'une unité → plan Direct.

**Feinte**
- Leurre: 2 unités de mêlée (les moins précieuses) attaquent le flanc A.
- `feinte`: le corps principal tient sa ligne (au plus 4 rounds).
- `assaut`: déclenché quand le centre latéral ennemi glisse de ≥ 2 cases vers
  A, ou au bout de 4 rounds: le corps principal attaque en couloirs penchés
  vers B.

**Ordre oblique**
- Aile forte (côté des unités les plus puissantes) avance normalement.
- Aile refusée: se tient 4 cases en retrait de la projection de l'aile forte.
- `engagement`: quand l'aile forte est au contact depuis 2 rounds, l'aile
  refusée s'engage à son tour.

**Tenir la colline**
- Objectif: case de colline choisie par score (proximité de notre camp,
  distance au centre ennemi, cases de colline voisines).
- `prise`: tireurs vers la colline, mêlée en avant de la colline.
- `tenue`: on attend l'ennemi (au plus 8 rounds, ou tant qu'on gagne
  l'échange de tir).
- `contre-attaque`: quand l'ennemi arrive au pied de la colline ou que
  l'échange tourne en notre défaveur.

**Réserve** (tous plans)
- Postée derrière le centre (centre de mêlée − axe × 5).
- Engagée quand: une de nos unités de mêlée tombe, un ennemi perce notre
  front, ou l'ennemi saigne plus vite que nous depuis 2 rounds. Elle fonce
  alors sur l'ennemi le plus menaçant près de notre ligne. Événement « La
  réserve s'engage ! ».

### Postures

Le plan s'applique en postures `balanced`, `hold_line` et `rush`. En `exploit`
(coup de grâce), `regroup` ou `screen`, il est suspendu; `exploit` le termine.

## Rendu des intentions

- Touche **I**: affiche/masque les intentions (affichées par défaut).
- Flèches semi-transparentes de la couleur du camp: trajet du marteau
  (approche puis revers), leurre de la feinte, poussée de l'aile forte.
- Zone en pointillés: réserve; drapeau sur l'objectif de colline.
- HUD: sous la posture, le plan et sa phase.
- Bannières aux changements de phase: « Armée 1 : le marteau frappe ! »,
  « Armée 2 : feinte sur l'aile nord », « Armée 1 : la réserve s'engage ! ».
- Tout est dessiné en surplomb léger, sous les unités.

## Tests (`src/test_battle_plan.py`)

- Choix: une armée avec cavalerie peut choisir le marteau; une armée de
  5 unités joue Direct; `use_plans = False` → aucun rôle.
- Marteau: rôles au flanc le moins tenu; passage `approche → frappe` quand
  l'enclume est au contact; ordres vers le point d'attente puis le revers.
- Feinte: 2 leurres; bascule en assaut après 4 rounds.
- Oblique: l'aile refusée reste en retrait tant que l'aile forte n'est pas
  engagée.
- Colline: objectif sur une case de colline; tireurs envoyés dessus.
- Réserve: engagée à la mort d'une unité de mêlée.
- Intentions: structure correcte, dans la carte.
- Déterminisme: `test_determinism.py` reste vert.

## Équilibre et mesures (`src/bench_plans.py`)

- IA avec plans contre IA sans plan, plans tour à tour dans chaque camp,
  affrontements de campagne, 40 graines chacun: la version avec plans gagne
  **≥ 50 %** des parties (elle ne doit pas jouer moins bien).
- Biais de côté (`bench_sides.py 300`): 50 % ± 5.
- `bench_balance.py 60`: batailles de campagne dans ± 12 points; sièges
  inchangés (pas de plan).
- Statistiques affichées: répartition des plans, part des batailles où le
  marteau frappe, où la réserve s'engage.
- Durée d'un round: + 15 % au plus.

## Décisions prises sans relecture

1. Intentions **visibles par défaut** (touche I pour masquer): la demande porte
   sur l'intérêt visuel.
2. Pas de plan au siège: les IA de siège ont déjà leurs phases propres
   (brèches, sortie, repli), et y greffer un plan brouillerait leur lecture.
3. Tirage entre les deux meilleurs plans plutôt que le meilleur: variété d'une
   bataille à l'autre, au prix d'un plan parfois moins optimal.

## Résultats mesurés (`docs/superpowers/baselines/bench-after-C.txt`)

- IA avec plans contre IA sans plan: **52,5 %** des parties décidées ✓
  (Prairie mixte 52,5, cavalerie 45, Forêt 50, Village 65, Défilé 50).
- Biais de côté: 47,3 / 53,0 / 47,5 / 51,6 % ✓.
- Sièges et Citadelle: inchangés ✓ (pas de plan).
- Batailles de campagne: **hors de la tolérance de ± 12 points** sur les
  affrontements asymétriques:
  | Affrontement | Lot B3 | Lot C |
  |---|---|---|
  | Mêlée contre archers | 41/19 | 27/33 |
  | Mixte miroir | 35/25 | 26/34 |
  | Village mixte (Skald contre Orlandar) | 40/20 | 18/41 |
  | Défilé mixte (Skald contre Orlandar) | 32/23 | 16/43 |

  Cause identifiée: le plan « Tenir la colline » exploite la règle de terrain
  du chantier 1a (+1 portée en hauteur). L'armée la mieux pourvue en tir
  (archers et cavalerie à javelots d'Orlandar) s'installe sur les pentes et
  l'emporte (Défilé, colline imposée: 34 victoires sur 40). Les autres plans
  ne coûtent que 1 à 4 parties sur 40 à la même armée.

## Corrections apportées pendant la mise au point

- Feinte: les leurres qui chargeaient seuls faisaient perdre (27 %); ils se
  montrent à distance et le corps principal se masse face à l'autre aile
  (49 %).
- Ordre oblique: concentration sur l'aile ennemie la plus faible au lieu d'un
  simple retard de l'aile refusée (45 % → 49,5 %).
- Marteau: cavalerie à javelots exclue (sa propre IA intercepte déjà les
  tireurs; la figer coûtait 15 points); pas de marteau si le flanc est
  encombré.
- Pas de manœuvre quand la bande entre les fronts compte ≥ 5 % de bois
  (Forêt: 33 % → 50 %).
- Plans suspendus en « charge générale » et assaut direct sans réserve quand
  l'armée est nettement dominée au tir (mêlée contre archers: 22 → 28
  victoires sur 40 pour la mêlée).
- Bug hors lot corrigé: le rapport de bataille comptait deux fois les
  fuyards encore sur la carte.

## Décision utilisateur (2026-09-17)

Écart d'équilibre asymétrique **accepté tel quel**: l'IA exploite une règle de
terrain existante; l'équilibre se rattrapera par les compositions d'armées.
