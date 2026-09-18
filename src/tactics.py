"""
Boîte à outils tactique — mathématiques de combat, cartes de menace et
anticipation. Partagée par le moteur de bataille et les commandants IA.

Pourquoi un module dédié: l'IA prenait ses décisions sur des heuristiques
grossières ("le plus proche", "le plus blessé"). Ici on lui donne de quoi
RAISONNER: combien de dégâts j'espère infliger, ai-je une chance de tuer
cette cible CE round, quelle case est dangereuse, où sera l'ennemi au
prochain round.
"""
import math

import combat
import terrain

# ── Dés: probabilités de base (tout se joue au d6, cf. combat.py) ──

p_d6_ge = combat.p_ge


def _avg_roll(arme):
    """Dégâts moyens d'un jet de l'arme."""
    return arme.dice.average


def expected_damage(attacker, target, dist=None, battlefield=None):
    """Dégâts moyens espérés en UN round de l'attaquant sur la cible.
    dist=None → on suppose l'attaquant à portée de toutes ses armes.
    Mêmes seuils que le moteur: combat.attack_profile."""
    if not attacker.is_alive or attacker.fleeing:
        return 0.0
    total = 0.0
    for arme in attacker.armes:
        if dist is not None:
            reach = (terrain.weapon_reach(battlefield, arme, attacker, target)
                     if battlefield is not None else arme.porte)
            if dist > reach:
                continue
        total += combat.attack_profile(attacker, target, arme, battlefield).expected_damage()
    for sp in attacker.spells:
        if sp.spell_type in ("fireball", "projectile"):
            if dist is not None and dist > sp.porte:
                continue
            total += 3.0
    return total


def kill_chance(expected_dmg, target):
    """Probabilité approximative d'abattre la cible ce round.
    Modèle simple mais monotone: rapport dégâts espérés / PV restants,
    écrasé pour éviter les certitudes abusives."""
    hp = max(1, target.hp)
    ratio = expected_dmg / hp
    if ratio <= 0:
        return 0.0
    if ratio < 1.0:
        return min(1.0, ratio ** 1.35)
    return min(1.0, 0.75 + 0.25 * min(1.0, ratio - 1.0))


# ── Valeur d'une unité (ce qu'on perd en la perdant) ──


def unit_value(u):
    """Valeur tactique d'une unité: capacité de nuisance + robustesse.
    Sert à comparer des échanges (vaut-il le coup de perdre X pour tuer Y)."""
    offense = sum(_avg_roll(a) * a.nb_attaque * p_d6_ge(a.toucher) for a in u.armes)
    offense += 4.0 * len(u.spells)
    toughness = u.max_hp * (0.6 + 0.4 * (1.0 - p_d6_ge(min(7, u.sauvegarde))))
    utility = 0.0
    if u.encouragement_range > 0:
        utility += 6.0
    if any(s.spell_type == "heal" for s in u.spells):
        utility += 6.0
    return offense * 1.4 + toughness * 0.5 + utility


def remaining_value(u):
    """Valeur restante (proportionnelle aux PV): une unité à 10% de PV
    ne vaut plus grand-chose — inutile de la protéger comme un trésor."""
    return unit_value(u) * (0.35 + 0.65 * max(0.0, u.hp / max(1, u.max_hp)))


# ── Carte de menace (influence map paresseuse) ──


