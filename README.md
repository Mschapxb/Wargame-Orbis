# ⚔️ Battle Simulator — Simulateur de Batailles Tactiques

Simulateur de batailles au tour par tour avec rendu visuel en temps réel. Composez vos armées, choisissez un terrain et regardez l'affrontement se dérouler avec pathfinding A*, système de moral, charges de cavalerie, sorts et siège de forteresse.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Pygame](https://img.shields.io/badge/Pygame-2.5+-green) ![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🚀 Installation

```bash
# Cloner le projet
git clone <url-du-repo>
cd battle-simulator

# Installer les dépendances
pip install -r requirements.txt

# Lancer le jeu
python main.py
```

> **Prérequis** : Python 3.10+ et Pygame 2.5+. Aucune autre dépendance externe.

---

## 🎮 Comment jouer

### Menu de composition

Au lancement, un menu permet de :

- Sélectionner une **armée prédéfinie** pour chaque camp (Orlandar, Skaldienne, Draconie, Légion sacrée, Héros)
- Articuler un camp en plusieurs **groupes** (jusqu'à 4) via les onglets `G1 G2 …`:
  chaque groupe est une portion d'armée — d'une seule faction ou de plusieurs — qui
  est **déployée comme un corps séparé** (front, centre et tireurs propres), marquée
  d'une pastille de couleur sur le terrain et **comptée à part dans le rapport de
  bataille**. Les boutons `+/-` alimentent le groupe sélectionné.
- Ajouter/retirer des unités individuellement avec les boutons **+/-**
- Choisir la **carte** (Prairie, Forêt, Village, Siège, Citadelle, Défilé)
- Lancer la bataille avec **COMBAT!**

### Contrôles en bataille

| Touche | Action |
|--------|--------|
| `ESPACE` | Pause / Reprendre |
| `F` | Mode rapide |
| `N` | Mode normal |
| `ZQSD` / `Flèches` | Déplacer la caméra |
| `Molette` | Zoom (×0,5 à ×2) autour du curseur |
| `+` / `-` / `0` | Zoomer / dézoomer / revenir à ×1 |
| `Clic milieu` | Glisser la caméra |
| `Tab` | Afficher/masquer la mini-carte (clic ou glissé dessus pour s'y rendre) |
| Survol d'une unité | Fiche: PV, moral, sauvegarde, armes, sorts, état, ordre et rôle dans le plan |
| `T` | Afficher/masquer les lignes de ciblage |
| `I` | Afficher/masquer les intentions des plans de bataille (flèches, réserves, colline) |
| `L` | Afficher/masquer la légende du terrain |
| `B` | Basculer plein écran / fenêtré sans bordure |
| `R` | Relancer la bataille |
| `M` | Retour au menu |
| `ESC` | Quitter |

---

## 🗺️ Cartes disponibles

| Carte | Description |
|-------|-------------|
| **Prairie** | Terrain ouvert, deux crêtes rocheuses dessinent trois couloirs. Favorise la cavalerie et les charges. Crêtes en collines, colline centrale, broussailles sur les flancs. |
| **Forêt** | Massif boisé **au centre** du champ de bataille, fait de bosquets entre lesquels on se faufile, avec clairières et sentiers. Les armées se déploient dans les champs et doivent entrer dans le bois pour se rencontrer. Bosquets à cœur impénétrable et sous-bois traversable, ruisseau à deux gués. |
| **Village** | Bourg **circulaire** au centre: place, maisons en anneaux, rues rayonnantes et haie d'enceinte percée à chaque rue. On se déploie hors du bourg et on s'engage dans les rues. Bourg sur une butte, jardins, mare. |
| **Siège** | Forteresse avec murs, remparts et portes destructibles. L'armée 2 défend. Fossé boueux au pied du mur (chaussée devant la porte), glacis derrière les escaliers, palissades inflammables côté assaillant, mur que les machines de guerre peuvent percer. |
| **Citadelle** | Double enceinte. L'armée 2 défend. Mur extérieur à **deux portes** (fossé, glacis, palissades côté assaillant), **basse-cour** avec maisons, jardins et butte, puis **donjon** à une porte. Quand l'enceinte extérieure est sur le point de tomber, la défense **se replie sur le donjon**. |
| **Défilé** | Goulet montagneux: chokepoint central, flancs impraticables. Pentes, éboulis, torrent avec pont et gué. |

### Terrain

Chaque case porte un terrain qui change la manière de se battre. Chaque
terrain a une teinte **et** un motif, pour rester lisible sans distinguer
les couleurs. `L` affiche la légende en bataille.

| Terrain | Déplacement | Vue | Combat |
|---------|-------------|-----|--------|
| **Colline** | ×1,5 pour monter | un tireur en hauteur voit par-dessus les bois; une colline masque ce qui est derrière | tir depuis la hauteur: +1 portée; mêlée contre une unité en hauteur: +1 au seuil de toucher (plus difficile) |
| **Bois** | ×2 | 3 cases de bois masquent la cible | tirs reçus: +1 au seuil de toucher (plus difficile); pas de charge |
| **Rivière** | infranchissable | — | — |
| **Gué** | ×2 | — | sauvegarde -1; pas de charge |
| **Pont** | normal | — | passage étroit |
| **Marais** | ×3 | — | sauvegarde -1; pas de charge |
| **Décombres** | ×2 | — | tirs reçus: +1 au seuil de toucher (couvert); pas de charge |
| **Brûlé** | normal | — | — (le bois consumé ne couvre ni ne masque plus rien) |

Une unité fait toujours au moins un pas par round, même en marais.

Les cartes sont larges (~2,6 écrans × 64 cases): les armées marchent un moment
avant le choc — premier corps-à-corps vers le 7e round en prairie, 9e en forêt et
au village. Le siège conserve son placement historique.

Hors siège, chaque carte est **symétrique** (la moitié ouest est recopiée à
l'est) et les deux armées se déploient en reflet exact: aucun camp ne part
avec plus de couverts. Mesuré sur 300 duels miroir par carte, l'armée de
gauche gagne 50 % des parties (contre 61 à 68 % auparavant).

Les **obstacles** — rochers, maisons, haies, cœurs de bosquet — sont
infranchissables et **coupent la ligne de tir**, comme les murs.

### Environnement destructible

Les obstacles de la Prairie (rochers), de la Forêt (cœurs de bosquet) et du
Village (maisons, haies) sont des **structures** qui ont des points de vie.
Une maison est une seule structure: on l'entame en frappant n'importe
laquelle de ses cases, et elle s'effondre d'un bloc.

| Structure | PV | Brûle | Laisse |
|-----------|----|-------|--------|
| Maison | 14 | oui (4 rounds) | décombres |
| Haie | 4 | oui, vite (2 rounds) | brûlé |
| Bosquet | 6 | oui (3 rounds) | brûlé |
| Rocher | 16 | non — seule une arme lourde (catapulte) l'entame | décombres |
| Palissade (siège) | 8 | oui (3 rounds) | décombres |
| Mur (siège, tronçon de 3 cases) | 24 | non — catapulte (dégâts pleins) ou baliste (moitié) | brèche en décombres |

- **Boule de feu**: entame les structures de sa zone et allume le combustible
  (une chance sur deux par case). Elle laisse un **cratère permanent**.
- **Incendie**: une case en feu brûle son occupant (1 dégât par round,
  sauvegarde normale), ébranle son moral, et sa fumée masque les tirs comme
  une case de bois. Le feu gagne les cases voisines combustibles, mais ni
  l'eau, ni les marais, ni les rues ou sentiers ne le transmettent, et au
  plus 8 nouveaux foyers s'allument par round.
- **Effondrement**: une maison qui s'écroule blesse les unités collées à ses
  murs (1d3) dans un nuage de poussière. Elle devient des **décombres**
  franchissables où l'on se met à couvert.
- **Machines de guerre**: une baliste ou une catapulte dont la cible est
  cachée derrière une structure **abat la structure** pour dégager son champ
  de tir.
- **Couvert**: une cible postée juste derrière un obstacle (palissade, haie,
  maison, rocher), du côté du tireur, reçoit +1 au seuil de toucher. C'est ce
  qui protège l'assaillant des tireurs du rempart, qui voient par-dessus.
- **Brèches**: quand un tronçon de mur tombe, le chemin de ronde et l'escalier
  de ces rangées s'écroulent avec lui (les défenseurs qui s'y tenaient
  chutent: 1d3) et une **entrée** s'ouvre. Tant que la porte tient, la
  catapulte assaillante vise le tronçon le moins défendu; la baliste, qui
  perce lentement, seulement quand elle n'a rien d'autre à viser. Dès qu'une
  brèche s'ouvre, l'assaut y bascule et la défense quitte ses positions pour
  aller au contact.
- **Double enceinte (Citadelle)**: seule l'enceinte *active* se défend et
  s'assaille. Elle tombe quand ses portes sont forcées (ou une brèche ouverte)
  et qu'au moins 3 assaillants — ou la moitié des vivants — sont passés, ou
  quand plus aucun défenseur ne tient devant le donjon. Avant cela, dès que
  les portes faiblissent (≤ 30 % des PV) sous la pression, la défense ouvre le
  donjon et **se replie**: tireurs et mages vers ses remparts, une
  **arrière-garde** (un tiers de la mêlée, les plus solides) tient deux
  rounds devant l'enceinte, le reste rentre; les portes se referment derrière
  les derniers. Bannière « L'ENCEINTE EXTÉRIEURE EST TOMBÉE ! ».
- **IA**: les unités fuient les flammes, les replis évitent les cases en feu
  et leurs abords, et un mage préfère embraser le couvert d'un ennemi plutôt
  qu'un bois où se tiennent ses propres troupes.

Le fond de carte n'est jamais reconstruit: seules les cases touchées sont
repeintes, au moment exact de l'action.

Chaque carte est habillée d'un **décor** généré (arbres, buissons, fougères,
fleurs, rochers, caisses, tonneaux, gravats…) et de taches de sol organiques.
Ce décor est purement visuel: il ne bloque rien, ne coupe aucune ligne de vue
et n'entre dans aucun calcul.

---

## ⚙️ Mécanique de combat

### Résolution d'attaque (système à D6)

Chaque attaque suit 3 jets successifs :

1. **Toucher** — jet de D6, réussi si `≥ toucher` de l'arme
2. **Blesser** — jet de D6, réussi si `≥ blesser` de l'arme
3. **Sauvegarde** — jet de D6, raté si `< sauvegarde` de la cible (modifié par la perforation)

Si les 3 passent, les dégâts de l'arme sont appliqués.

### Réactions — le tour par tour qui mord

Le moteur reste au tour par tour, mais un round n'est plus une succession de
phases figées : les actions sont **horodatées** et s'enchaînent.

| Réaction | Déclencheur | Effet |
|----------|-------------|-------|
| **Attaque d'opportunité** | Une unité rompt le contact (recul, kiting, fuite) | L'adversaire au contact porte un coup gratuit (1 par round et par unité) |
| **Tir de réaction** | Un ennemi débouche dans la zone de feu d'un tireur immobile | Le tireur lâche sa volée pendant le mouvement, pas trois phases plus tard |
| **Élan** | Une unité de mêlée abat son adversaire | Elle enchaîne aussitôt sur une autre cible à portée (1 par round) |
| **Prise à revers** | La cible est déjà accrochée par un camarade | **-1 au toucher** (le débordement devient réellement payant) |
| **Ébranlement** | Coup emportant ≥ 30 % des PV, ou feu nourri | Test de moral : l'unité combat moins bien au round suivant |

### Rythme d'un round

L'ordre d'action est un **ordre d'initiative** (vitesse, charge, allonge, un
peu d'aléa) : frapper en premier compte, un mort ne riposte pas. Chaque action
reçoit un instant dans le round, et le rendu les rejoue dans cet ordre :

```
0 %            26 %          46 %                        96 %
|--- mouvement + réactions ---|
              |-- charges --|
                        |------ échange général (initiative) ------|
```

Le round suivant enchaîne sans temps mort : à l'écran, la bataille se lit
comme un affrontement continu.

### Moral — on tient, ou on rompt pour une bonne raison

Chaque unité a un score de moral (1-5), affecté par les pertes alliées, les auras de
peur et la présence d'officiers. Mais un moral tombé à zéro **ne suffit pas** à faire
tourner les talons: une troupe ne rompt que si elle a une raison de le faire.

| Facteur | Effet |
|---------|-------|
| **Ascendant** | Une armée qui domine (valeur restante ≥ 1,15× / 1,6×) gagne +1 / +2 de bravoure — elle ne se débande pas devant plus faible qu'elle |
| **Aguerrissement** | Une unité qui a abattu 2 adversaires gagne +1 |
| **Conditions de rupture** | Ennemi au contact, unité exsangue, **feu nourri** (6 traits reçus) ou camarade tombé à côté. Sinon: statut *ébranlé*, et elle continue le combat |
| **Ralliement** | Une unité en fuite, hors de portée de l'ennemi, teste son moral chaque round — la voix d'un officier vaut +2. Réussi: elle revient au combat |
| **Retour au calme** | Deux rounds sans dégâts et sans ennemi à moins de 4 cases: le malus de moral se résorbe |
| **Pertes critiques** | Au-delà de 75 % de pertes, l'armée est brisée: là, plus d'ascendant qui tienne |

Concrètement: un camp en surnombre pilonné de loin par deux balistes **tient et va
les chercher** au lieu de se débander (mesuré: 2/30 → 30/30 victoires).

### Charges

- **Charge montée** (cavalerie) : allonge portée à 1.5× la vitesse **sur l'ensemble du round** (mouvement + charge) + **+1 dégâts** à l'impact
- **Charge d'aïda** (infanterie) : déplacement à 1.5× la vitesse + **-1 au jet de blesser** à l'impact
- Les charges nécessitent un chemin libre (pas de téléportation)
- Seule la première arme de mêlée frappe pendant la charge

### Siège

- Les **tireurs** et **mages** sur les remparts ne bougent jamais (avantage positionnel)
- Les défenseurs sur rempart bénéficient de **+2 sauvegarde** (seuil réduit de 2)
- Les attaquants sur les murs ont **-1 toucher** (plus facile de toucher)
- Les **portes** ont des PV et peuvent être détruites pour percer la défense

### Sorts

| Sort | Effet |
|------|-------|
| Boule de feu | Dégâts de zone (AoE) |
| Soin | Restaure les PV d'un allié |
| Armure magique | Bonus de sauvegarde temporaire |
| Projectile magique | Attaque à distance ciblée |
| Mur magique | Crée des obstacles temporaires |

### Traits spéciaux

- **Anti-infanterie / Anti-large** : bonus au toucher et blesser contre le type ciblé
- **Phalange** : bonus défensif en formation serrée
- **Aura de peur** : force des tests de moral aux unités ennemies proches
- **Régénération** : récupère des PV chaque tour
- **Vengeance sanglante** : contre-attaque en mourant

---

## 🎨 Rendu graphique

Tout est **généré en code** (aucune image à fournir hormis les tokens optionnels):
les sprites sont dessinés une fois à la taille de cellule courante puis mis en
cache, rotations comprises.

| Élément | Rendu |
|---------|-------|
| **Projectiles** | Flèche, carreau d'arbalète et trait de baliste distincts (choisis selon l'arme), trajectoire en cloche proportionnelle à la portée, pointe qui suit la tangente, ombre au sol et sillage |
| **Corps à corps** | Arc de lame qui balaie et s'efface (coups successifs alternés coup droit / revers), estoc pour les armes d'hast, couleur selon la nature du coup (charge, opportunité, élan…) |
| **Sorts** | Boule de feu animée avec traînée de braises, explosion (éclair, anneau, braises, fumée, trace calcinée), orbe arcanique lumineux, rayon de soin et croix qui s'élèvent, rune de bouclier tournante, blocs qui surgissent du sol |
| **Impacts** | Étincelles, gouttes de sang, poussière ou débris selon le coup; éclairs lumineux en mélange additif |
| **Morts** | Le token reste debout jusqu'à l'instant du coup fatal, recule sous le choc, chute dans le sens du coup, s'assombrit puis s'efface en laissant une dépouille au sol |
| **Cartes** | Grain de texture, taches de terrain organiques, décor semé (arbres, buissons, rochers, caisses…), maisons d'un seul tenant, falaises stratifiées, remparts crénelés avec ombre portée, portes qui se fissurent |
| **Destruction** | Flammes animées et variées, halo qui palpite, braises et colonnes de fumée qui dérivent; maisons au toit percé puis éventré; effondrement dans un nuage de poussière; décombres, sol calciné et souches noires; cratères permanents |
| **Interface** | Zoom ×0,5 à ×2 (le monde est dessiné à taille réelle puis mis à l'échelle: ≤ 3 ms par image), mini-carte cliquable, fiche d'unité au survol, bandeau à deux panneaux (jauges au combat / en fuite / tombés, posture, plan, tempérament), chevron d'orientation vers la cible, bannières limitées aux 3 plus récentes |
| **Ambiance** | Ombres de nuages qui dérivent, vignettage des bords de l'écran |

Les décalques au sol (sang, brûlures, dépouilles) s'estompent au bout d'une
trentaine de secondes; particules et décalques sont plafonnés. Mesuré avec 79
unités en pleine mêlée: **7 ms** par image en médiane, **12,5 ms** au 99e
percentile (le budget à 60 i/s est de 16,6 ms). La pause fige aussi les effets.

## 🏗️ Architecture du projet

```
battle-simulator/
├── main.py              # Point d'entrée
├── menu.py              # Menu de composition des armées (Pygame)
├── battle.py            # Boucle de simulation (rounds, phases, moral)
├── battlefield.py       # Grille, pathfinding A*, calcul de mouvement
├── ai_commander.py      # IA tactique (postures, manœuvres, ciblage)
├── tactics.py           # Maths de combat, carte de menace, anticipation
├── renderer.py          # Rendu visuel Pygame (grille, unités, effets)
├── unit.py              # Classe Unit (stats, combat, animations)
├── unit_library.py      # Base de données d'unités et armées prédéfinies
├── models.py            # Armes et sorts (Arme, SpellFireball, etc.)
├── effects.py           # Données d'effets horodatées (projectiles, coups, sorts, morts)
├── fx_render.py         # Mise en scène: particules, décalques, animations de mort
├── sprites.py           # Sprites procéduraux mis en cache (projectiles, lames, sorts…)
├── maps.py              # Définition des cartes et génération de terrain
├── terrain.py           # Règles de terrain (coûts, vue, modificateurs)
├── terrain_render.py    # Motifs et légende du terrain
├── tokens/              # Images PNG des tokens d'unités (optionnel)
└── requirements.txt     # Dépendances Python
```

### Déploiement

Chaque groupe reçoit une **bande de terrain proportionnelle à son effectif**, et
l'ensemble est centré verticalement sur la carte. À l'intérieur d'une bande, les
unités sont rangées en colonnes: front, puis centre, puis tireurs et machines.
Quand une colonne atteindrait la hauteur de sa bande, un **rang supplémentaire**
s'ouvre en arrière — c'est ce qui évite qu'une armée nombreuse forme une file
plus haute que la carte et finisse tassée contre le bord. Un rôle vide ne
consomme pas de colonne, pour qu'un groupe sans infanterie de première ligne ne
laisse pas de trou dans le front.

### Boucle de simulation (`battle.py`)

Chaque round se déroule en phases :

1. **Commandement** — l'IA évalue la situation, choisit sa posture et assigne les ordres
2. **Mouvement cohésif** en 3 passes :
   - Statiques (fuyards, artillerie)
   - Engagées (au contact) — micro-ajustements
   - En approche — avance en formation avec cohésion et étalement latéral
3. **Réactions au mouvement** — attaques d'opportunité sur rupture de contact, tirs de réaction
4. **Moral** — pertes lourdes, auras de peur, ébranlement sous le feu
5. **Charge** — choc horodaté tôt dans le round, cible choisie pour sa valeur
6. **Échange général** — résolution dans l'ordre d'initiative, avec enchaînements (élan)

Le banc d'essai `bench_balance.py` rejoue des affrontements types sur N graines
et affiche taux de victoire, durée et survivants : de quoi vérifier qu'une
modification de mécanique ne fait pas basculer l'équilibre.

### Tests

```bash
python src/test_terrain.py                  # terrain: règles, cartes, rendu
python src/test_fondations.py               # symétrie des cartes, ligne de tir, estimation IA
python src/test_destruction.py              # structures, incendie, ruines, IA et rendu incrémental
python src/test_citadelle.py                # double enceinte: portes par case, bascule, repli, rendu
python src/test_battle_plan.py              # plans de bataille: choix, phases, réserve, intentions
python src/test_ui.py                       # interface: zoom, mini-carte, fiche d'unité, bandeau, boucle réelle
python src/test_determinism.py              # une graine rejoue la même bataille
python src/test_edge_cases.py               # cas limites: armées vides, carte minuscule, siège dégénéré…
python src/test_ai_headless.py              # scénarios IA (sortie, rush, ligne de tir…)
python src/measure_contact.py               # round du premier contact par carte
python src/bench_balance.py 60              # équilibrage sur 60 graines par affrontement
python src/bench_maps.py 60                 # équilibrage Village et Défilé
python src/bench_sides.py 300               # biais de côté: une armée contre son double, par carte
python src/bench_fire.py 60                 # incendies: part du combustible consumé, durée des batailles
python src/bench_plans.py 40                # IA avec plans contre la même IA sans plan
```

### Pathfinding (`battlefield.py`)

- A* optimisé avec opérations inlinées (chebyshev, is_valid)
- Les alliés sont **traversables** avec pénalité (pas de blocage permanent)
- Mouvement latéral de secours quand le chemin est bloqué

### Plans de bataille (`battle_plan.py`)

Au-dessus des décisions round par round, chaque commandant joue un **plan**
choisi au début de la bataille et mené en phases sur plusieurs rounds
(hors siège). Le tirage se fait entre les deux plans les mieux notés selon
l'armée, le terrain et le tempérament: deux batailles identiques ne se jouent
pas forcément pareil.

| Plan | Idée | Phases |
|------|------|--------|
| **Enclume et marteau** | Le centre accroche l'ennemi, un détachement de mêlée rapide contourne un flanc | approche (point d'attente hors de portée) → frappe (revers, sur les tireurs et officiers) |
| **Feinte** | Deux leurres se montrent sur une aile, le corps principal se masse face à l'autre | feinte → assaut principal |
| **Ordre oblique** | Concentration sur l'aile ennemie la plus faible; une petite aile refusée fixe l'autre | aile refusée → engagement |
| **Tenir la colline** | Les tireurs prennent une colline (+1 portée), la mêlée tient devant | prise → tenue → contre-attaque |
| **Assaut direct** | Petite armée, terrain boisé entre les armées, ou plan abandonné | — |

