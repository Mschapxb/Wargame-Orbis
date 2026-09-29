"""Briques d'interface de l'écran de bataille: barre d'outils à icônes,
infobulles, notifications, panneaux (aide, options, menu), cases à cocher.

Mode immédiat, comme le reste de l'interface: chaque image redessine tout
et note ses zones cliquables dans un `Clicks`. Le clic suivant est rendu à
la zone qu'il touche; une zone d'interface « bloque » aussi la souris pour
le monde (pas de défilement au bord ni de glisser sous un bouton).
"""
import pygame

import icons
import theme as T

# Couleurs de l'interface (thème ardoise et or)
ICON = (232, 224, 204)
ICON_DIM = (150, 144, 130)
ACTIVE_FILL = (184, 142, 64)
HOVER_FILL = (70, 76, 92)
BUTTON_FILL = (34, 37, 46)


class Clicks:
    """Zones cliquables de l'image en cours: (rect, action, infobulle)."""

    def __init__(self):
        self.zones = []

    def add(self, rect, action=None, tooltip=None):
        self.zones.append((pygame.Rect(rect), action, tooltip))

    def at(self, pos):
        """La zone la plus haute (dernière dessinée) sous `pos`, ou None."""
        for zone in reversed(self.zones):
            if zone[0].collidepoint(pos):
                return zone
        return None


# ─── Boutons ───

def icon_button(surf, clicks, rect, name, mouse, action, tooltip=None, active=False,
                enabled=True, accent=None, size=None):
    """Bouton carré à icône. `active`: bascule enclenchée (fond doré)."""
    rect = pygame.Rect(rect)
    hovered = enabled and rect.collidepoint(mouse)
    if active:
        fill = T.lighten(ACTIVE_FILL, 0.12) if hovered else ACTIVE_FILL
    elif hovered:
        fill = HOVER_FILL
    else:
        fill = BUTTON_FILL
    surf.blit(T.rounded_gradient(rect.w, rect.h, T.lighten(fill, 0.1), T.darken(fill, 0.15),
                                 7), rect.topleft)
    edge = T.GOLD if active else (T.lighten(fill, 0.25) if hovered else T.darken(fill, 0.4))
    pygame.draw.rect(surf, edge, rect, 1, border_radius=7)
    color = (32, 24, 12) if active else (accent or (ICON if enabled else ICON_DIM))
    img = icons.icon(name, size or int(rect.h * 0.62), color)
    surf.blit(img, img.get_rect(center=rect.center))
    clicks.add(rect, action if enabled else None, tooltip)
    return hovered