class ThreatField:
    """Menace ennemie ressentie sur une case donnée.

    Calcul à la demande + cache: sur une grande carte, calculer toute la
    grille chaque round coûterait bien trop cher pour ce qu'on en utilise
    (quelques dizaines de cases candidates).
    """

    __slots__ = ['enemies', 'battlefield', '_cache', '_melee', '_ranged', '_fires']

    FIRE_THREAT = 1.5          # case en feu
    FIRE_NEAR_THREAT = 0.5     # case voisine d'un foyer (chaleur, effondrement)

    def __init__(self, enemies, battlefield):
        self.battlefield = battlefield
        self.enemies = [e for e in enemies if e.is_alive and not e.fleeing]
        self._cache = {}
        self._melee = []
        self._ranged = []
        self._fires = getattr(battlefield, 'fires', None) or {}
        for e in self.enemies:
            mp = sum(_avg_roll(a) * a.nb_attaque * p_d6_ge(a.toucher)
                     for a in e.armes if a.porte < 4)
            rp = sum(_avg_roll(a) * a.nb_attaque * p_d6_ge(a.toucher)
                     for a in e.armes if a.porte >= 4)
            rp += 3.0 * sum(1 for s in e.spells
                            if s.spell_type in ("fireball", "projectile"))
            if mp > 0:
                # Allonge de menace: ce que l'unité peut atteindre en un round
                self._melee.append((e.position, mp, e.vitesse + e._max_range))
            if rp > 0:
                span = max(e._max_range,
                           max((s.porte for s in e.spells), default=0))
                self._ranged.append((e.position, rp, span))

    def at(self, pos):
        """Menace totale subie sur cette case (0 = sûr)."""
        v = self._cache.get(pos)
        if v is not None:
            return v
        px, py = pos
        total = 0.0
        for (ex, ey), power, reach in self._melee:
            d = abs(ex - px) + abs(ey - py)
            if d <= reach:
                total += power * (1.0 - 0.5 * d / max(1, reach))
            elif d <= reach * 2:
                total += power * 0.15  # Menace du round suivant
        for (ex, ey), power, span in self._ranged:
            d = abs(ex - px) + abs(ey - py)
            if d <= span:
                total += power * (0.55 + 0.45 * (1.0 - d / max(1, span)))
        fires = self._fires
        if fires:
            if pos in fires:
                total += self.FIRE_THREAT
            elif any((px + dx, py + dy) in fires for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                total += self.FIRE_NEAR_THREAT
        self._cache[pos] = total
        return total

    def safest(self, candidates, prefer=None, weight=1.0):
        """Choisit parmi des cases celle qui minimise la menace, avec un
        bonus optionnel pour la proximité d'un point souhaité."""
        best, best_score = None, None
        for c in candidates:
            score = self.at(c) * weight
            if prefer is not None:
                score += 0.8 * (abs(c[0] - prefer[0]) + abs(c[1] - prefer[1]))
            if best_score is None or score < best_score:
                best, best_score = c, score
        return best


# ── Anticipation ──


# ─── Symétrie gauche/droite ───
# La carte est un miroir (x → largeur-1-x) et les armées s'y déploient en
# reflet. Tout arrondi ou départage sur l'axe x doit donc se comporter en
# miroir, sinon un camp gagne une case d'avance à chaque égalité.

def mirror_round_x(x, width):
    """Arrondi d'une abscisse cohérent avec le miroir: les demis vont vers
    le centre de la carte (round() de Python arrondit au pair: 10,5 → 10 à
    l'ouest mais 28,5 → 28 à l'est, au lieu de 29)."""
    c = (width - 1) / 2.0
    return int(math.floor(x + 0.5)) if x < c else int(math.ceil(x - 0.5))


def mirror_sign(x, width):
    """+1 dans la moitié ouest, -1 dans la moitié est: multiplie un écart
    en x pour que « vers l'arrière de son camp » se départage pareil des
    deux côtés."""
    return 1 if x < (width - 1) / 2.0 else -1


def predicted_position(unit, steps=1, clamp=None):
    """Extrapole où sera l'unité dans `steps` round(s) d'après son
    déplacement du round précédent. Permet d'INTERCEPTER au lieu de
    courir derrière (la cavalerie n'arrivait jamais sur les tireurs)."""
    cx, cy = unit.position
    dx, dy = getattr(unit, '_last_step', (0, 0))
    nx = cx + dx * steps
    ny = cy + dy * steps
    if clamp is not None:
        w, h = clamp
        nx = max(0, min(w - 1, nx))
        ny = max(0, min(h - 1, ny))
    return (int(nx), int(ny))


def intercept_point(hunter, prey, clamp=None):
    """Point de rencontre estimé: on vise là où la proie SERA quand on
    pourra l'atteindre, pas là où elle est maintenant."""
    hx, hy = hunter.position
    px, py = prey.position
    dist = abs(hx - px) + abs(hy - py)
    speed = max(1, hunter.vitesse)
    # Deux rounds au plus, et un pas plafonné à la vitesse de la proie:
    # extrapoler sur 4 rounds le dernier bond d'une proie rapide (cavalier
    # à javelots, 12 cases avec l'élan) envoyait le chasseur à 30 cases,
    # au bord de la carte — des courses à vide qui ne se compensaient pas
    # d'un camp à l'autre (camp gauche 62 % en forêt, armées égales).
    turns = max(1, min(2, int(math.ceil(dist / speed))))
    dx, dy = getattr(prey, '_last_step', (0, 0))
    cap = max(1, prey.vitesse)
    dx, dy = max(-cap, min(cap, dx)), max(-cap, min(cap, dy))
    nx, ny = px + dx * turns, py + dy * turns
    if clamp is not None:
        nx = max(0, min(clamp[0] - 1, nx))
        ny = max(0, min(clamp[1] - 1, ny))
    return (int(nx), int(ny))


# ── Lecture de situation ──


def support_count(pos, units, radius=4, exclude=None):
    """Nombre d'unités amies capables d'épauler cette position."""
    n = 0
    for u in units:
        if not u.is_alive or u.fleeing or u is exclude:
            continue
        if abs(u.position[0] - pos[0]) + abs(u.position[1] - pos[1]) <= radius:
            n += 1
    return n


def is_isolated(enemy, enemy_army, radius=5, max_support=1):
    """Un ennemi coupé de ses soutiens = une occasion de le détruire à bon
    compte. C'est la base de la défaite en détail."""
    return support_count(enemy.position, enemy_army, radius, exclude=enemy) <= max_support


def engagement_ratio(pos, allies, enemies, radius=6):
    """Rapport de forces LOCAL autour d'une position (>1 = on domine)."""
    mine = sum(remaining_value(u) for u in allies
               if u.is_alive and not u.fleeing
               and abs(u.position[0] - pos[0]) + abs(u.position[1] - pos[1]) <= radius)
    theirs = sum(remaining_value(e) for e in enemies
                 if e.is_alive and not e.fleeing
                 and abs(e.position[0] - pos[0]) + abs(e.position[1] - pos[1]) <= radius)
    if theirs <= 0.01:
        return 99.0 if mine > 0 else 1.0
    return mine / theirs
