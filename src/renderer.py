import math
import os
import pygame
import sys


simulation_speed = "normal"
pause = True

HUD_HEIGHT = 80
# Taille de cellule cible (sera ajustée à l'écran)
TARGET_CELL_SIZE = 28
MIN_CELL_SIZE = 12
MAX_CELL_SIZE = 64

# Dossier des tokens (à côté des fichiers .py)
TOKENS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")

# Cache des images de tokens: {(token_name, size): Surface ou None}
_token_cache = {}


def load_token(token_name, size):
    """Charge et redimensionne un token. Retourne None si pas trouvé."""
    key = (token_name, size)
    if key in _token_cache:
        return _token_cache[key]
    
    filepath = os.path.join(TOKENS_DIR, f"{token_name}.png")
    if os.path.exists(filepath):
        try:
            img = pygame.image.load(filepath).convert_alpha()
            img = pygame.transform.smoothscale(img, (size, size))
            _token_cache[key] = img
            return img
        except Exception:
            _token_cache[key] = None
            return None
    
    _token_cache[key] = None
    return None


def clear_token_cache():
    """Vide le cache (utile après resize)."""
    _token_cache.clear()



def compute_grid_from_screen(target_cell=TARGET_CELL_SIZE):
    """Détecte la résolution écran et calcule la grille qui remplit l'écran.
    
    Retourne (grid_width, grid_height, cell_size).
    """
    info = pygame.display.Info()
    screen_w = info.current_w
    screen_h = info.current_h
    
    # Prendre 95% de l'écran pour laisser un peu de marge
    usable_w = int(screen_w * 0.95)
    usable_h = int(screen_h * 0.90)
    
    cell_size = max(MIN_CELL_SIZE, min(target_cell, MAX_CELL_SIZE))
    
    grid_w = usable_w // cell_size
    grid_h = (usable_h - HUD_HEIGHT) // cell_size
    
    # Minimums raisonnables
    grid_w = max(30, grid_w)
    grid_h = max(20, grid_h)
    
    return grid_w, grid_h, cell_size


def build_grid_surface(battle, cell_size):
    """Pré-rend la surface de la grille."""
    W = battle.battlefield.width * cell_size
    grid_h = battle.battlefield.height * cell_size
    grid_surface = pygame.Surface((W, grid_h))
    for x in range(battle.battlefield.width):
        for y in range(battle.battlefield.height):
            r = pygame.Rect(x * cell_size, y * cell_size, cell_size, cell_size)
            if battle.battlefield.grid[x][y]:
                col = (80, 100, 70)
            else:
                v = ((x + y) % 3) * 3
                col = (40 + v, 60 + v, 40 + v)
            pygame.draw.rect(grid_surface, col, r)
            pygame.draw.rect(grid_surface, (50, 70, 50), r, 1)
    return grid_surface


