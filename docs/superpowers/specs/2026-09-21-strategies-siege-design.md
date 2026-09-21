# Stratégies de siège — offensive et défensive

Date: 2026-09-21. Demande: « refait les stratégies de siège à l'offensive et
défensive ». Choix tranchés ici sans relecture (cf. mémoire du projet).

## Constat (mesuré pendant les lots fortification / engins / servants)

Offensive (armée 1):
- l'infanterie marche droit au mur dès le round 1 et perd le duel de tir
  sous le rempart (Siège sans machine: ~15 % de victoires);
- elle n'attend pas ses engins: bélier et tour arrivent quand l'infanterie
  est déjà morte (trace: assaillants anéantis avant l'accostage de la tour);
- aucune coordination entre catapulte/baliste et l'assaut (l'infanterie
  s'expose pendant que la machine perce);
- les deux portes de la Citadelle ne servent jamais à diviser la défense.

Défensive (armée 2):
- garnison statique: la mêlée attend derrière SA porte de déploiement, même
  quand la menace est une tour de siège à l'autre bout du mur;
- les tireurs ne visent pas ce qui fait avancer les engins (pousseurs,
  artilleurs), alors que tuer deux pousseurs arrête un bélier;
- après une brèche, la mêlée sort « au combat ouvert » au lieu de tenir
  la sortie de la brèche.

## Conception

Nouveau module pur `siege_plan.py`, classe `SiegePlan`, même interface que
`BattlePlan` (kind, phase, roles, label(), active(), pop_events(),
order_for(), intents(), update()). En siège, `CommanderAI.plan` est un
`SiegePlan` (les bannières, le bandeau et la touche I marchent tels quels).

### Offensive — un plan choisi au premier round selon l'armée

| Plan | Quand | Phases |
|---|---|---|
| Assaut coordonné (`engins`) | bélier ou tour de siège | approche → assaut |
| Pilonnage (`pilonnage`) | machine de tir servie, pas d'engin | bombardement → assaut |
| Feinte sur une porte (`feinte`) | ≥ 2 portes (Citadelle), ≥ 6 mêlées | feinte → assaut |
| Assaut direct (`direct`) | sinon | — (comportement actuel) |

- Ligne d'attente: hors de portée du rempart (portée max des tireurs
  défenseurs + 2 cases). La mêlée qui attend s'y range, alignée sur l'axe
  d'assaut; au contact, elle combat.
- `engins/approche`: la mêlée marche en colonne 2 cases derrière l'engin
  le plus avancé; les tireurs se portent sur son flanc et tirent sur le
  rempart. Assaut quand un engin est à ≤ 6 cases de son but, quand un
  passage s'ouvre, ou quand il n'y a plus d'engin. (Variante « attendre à
  la ligne d'attente » essayée et rejetée: toute la garnison tirait sur le
  bélier et ses pousseurs, bélier au Siège N2 17 % → 3 %.)
- `pilonnage/bombardement`: tout le monde hors de portée, les machines
  percent. Assaut à la brèche/porte brisée, ou au bout de 5 rounds (10:
  catapulte 75-82 %, sans riposte possible), ou si l'on saigne plus vite
  que la garnison. Sortie de la garnison contre la batterie essayée et
  rejetée (suicide face à l'armée intacte: assaillant 89-98 %).
- `feinte`: deux mêlées se montrent devant la porte secondaire (à portée
  de rempart, sans aller au contact); le corps principal attend à la ligne
  d'attente devant la porte d'assaut, puis donne l'assaut 3 rounds après
  l'arrivée des leurres.
- Cibles de l'assaillant: tireurs de rempart proches d'un engin +3.

### Défensive — plan `defense`, phase = menace courante

Menace (ordre de priorité): brèche ouverte → bélier en marche (sa porte)
→ tour de siège en approche (son poste d'accostage) → porte la plus
pressée par la mêlée ennemie. Phases: `murs`, `porte`, `tour`, `brèche`.

- Réserve mobile: la mêlée qui n'est pas sur le rempart se poste juste
  derrière le point menacé (étalée sur ±2 rangées); face à une tour, elle
  monte tenir la sortie de la passerelle sur le chemin de ronde.
- Après une brèche: tenir la sortie de la brèche (au lieu de sortir);
  intercepter tout ennemi entré.
- Cibles de la garnison: pousseurs d'un engin à ≤ 12 cases du mur +6,
  artilleurs +3 (contre-batterie).
- Sortie, contre-attaque et repli sur le donjon: inchangés.

## Critères

- Siège et Citadelle, niveaux 1-3, avec et sans machines (suite
  `bench.py fortification`, 120 graines): l'assaillant doit rester dans une
  fourchette jouable (cible 25-50 % au niveau 1 avec machines), sans nuls.
- Batailles rangées strictement inchangées (le plan de siège n'existe que
  sur une carte de siège).
- Tests: `test_siege_plan.py`.

## Correctifs trouvés en mesurant

- Repli sur le donjon: la passerelle d'une tour ne déclenche plus le repli
  à elle seule (il faut ≥ 2 assaillants derrière le mur). Citadelle + tour
  N2: 76 % → 39 %.
- « Cible sur le rempart » (-2 svg) ne vaut que contre les TIRS: en mêlée
  sur le chemin de ronde, deux unités devenaient intouchables (nuls).
- Pousseurs au contact de leur engin: -2 svg contre les tirs (abrités).
- Poste d'accostage d'une tour: jamais sur un autre engin (le bélier rangé
  la bloquait); un engin bloqué 4 rounds libère ses pousseurs.

## Mesures finales (120 graines, % de victoires de l'assaillant, N1/N2/N3)

Voir le message de livraison et la mémoire du projet.
