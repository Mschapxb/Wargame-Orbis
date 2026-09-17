import pygame

from unit_library import list_armies, list_units
from battle import Battle
from renderer import compute_grid_from_screen, run_visual
from menu import run_army_menu
from maps import describe_options


def main():
    pygame.init()
    
    print("=== Armées disponibles ===")
    for name in list_armies():
        units = list_units(name)
        print(f"  {name}: {', '.join(units)}")
    print()
    
    while True:
        # Menu de composition
        result = run_army_menu()
        if result is None:
            break
        
        army1, army2, map_name, map_options = result
        print(f"\nArmée 1: {len(army1)} unités")
        print(f"Armée 2: {len(army2)} unités")

        grid_w, grid_h, cell_size = compute_grid_from_screen()
        battle = Battle(army1, army2, grid_w, grid_h, 8, map_name=map_name,
                        map_options=map_options)
        print(f"Map: {describe_options(map_name, battle.battlefield.theme)}")
        
        # run_visual retourne "menu" pour revenir, ou None pour quitter
        action = run_visual(battle, cell_size)
        
        if action == "menu":
            continue
        else:
            break


if __name__ == "__main__":
    main()