def draw_projectile(screen, proj):
    pos = proj.get_current_pos()
    angle = proj.get_angle()
    
    if proj.projectile_type == "arrow":
        length = 12
        ex = pos[0] + length * math.cos(angle)
        ey = pos[1] + length * math.sin(angle)
        sx = pos[0] - length * math.cos(angle)
        sy = pos[1] - length * math.sin(angle)
        pygame.draw.line(screen, proj.color, (sx, sy), (ex, ey), 2)
        a = math.pi / 6
        p1 = (ex - 6 * math.cos(angle - a), ey - 6 * math.sin(angle - a))
        p2 = (ex - 6 * math.cos(angle + a), ey - 6 * math.sin(angle + a))
        pygame.draw.polygon(screen, (255, 200, 100), [(ex, ey), p1, p2])
    elif proj.projectile_type == "fireball":
        r = 6
        pygame.draw.circle(screen, (255, 200, 0), (int(pos[0]), int(pos[1])), r + 2)
        pygame.draw.circle(screen, (255, 100, 0), (int(pos[0]), int(pos[1])), r)
        pygame.draw.circle(screen, (255, 255, 100), (int(pos[0]), int(pos[1])), r // 2)
    elif proj.projectile_type == "magic":
        r = 5
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        for i in range(4):
            tx = pos[0] - i * 4 * cos_a
            ty = pos[1] - i * 4 * sin_a
            pygame.draw.circle(screen, (150, 100, min(255, 200 + i * 10)), (int(tx), int(ty)), max(1, r - i))
        pygame.draw.circle(screen, (200, 150, 255), (int(pos[0]), int(pos[1])), r)


def run_visual(battle, cell_size):
    global pause, simulation_speed
    
    bf_w = battle.battlefield.width
    bf_h = battle.battlefield.height
    W = bf_w * cell_size
    H = bf_h * cell_size + HUD_HEIGHT
    
    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    pygame.display.set_caption("Battle Simulator")
    clock = pygame.time.Clock()
    
    font_small_size = max(9, cell_size // 3)
    font_tiny_size = max(7, cell_size // 4)
    small_font = pygame.font.SysFont("arial", font_small_size)
    tiny_font = pygame.font.SysFont("arial", font_tiny_size)
    
    grid_surface = build_grid_surface(battle, cell_size)
    
    running = True
    last_round = pygame.time.get_ticks()
    winner = None
    show_lines = True
    
    _original_army1 = battle.army1
    _original_army2 = battle.army2
    _obstacle_count = 8
    
    while running:
        now = pygame.time.get_ticks()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.VIDEORESIZE:
                new_w, new_h = event.w, event.h
                cell_from_w = new_w // bf_w
                cell_from_h = (new_h - HUD_HEIGHT) // bf_h
                cell_size = max(MIN_CELL_SIZE, min(min(cell_from_w, cell_from_h), MAX_CELL_SIZE))
                W = bf_w * cell_size
                H = bf_h * cell_size + HUD_HEIGHT
                screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
                grid_surface = build_grid_surface(battle, cell_size)
                font_small_size = max(9, cell_size // 3)
                font_tiny_size = max(7, cell_size // 4)
                small_font = pygame.font.SysFont("arial", font_small_size)
                tiny_font = pygame.font.SysFont("arial", font_tiny_size)
                clear_token_cache()
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    pause = not pause
                elif event.key == pygame.K_a:
                    simulation_speed, pause = "fast", False
                elif event.key == pygame.K_n:
                    simulation_speed, pause = "normal", False
                elif event.key == pygame.K_p:
                    pause = True
                elif event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    from battle import Battle
                    battle = Battle(_original_army1, _original_army2, bf_w, bf_h, _obstacle_count)
                    grid_surface = build_grid_surface(battle, cell_size)
                    winner = None
                elif event.key == pygame.K_t:
                    show_lines = not show_lines
        
        if not pause and winner is None:
            delay = 150 if simulation_speed == "fast" else 800
            if now - last_round >= delay:
                battle.simulate_round(cell_size)
                last_round = now
                a1 = sum(1 for u in battle.army1 if u.is_alive)
                a2 = sum(1 for u in battle.army2 if u.is_alive)
                if a1 == 0:
                    winner = "Armée 2"
                elif a2 == 0:
                    winner = "Armée 1"
        
        # Vieillir effets visuels
        for p in battle.visual_effects['projectiles'][:]:
            p.age += 1
            if p.age >= p.duration:
                battle.visual_effects['projectiles'].remove(p)
        
        for l in battle.visual_effects['attack_lines'][:]:
            l.age += 1
            if l.age >= l.duration:
                battle.visual_effects['attack_lines'].remove(l)
        
        screen.fill((25, 40, 30))
        screen.blit(grid_surface, (0, 0))
        
        # Ligne centrale
        center_x = bf_w // 2 * cell_size
        pygame.draw.line(screen, (60, 60, 60), (center_x, 0), (center_x, bf_h * cell_size), 1)
        
        # Lignes de ciblage (couleur selon type d'attaque)
        if show_lines:
            for att, tgt in battle.visual_effects['target_indicators']:
                if att.is_alive and tgt.is_alive:
                    sp = (att.position[0] * cell_size + cell_size // 2, att.position[1] * cell_size + cell_size // 2)
                    ep = (tgt.position[0] * cell_size + cell_size // 2, tgt.position[1] * cell_size + cell_size // 2)
                    dist = battle.battlefield.manhattan_distance(att.position, tgt.position)
                    if dist <= att._max_range:
                        if att.attack_type == "spell":
                            color = (120, 60, 180)
                        elif att.attack_type == "ranged":
                            color = (60, 120, 180)
                        elif att.attack_type == "reach":
                            color = (180, 150, 40)
                        else:
                            color = (180, 60, 60)
                        pygame.draw.line(screen, color, sp, ep, 1)
        
        # Lignes d'attaque (rouge=CaC, jaune=portée)
        for line in battle.visual_effects['attack_lines']:
            alpha = line.get_alpha()
            t = alpha / 255
            r, g, b = line.color
            color = (int(r * t), int(g * t), int(b * t))
            pygame.draw.line(screen, color, line.start_pos, line.end_pos, max(1, int(3 * t)))
        
        # Projectiles
        for proj in battle.visual_effects['projectiles']:
            draw_projectile(screen, proj)
        
        # Unités
        ur = max(3, cell_size // 2 - 4)
        tick_time = pygame.time.get_ticks()
        pulse = (tick_time // 200) % 4
        army1_set = set(id(u) for u in battle.army1)
        
        for u in battle.army1 + battle.army2:
            if u.position is None:
                continue
            x, y = u.position
            cx = x * cell_size + cell_size // 2
            cy = y * cell_size + cell_size // 2
            
            # Aura de peur
            if u.fear_aura > 0 and u.is_alive:
                for i in range(6):
                    ang = i * 60 + pulse * 20
                    rad = math.radians(ang)
                    px = cx + int((ur + 8) * math.cos(rad))
                    py = cy + int((ur + 8) * math.sin(rad))
                    fc = (220, 40, 40) if u.fear_aura == 1 else (240, 140, 0) if u.fear_aura == 2 else (255, 50, 150)
                    pygame.draw.circle(screen, fc, (px, py), max(1, 3 * cell_size // 32))
            
            # Symbole d'attaque au-dessus de l'unité
            # ⚔ CaC pur = X rouge | Lance/portée = | jaune | Tir = → bleu | Sort = ✦ violet
            if u.is_alive and u.current_target and u.current_target.is_alive and not u.fleeing:
                sy = cy - ur - 10
                s = max(3, cell_size // 8)  # Taille adaptative
                
                if u.attack_type == "spell":
                    # Étoile violette (losange + croix)
                    c = (180, 80, 255)
                    pygame.draw.line(screen, c, (cx, sy - s), (cx, sy + s), 2)
                    pygame.draw.line(screen, c, (cx - s, sy), (cx + s, sy), 2)
                    pygame.draw.line(screen, c, (cx - s + 1, sy - s + 1), (cx + s - 1, sy + s - 1), 1)
                    pygame.draw.line(screen, c, (cx + s - 1, sy - s + 1), (cx - s + 1, sy + s - 1), 1)
                
                elif u.attack_type == "ranged":
                    # Flèche bleue →
                    c = (80, 160, 255)
                    pygame.draw.line(screen, c, (cx - s, sy), (cx + s, sy), 2)
                    pygame.draw.line(screen, c, (cx + s, sy), (cx + s - 3, sy - 3), 2)
                    pygame.draw.line(screen, c, (cx + s, sy), (cx + s - 3, sy + 3), 2)
                
                elif u.attack_type == "reach":
                    # Lance jaune (trait vertical + pointe)
                    c = (255, 200, 50)
                    pygame.draw.line(screen, c, (cx, sy + s), (cx, sy - s), 2)
                    pygame.draw.line(screen, c, (cx, sy - s), (cx - 2, sy - s + 3), 2)
                    pygame.draw.line(screen, c, (cx, sy - s), (cx + 2, sy - s + 3), 2)
                
                else:
                    # X rouge (CaC pur)
                    c = (220, 80, 80)
                    pygame.draw.line(screen, c, (cx - s, sy - s), (cx + s, sy + s), 2)
                    pygame.draw.line(screen, c, (cx + s, sy - s), (cx - s, sy + s), 2)
            
            # Corps: cercle d'équipe (bleu=A1, rouge=A2) + token ou cercle intérieur
            token_size = ur * 2
            is_army1 = id(u) in army1_set
            team_color = (60, 120, 220) if is_army1 else (220, 60, 60)
            
            if u.is_alive:
                # Cercle d'équipe (contour)
                ring_r = ur + 2
                pygame.draw.circle(screen, team_color, (cx, cy), ring_r)
                
                if u.fleeing:
                    # Fuite = cercle orange
                    pygame.draw.circle(screen, (255, 140, 0), (cx, cy), ur)
                else:
                    token_img = load_token(u.token_name, token_size) if u.token_name else None
                    if token_img:
                        # Token image par-dessus le cercle d'équipe
                        screen.blit(token_img, (cx - token_size // 2, cy - token_size // 2))
                    else:
                        # Fallback: cercle couleur de l'unité + point de rôle
                        pygame.draw.circle(screen, u.color, (cx, cy), ur)
                        dot_r = max(1, 3 * cell_size // 32)
                        rc = (255, 255, 255) if u.role == "front" else (128, 128, 128) if u.role == "mid" else (0, 0, 0)
                        pygame.draw.circle(screen, rc, (cx, cy), dot_r)
            else:
                # Mort: cercle gris avec contour équipe
                pygame.draw.circle(screen, team_color, (cx, cy), ur + 2, 2)
                pygame.draw.circle(screen, (60, 60, 60), (cx, cy), max(1, ur - 2), 2)
            
            # Barre HP
            bw = max(4, cell_size - 8)
            hp_r = max(0, u.hp / u.max_hp) if u.max_hp > 0 else 0
            by = cy - ur - 5
            pygame.draw.rect(screen, (140, 30, 30), (cx - bw // 2, by, bw, 3))
            pygame.draw.rect(screen, (30, 140, 30), (cx - bw // 2, by, int(bw * hp_r), 3))
            
            # Nom et moral
            if cell_size >= 20:
                name_txt = tiny_font.render(u.name[:5], True, (220, 220, 220))
                screen.blit(name_txt, (cx - name_txt.get_width() // 2, cy + ur + 2))
                
                if u.is_alive:
                    effective_morale = u.get_effective_morale()
                    moral_color = (100, 255, 100) if effective_morale >= 3 else (255, 255, 100) if effective_morale >= 2 else (255, 100, 100)
                    moral_txt = tiny_font.render(f"M:{effective_morale}", True, moral_color)
                    screen.blit(moral_txt, (cx - moral_txt.get_width() // 2, cy + ur + 12))
            
            # Statut
            if u.status_text and cell_size >= 16:
                st = small_font.render(u.status_text, True, (255, 80, 80))
                screen.blit(st, (cx - st.get_width() // 2, cy - ur - 18))
            
            # Textes flottants
            if cell_size >= 16:
                oy = -ur - 6
                for ft in list(u.floating_texts):
                    ft.age += 1
                    if ft.age > ft.duration:
                        u.floating_texts.remove(ft)
                        continue
                    alpha = 255 - int(255 * (ft.age / ft.duration))
                    ts = tiny_font.render(ft.text, True, ft.color)
                    ts.set_alpha(alpha)
                    screen.blit(ts, (cx - ts.get_width() // 2, cy + oy - ft.age // 4))
                    oy -= 10
        
        # HUD
        hy = bf_h * cell_size + 5
        status = "VICTOIRE: " + winner if winner else ("PAUSE" if pause else ("RAPIDE" if simulation_speed == "fast" else "NORMAL"))
        color = (255, 215, 0) if winner else ((255, 100, 100) if pause else ((255, 220, 80) if simulation_speed == "fast" else (100, 220, 100)))
        a1c = sum(1 for u in battle.army1 if u.is_alive)
        a2c = sum(1 for u in battle.army2 if u.is_alive)
        hud = small_font.render(f"Round {battle.round - 1} | {status} | Verts: {a1c} | Rouges: {a2c}", True, color)
        screen.blit(hud, (10, hy))
        
        # Légende
        ly = hy + 18
        lx = 10
        # Rôles
        pygame.draw.circle(screen, (255, 255, 255), (lx + 5, ly + 5), 4)
        screen.blit(tiny_font.render("Front", True, (180, 180, 180)), (lx + 15, ly))
        pygame.draw.circle(screen, (128, 128, 128), (lx + 60, ly + 5), 4)
        screen.blit(tiny_font.render("Mid", True, (180, 180, 180)), (lx + 70, ly))
        pygame.draw.circle(screen, (0, 0, 0), (lx + 105, ly + 5), 4)
        screen.blit(tiny_font.render("Back", True, (180, 180, 180)), (lx + 115, ly))
        
        # Séparateur
        lx2 = lx + 160
        # Symboles d'attaque
        # CaC: X rouge
        pygame.draw.line(screen, (220, 80, 80), (lx2, ly + 1), (lx2 + 8, ly + 9), 2)
        pygame.draw.line(screen, (220, 80, 80), (lx2 + 8, ly + 1), (lx2, ly + 9), 2)
        screen.blit(tiny_font.render("CaC", True, (180, 180, 180)), (lx2 + 12, ly))
        
        # Portée: | jaune
        lx3 = lx2 + 45
        pygame.draw.line(screen, (255, 200, 50), (lx3 + 4, ly + 9), (lx3 + 4, ly + 1), 2)
        pygame.draw.line(screen, (255, 200, 50), (lx3 + 4, ly + 1), (lx3 + 2, ly + 4), 2)
        pygame.draw.line(screen, (255, 200, 50), (lx3 + 4, ly + 1), (lx3 + 6, ly + 4), 2)
        screen.blit(tiny_font.render("Portée", True, (180, 180, 180)), (lx3 + 12, ly))
        
        # Tir: → bleu
        lx4 = lx3 + 60
        pygame.draw.line(screen, (80, 160, 255), (lx4, ly + 5), (lx4 + 8, ly + 5), 2)
        pygame.draw.line(screen, (80, 160, 255), (lx4 + 8, ly + 5), (lx4 + 5, ly + 2), 2)
        pygame.draw.line(screen, (80, 160, 255), (lx4 + 8, ly + 5), (lx4 + 5, ly + 8), 2)
        screen.blit(tiny_font.render("Tir", True, (180, 180, 180)), (lx4 + 12, ly))
        
        # Sort: ✦ violet
        lx5 = lx4 + 40
        sc = lx5 + 4
        pygame.draw.line(screen, (180, 80, 255), (sc, ly + 1), (sc, ly + 9), 2)
        pygame.draw.line(screen, (180, 80, 255), (sc - 4, ly + 5), (sc + 4, ly + 5), 2)
        pygame.draw.line(screen, (180, 80, 255), (sc - 3, ly + 2), (sc + 3, ly + 8), 1)
        pygame.draw.line(screen, (180, 80, 255), (sc + 3, ly + 2), (sc - 3, ly + 8), 1)
        screen.blit(tiny_font.render("Sort", True, (180, 180, 180)), (lx5 + 12, ly))
        
        # Contrôles
        ctrl = tiny_font.render("ESPACE=Pause A=Vite N=Normal R=Reset T=Lignes ESC=Quit", True, (150, 170, 200))
        screen.blit(ctrl, (10, ly + 18))
        
        size = tiny_font.render(f"Grille {bf_w}x{bf_h} | Cell {cell_size}px | FPS: {int(clock.get_fps())}", True, (120, 120, 120))
        screen.blit(size, (W - size.get_width() - 10, ly + 18))
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()
    sys.exit()