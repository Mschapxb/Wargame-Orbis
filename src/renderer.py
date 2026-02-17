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
    """Calcule une grille large avec hauteur fixe de 50 cases.
    
    Retourne (grid_width, grid_height, cell_size).
    """
    info = pygame.display.Info()
    screen_w = info.current_w
    screen_h = info.current_h
    
    cell_size = max(MIN_CELL_SIZE, min(target_cell, MAX_CELL_SIZE))
    
    # Largeur: ~2x l'écran, hauteur: fixe 50 cases
    grid_w = (screen_w * 2) // cell_size
    grid_h = 50
    
    grid_w = max(80, grid_w)
    
    return grid_w, grid_h, cell_size


def build_grid_surface(battle, cell_size):
    """Pré-rend la surface de la grille avec le thème de la map."""
    from maps import get_map_info
    
    bf = battle.battlefield
    W = bf.width * cell_size
    grid_h = bf.height * cell_size
    grid_surface = pygame.Surface((W, grid_h))
    
    theme = get_map_info(bf.map_name)
    bg = theme["bg_color"]
    obs_color = theme["obstacle_color"]
    grid_color = theme["grid_color"]
    wall_color = theme.get("wall_color", (100, 100, 110))
    gate_color = theme.get("gate_color", (140, 100, 50))
    
    for x in range(bf.width):
        for y in range(bf.height):
            r = pygame.Rect(x * cell_size, y * cell_size, cell_size, cell_size)
            cell = bf.grid[x][y]
            
            if cell == 2:  # Mur
                pygame.draw.rect(grid_surface, wall_color, r)
                # Crénelage
                pygame.draw.rect(grid_surface, (120, 120, 130), r, 2)
            elif cell == 3:  # Porte
                hp = bf.gate_hp.get((x, y), 0)
                if hp > 0:
                    pygame.draw.rect(grid_surface, gate_color, r)
                    # Barres de PV de porte
                    bar_w = cell_size - 4
                    pct = hp / 10
                    pygame.draw.rect(grid_surface, (60, 40, 20),
                                     (x * cell_size + 2, y * cell_size + cell_size - 5, bar_w, 3))
                    pygame.draw.rect(grid_surface, (200, 150, 50),
                                     (x * cell_size + 2, y * cell_size + cell_size - 5, int(bar_w * pct), 3))
                else:
                    # Porte détruite — sol visible
                    v = ((x + y) % 3) * 3
                    col = (bg[0] + v, bg[1] + v, bg[2] + v)
                    pygame.draw.rect(grid_surface, col, r)
                    # Débris
                    pygame.draw.line(grid_surface, (90, 70, 40),
                                     (x * cell_size + 2, y * cell_size + 2),
                                     (x * cell_size + cell_size - 2, y * cell_size + cell_size - 2), 1)
            elif cell == 1:  # Obstacle
                if bf.map_name == "Forêt":
                    pygame.draw.rect(grid_surface, (25, 50, 20), r)
                    cx = x * cell_size + cell_size // 2
                    cy_tree = y * cell_size + cell_size // 2
                    tr = max(2, cell_size // 3)
                    pygame.draw.circle(grid_surface, (30, 80, 25), (cx, cy_tree), tr)
                    pygame.draw.circle(grid_surface, (20, 60, 15), (cx, cy_tree), tr, 1)
                elif bf.map_name == "Village":
                    pygame.draw.rect(grid_surface, obs_color, r)
                    pygame.draw.rect(grid_surface, (70, 55, 35), r, 2)
                    pygame.draw.line(grid_surface, (110, 80, 50),
                                     (x * cell_size, y * cell_size),
                                     (x * cell_size + cell_size, y * cell_size), 2)
                else:
                    pygame.draw.rect(grid_surface, obs_color, r)
            elif cell == 4:  # Rempart marchable
                # Sol plus clair que le mur, avec bordure
                ramp_color = (85, 85, 95)
                pygame.draw.rect(grid_surface, ramp_color, r)
                pygame.draw.rect(grid_surface, (100, 100, 110), r, 1)
            elif cell == 5:  # Escalier
                stair_color = (75, 70, 60)
                pygame.draw.rect(grid_surface, stair_color, r)
                # Lignes horizontales pour figurer les marches
                step_h = max(2, cell_size // 4)
                for sy in range(y * cell_size + 2, (y + 1) * cell_size - 1, step_h):
                    pygame.draw.line(grid_surface, (95, 85, 70),
                                     (x * cell_size + 2, sy),
                                     (x * cell_size + cell_size - 2, sy), 1)
            else:
                # Sol
                v = ((x + y) % 3) * 3
                col = (bg[0] + v, bg[1] + v, bg[2] + v)
                pygame.draw.rect(grid_surface, col, r)
            
            pygame.draw.rect(grid_surface, grid_color, r, 1)
    
    return grid_surface


def draw_projectile(screen, proj, ox=0, oy=0):
    pos = proj.get_current_pos()
    px, py = pos[0] + ox, pos[1] + oy
    angle = proj.get_angle()
    
    if proj.projectile_type == "arrow":
        length = 12
        ex = px + length * math.cos(angle)
        ey = py + length * math.sin(angle)
        sx = px - length * math.cos(angle)
        sy = py - length * math.sin(angle)
        pygame.draw.line(screen, proj.color, (sx, sy), (ex, ey), 2)
        a = math.pi / 6
        p1 = (ex - 6 * math.cos(angle - a), ey - 6 * math.sin(angle - a))
        p2 = (ex - 6 * math.cos(angle + a), ey - 6 * math.sin(angle + a))
        pygame.draw.polygon(screen, (255, 200, 100), [(ex, ey), p1, p2])
    elif proj.projectile_type == "fireball":
        r = 6
        pygame.draw.circle(screen, (255, 200, 0), (int(px), int(py)), r + 2)
        pygame.draw.circle(screen, (255, 100, 0), (int(px), int(py)), r)
        pygame.draw.circle(screen, (255, 255, 100), (int(px), int(py)), r // 2)
    elif proj.projectile_type == "magic":
        r = 5
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        for i in range(4):
            tx = px - i * 4 * cos_a
            ty = py - i * 4 * sin_a
            pygame.draw.circle(screen, (150, 100, min(255, 200 + i * 10)), (int(tx), int(ty)), max(1, r - i))
        pygame.draw.circle(screen, (200, 150, 255), (int(px), int(py)), r)


def draw_battle_report(screen, report, screen_w, battlefield_h, small_font, tiny_font):
    """Dessine le rapport de bataille en overlay semi-transparent."""
    title_font = pygame.font.SysFont("arial", 22, bold=True)
    header_font = pygame.font.SysFont("arial", 17, bold=True)
    body_font = pygame.font.SysFont("arial", 14)
    detail_font = pygame.font.SysFont("arial", 13)
    
    panel_w = min(750, screen_w - 20)
    panel_h = min(550, battlefield_h - 10)
    px = (screen_w - panel_w) // 2
    py = (battlefield_h - panel_h) // 2
    
    overlay = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    overlay.fill((15, 20, 25, 230))
    screen.blit(overlay, (px, py))
    pygame.draw.rect(screen, (200, 180, 80), (px, py, panel_w, panel_h), 2)
    
    y = py + 14
    
    title = title_font.render("RAPPORT DE BATAILLE", True, (255, 215, 0))
    screen.blit(title, (px + (panel_w - title.get_width()) // 2, y))
    y += 28
    
    winner_txt = header_font.render(f"Victoire: {report['winner']}  —  {report['rounds']} rounds", True, (220, 200, 120))
    screen.blit(winner_txt, (px + (panel_w - winner_txt.get_width()) // 2, y))
    y += 26
    
    pygame.draw.line(screen, (120, 120, 80), (px + 15, y), (px + panel_w - 15, y), 1)
    y += 10
    
    col_w = (panel_w - 40) // 2
    
    for i, army_key in enumerate(['army1', 'army2']):
        army = report[army_key]
        col_x = px + 15 + i * (col_w + 10)
        cy = y
        
        team_color = (80, 160, 255) if i == 0 else (255, 80, 80)
        
        header = header_font.render(army['name'], True, team_color)
        screen.blit(header, (col_x, cy))
        cy += 24
        
        total = army['total']
        n_alive = army['alive_count']
        n_dead = army['dead_count']
        n_fled = army['fled_count']
        
        bar_w = col_w - 5
        bar_h = 16
        
        if total > 0:
            alive_pct = n_alive / total
            dead_pct = n_dead / total
            fled_pct = n_fled / total
            
            pygame.draw.rect(screen, (40, 40, 40), (col_x, cy, bar_w, bar_h))
            if alive_pct > 0:
                pygame.draw.rect(screen, (50, 180, 50), (col_x, cy, int(bar_w * alive_pct), bar_h))
            if fled_pct > 0:
                fx = col_x + int(bar_w * alive_pct)
                pygame.draw.rect(screen, (220, 150, 30), (fx, cy, int(bar_w * fled_pct), bar_h))
            if dead_pct > 0:
                dx = col_x + int(bar_w * (alive_pct + fled_pct))
                pygame.draw.rect(screen, (180, 40, 40), (dx, cy, int(bar_w * dead_pct), bar_h))
            pygame.draw.rect(screen, (100, 100, 100), (col_x, cy, bar_w, bar_h), 1)
        cy += bar_h + 8
        
        txt_alive = body_font.render(f"Vivants: {n_alive}/{total}", True, (80, 220, 80))
        screen.blit(txt_alive, (col_x, cy))
        cy += 20
        
        txt_dead = body_font.render(f"Morts: {n_dead}/{total}", True, (220, 80, 80))
        screen.blit(txt_dead, (col_x, cy))
        cy += 20
        
        txt_fled = body_font.render(f"Fuyants: {n_fled}/{total}", True, (220, 170, 50))
        screen.blit(txt_fled, (col_x, cy))
        cy += 24
        
        pygame.draw.line(screen, (60, 60, 60), (col_x, cy), (col_x + col_w - 5, cy), 1)
        cy += 6
        
        # Survivants (groupés: nom x quantité)
        if army['alive']:
            label = body_font.render("Survivants:", True, (80, 220, 80))
            screen.blit(label, (col_x, cy))
            cy += 18
            for name, count in army['alive'][:8]:
                txt = f"  {name} x{count}" if count > 1 else f"  {name}"
                t = detail_font.render(txt, True, (160, 220, 160))
                screen.blit(t, (col_x, cy))
                cy += 16
            if len(army['alive']) > 8:
                rest = sum(c for _, c in army['alive'][8:])
                more = detail_font.render(f"  ...et {rest} autres", True, (120, 160, 120))
                screen.blit(more, (col_x, cy))
                cy += 16
        
        # Fuyants (groupés: nom x quantité)
        if army['fled']:
            cy += 4
            label = body_font.render("Fuyants:", True, (220, 170, 50))
            screen.blit(label, (col_x, cy))
            cy += 18
            for name, count in army['fled'][:8]:
                txt = f"  {name} x{count}" if count > 1 else f"  {name}"
                t = detail_font.render(txt, True, (200, 170, 80))
                screen.blit(t, (col_x, cy))
                cy += 16
            if len(army['fled']) > 8:
                rest = sum(c for _, c in army['fled'][8:])
                more = detail_font.render(f"  ...et {rest} autres", True, (150, 130, 60))
                screen.blit(more, (col_x, cy))
                cy += 16
        
        # Morts (groupés: nom x quantité)
        if army['dead']:
            cy += 4
            label = body_font.render("Morts:", True, (220, 80, 80))
            screen.blit(label, (col_x, cy))
            cy += 18
            for name, count in army['dead'][:8]:
                txt = f"  {name} x{count}" if count > 1 else f"  {name}"
                t = detail_font.render(txt, True, (180, 100, 100))
                screen.blit(t, (col_x, cy))
                cy += 16
            if len(army['dead']) > 8:
                rest = sum(c for _, c in army['dead'][8:])
                more = detail_font.render(f"  ...et {rest} autres", True, (120, 80, 80))
                screen.blit(more, (col_x, cy))
                cy += 16


def run_visual(battle, cell_size):
    global pause, simulation_speed
    
    bf_w = battle.battlefield.width
    bf_h = battle.battlefield.height
    
    info = pygame.display.Info()
    SCREEN_W = info.current_w
    SCREEN_H = info.current_h
    
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
    pygame.display.set_caption("Battle Simulator")
    clock = pygame.time.Clock()
    
    font_small_size = max(9, cell_size // 3)
    font_tiny_size = max(7, cell_size // 4)
    small_font = pygame.font.SysFont("arial", font_small_size)
    tiny_font = pygame.font.SysFont("arial", font_tiny_size)
    
    grid_surface = build_grid_surface(battle, cell_size)
    
    # ─── Caméra ───
    world_w = bf_w * cell_size
    world_h = bf_h * cell_size
    
    # Centrer la caméra au départ
    cam_x = (world_w - SCREEN_W) / 2
    cam_y = (world_h - (SCREEN_H - HUD_HEIGHT)) / 2
    cam_x = max(0, cam_x)
    cam_y = max(0, cam_y)
    
    CAM_SPEED = 12  # pixels/frame
    EDGE_SCROLL_MARGIN = 30
    dragging = False
    drag_start = (0, 0)
    drag_cam_start = (0, 0)
    
    def clamp_camera():
        nonlocal cam_x, cam_y
        view_h = SCREEN_H - HUD_HEIGHT
        max_x = max(0, world_w - SCREEN_W)
        max_y = max(0, world_h - view_h)
        cam_x = max(0, min(cam_x, max_x))
        cam_y = max(0, min(cam_y, max_y))
    
    clamp_camera()
    
    running = True
    _return_action = None
    last_round = pygame.time.get_ticks()
    winner = None
    battle_report = None
    show_lines = True
    
    import copy
    _original_army1 = copy.deepcopy(battle.army1_roster)
    _original_army2 = copy.deepcopy(battle.army2_roster)
    _bf_w = battle.battlefield.width
    _bf_h = battle.battlefield.height
    _obstacle_count = 8
    _map_name = battle.map_name
    
    while running:
        now = pygame.time.get_ticks()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                _return_action = None
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 2:  # Middle click → drag
                    dragging = True
                    drag_start = event.pos
                    drag_cam_start = (cam_x, cam_y)
            
            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 2:
                    dragging = False
            
            if event.type == pygame.MOUSEMOTION and dragging:
                dx = drag_start[0] - event.pos[0]
                dy = drag_start[1] - event.pos[1]
                cam_x = drag_cam_start[0] + dx
                cam_y = drag_cam_start[1] + dy
                clamp_camera()
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    pause = not pause
                elif event.key == pygame.K_f:
                    simulation_speed, pause = "fast", False
                elif event.key == pygame.K_n:
                    simulation_speed, pause = "normal", False
                elif event.key == pygame.K_p:
                    pause = True
                elif event.key == pygame.K_ESCAPE:
                    running = False
                    _return_action = None
                elif event.key == pygame.K_m:
                    running = False
                    _return_action = "menu"
                elif event.key == pygame.K_r:
                    from battle import Battle
                    battle = Battle(_original_army1, _original_army2, _bf_w, _bf_h, _obstacle_count, map_name=_map_name)
                    grid_surface = build_grid_surface(battle, cell_size)
                    world_w = _bf_w * cell_size
                    world_h = _bf_h * cell_size
                    cam_x = max(0, (world_w - SCREEN_W) / 2)
                    cam_y = max(0, (world_h - (SCREEN_H - HUD_HEIGHT)) / 2)
                    clamp_camera()
                    winner = None
                    battle_report = None
                elif event.key == pygame.K_t:
                    show_lines = not show_lines
        
        # Déplacement caméra continu (touches maintenues)
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_q]:
            cam_x -= CAM_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            cam_x += CAM_SPEED
        if keys[pygame.K_UP] or keys[pygame.K_z]:
            cam_y -= CAM_SPEED
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            cam_y += CAM_SPEED
        
        # Edge scroll (souris au bord de l'écran)
        mx, my = pygame.mouse.get_pos()
        if mx < EDGE_SCROLL_MARGIN:
            cam_x -= CAM_SPEED
        elif mx > SCREEN_W - EDGE_SCROLL_MARGIN:
            cam_x += CAM_SPEED
        if my < EDGE_SCROLL_MARGIN:
            cam_y -= CAM_SPEED
        elif my > SCREEN_H - HUD_HEIGHT - EDGE_SCROLL_MARGIN:
            cam_y += CAM_SPEED
        
        clamp_camera()
        
        if not pause and winner is None:
            delay = 150 if simulation_speed == "fast" else 800
            if now - last_round >= delay:
                battle.simulate_round(cell_size)
                last_round = now
                # Rafraîchir la grille si siège (portes détruites)
                if battle.map_name == "Siège":
                    grid_surface = build_grid_surface(battle, cell_size)
                result = battle.is_battle_over()
                if result:
                    winner = result
                    battle_report = battle.get_battle_report()
        
        # Vieillir effets visuels
        for p in battle.visual_effects['projectiles'][:]:
            p.age += 1
            if p.age >= p.duration:
                battle.visual_effects['projectiles'].remove(p)
        
        for l in battle.visual_effects['attack_lines'][:]:
            l.age += 1
            if l.age >= l.duration:
                battle.visual_effects['attack_lines'].remove(l)
        
        # Effets de sorts
        for key in ['aoe_explosions', 'heal_beams', 'armor_shimmers', 'wall_effects']:
            for fx in battle.visual_effects.get(key, [])[:]:
                fx.age += 1
                if not fx.is_alive():
                    battle.visual_effects[key].remove(fx)
        
        screen.fill((25, 40, 30))
        
        # Camera offset pour le rendu monde
        ox = int(-cam_x)
        oy = int(-cam_y)
        
        # Clipper le rendu monde pour ne pas déborder sur le HUD
        view_h = SCREEN_H - HUD_HEIGHT
        screen.set_clip(pygame.Rect(0, 0, SCREEN_W, view_h))
        
        screen.blit(grid_surface, (ox, oy))
        
        # Ligne centrale
        center_x = bf_w // 2 * cell_size + ox
        view_h = SCREEN_H - HUD_HEIGHT
        pygame.draw.line(screen, (60, 60, 60), (center_x, 0), (center_x, view_h), 1)
        
        # Lignes de ciblage (couleur selon type d'attaque)
        if show_lines:
            for att, tgt in battle.visual_effects['target_indicators']:
                if att.is_alive and tgt.is_alive:
                    sp = (att.position[0] * cell_size + cell_size // 2 + ox,
                          att.position[1] * cell_size + cell_size // 2 + oy)
                    ep = (tgt.position[0] * cell_size + cell_size // 2 + ox,
                          tgt.position[1] * cell_size + cell_size // 2 + oy)
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
            sp = (line.start_pos[0] + ox, line.start_pos[1] + oy)
            ep = (line.end_pos[0] + ox, line.end_pos[1] + oy)
            pygame.draw.line(screen, color, sp, ep, max(1, int(3 * t)))
        
        # Projectiles
        for proj in battle.visual_effects['projectiles']:
            draw_projectile(screen, proj, ox, oy)
        
        # Explosions AoE (boule de feu)
        for aoe in battle.visual_effects.get('aoe_explosions', []):
            alpha = aoe.get_alpha()
            r_px = aoe.get_current_radius()
            if r_px > 0 and alpha > 10:
                surf = pygame.Surface((r_px * 2, r_px * 2), pygame.SRCALPHA)
                # Cercle extérieur orange
                pygame.draw.circle(surf, (*aoe.color, min(alpha, 150)),
                                   (r_px, r_px), r_px)
                # Cercle intérieur jaune
                inner_r = max(1, r_px // 2)
                pygame.draw.circle(surf, (255, 220, 50, min(alpha, 200)),
                                   (r_px, r_px), inner_r)
                screen.blit(surf, (aoe.center_pos[0] - r_px + ox, aoe.center_pos[1] - r_px + oy))
        
        # Rayons de soin
        for beam in battle.visual_effects.get('heal_beams', []):
            alpha = beam.get_alpha()
            if alpha > 10:
                t = alpha / 255
                # Ligne verte épaisse + scintillements
                c = (int(50 * t), int(255 * t), int(100 * t))
                sp = (beam.start_pos[0] + ox, beam.start_pos[1] + oy)
                ep = (beam.end_pos[0] + ox, beam.end_pos[1] + oy)
                pygame.draw.line(screen, c, sp, ep, max(2, int(4 * t)))
                # Croix verte au point d'arrivée
                ex, ey = ep
                s = max(3, int(8 * t))
                pygame.draw.line(screen, c, (ex - s, ey), (ex + s, ey), 2)
                pygame.draw.line(screen, c, (ex, ey - s), (ex, ey + s), 2)
        
        # Scintillements d'armure
        for shim in battle.visual_effects.get('armor_shimmers', []):
            alpha = shim.get_alpha()
            if alpha > 10:
                r_px = shim.radius_px + 4
                surf = pygame.Surface((r_px * 2, r_px * 2), pygame.SRCALPHA)
                # Anneau bleu qui pulse
                pygame.draw.circle(surf, (80, 180, 255, min(alpha, 120)),
                                   (r_px, r_px), r_px, max(2, r_px // 4))
                screen.blit(surf, (shim.center_pos[0] - r_px + ox, shim.center_pos[1] - r_px + oy))
        
        # Effets de mur
        for wall in battle.visual_effects.get('wall_effects', []):
            alpha = wall.get_alpha()
            if alpha > 10:
                for wx, wy in wall.positions:
                    px = wx * cell_size + ox
                    py = wy * cell_size + oy
                    surf = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
                    surf.fill((160, 80, 220, min(alpha, 180)))
                    screen.blit(surf, (px, py))
                    pygame.draw.rect(screen, (200, 120, 255),
                                     (px, py, cell_size, cell_size), 2)
        
        # Unités
        ur_base = max(3, cell_size // 2 - 4)
        tick_time = pygame.time.get_ticks()
        pulse = (tick_time // 200) % 4
        army1_set = set(id(u) for u in battle.army1)
        drawn_ids = set()  # Éviter de dessiner 2 fois les grosses unités
        
        for u in battle.army1 + battle.army2:
            if u.position is None or id(u) in drawn_ids:
                continue
            drawn_ids.add(id(u))
            
            x, y = u.position
            # Dimensions en cases selon la taille
            if u.size <= 1:
                uw, uh = 1, 1
            elif u.size == 2:
                uw, uh = 2, 2
            else:
                uw, uh = 2, 4
            
            # Centre pixel de l'unité (milieu de son bloc de cases)
            cx = x * cell_size + (uw * cell_size) // 2 + ox
            cy = y * cell_size + (uh * cell_size) // 2 + oy
            # Rayon adapté à la taille
            ur = max(3, min(uw, uh) * cell_size // 2 - 4)
            
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
            token_size = min(uw, uh) * cell_size - 4
            is_army1 = id(u) in army1_set
            team_color = (60, 120, 220) if is_army1 else (220, 60, 60)
            
            if u.is_alive:
                if u.fleeing:
                    pygame.draw.circle(screen, (255, 140, 0), (cx, cy), ur)
                else:
                    token_img = load_token(u.token_name, token_size) if u.token_name else None
                    if token_img:
                        screen.blit(token_img, (cx - token_size // 2, cy - token_size // 2))
                    else:
                        pygame.draw.circle(screen, u.color, (cx, cy), ur)
                        dot_r = max(1, 3 * cell_size // 32)
                        rc = (255, 255, 255) if u.role == "front" else (128, 128, 128) if u.role == "mid" else (0, 0, 0)
                        pygame.draw.circle(screen, rc, (cx, cy), dot_r)
                # Contour d'équipe PAR-DESSUS (outline épaisse)
                ring_r = ur + 2
                ring_w = max(2, cell_size // 8)
                pygame.draw.circle(screen, team_color, (cx, cy), ring_r, ring_w)
            else:
                pygame.draw.circle(screen, (60, 60, 60), (cx, cy), max(1, ur - 2), 2)
                ring_w = max(2, cell_size // 8)
                pygame.draw.circle(screen, team_color, (cx, cy), ur + 2, ring_w)
            
            # Barre HP (largeur adaptée à la taille)
            bw = max(4, uw * cell_size - 8)
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
                ft_oy = -ur - 6
                for ft in list(u.floating_texts):
                    ft.age += 1
                    if ft.age > ft.duration:
                        u.floating_texts.remove(ft)
                        continue
                    alpha = 255 - int(255 * (ft.age / ft.duration))
                    ts = tiny_font.render(ft.text, True, ft.color)
                    ts.set_alpha(alpha)
                    screen.blit(ts, (cx - ts.get_width() // 2, cy + ft_oy - ft.age // 4))
                    ft_oy -= 10
        
        # HUD (position fixe en bas de l'écran)
        screen.set_clip(None)  # Retirer le clip pour le HUD
        view_h = SCREEN_H - HUD_HEIGHT
        pygame.draw.rect(screen, (20, 25, 30), (0, view_h, SCREEN_W, HUD_HEIGHT))
        hy = view_h + 5
        a1c = sum(1 for u in battle.army1 if u.is_alive)
        a2c = sum(1 for u in battle.army2 if u.is_alive)
        a1f = len(battle.army1_fled) + sum(1 for u in battle.army1 if u.fleeing and u.is_alive)
        a2f = len(battle.army2_fled) + sum(1 for u in battle.army2 if u.fleeing and u.is_alive)
        
        status = "VICTOIRE: " + winner if winner else ("PAUSE" if pause else ("RAPIDE" if simulation_speed == "fast" else "NORMAL"))
        color = (255, 215, 0) if winner else ((255, 100, 100) if pause else ((255, 220, 80) if simulation_speed == "fast" else (100, 220, 100)))
        hud = small_font.render(f"Round {battle.round - 1} | {status} | A1: {a1c} vivants {a1f} fuyants | A2: {a2c} vivants {a2f} fuyants", True, color)
        screen.blit(hud, (10, hy))
        
        # Rapport de bataille (overlay)
        if battle_report:
            draw_battle_report(screen, battle_report, SCREEN_W, view_h, small_font, tiny_font)
        
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
        
        lx2 = lx + 160
        pygame.draw.line(screen, (220, 80, 80), (lx2, ly + 1), (lx2 + 8, ly + 9), 2)
        pygame.draw.line(screen, (220, 80, 80), (lx2 + 8, ly + 1), (lx2, ly + 9), 2)
        screen.blit(tiny_font.render("CaC", True, (180, 180, 180)), (lx2 + 12, ly))
        
        lx3 = lx2 + 45
        pygame.draw.line(screen, (255, 200, 50), (lx3 + 4, ly + 9), (lx3 + 4, ly + 1), 2)
        pygame.draw.line(screen, (255, 200, 50), (lx3 + 4, ly + 1), (lx3 + 2, ly + 4), 2)
        pygame.draw.line(screen, (255, 200, 50), (lx3 + 4, ly + 1), (lx3 + 6, ly + 4), 2)
        screen.blit(tiny_font.render("Portée", True, (180, 180, 180)), (lx3 + 12, ly))
        
        lx4 = lx3 + 60
        pygame.draw.line(screen, (80, 160, 255), (lx4, ly + 5), (lx4 + 8, ly + 5), 2)
        pygame.draw.line(screen, (80, 160, 255), (lx4 + 8, ly + 5), (lx4 + 5, ly + 2), 2)
        pygame.draw.line(screen, (80, 160, 255), (lx4 + 8, ly + 5), (lx4 + 5, ly + 8), 2)
        screen.blit(tiny_font.render("Tir", True, (180, 180, 180)), (lx4 + 12, ly))
        
        lx5 = lx4 + 40
        sc = lx5 + 4
        pygame.draw.line(screen, (180, 80, 255), (sc, ly + 1), (sc, ly + 9), 2)
        pygame.draw.line(screen, (180, 80, 255), (sc - 4, ly + 5), (sc + 4, ly + 5), 2)
        pygame.draw.line(screen, (180, 80, 255), (sc - 3, ly + 2), (sc + 3, ly + 8), 1)
        pygame.draw.line(screen, (180, 80, 255), (sc + 3, ly + 2), (sc - 3, ly + 8), 1)
        screen.blit(tiny_font.render("Sort", True, (180, 180, 180)), (lx5 + 12, ly))
        
        # Contrôles
        ctrl = tiny_font.render("ESPACE=Pause  ZQSD/Flèches=Caméra  F=Vite  N=Normal  R=Reset  T=Lignes  M=Menu  ESC=Quit", True, (150, 170, 200))
        screen.blit(ctrl, (10, ly + 18))
        
        size = tiny_font.render(f"Grille {bf_w}x{bf_h} | Cell {cell_size}px | FPS: {int(clock.get_fps())}", True, (120, 120, 120))
        screen.blit(size, (SCREEN_W - size.get_width() - 10, ly + 18))
        
        pygame.display.flip()
        clock.tick(60)
    
    return _return_action