"""Réglages et mémoire de session, gardés d'une partie à l'autre.

Tout ce que l'utilisateur a choisi une fois n'a pas à être refait: armées
composées, carte et options du champ de bataille, affichage en bataille,
réglages vidéo. Un seul fichier JSON, écrit de façon atomique:

    Windows: %APPDATA%/Wargame-Orbis/settings.json
    ailleurs: ~/.config/wargame-orbis/settings.json

WARGAME_ORBIS_SETTINGS=chemin impose un autre fichier; « memory » garde
les réglages en mémoire sans rien lire ni écrire (tests).
"""
import copy
import json
import os

DEFAULTS = {
    "battle": {
        "speed": "normal",          # normal | fast | faster
        "start_paused": True,       # la bataille attend le premier ESPACE
        "show_lines": True,
        "show_intents": True,
        "show_minimap": True,
        "show_legend": False,
        "edge_scroll": True,        # la souris au bord de l'écran fait défiler
        "camera_speed": 12,         # pixels écran par image
    },
    "video": {
        "resolution": "1080p",      # 720p | 1080p
        "fps": 24,
        "seconds_per_round": 1.0,
    },
    "session": {
        "armies": None,             # cf. menu.ArmyState.to_dict
        "map": None,                # cf. map_screen.MapSetup.to_dict
    },
}


def default_path():
    override = os.environ.get("WARGAME_ORBIS_SETTINGS")
    if override:
        return None if override == "memory" else override
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, "Wargame-Orbis", "settings.json")
    return os.path.join(os.path.expanduser("~"), ".config", "wargame-orbis", "settings.json")


class Settings:
    """Réglages par sections (cf. DEFAULTS). Une valeur absente ou d'un
    autre type que sa valeur par défaut est ignorée à la lecture: un fichier
    abîmé ou d'une ancienne version ne casse rien."""

    def __init__(self, path=None, load=True):
        self.path = path
        self.data = copy.deepcopy(DEFAULTS)
        self.dirty = False
        if load and path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self._merge(json.load(f))
            except (OSError, ValueError):
                pass

    def _merge(self, raw):
        if not isinstance(raw, dict):
            return
        for section, values in raw.items():
            known = self.data.get(section)
            if not isinstance(known, dict) or not isinstance(values, dict):
                continue
            for key, value in values.items():
                if key not in known:
                    continue
                default = DEFAULTS[section][key]
                if default is None or value is None or isinstance(value, type(default)) or (
                        isinstance(default, float) and isinstance(value, int)):
                    known[key] = value

    def get(self, section, key):
        return self.data[section][key]

    def set(self, section, key, value):
        if self.data[section].get(key) != value:
            self.data[section][key] = value
            self.dirty = True

    def section(self, name):
        return self.data[name]

    def save(self):
        """Écrit le fichier s'il y a du nouveau (écriture atomique)."""
        if not self.dirty or not self.path:
            self.dirty = False
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = f"{self.path}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError:
            pass            # réglages non sauvegardés: le jeu continue


_current = None


def get():
    """Les réglages de cette session (lus une fois)."""
    global _current
    if _current is None:
        path = default_path()
        _current = Settings(path, load=path is not None)
    return _current


def reset(path="memory"):
    """Repart de réglages neufs (tests)."""
    global _current
    _current = Settings(None if path == "memory" else path, load=path != "memory")
    return _current
