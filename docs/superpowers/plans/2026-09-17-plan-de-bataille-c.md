# Lot C — IA « plan de bataille » — Plan d'implémentation

**Spec:** `docs/superpowers/specs/2026-09-17-plan-de-bataille-design.md`

**Branche:** `lot-a-fondations`; commits gérés par l'utilisateur.

## Référence

`docs/superpowers/baselines/bench-after-B3.txt`.

## Tâches

1. **`battle_plan.py`** — `BattlePlan`: choix pondéré (deux meilleurs, 2:1),
   rôles (marteau, leurre, aile refusée, colline, réserve), phases, abandon,
   événements, intentions. Pur, déterministe (RNG du commandant).
2. **Branchement IA** — `CommanderAI.use_plans`, `self.plan`; `plan.update`
   dans `issue_orders` hors siège (postures balanced/hold_line/rush);
   `plan.order_for` dans `_standard` après les affectations opportunistes et
   le décrochage; `envelop` désactivé si marteau; `exploit` termine le plan.
3. **Annonces** — `Battle.simulate_round` relaie `plan.events` au journal
   (importance 2 → bannières).
4. **Rendu** — `renderer.draw_intents` (flèches, zones, drapeau), touche `I`,
   plan et phase dans le HUD, aide des touches.
5. **Tests** — `test_battle_plan.py` (cf. spec).
6. **Mesures** — `bench_plans.py`; `bench_balance.py 60`, `bench_maps.py 60`,
   `bench_sides.py 300` → `bench-after-C.txt`; coût d'un round.
7. **Documentation** — README (section IA, touche I), mémoire.
