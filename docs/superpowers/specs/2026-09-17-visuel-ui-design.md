# Lot D — Visuel et interface

Date: 2026-09-17
Statut: rédigée et appliquée (l'utilisateur a demandé de continuer le travail).

## Contexte

Demande utilisateur: « améliorer visuellement le jeu, que cela soit l'UI mais
les batailles aussi ». Les lots B et C ont apporté la destruction et les
intentions d'IA; il manque de quoi **naviguer** et **comprendre** une grande
bataille (178 × 64 cases, ~2,6 écrans de large): la caméra ne zoome pas,
aucune vue d'ensemble, rien pour inspecter une unité, et le bas d'écran n'est
qu'une ligne de texte.

## Livraisons

### D1 — Zoom
- Niveaux: 0,5 · 0,67 · 0,8 · 1 · 1,25 · 1,6 · 2. Molette (zoom autour du
  curseur), touches `+`/`-`, `0` pour revenir à 1.
- Le monde est dessiné à la taille de case d'origine dans une surface de vue
  (largeur écran / zoom), puis mise à l'échelle. Aucune coordonnée du moteur,
  des effets ou des repeints ne change; la destruction, les flammes et les
  intentions suivent le zoom sans code supplémentaire.
- Glisser au clic milieu et défilement aux bords restent en pixels écran.

### D2 — Mini-carte
- Coin supérieur droit, sous le bandeau: vignette du terrain, points d'unités
  aux couleurs des camps, rectangle de la vue courante.
- Clic (ou glissé) sur la mini-carte: la caméra s'y centre. `Tab` la masque
  (`M` est déjà le retour au menu).
- Vignette rafraîchie après les repeints de destruction (au plus une fois par
  seconde).

### D3 — Fiche d'unité au survol
- Survol d'une unité: panneau à côté du curseur avec nom et camp, PV (barre),
  moral effectif, sauvegarde, armes (portée, attaques, toucher/blesser,
  dégâts), sorts, état (en fuite, ébranlé, sous le feu), ordre en cours et
  rôle dans le plan de bataille.
- Anneau de sélection autour de l'unité survolée.

### D4 — Bandeau inférieur
- Deux panneaux d'armée (gauche/droite): nom, jauge vivants / fuyards / morts,
  posture et plan en cours.
- Au centre: état (pause, vitesse, victoire), round, zoom.
- Aide des touches condensée sur une ligne.

### D5 — Orientation des unités
- Petit chevron sur l'anneau d'équipe, tourné vers la cible courante (ou vers
  le déplacement en cours): on voit d'un coup d'œil qui fait face à qui.

## Tests
- `test_ui.py` (pygame en mode `dummy`): conversions écran ↔ monde au zoom,
  bornes de caméra, mini-carte (clic → centre caméra), sélection de l'unité
  survolée, construction de la fiche (lignes attendues), bandeau et chevrons
  dessinés sans erreur; boucle d'affichage réelle avec zoom, survol et
  mini-carte.

## Performance
- Zoom 1: aucun surcoût. Zoom ≠ 1: une mise à l'échelle par image
  (`transform.scale`, pas `smoothscale`), ≤ 3 ms en 1920×1000.
