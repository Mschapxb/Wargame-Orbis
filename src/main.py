import copy
import pygame

import os

from unit_library import get_library, create_unit_from_data
from battle import Battle
from renderer import compute_grid_from_screen, run_visual


# Chemin relatif au dossier du script (fonctionne quel que soit le dossier de lancement)
EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "Livre_des_armées_d_Orbis_Naturae.xlsx")


def build_army(library, army_name, composition):
    """Construit une armée à partir de la bibliothèque.
    
    composition: liste de tuples (nom_unité, quantité)
    Exemple: [("Infanterie régulière", 10), ("Arbaletrier régulier", 4)]
    """
    army = []
    army_units = library.get(army_name, [])
    unit_by_name = {u['name']: u for u in army_units}
    
    for unit_name, count in composition:
        data = unit_by_name.get(unit_name)
        if data is None:
            print(f"  ATTENTION: '{unit_name}' introuvable dans '{army_name}'")
            continue
        for i in range(count):
            u = create_unit_from_data(data)
            # Nom court unique
            short = unit_name[:4]
            u.name = f"{short}{i + 1}" if count > 1 else short
            army.append(u)
    
    return army


def main():
    pygame.init()
    
    # Charger la bibliothèque
    lib = get_library(EXCEL_PATH)
    
    print("=== Armées disponibles ===")
    for name in sorted(lib.keys()):
        units = [u['name'] for u in lib[name]]
        print(f"  {name}: {', '.join(units)}")
    print()
    
    # ---- Composer les armées ici ----
    
    army1 = build_army(lib, "Armée Skaldienne", [
        ("Infanterie régulière", 30),
        ("Hallbardier", 30),
        ("Arbaletrier régulier", 20),
        ("Officier", 10),
    ])
    
    army2 = build_army(lib, "Armée Skaldienne", [
        ("Infanterie régulière", 40),
        ("Hallbardier", 20),
        ("Arbaletrier régulier", 15),
        ("Officier", 15),
    ])
    
    print(f"Armée 1: {len(army1)} unités")
    print(f"Armée 2: {len(army2)} unités")
    
    # Grille adaptée à l'écran
    grid_w, grid_h, cell_size = compute_grid_from_screen()
    
    battle = Battle(army1, army2, grid_w, grid_h, 8)
    run_visual(battle, cell_size)


if __name__ == "__main__":
    main()
