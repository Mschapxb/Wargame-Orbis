"""Simulation en tâche de fond: le round suivant se calcule pendant que
l'écran anime le précédent.

Simuler un round d'une grande bataille prend plusieurs centaines de
millisecondes. Fait dans la boucle d'affichage, entre deux images, cela
figeait l'écran à chaque round. Ici, deux mondes:

- la bataille VIVANTE, que seul le fil de simulation touche: il y joue les
  rounds l'un après l'autre;
- des INSTANTANÉS (copies profondes de la bataille vivante, un par round),
  que seul l'écran touche: il les anime, en vieillit les effets, en consomme
  les repeints.

Rien de mutable n'est partagé entre les deux fils: pas de verrou dans le
moteur, et la bataille jouée est exactement celle qu'aurait jouée
simulate_round() appelé à la main (même graine, mêmes rounds — l'écran ne
tire jamais dans le `random` global).

Ce que la simulation produit POUR L'ÉCRAN (effets visuels, textes flottants,
flash de dégâts, bond de mêlée) passe à l'instantané puis est effacé de la
bataille vivante: personne ne l'y vieillirait, et il resservirait à chaque
round. carry_over() raccorde ensuite deux instantanés successifs: ce qui
jouait encore à la fin d'un round continue au suivant.
"""
import copy
import pickle
import threading

import spatial

# Effets que l'écran fait vivre image après image et qui peuvent déborder
# sur le round suivant (les autres clés sont refaites à chaque round).
LASTING_EFFECTS = ('projectiles', 'attack_lines', 'aoe_explosions', 'heal_beams',
                   'armor_shimmers', 'wall_effects', 'impacts', 'shockwaves',
                   'slashes', 'thrusts', 'deaths')


# ═══════════════════════════════════════════════════════════════
#   INSTANTANÉ
# ═══════════════════════════════════════════════════════════════

def take_snapshot(battle):
    """Copie profonde de `battle` pour l'écran, puis remise à zéro, dans
    `battle`, de ce qui n'appartient qu'à l'affichage.

    À n'appeler que depuis le fil qui possède la bataille vivante."""
    # Les armées de relance ne changent jamais: partagées, pas copiées
    memo = {id(battle._restart_army1): battle._restart_army1,
            id(battle._restart_army2): battle._restart_army2}
    snap = copy.deepcopy(battle, memo)
    _fix_identities(battle, snap, memo)
    _hand_over(battle)
    return snap


def _all_units(battle):
    """Toutes les unités de la bataille (rôles, armées, grille), sans doublon."""
    seen = {}
    for army in (battle.army1_roster, battle.army2_roster, battle.army1, battle.army2,
                 list(battle.battlefield.units.values())):
        for u in army:
            seen.setdefault(id(u), u)
    return list(seen.values())


def _fix_identities(live, snap, memo):
    """Ce qui est indexé par id(unité) désigne encore les unités vivantes:
    recalé sur leurs copies (ou reconstruit)."""
    idmap = {}
    for u in _all_units(live):
        twin = memo.get(id(u))
        if twin is not None:
            idmap[id(u)] = id(twin)
    _reidentify(snap, idmap)


def _reidentify(snap, idmap):
    """Recale sur `idmap` (ancien id → nouvel id) tout ce qui est indexé par
    id(unité), et reconstruit ce qui peut l'être."""
    snap._army1_ids = snap._army2_ids = None
    snap._alive_cache['dirty'] = True
    snap._near_enemy_cache = None
    bf = snap.battlefield
    bf.index = spatial.UnitIndex()
    placed = set()
    for u in bf.units.values():
        if id(u) not in placed:
            placed.add(id(u))
            bf.index.add(u)
    _remap_ids(bf, idmap)
    for cmd in (snap.commander1, snap.commander2):
        cmd._ids_cache = [None, None]
        cmd._nd_cache = None
        _remap_ids(cmd, idmap)
        plan = getattr(cmd, 'plan', None)
        if plan is not None and hasattr(plan, '__dict__'):
            _remap_ids(plan, idmap)


def _remap_ids(obj, idmap):
    """Clés id(unité) des dicts et sets d'attributs de `obj` → id des copies
    (la fiche d'unité lit par exemple plan.roles[id(unité)])."""
    for name, val in list(vars(obj).items()):
        if isinstance(val, dict) and any(k in idmap for k in val if isinstance(k, int)):
            setattr(obj, name, {idmap.get(k, k) if isinstance(k, int) else k: v
                                for k, v in val.items()})
        elif isinstance(val, set) and any(k in idmap for k in val if isinstance(k, int)):
            setattr(obj, name, {idmap.get(k, k) if isinstance(k, int) else k for k in val})


def pack_battle(battle, rng_state):
    """Bataille (au repos, entre deux rounds) et état du hasard global → octets,
    pour la rejouer ailleurs à l'identique (cf. video_export). Les id() ne
    survivent pas au voyage: on emporte la correspondance uid → id."""
    ids = {u.uid: id(u) for u in _all_units(battle)}
    return pickle.dumps({'battle': battle, 'rng': rng_state, 'ids': ids},
                        protocol=pickle.HIGHEST_PROTOCOL)


