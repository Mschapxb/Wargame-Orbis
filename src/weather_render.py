"""Rendu de la météo (weather.py): un calque en coordonnées ÉCRAN, posé
après le monde et avant le vignettage.

    Pluie       traînées obliques qui tombent, voile bleuté
    Brouillard  voile laiteux et bancs de brume qui dérivent
    Vent        poussière et brins emportés dans le sens du vent
    Crépuscule  teinte ambrée et bords assombris
    Chaleur     teinte dorée, air qui tremble par bandes

Budget: quelques centaines de traits et une poignée de blits alpha par
image; les surfaces pleines sont mises en cache par taille d'écran. La
pause fige tout (l'horloge n'avance qu'avec update()).
"""
import math
import random

import pygame

import sprites as S
import weather as W

_RAIN_DROPS = 260
_WIND_MOTES = 90
_FOG_BANKS = 9


class WeatherFx:
    def __init__(self, weather):
        self.weather = weather or W.Weather()
        self.rng = random.Random(1234)   # jamais le random du moteur
        self.t = 0
        self._size = None
        self._drops = []
        self._motes = []
        self._banks = []
        self._tints = {}

    # ─── état ───

    def _init_for(self, w, h):
        rng = self.rng
        self._size = (w, h)
        self._drops = [[rng.uniform(0, w), rng.uniform(0, h), rng.uniform(9, 16),
                        rng.uniform(0.6, 1.0)] for _ in range(_RAIN_DROPS)]
        self._motes = [[rng.uniform(0, w), rng.uniform(0, h), rng.uniform(2.5, 5.5),
                        rng.uniform(0, math.tau), rng.random() < 0.3]
                       for _ in range(_WIND_MOTES)]
        self._banks = [[rng.uniform(-200, w + 200), rng.uniform(0, h),
                        rng.uniform(160, 340), rng.uniform(0.15, 0.4)]
                       for _ in range(_FOG_BANKS)]
        self._tints = {}

    def update(self, paused=False):
        if paused or self._size is None:
            return
        self.t += 1
        w, h = self._size
        name = self.weather.name
        if name == W.RAIN:
            for d in self._drops:
                d[0] -= d[2] * 0.22
                d[1] += d[2]
                if d[1] > h:
                    d[0] = self.rng.uniform(0, w + 40)
                    d[1] = self.rng.uniform(-30, 0)
                elif d[0] < -20:
                    d[0] += w + 40
        elif name == W.WIND:
            sgn = self.weather.wind or 1
            for m in self._motes:
                m[0] += sgn * m[2]
                m[1] += math.sin(self.t * 0.05 + m[3]) * 0.6
                if sgn > 0 and m[0] > w + 10:
                    m[0] = -10
                    m[1] = self.rng.uniform(0, h)
                elif sgn < 0 and m[0] < -10:
                    m[0] = w + 10
                    m[1] = self.rng.uniform(0, h)
        elif name == W.FOG:
            for b in self._banks:
                b[0] += b[3]
                if b[0] - b[2] > w:
                    b[0] = -b[2]
                    b[1] = self.rng.uniform(0, h)

    # ─── dessin ───

    def _tint(self, w, h, color, alpha):
        k = (w, h, color, alpha)
        s = self._tints.get(k)
        if s is None:
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            s.fill(color + (alpha,))
            self._tints[k] = s
        return s

    def draw(self, screen, w, h):
        name = self.weather.name
        if name == W.CLEAR:
            return
        if self._size != (w, h):
            self._init_for(w, h)
        if name == W.RAIN:
            screen.blit(self._tint(w, h, (40, 60, 90), 38), (0, 0))
            col = (170, 190, 215)
            for x, y, v, a in self._drops:
                c = tuple(int(ch * a) for ch in col)
                pygame.draw.line(screen, c, (x, y), (x + v * 0.22, y - v), 1)
        elif name == W.FOG:
            screen.blit(self._tint(w, h, (205, 210, 215), 70), (0, 0))
            for x, y, r, _ in self._banks:
                blob = S.soft_blob(int(r), (225, 228, 232), 110)
                screen.blit(blob, (x - r, y - r))
        elif name == W.WIND:
            for x, y, sz, ph, leaf in self._motes:
                if leaf:
                    c = (120, 140, 60)
                    ang = self.t * 0.2 + ph
                    dx, dy = math.cos(ang) * sz, math.sin(ang) * sz * 0.5
                    pygame.draw.line(screen, c, (x - dx, y - dy), (x + dx, y + dy), 2)
                else:
                    pygame.draw.line(screen, (205, 195, 170),
                                     (x, y), (x - (self.weather.wind or 1) * sz * 3, y), 1)
        elif name == W.DUSK:
            # Un seul voile (ambre sur violet sombre, pré-mélangés): un blit
            # plein écran de moins par image
            screen.blit(self._tint(w, h, (78, 38, 36), 84), (0, 0))
        elif name == W.HEAT:
            screen.blit(self._tint(w, h, (255, 200, 90), 26), (0, 0))
            band = self._tint(w, 3, (255, 240, 200), 16)
            for i in range(0, h, 24):
                off = int(math.sin(self.t * 0.07 + i * 0.13) * 4)
                screen.blit(band, (off, i))


def label(weather):
    """Libellé court pour le bandeau (None si ciel clair)."""
    if weather is None or weather.name == W.CLEAR:
        return None
    return weather.label
