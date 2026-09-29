"""Vidéo d'une bataille, en vue globale (toute la carte), sans quitter le jeu.

La bataille est REJOUÉE dans un autre processus, depuis son état de départ et
l'état du hasard à cet instant (battle_pipeline.pack_battle): c'est
exactement la même bataille, du premier au dernier round, même si l'on n'en a
regardé qu'une partie. Le jeu continue pendant ce temps — autre processus,
autre cœur.

Chaque image est dessinée par l'écran de bataille lui-même (GlobalView, une
BattleView hors écran), carte entière avec bandeau, bannières et bilan, puis
encodée:
- en MP4 (H.264) si ffmpeg est disponible (PATH, ou paquet imageio-ffmpeg);
- sinon en AVI Motion-JPEG, écrit ici même: aucune dépendance, lisible par
  VLC et les lecteurs de Windows, mais des fichiers bien plus lourds.

    python video_export.py JOB.json     # processus d'export (cf. ExportJob)
"""
import io
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))

RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080)}
MAX_ROUNDS = 150            # garde-fou: une vidéo finit toujours
END_HOLD_SECONDS = 4        # le bilan reste à l'écran à la fin
TITLE_SECONDS = 2.5         # carton de titre au début
TOP_BAR = 36                # cf. BattleView._draw_top_bar


# ═══════════════════════════════════════════════════════════════
#   ENCODAGE
# ═══════════════════════════════════════════════════════════════

def output_dir():
    """Dossier des vidéos: Vidéos/Wargame Orbis (WARGAME_ORBIS_VIDEOS pour
    en imposer un autre)."""
    override = os.environ.get("WARGAME_ORBIS_VIDEOS")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), "Videos", "Wargame Orbis")


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def encoder_label():
    if find_ffmpeg():
        return "Format : MP4 (H.264, via ffmpeg)"
    return ("Format : AVI Motion-JPEG — installez ffmpeg (ou « pip install imageio-ffmpeg ») "
            "pour des MP4 bien plus légers")


