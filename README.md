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

---

## ⚙️ Mécanique de combat

### Résolution d'attaque (système à D6)

Chaque attaque suit 3 jets successifs :

1. **Toucher** — jet de D6, réussi si `≥ toucher` de l'arme
2. **Blesser** — jet de D6, réussi si `≥ blesser` de l'arme
3. **Sauvegarde** — jet de D6, raté si `< sauvegarde` de la cible (modifié par la perforation)

Si les 3 passent, les dégâts de l'arme sont appliqués.

### Moral

Chaque unité a un score de moral (1-5). Le moral est affecté par les pertes alliées, les auras de peur et la présence d'officiers. Quand le moral est brisé, l'unité **fuit** vers le bord de la carte. Si trop d'unités fuient, c'est la **déroute** générale.

### Charges

- **Charge montée** (cavalerie) : déplacement à 1.5× la vitesse + **+1 dégâts** à l'impact
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
├── ai_commander.py      # IA tactique (ordres, ciblage, flanquement)
├── renderer.py          # Rendu visuel Pygame (grille, unités, effets)
├── unit.py              # Classe Unit (stats, combat, animations)
├── unit_library.py      # Base de données d'unités et armées prédéfinies
├── models.py            # Armes et sorts (Arme, SpellFireball, etc.)
├── effects.py           # Effets visuels (projectiles, explosions, soins)
├── maps.py              # Définition des cartes et génération de terrain
├── tokens/              # Images PNG des tokens d'unités (optionnel)
└── requirements.txt     # Dépendances Python
```

### Boucle de simulation (`battle.py`)

Chaque round se déroule en phases :

1. **Commandement** — l'IA assigne des ordres tactiques (attaque, flanquement, protection, hold)
2. **Mouvement cohésif** en 3 passes :
   - Statiques (fuyards, artillerie)
   - Engagées (au contact) — micro-ajustements
   - En approche — avance en formation avec cohésion et étalement latéral
3. **Charge** — cavalerie et infanterie avec bonus temporaires
4. **Combat** — résolution des attaques (mêlée, portée, sorts)
5. **Moral** — tests de moral, fuite, déroute

### Pathfinding (`battlefield.py`)

- A* optimisé avec opérations inlinées (chebyshev, is_valid)
- Les alliés sont **traversables** avec pénalité (pas de blocage permanent)
- Mouvement latéral de secours quand le chemin est bloqué

### IA tactique (`ai_commander.py`)

- Attribution de **lanes** pour un front étalé
- Ordres contextuels : attaque, flanquement, protection des tireurs, hold
- Ciblage prioritaire : blessés, officiers, artillerie

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