def unpack_battle(data):
    """(bataille, état du hasard) depuis pack_battle, identités recalées."""
    kit = pickle.loads(data)
    battle = kit['battle']
    now = {u.uid: id(u) for u in _all_units(battle)}
    _reidentify(battle, {old: now[uid] for uid, old in kit['ids'].items() if uid in now})
    return battle, kit['rng']


def _hand_over(live):
    """Efface de la bataille vivante ce que l'instantané emporte pour
    l'écran. Rien de tout cela n'est relu par la simulation."""
    for lst in live.visual_effects.values():
        lst.clear()
    for army in (live.army1_roster, live.army2_roster):
        for u in army:
            u.floating_texts.clear()
            u._hit_flash = 0
            u._lunge_timer = 0


def carry_over(old, new):
    """Raccorde l'instantané `new` à `old`, que l'écran vient de finir
    d'animer: effets et textes encore en cours, flash et bond pas finis, et
    ce que l'écran a lui-même accroché à la bataille (couche de sol)."""
    for key in LASTING_EFFECTS:
        alive = [e for e in old.visual_effects.get(key, ()) if e.is_alive()]
        if alive:
            new.visual_effects[key] = alive + new.visual_effects.get(key, [])
    before = {u.uid: u for u in old.army1 + old.army2}
    for u in new.army1 + new.army2:
        prev = before.get(u.uid)
        if prev is None:
            continue
        texts = [ft for ft in prev.floating_texts if ft.is_alive()]
        if texts:
            texts.extend(u.floating_texts)
            u.floating_texts.clear()
            u.floating_texts.extend(texts)      # deque bornée: les plus récents
        # Un nouveau round remet les estampilles à zéro: ce qui restait
        # d'un flash ou d'un bond reprend aussitôt (cf. Unit.start_round)
        if u._hit_flash <= 0 < prev._hit_flash:
            u._hit_flash, u._hit_flash_delay = prev._hit_flash, 0
        if u._lunge_timer <= 0 < prev._lunge_timer:
            u._lunge_timer, u._lunge_delay = prev._lunge_timer, 0
            u._lunge_target = prev._lunge_target
    for attr in ('_ground_layer',):
        if hasattr(old, attr):
            setattr(new, attr, getattr(old, attr))
    if hasattr(old.battlefield, '_has_buildings'):
        new.battlefield._has_buildings = old.battlefield._has_buildings


# ═══════════════════════════════════════════════════════════════
#   FIL DE SIMULATION
# ═══════════════════════════════════════════════════════════════

class RoundPipeline:
    """Joue les rounds de `battle` à la demande et rend un instantané par
    round.

        pipe.request(frames)   # lancer le round suivant (non bloquant)
        snap = pipe.take()     # l'instantané s'il est prêt, sinon None

    Au plus un round d'avance: le suivant n'est lancé que sur demande.
    threaded=False joue le round au moment de take() — le comportement
    d'avant, déterministe à l'image près (tests)."""

    def __init__(self, battle, threaded=True):
        self.live = battle
        self.threaded = threaded
        self._cond = threading.Condition()
        self._pending = None        # images par round du round demandé
        self._ready = None          # (instantané, exception) prêt à prendre
        self._busy = False
        self._closed = False
        self._thread = None
        if threaded:
            self._thread = threading.Thread(target=self._run, name="simulation",
                                            daemon=True)
            self._thread.start()

    def initial_snapshot(self):
        """Instantané de l'état de départ (avant tout round demandé)."""
        with self._cond:
            assert self._pending is None and not self._busy
            return take_snapshot(self.live)

    def request(self, frames):
        """Demande le round suivant, ses actions réparties sur `frames`
        images (cf. Battle.fx_frames_per_round)."""
        with self._cond:
            if self._closed:
                return
            self._pending = frames
            self._cond.notify_all()

    def pending(self):
        """Un round est-il demandé, en cours ou prêt ?"""
        with self._cond:
            return self._pending is not None or self._busy or self._ready is not None

    def take(self):
        """L'instantané du round demandé s'il est prêt, sinon None. Une
        erreur de la simulation est relevée ici, dans le fil de l'écran."""
        if not self.threaded:
            with self._cond:
                frames, self._pending = self._pending, None
            if frames is None:
                return None
            return self._step(frames)
        with self._cond:
            ready, self._ready = self._ready, None
        if ready is None:
            return None
        snap, error = ready
        if error is not None:
            raise error
        return snap

    def wait(self, timeout=None):
        """Attend que le round demandé soit prêt (True) ou le délai écoulé."""
        if not self.threaded:
            return True
        with self._cond:
            return self._cond.wait_for(
                lambda: self._ready is not None or self._closed
                or (self._pending is None and not self._busy), timeout)

    def close(self):
        """Arrête le fil après le round en cours (un round ne s'interrompt
        pas: la bataille vivante reste cohérente) et l'attend."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join()

    def _step(self, frames):
        battle = self.live
        battle.fx_frames_per_round = frames
        battle.simulate_round()
        return take_snapshot(battle)

    def _run(self):
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._pending is not None or self._closed)
                if self._closed:
                    return
                frames, self._pending = self._pending, None
                self._busy = True
            try:
                result = (self._step(frames), None)
            except BaseException as e:     # relevée dans le fil de l'écran
                result = (None, e)
            with self._cond:
                self._busy = False
                if self._closed:
                    return
                self._ready = result
                self._cond.notify_all()