class AviWriter:
    """AVI 1.0 à flux vidéo Motion-JPEG, en Python pur: en-têtes, un bloc
    '00dc' par image JPEG, index 'idx1'. Les totaux sont réécrits à la
    fermeture (en-têtes de taille fixe)."""

    def __init__(self, path, width, height, fps):
        self.path = path
        self.w, self.h, self.fps = width, height, fps
        self.f = open(path, "wb")
        self.index = []             # (décalage depuis 'movi', taille)
        self.max_frame = 0
        f = self.f
        f.write(b"RIFF" + struct.pack("<I", 0) + b"AVI ")
        hdrl = self._hdrl(0, 0)
        f.write(b"LIST" + struct.pack("<I", len(hdrl) + 4) + b"hdrl")
        self._hdrl_pos = f.tell()
        f.write(hdrl)
        f.write(b"LIST")
        self._movi_size_pos = f.tell()
        f.write(struct.pack("<I", 0))
        self._movi_pos = f.tell()
        f.write(b"movi")

    def _hdrl(self, frames, max_size):
        w, h, fps = self.w, self.h, self.fps
        avih = struct.pack("<14I", int(1_000_000 / fps), max_size * fps, 0, 0x10, frames, 0, 1,
                           max_size, w, h, 0, 0, 0, 0)
        strh = struct.pack("<4s4sIHHIIIIIIiI4h", b"vids", b"MJPG", 0, 0, 0, 0, 1, fps, 0, frames,
                           max_size, -1, 0, 0, 0, w, h)
        strf = struct.pack("<IiiHH4sIiiII", 40, w, h, 1, 24, b"MJPG", w * h * 3, 0, 0, 0, 0)
        strl = (b"strh" + struct.pack("<I", len(strh)) + strh
                + b"strf" + struct.pack("<I", len(strf)) + strf)
        return (b"avih" + struct.pack("<I", len(avih)) + avih
                + b"LIST" + struct.pack("<I", len(strl) + 4) + b"strl" + strl)

    def add_jpeg(self, data):
        pos = self.f.tell()
        self.f.write(b"00dc" + struct.pack("<I", len(data)) + data)
        if len(data) % 2:
            self.f.write(b"\0")
        self.index.append((pos - self._movi_pos, len(data)))
        self.max_frame = max(self.max_frame, len(data))

    def add_frame(self, surface):
        import pygame
        buf = io.BytesIO()
        pygame.image.save(surface, buf, "frame.jpg")
        self.add_jpeg(buf.getvalue())

    def close(self):
        f = self.f
        end = f.tell()
        f.write(b"idx1" + struct.pack("<I", 16 * len(self.index)))
        for offset, size in self.index:
            f.write(b"00dc" + struct.pack("<III", 0x10, offset, size))
        total = f.tell()
        f.seek(4)
        f.write(struct.pack("<I", total - 8))
        f.seek(self._movi_size_pos)
        f.write(struct.pack("<I", end - self._movi_pos))
        f.seek(self._hdrl_pos)
        f.write(self._hdrl(len(self.index), self.max_frame))
        f.close()
        return self.path


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FfmpegWriter:
    """Images brutes RGB envoyées à ffmpeg (H.264, MP4)."""

    def __init__(self, exe, path, width, height, fps):
        self.path = path
        self.log = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(
            [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", path],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log,
            creationflags=_NO_WINDOW)

    def add_frame(self, surface):
        import pygame
        self.proc.stdin.write(pygame.image.tobytes(surface, "RGB"))

    def close(self):
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            self.log.seek(0)
            raise RuntimeError("ffmpeg: " + self.log.read().decode("utf-8", "replace")[-300:])
        return self.path


def open_writer(base, width, height, fps, prefer_ffmpeg=True):
    """Encodeur et chemin final: MP4 via ffmpeg si possible, sinon AVI."""
    exe = find_ffmpeg() if prefer_ffmpeg else None
    if exe:
        return FfmpegWriter(exe, base + ".mp4", width, height, fps)
    return AviWriter(base + ".avi", width, height, fps)


# ═══════════════════════════════════════════════════════════════
#   VUE GLOBALE (hors écran)
# ═══════════════════════════════════════════════════════════════

def _global_view_class():
    import pygame
    import battle_view
    import hud
    import renderer as R
    import theme as T
    import ui

    class GlobalView(battle_view.BattleView):
        """L'écran de bataille dessiné sur une surface: toute la carte,
        caméra fixe, bandeau, bannières et bilan — pas de barre d'outils."""

        def __init__(self, battle, cell_size, size, frames_per_round, title):
            self.frames_per_round = frames_per_round
            self.title = title
            self._setup(battle, cell_size, pygame.Surface(size), threaded=False)
            self.world_bg = T.BG_BOTTOM
            self.show_minimap = self.show_lines = self.show_intents = False
            self.show_terrain_legend = False
            self.paused = False
            # Carte centrée entre le bandeau du haut et celui du bas
            self.cam_x = -(self.screen_w - self.world_w) / 2
            self.cam_y = -(TOP_BAR + (self.view_h - TOP_BAR - self.world_h) / 2)

        def _round_frames(self):
            return self.frames_per_round

        def clamp_camera(self):
            pass                                # caméra fixe

        def _draw_bottom_hud(self):
            status = "VICTOIRE : " + self.winner if self.winner else self.title
            ui.draw_bottom_hud(self.screen, self.battle, self.screen_w, self.view_h,
                               R.HUD_HEIGHT, (self.hud_font, self.hud_bold), status,
                               (255, 215, 0) if self.winner else T.GOLD, None, None, "",
                               R.POSTURE_LABELS)

        def render(self, now, title_alpha=0):
            self.clicks = hud.Clicks()
            self._draw_world(now, None)
            self.wfx.draw(self.screen, self.screen_w, self.view_h)
            self.fxr.draw_screen(self.screen, self.screen_w, self.view_h)
            self._draw_top_bar()
            self._draw_banners()
            self._draw_bottom_hud()
            if self.battle_report:
                R.draw_battle_report(self.screen, self.battle_report, self.screen_w, self.view_h,
                                     self.small_font, self.tiny_font)
            if title_alpha > 0:
                self._draw_title_card(title_alpha)

        def _draw_title_card(self, alpha):
            fnt = T.font('title', 44)
            img = T.gold_text(self.title, fnt)
            card = pygame.Rect(0, 0, img.get_width() + 140, img.get_height() + 70)
            card.center = (self.screen_w // 2, self.view_h // 2)
            layer = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            T.glass(layer, card, 225, 12)
            T.corner_marks(layer, card, T.GOLD_DIM, 12)
            layer.blit(img, (card.centerx - img.get_width() // 2, card.y + 18))
            T.text(layer, "Wargame Orbis", T.font('serif', 18), (card.centerx, card.bottom - 34),
                   T.PARCHMENT_DIM, align="center")
            layer.set_alpha(alpha)
            self.screen.blit(layer, (0, 0))

    return GlobalView


# ═══════════════════════════════════════════════════════════════
#   EXPORT (processus d'export)
# ═══════════════════════════════════════════════════════════════

def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def export(job, on_round=None):
    """Rejoue la bataille du kit et en écrit la vidéo. Retourne (chemin, vue).

    job: {'kit': chemin du kit, 'base': chemin sans extension, 'video':
    réglages vidéo, 'title', 'max_rounds' (facultatif), 'ffmpeg' (False:
    toujours AVI)}."""
    import pygame
    import battle_pipeline as BP
    import renderer as R

    if not pygame.display.get_init() or pygame.display.get_surface() is None:
        pygame.display.init()
        pygame.display.set_mode((1, 1))
    pygame.font.init()
    with open(job['kit'], "rb") as f:
        battle, rng_state = BP.unpack_battle(f.read())
    video = job['video']
    width, height = RESOLUTIONS.get(video.get('resolution'), RESOLUTIONS["1080p"])
    fps = int(video.get('fps', 24))
    frames_per_round = max(6, round(fps * float(video.get('seconds_per_round', 1.0))))
    bf = battle.battlefield
    avail_h = height - TOP_BAR - R.HUD_HEIGHT
    cell = max(4, min(width // bf.width, avail_h // bf.height))

    view = _global_view_class()(battle, cell, (width, height), frames_per_round,
                                job.get('title') or battle.map_name)
    # Le hasard reprend exactement où la bataille l'avait trouvé
    random.setstate(rng_state)
    writer = open_writer(job['base'], width, height, fps, job.get('ffmpeg', True))
    max_rounds = int(job.get('max_rounds') or MAX_ROUNDS)
    title_frames = int(TITLE_SECONDS * fps)
    frame, hold, last_round = 0, 0, -1
    try:
        while True:
            view.update()
            fade = 0
            if frame < title_frames:
                fade = int(255 * min(1.0, (title_frames - frame) / (fps * 0.6)))
            view.render(frame * 1000 // fps, fade)
            writer.add_frame(view.screen)
            frame += 1
            played = view.battle.round - 1
            if played != last_round:
                last_round = played
                if on_round is not None:
                    on_round(played)
            if view.winner is not None:
                hold += 1
                if hold >= END_HOLD_SECONDS * fps:
                    break
            elif played >= max_rounds and view.round_frame >= frames_per_round:
                break
    finally:
        path = writer.close()
    return path, view


def _child_main(job_path):
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    progress = job['progress']
    total = job.get('expected_rounds')

    def on_round(r):
        _write_json(progress, {'state': "running", 'round': r, 'total': total})

    try:
        on_round(0)
        path, _view = export(job, on_round)
        _write_json(progress, {'state': "done", 'path': path})
        return 0
    except Exception as e:
        _write_json(progress, {'state': "error", 'message': f"{type(e).__name__}: {e}",
                               'trace': traceback.format_exc()[-2000:]})
        return 1


# ═══════════════════════════════════════════════════════════════
#   CÔTÉ JEU
# ═══════════════════════════════════════════════════════════════

class ExportJob:
    """Lance l'export dans un autre processus et en suit l'avancement."""

    def __init__(self, kit, video_settings, title="", expected_rounds=None, out_dir=None,
                 max_rounds=None, ffmpeg=True):
        self.out_dir = out_dir or output_dir()
        os.makedirs(self.out_dir, exist_ok=True)
        self.work = tempfile.mkdtemp(prefix="wargame-video-")
        kit_path = os.path.join(self.work, "kit.bin")
        with open(kit_path, "wb") as f:
            f.write(kit)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.progress_path = os.path.join(self.work, "progress.json")
        job = {'kit': kit_path, 'base': os.path.join(self.out_dir, f"bataille-{stamp}"),
               'progress': self.progress_path, 'video': video_settings, 'title': title,
               'expected_rounds': expected_rounds, 'max_rounds': max_rounds, 'ffmpeg': ffmpeg}
        job_path = os.path.join(self.work, "job.json")
        _write_json(job_path, job)
        env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy",
                   PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), job_path],
                                     cwd=HERE, env=env, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        self._state = {'state': "running", 'round': 0, 'total': expected_rounds}
        self._read_at = 0.0

    @property
    def running(self):
        return self.proc.poll() is None

    def poll(self):
        """{'state': running|done|error, ...} — lu au plus 4 fois par seconde."""
        now = time.time()
        finished = self.proc.poll() is not None
        if finished or now - self._read_at > 0.25:
            self._read_at = now
            try:
                with open(self.progress_path, encoding="utf-8") as f:
                    self._state = json.load(f)
            except (OSError, ValueError):
                pass
            if finished and self._state.get('state') == "running":
                self._state = {'state': "error",
                               'message': f"export interrompu (code {self.proc.returncode})"}
        if self._state.get('state') != "running" and finished:
            shutil.rmtree(self.work, ignore_errors=True)
        return self._state

    def wait(self, timeout=None):
        self.proc.wait(timeout)
        return self.poll()


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    sys.exit(_child_main(sys.argv[1]))