Une **réserve** (≈ 20 % de la mêlée, les plus robustes) attend derrière le
centre et s'engage quand une unité de première ligne tombe, qu'un ennemi
perce le front, ou que l'ennemi saigne plus vite que nous. Les réflexes
restent prioritaires (fuir le feu, décrocher à l'agonie, achever un isolé,
escorter ses tireurs, percer une brèche).

Les intentions s'affichent sur le champ de bataille (touche `I`) et les
changements de phase s'annoncent en bannière (« Armée 1 : le marteau
frappe ! »). Mesuré par `bench_plans.py`: l'IA avec plans gagne un peu plus
de la moitié de ses parties contre la même IA sans plan — les plans rendent
les batailles lisibles sans affaiblir l'IA (une feinte où les leurres
chargeaient seuls tombait à 27 %; en sous-bois, les manœuvres cèdent la place
à l'assaut direct).

### IA tactique (`ai_commander.py` + `tactics.py`)

- **Tempérament** tiré à la création (audacieux, méthodique, prudent,
  manœuvrier, brutal) : il déforme tous les seuils de décision, donc deux
  parties identiques ne se jouent pas de la même façon.
- **Postures** avec inertie (on ne change pas d'avis à chaque dé) :
  `balanced`, `rush`, `hold_line`, `screen` (couvrir ses tireurs),
  `exploit` (achever un ennemi qui craque), `regroup`, plus `hold_walls`,
  `sortie` et `recall` en siège.
- **Manœuvres** : concentration contre un ennemi scindé, débordement par
  les ailes, **curée** sur une unité isolée, **percée** dans une faille de
  la ligne adverse, escorte des tireurs **et des machines de guerre**.
- **Appui avant assaut** : tant qu'une baliste ou un scorpion a un champ de
  tir dégagé, l'infanterie tient la ligne au lieu d'aller masquer son propre
  feu et d'arriver en ordre dispersé (mesuré: 52 % → 68 % de victoires pour
  l'armée qui aligne des machines).
- **Front resserré** : la mêlée reçoit des couloirs compacts (un mur de
  boucliers), les tireurs un étalement plus large; l'avance penche vers le
  secteur le moins tenu de la ligne adverse.
- **Évaluation chiffrée** (`tactics.py`) : dégâts espérés, probabilité de
  tuer ce round, valeur résiduelle d'une unité, rapport de forces local.
  Le feu se concentre sur une cible réellement **abattable**.
- **Carte de menace** (influence map) : replis, kiting et décrochages
  choisissent une case sûre au lieu de reculer sous un autre tir.
- **Anticipation** : la cavalerie vise le point d'**interception** de sa
  proie ; l'écran se poste sur l'axe d'approche prévu de la menace.
- **Décrochage** : une unité à l'agonie que la ligne peut remplacer rompt
  le combat au lieu de mourir sur place.
- **Assaut de siège** : la porte visée est la moins défendue, pas la plus
  proche, et le choix tient plusieurs rounds.
- Attribution de **couloirs** sans croisement (les colonnes ne se
  traversent plus pendant l'avance).

---

## 🎨 Tokens personnalisés

Placez des images PNG dans le dossier `tokens/` avec le nom correspondant au `token_name` de l'unité. Les tokens sont automatiquement redimensionnés à la taille de la cellule.

Exemple : pour une unité avec `token_name = "chevalier"`, créez `tokens/chevalier.png`.

---

## 🔧 Personnalisation

### Ajouter une unité

Éditez `unit_library.py` et ajoutez une entrée dans le dictionnaire de la faction :

```python
"Mon Unité": {
    "pv": 10,           # Points de vie
    "vitesse": 4,       # Cases par tour
    "morale": 3,        # Score de moral (1-5)
    "sauvegarde": 5,    # Seuil de sauvegarde (D6)
    "color": (R, G, B), # Couleur du token
    "role": "front",    # front / mid / back
    "unit_type": "Infanterie",  # Infanterie / Cavalerie / Large / Artillerie / Monstre / Héros
    "armes": [
        Arme("Épée", nb_attaque=2, toucher=3, blesser=4, perforation=0, degats="1d6", porte=1),
    ],
}
```

### Ajouter une carte

Éditez `maps.py` et ajoutez une entrée dans `MAP_TYPES` avec les couleurs et la fonction de génération d'obstacles.

---

## 📋 Crédits

Développé en Python avec Pygame. Système de combat inspiré des wargames sur table.