def text_button(surf, clicks, rect, label, fnt, mouse, action, icon_name=None, primary=False,
                danger=False, enabled=True):
    """Bouton à libellé (et icône facultative), au thème commun."""
    rect = pygame.Rect(rect)
    base = T.BTN_GOLD if primary else T.BTN_RED if danger else T.BTN
    hovered = T.button(surf, rect, "", fnt, mouse, base=base, enabled=enabled)
    color = (32, 24, 12) if primary else (T.PARCHMENT if enabled else T.MUTED)
    img = fnt.render(label, True, color)
    w = img.get_width() + (22 if icon_name else 0)
    x = rect.centerx - w // 2
    if icon_name:
        ic = icons.icon(icon_name, 16, color)
        surf.blit(ic, (x, rect.centery - 8))
        x += 22
    surf.blit(img, (x, rect.centery - img.get_height() // 2))
    clicks.add(rect, action if enabled else None, None)
    return hovered


def keycap(surf, label, fnt, x, y):
    """Touche de clavier dessinée: [Espace]. Retourne sa largeur."""
    img = fnt.render(label, True, T.PARCHMENT)
    w = max(22, img.get_width() + 12)
    h = img.get_height() + 4
    surf.blit(T.rounded_gradient(w, h, (62, 66, 80), (38, 41, 50), 4), (x, y))
    pygame.draw.rect(surf, (20, 21, 26), (x, y, w, h), 1, border_radius=4)
    pygame.draw.line(surf, (96, 100, 116), (x + 3, y + 1), (x + w - 4, y + 1))
    surf.blit(img, (x + (w - img.get_width()) // 2, y + 2))
    return w


def checkbox(surf, clicks, x, y, label, value, fnt, mouse, action):
    """Case à cocher + libellé, entièrement cliquables. Retourne la largeur."""
    img = fnt.render(label, True, T.PARCHMENT if value else T.PARCHMENT_DIM)
    rect = pygame.Rect(x, y, 22 + 8 + img.get_width(), 22)
    hovered = rect.collidepoint(mouse)
    box = pygame.Rect(x, y, 22, 22)
    fill = ACTIVE_FILL if value else (HOVER_FILL if hovered else BUTTON_FILL)
    surf.blit(T.rounded_gradient(22, 22, T.lighten(fill, 0.1), T.darken(fill, 0.15), 5), box)
    pygame.draw.rect(surf, T.GOLD if value else T.darken(T.GOLD_DIM, 0.2), box, 1, border_radius=5)
    if value:
        surf.blit(icons.icon("check", 18, (32, 24, 12)), (x + 2, y + 2))
    surf.blit(img, (x + 30, y + (22 - img.get_height()) // 2))
    clicks.add(rect, action)
    return rect.w


def choice(surf, clicks, x, y, options, selected, fnt, mouse, on_pick):
    """Boutons segmentés (un seul choisi). options: [(valeur, libellé)].
    Retourne la largeur totale."""
    x0 = x
    for value, label in options:
        img = fnt.render(label, True, (32, 24, 12) if value == selected else T.PARCHMENT)
        rect = pygame.Rect(x, y, img.get_width() + 20, 24)
        hovered = rect.collidepoint(mouse)
        if value == selected:
            fill = ACTIVE_FILL
        else:
            fill = HOVER_FILL if hovered else BUTTON_FILL
        surf.blit(T.rounded_gradient(rect.w, rect.h, T.lighten(fill, 0.1), T.darken(fill, 0.15),
                                     5), rect)
        pygame.draw.rect(surf, T.GOLD if value == selected else T.darken(fill, 0.4), rect, 1,
                         border_radius=5)
        surf.blit(img, (rect.x + 10, rect.y + (rect.h - img.get_height()) // 2))
        clicks.add(rect, (lambda v=value: on_pick(v)))
        x += rect.w + 4
    return x - x0


# ─── Barre d'outils ───

def toolbar(surf, clicks, groups, center_x, bottom_y, mouse, button=34, gap=4, group_gap=14):
    """Barre d'outils flottante: `groups` = [[(icône, action, infobulle,
    active), ...], ...], séparés par un filet. Retourne son rect."""
    n = sum(len(g) for g in groups)
    width = n * button + (n - len(groups)) * gap + (len(groups) - 1) * group_gap + 16
    rect = pygame.Rect(center_x - width // 2, bottom_y - button - 12, width, button + 12)
    shadow = T.soft_shadow(rect.w, rect.h, 10, 10, 140)
    surf.blit(shadow, (rect.x - 10, rect.y - 6))
    T.glass(surf, rect, 225, 10)
    clicks.add(rect)                       # la barre entière bloque le monde
    x = rect.x + 8
    for gi, group in enumerate(groups):
        if gi:
            sep_x = x - group_gap // 2 - gap // 2
            pygame.draw.line(surf, T.darken(T.GOLD_DIM, 0.3), (sep_x, rect.y + 9),
                             (sep_x, rect.bottom - 9))
        for name, action, tip, active in group:
            icon_button(surf, clicks, (x, rect.y + 6, button, button), name, mouse, action,
                        tip, active=active)
            x += button + gap
        x += group_gap - gap
    return rect


class Tooltip:
    """Infobulle qui apparaît après un court survol immobile."""
    DELAY_MS = 350

    def __init__(self):
        self._text = None
        self._since = 0

    def draw(self, surf, zone, now, fnt, bounds):
        text = zone[2] if zone is not None else None
        if text != self._text:
            self._text, self._since = text, now
        if not text or now - self._since < self.DELAY_MS:
            return
        rect = zone[0]
        img = fnt.render(text, True, T.PARCHMENT)
        tip = pygame.Rect(0, 0, img.get_width() + 18, img.get_height() + 10)
        tip.midbottom = (rect.centerx, rect.top - 6)
        tip.clamp_ip(bounds)
        T.glass(surf, tip, 240, 6, T.GOLD_DIM)
        surf.blit(img, (tip.x + 9, tip.y + 5))


# ─── Notifications ───

class Toasts:
    """Petites notifications empilées en bas à droite. Une notification à
    clé (`key`) remplace la précédente de même clé (progression)."""

    def __init__(self):
        self.items = []

    def add(self, text, color=T.GOLD, seconds=4.0, action=None, key=None, sub=None,
            progress=None, now=None):
        now = pygame.time.get_ticks() if now is None else now
        if key is not None:
            self.items = [t for t in self.items if t.get('key') != key]
        self.items.append({'text': text, 'sub': sub, 'color': color, 'action': action,
                           'key': key, 'progress': progress,
                           'until': None if seconds is None else now + int(seconds * 1000)})

    def remove(self, key):
        self.items = [t for t in self.items if t.get('key') != key]

    def draw(self, surf, clicks, right, bottom, now, fonts, mouse):
        title_font, sub_font = fonts
        self.items = [t for t in self.items if t['until'] is None or t['until'] > now]
        y = bottom
        for t in reversed(self.items[-4:]):
            img = title_font.render(t['text'], True, T.PARCHMENT)
            sub = sub_font.render(t['sub'], True, T.PARCHMENT_DIM) if t['sub'] else None
            w = max(img.get_width(), sub.get_width() if sub else 0) + 40
            h = img.get_height() + (sub.get_height() + 2 if sub else 0) + 16
            if t['progress'] is not None:
                h += 10
            rect = pygame.Rect(right - w, y - h, w, h)
            fade = 1.0 if t['until'] is None else min(1.0, (t['until'] - now) / 400)
            hovered = t['action'] is not None and rect.collidepoint(mouse)
            T.glass(surf, rect, int(235 * fade), 8, T.GOLD if hovered else T.GOLD_DIM)
            pygame.draw.rect(surf, t['color'], (rect.x + 1, rect.y + 6, 4, rect.h - 12),
                             border_radius=2)
            surf.blit(img, (rect.x + 16, rect.y + 8))
            if sub:
                surf.blit(sub, (rect.x + 16, rect.y + 10 + img.get_height()))
            if t['progress'] is not None:
                T.bar(surf, (rect.x + 16, rect.bottom - 12, rect.w - 30, 5),
                      [(max(0.0, min(1.0, t['progress'])), t['color'])])
            clicks.add(rect, t['action'])
            y = rect.y - 8


# ─── Panneaux ───

def modal(surf, screen_rect, w, h, title, subtitle=None):
    """Voile sombre + panneau centré avec titre. Retourne (panneau, y du
    contenu)."""
    veil = pygame.Surface(screen_rect.size, pygame.SRCALPHA)
    veil.fill((6, 7, 9, 165))
    surf.blit(veil, screen_rect.topleft)
    rect = pygame.Rect(0, 0, min(w, screen_rect.w - 20), min(h, screen_rect.h - 20))
    rect.center = screen_rect.center
    T.panel(surf, rect)
    y = T.title(surf, title, rect.centerx, rect.y + 12, 26, subtitle)
    return rect, y + 6
