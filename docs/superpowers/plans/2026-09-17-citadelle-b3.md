# Lot B3 — Citadelle à double enceinte — Plan d'implémentation

**Spec:** `docs/superpowers/specs/2026-09-16-terrain-design.md` §1b, complétée
par `docs/superpowers/specs/2026-09-17-destruction-design.md` §B3 (structures,
brèches et fossé de B1/B2).

**Branche:** `lot-a-fondations`, par-dessus A, B1 et B2 (non commités).

## Principe

Deux temps, pour que le Siège actuel ne bouge pas:

1. **Modèle d'enceintes** sans changement de comportement: le Siège devient
   une forteresse à une seule enceinte. Contrôle: `bench_balance.py 60`
   donne exactement les mêmes lignes « Siege* » qu'après B2, et
   `test_determinism.py` reste vert.
2. **Citadelle**: carte, bascule d'enceinte, repli vers le donjon, rendu,
   tests et équilibre.

## Tâche 1 — Modèle d'enceintes (`battlefield.py`)

- `siege_data['rings']` = `[{wall_x, gates}]`, de l'extérieur vers
  l'intérieur; à défaut, une enceinte construite depuis les clés historiques
  (`wall_x`, `gates`).
- `bf.rings`, `bf.active_ring`, propriétés `is_siege`, `wall_x`,
  `active_gates` (`{pos: pv}` de l'enceinte active), `active_breaches`,
  `has_next_ring`.
- Portes ouvertes **par case**: `bf.open_gate_cells`. `gates_open` devient
  une propriété (portes de l'enceinte active ouvertes); `open_gates()` /
  `close_gates()` agissent sur l'enceinte active; `open_ring_gates(i)`.
  Physique (passage, ligne de vue, A*): une porte laisse passer si elle est
  détruite ou si sa case est ouverte.
- `advance_ring()`: les portes encore debout de l'enceinte tombée sont
  forcées (PV 0), l'enceinte suivante devient active.

## Tâche 2 — Lectures migrées

- `siege_data.get('wall_x')` → `bf.wall_x`; portes « à défendre / à
  enfoncer » → `bf.active_gates`; brèches utiles → `bf.active_breaches`;
  tests `map_name == "Siège"` → `bf.is_siege` (déploiement, moral).
- `gate_hp` reste l'état physique global (toutes enceintes).

## Tâche 3 — Carte Citadelle (`maps.generate_citadel`)

- Mur extérieur à `0,55 × width`, 2 portes (1/3 et 2/3 de la hauteur),
  remparts, escaliers, fossé et palissades comme le Siège.
- Donjon à `0,80 × width`, 1 porte centrale, remparts et escaliers.
- Basse-cour: maisons (`HOUSE`), jardins (`WOOD`), butte (`HILL`) devant le
  donjon; glacis derrière le mur extérieur.
- `MAP_TYPES["Citadelle"]`, décor, taches de sol, menu (automatique).

## Tâche 4 — Bascule d'enceinte (`battle.py`)

Une fois par round après le moral, s'il existe une enceinte suivante:
l'enceinte active tombe si (a) toutes ses portes sont détruites ou une
brèche y est ouverte, **et** au moins 3 assaillants (ou la moitié des vivants)
sont au-delà de son mur; ou (b) plus aucun défenseur non fuyard ne se trouve
entre son mur et celui de l'enceinte suivante. Journal d'importance 3
« L'ENCEINTE EXTÉRIEURE EST TOMBÉE ! ».

## Tâche 5 — IA

- Défense: posture `fall_back` quand l'enceinte active est sur le point de
  tomber (PV des portes ≤ 30 % ou brèche ouverte, et ennemis à ≤ 2 cases du
  mur). Portes du donjon ouvertes; tireurs et mages → remparts du donjon;
  arrière-garde (≈ 1/3 de la mêlée, la plus robuste) tient 2 rounds devant
  l'enceinte puis rentre; le reste rentre au donjon. Après la bascule, les
  portes du donjon se referment quand tout le monde est rentré.
- `sortie` n'est proposée que depuis l'enceinte active.
- Assaut: choix de porte, brèches et couloirs sur l'enceinte active (hérité
  de la tâche 2); verrous remis à zéro à la bascule.

## Tâche 6 — Rendu

- Palissades dessinées comme des pieux (et non plus comme des rochers).
- Maisons et haies dessinées d'un seul tenant sur toute carte qui en a.
- Portes ouvertes par case; bannière de chute d'enceinte.

## Tâche 7 — Tests, bancs, documentation

- `test_citadelle.py`: modèle d'enceintes (portes du donjon fermées tant que
  l'extérieur tient, ouverture par case, `advance_ring`), géographie
  (connexité assaillant → donjon une fois les portes forcées), bascule (a) et
  (b), `fall_back` ouvre le donjon, scénario headless qui se termine et où la
  bascule survient dans la majorité des graines d'un assaut fort.
- `test_edge_cases.py`: Citadelle dans la boucle des cartes; citadelle sans
  défenseurs.
- `bench_balance.py`: « Citadelle » équilibrée, défenseur vainqueur entre
  40 % et 65 %.
- README (carte, bascule, repli), mémoire.
