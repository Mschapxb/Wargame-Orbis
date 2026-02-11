import pygame

from unit_library import build_army, list_armies, list_units
from battle import Battle
from renderer import compute_grid_from_screen, run_visual


def main():
    pygame.init()
    
    # Afficher les armées disponibles
    print("=== Armées disponibles ===")
    for name in list_armies():
        units = list_units(name)
        print(f"  {name}: {', '.join(units)}")
    print()
    
    # ──────────────── COMPOSER LES ARMÉES ICI ────────────────
    
    army1 = build_army("Armée Skaldienne", [
        ("Infanterie régulière", 50),
        ("Hallbardier", 20),
        ("Arbaletrier régulier", 20),
        ("Officier", 10),
        ("Scorpion", 10),
        ("Baliste", 5),
        ("Housecarl", 5),
    ])
    
    army2 = build_army("Armée Skaldienne", [
        ("Infanterie régulière", 50),
        ("Hallbardier", 20),
        ("Arbaletrier régulier", 20),
        ("Officier", 10),
        ("Mage de guerre", 5),
    ])
    
    # ────────────────────────────────────────────────────────
    
    print(f"Armée 1: {len(army1)} unités")
    print(f"Armée 2: {len(army2)} unités")
    
    grid_w, grid_h, cell_size = compute_grid_from_screen()
    battle = Battle(army1, army2, grid_w, grid_h, 8)
    run_visual(battle, cell_size)


if __name__ == "__main__":
    main()