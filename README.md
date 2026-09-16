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
- Choisir la **carte** (Prairie, Forêt, Village, Siège)
- Lancer la bataille avec **COMBAT!**

### Contrôles en bataille

| Touche | Action |
|--------|--------|
| `ESPACE` | Pause / Reprendre |
| `F` | Mode rapide |
| `N` | Mode normal |
| `ZQSD` / `Flèches` | Déplacer la caméra |
| `Molette` / `Clic milieu` | Drag caméra |
| `T` | Afficher/masquer les lignes de ciblage |
| `B` | Basculer plein écran / fenêtré sans bordure |
| `R` | Relancer la bataille |
| `M` | Retour au menu |
| `ESC` | Quitter |

---

## 🗺️ Cartes disponibles

| Carte | Description |
|-------|-------------|
| **Prairie** | Terrain ouvert, quelques obstacles. Favorise la cavalerie et les charges. |
| **Forêt** | Dense, beaucoup d'arbres. Ralentit les charges, avantage aux embuscades. |
| **Village** | Bâtiments qui créent des couloirs et des points de choke. |
| **Siège** | Forteresse avec murs, remparts et portes destructibles. L'armée 2 défend. |
| **Défilé** | Goulet montagneux: chokepoint central, flancs impraticables. |

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
├── effects.py           # Effets visuels (projectiles, explosions, soins)
├── maps.py              # Définition des cartes et génération de terrain
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
python -m pytest tests/test_main.py -q      # unitaires (règles, groupes du menu, régressions)
python src/test_edge_cases.py               # cas limites: armées vides, carte minuscule, siège dégénéré…
python src/test_ai_headless.py              # scénarios IA (sortie, rush, ligne de tir…)
python src/bench_balance.py 60              # équilibrage sur 60 graines par affrontement
```

### Pathfinding (`battlefield.py`)

- A* optimisé avec opérations inlinées (chebyshev, is_valid)
- Les alliés sont **traversables** avec pénalité (pas de blocage permanent)
- Mouvement latéral de secours quand le chemin est bloqué

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