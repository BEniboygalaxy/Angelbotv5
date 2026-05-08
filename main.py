"""
Minecraft Cyan->Green Bar Bot v3
--------------------------------
Spezialisiert auf das Angel-Minigame mit segmentierter Bar:
  blau ............ blau-blau-cyan-blau-gruen-gruen-gruen-blau ........ blau

Optimiert fuer WQHD (2560x1440) - skaliert automatisch fuer andere Aufloesungen.

NEU IN v3
- Captcha-Erkennung unten links (konfigurierbarer Bereich)
- OCR per Tesseract (optional) -> tippt Text automatisch
- Sicherer Fallback: bei OCR-Fehler -> Bot pausiert + Sound + Logging
- Captcha-Bereich Live kalibrierbar (F2/F3)
- Auto-Skalierung der Default-Werte auf jede Bildschirmaufloesung

HOTKEYS
- F2  : oben-links Ecke des Captcha-Bereichs setzen (Maus dort halten)
- F3  : unten-rechts Ecke des Captcha-Bereichs setzen
- F4  : Captcha-Test: macht Screenshot + speichert + versucht OCR
- F6  : Bot Start / Stop
- F7  : Auto-Scan fuer Angel-Bar
- F8  : X_START setzen          F9 : X_END setzen          F10 : SCAN_Y
- F11 : Konfig in config.ini speichern
- F12 : Programm beenden
"""

from __future__ import annotations

import configparser
import ctypes
import json
import os
import random
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, Tuple

import cv2
import keyboard
import mss
import numpy as np
import pydirectinput

pydirectinput.PAUSE = 0.0
pydirectinput.FAILSAFE = False

# OCR ist optional - wenn pytesseract/tesseract nicht da, fallback
try:
    import pytesseract  # type: ignore
    _OCR_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore
    _OCR_AVAILABLE = False

# Sound (nur Windows)
try:
    import winsound  # type: ignore
    _SOUND_AVAILABLE = True
except ImportError:
    winsound = None  # type: ignore
    _SOUND_AVAILABLE = False


# ============================================================
# DEFAULTS  (basierend auf WQHD-Screenshot vom User)
# ============================================================

CONFIG_FILE = "config.ini"
CAPTCHA_SAVE_DIR = "captcha_logs"
STATS_FILE = "stats.json"
PROFILES_DIR = "profiles"


def _app_dir() -> str:
    """Verzeichnis der EXE (oder des Scripts im Dev-Modus)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _config_path(profile: str = "") -> str:
    if profile and profile != "default":
        os.makedirs(os.path.join(_app_dir(), PROFILES_DIR), exist_ok=True)
        return os.path.join(_app_dir(), PROFILES_DIR, f"{profile}.ini")
    return os.path.join(_app_dir(), CONFIG_FILE)


def _captcha_dir() -> str:
    return os.path.join(_app_dir(), CAPTCHA_SAVE_DIR)


def _stats_path() -> str:
    return os.path.join(_app_dir(), STATS_FILE)


def list_profiles() -> list:
    """Findet alle existierenden Profile-Dateien."""
    profs = ["default"]
    pdir = os.path.join(_app_dir(), PROFILES_DIR)
    if os.path.isdir(pdir):
        for fn in sorted(os.listdir(pdir)):
            if fn.endswith(".ini"):
                profs.append(fn[:-4])
    return profs


# ============================================================
# WIN32 HELPERS (Maus, Fenster-Fokus, Monitore)
# ============================================================

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_cursor_pos() -> Tuple[int, int]:
    pt = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def get_foreground_title() -> str:
    """Titel des aktuell fokussierten Fensters."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except OSError:
        return ""


def beep_alert(enabled: bool = True) -> None:
    if not enabled or not _SOUND_AVAILABLE:
        return
    try:
        winsound.Beep(880, 200)
        winsound.Beep(660, 200)
        winsound.Beep(880, 300)
    except RuntimeError:
        pass


# ============================================================
# STATS-Persistenz
# ============================================================

def load_stats() -> dict:
    p = _stats_path()
    if not os.path.exists(p):
        return {"sessions": [], "total_hits": 0, "total_captchas": 0,
                "total_runtime_sec": 0, "by_day": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"sessions": [], "total_hits": 0, "total_captchas": 0,
                "total_runtime_sec": 0, "by_day": {}}


def save_stats(stats: dict) -> None:
    try:
        with open(_stats_path(), "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
    except OSError:
        pass


def record_session(hits: int, captchas: int, runtime_sec: int) -> None:
    """Speichert eine Session in stats.json - aggregiert pro Tag."""
    stats = load_stats()
    today = time.strftime("%Y-%m-%d")
    sess = {
        "date": today,
        "time": time.strftime("%H:%M:%S"),
        "hits": hits,
        "captchas": captchas,
        "runtime_sec": runtime_sec,
    }
    stats.setdefault("sessions", []).append(sess)
    # Nur die letzten 200 Sessions behalten
    stats["sessions"] = stats["sessions"][-200:]
    stats["total_hits"] = stats.get("total_hits", 0) + hits
    stats["total_captchas"] = stats.get("total_captchas", 0) + captchas
    stats["total_runtime_sec"] = stats.get("total_runtime_sec", 0) + runtime_sec
    by_day = stats.setdefault("by_day", {})
    d = by_day.setdefault(today, {"hits": 0, "captchas": 0, "runtime_sec": 0})
    d["hits"] += hits
    d["captchas"] += captchas
    d["runtime_sec"] += runtime_sec
    save_stats(stats)


# ============================================================
# DISCORD WEBHOOK
# ============================================================

def send_discord(webhook_url: str, message: str) -> None:
    """Sendet eine Nachricht an einen Discord-Webhook (best effort, non-blocking)."""
    if not webhook_url or not webhook_url.startswith("http"):
        return

    def _post():
        try:
            data = json.dumps({"content": message}).encode("utf-8")
            req = urllib.request.Request(
                webhook_url, data=data,
                headers={"Content-Type": "application/json", "User-Agent": "FishingBot/4"},
            )
            urllib.request.urlopen(req, timeout=5).read()
        except (OSError, ValueError):
            pass

    threading.Thread(target=_post, daemon=True).start()

# Erprobte Farben aus dem Spiel-Screenshot
DEFAULT_GREEN_RGB = (84, 252, 84)
DEFAULT_CURSOR_RGB = (84, 252, 252)
DEFAULT_THRESHOLD = 35           # gross genug damit jeder Pixel gefunden wird
DEFAULT_MIN_CURSOR_PIXELS = 2    # niedriger = empfindlicher
DEFAULT_HIT_TOLERANCE_PX = 2     # kleine Messtoleranz, vermeidet Rand-Misclicks

# Multi-Line-Scan: wie viele Pixelzeilen werden gescannt?
# Mehr = genauer (faengt Bar auch wenn SCAN_Y leicht off ist), etwas mehr CPU
DEFAULT_SCAN_BAND = 30           # +/- 15px um SCAN_Y

# Auto-Re-Scan wenn lange keine Bar gesehen
AUTO_RESCAN_AFTER_SEC = 3.0

# Bar-Defaults relativ zur Aufloesung (skalieren auf jeden Bildschirm)
# Werte aus 2560x1440 Screenshot:  SCAN_Y=641
# X-Range = volle Bildschirmbreite (Single-Line-Scan ist eh blitzschnell,
# so verpassen wir die aeussersten Segmente nicht)
DEFAULT_REL_SCAN_Y = 641 / 1440      # ~0.445
DEFAULT_REL_X_START = 0.0
DEFAULT_REL_X_END = 1.0

# Captcha-Bereich relativ (unten links): X 0-30%, Y 60-95%
DEFAULT_REL_CAP_X1 = 0.00
DEFAULT_REL_CAP_X2 = 0.30
DEFAULT_REL_CAP_Y1 = 0.60
DEFAULT_REL_CAP_Y2 = 0.95

DEFAULT_SECOND_CLICK_DELAY = 1.2
DEFAULT_POST_CYCLE_COOLDOWN = 2.0
DEFAULT_SCAN_FPS = 10000     # Maximale Scan-Frequenz, real begrenzt durch Capture-Speed

# PIXEL-PERFEKT TIMING
# Wie viele ms vergehen zwischen "Cursor erkannt" und "Klick wirkt im Spiel"?
# 0 = klickt exakt wenn Cursor JETZT in green
# negativ = klickt etwas SPAETER (gut wenn er zu frueh klickt)
# positiv = klickt etwas FRUEHER (gut wenn er zu spaet klickt)
DEFAULT_INPUT_LAG_MS = 1
DEFAULT_CLICK_HOLD_MS = 1
DEFAULT_AUTO_TIMING_ENABLED = True
DEFAULT_TIMING_SAFETY_MS = 3.0
DEFAULT_END_ZONE_BOOST_MS = 8.0
# Wie viele Frames Cursor-History fuer Velocity-Berechnung
VELOCITY_WINDOW = 4
# Mindest-Sicherheitsabstand vom Green-Rand (in % der Green-Breite)
# 0.10 = 10% Rand wird gemieden -> nur die mittleren 80% sind "safe"
DEFAULT_GREEN_INNER_RATIO = 0.12

# Captcha-Detection: alle X Sekunden scannen (zu haeufig = CPU-Last)
DEFAULT_CAPTCHA_CHECK_INTERVAL = 3.0

# Wie soll der Bot den OCR-Text eintippen?
#   "chat"   -> druecke T, tippe Text, druecke Enter   (Minecraft Chat)
#   "direct" -> tippe direkt ohne Chat zu oeffnen
#   "none"   -> nur erkennen + ausloggen, nicht eintippen
DEFAULT_TYPE_MODE = "chat"

# ============================================================
# WAFFENTRAINING DEFAULTS
# ============================================================
# Farbe der roten Zielscheibe (RGB)
WT_DEFAULT_TARGET_RGB = (255, 0, 0)
# Farbtoleranz fuer Ziel-Erkennung
WT_DEFAULT_THRESHOLD = 60
# Minimale Pixelanzahl damit ein Cluster als Ziel zaehlt
WT_DEFAULT_MIN_TARGET_PIXELS = 30
# Scan-Region relativ zum Bildschirm (0.0 - 1.0)
WT_DEFAULT_REL_X1 = 0.10
WT_DEFAULT_REL_Y1 = 0.10
WT_DEFAULT_REL_X2 = 0.90
WT_DEFAULT_REL_Y2 = 0.85
# Verzoegerung nach Schuss (Sekunden) - Zeit fuer Nachladen/Animation
WT_DEFAULT_SHOT_DELAY = 0.08
# Verzoegerung fuer Mausbewegung zum Ziel (Sekunden)
WT_DEFAULT_AIM_SETTLE_MS = 5
# Klick-Hold fuer Schuss (ms)
WT_DEFAULT_SHOT_HOLD_MS = 50
# Scan-Intervall (Sekunden) - wie oft nach Zielen gesucht wird
WT_DEFAULT_SCAN_INTERVAL = 0.02
# Ob Maus sofort zum Ziel-Mittelpunkt springt oder interpoliert
WT_DEFAULT_INSTANT_AIM = True
# HSV-Modus: nutze HSV statt RGB fuer robustere Farberkennung
WT_DEFAULT_USE_HSV = True
# HSV-Bereiche fuer rote Erkennung (Rot liegt in HSV um 0 und 170-180)
WT_DEFAULT_HSV_H_LOW1 = 0
WT_DEFAULT_HSV_H_HIGH1 = 10
WT_DEFAULT_HSV_H_LOW2 = 160
WT_DEFAULT_HSV_H_HIGH2 = 180
WT_DEFAULT_HSV_S_MIN = 80
WT_DEFAULT_HSV_V_MIN = 80


# ============================================================
# CONFIG
# ============================================================

@dataclass
class BotConfig:
    # bar
    scan_y: int = 0
    x_start: int = 0
    x_end: int = 0
    green_rgb: Tuple[int, int, int] = DEFAULT_GREEN_RGB
    cursor_rgb: Tuple[int, int, int] = DEFAULT_CURSOR_RGB
    threshold: int = DEFAULT_THRESHOLD
    second_click_delay: float = DEFAULT_SECOND_CLICK_DELAY
    post_cycle_cooldown: float = DEFAULT_POST_CYCLE_COOLDOWN
    scan_fps: int = DEFAULT_SCAN_FPS
    input_lag_ms: int = DEFAULT_INPUT_LAG_MS
    click_hold_ms: int = DEFAULT_CLICK_HOLD_MS
    auto_timing_enabled: bool = DEFAULT_AUTO_TIMING_ENABLED
    timing_safety_ms: float = DEFAULT_TIMING_SAFETY_MS
    end_zone_boost_ms: float = DEFAULT_END_ZONE_BOOST_MS
    green_inner_ratio: float = DEFAULT_GREEN_INNER_RATIO
    scan_band: int = DEFAULT_SCAN_BAND
    # captcha
    cap_x1: int = 0
    cap_y1: int = 0
    cap_x2: int = 0
    cap_y2: int = 0
    captcha_check_interval: float = DEFAULT_CAPTCHA_CHECK_INTERVAL
    captcha_enabled: bool = True
    type_mode: str = DEFAULT_TYPE_MODE
    tesseract_path: str = ""
    # neue v4 features
    sound_enabled: bool = False
    anti_afk_enabled: bool = False
    anti_afk_interval_sec: int = 90
    auto_pause_on_focus_loss: bool = False
    focus_window_keyword: str = "Minecraft"
    discord_webhook_url: str = ""
    monitor_index: int = 1   # mss: 0=alles, 1=Primaer, 2+=weitere
    theme: str = "dark"      # dark / light / system
    hud_color: str = "#8b5cf6"
    overlay_enabled: bool = False
    overlay_capture_mode: str = "visible"  # visible / stream_safe
    overlay_opacity: float = 0.72
    profile_name: str = "default"
    # Waffentraining
    wt_enabled: bool = False
    wt_target_rgb: Tuple[int, int, int] = WT_DEFAULT_TARGET_RGB
    wt_threshold: int = WT_DEFAULT_THRESHOLD
    wt_min_target_pixels: int = WT_DEFAULT_MIN_TARGET_PIXELS
    wt_scan_x1: int = 0
    wt_scan_y1: int = 0
    wt_scan_x2: int = 0
    wt_scan_y2: int = 0
    wt_shot_delay: float = WT_DEFAULT_SHOT_DELAY
    wt_aim_settle_ms: int = WT_DEFAULT_AIM_SETTLE_MS
    wt_shot_hold_ms: int = WT_DEFAULT_SHOT_HOLD_MS
    wt_scan_interval: float = WT_DEFAULT_SCAN_INTERVAL
    wt_instant_aim: bool = WT_DEFAULT_INSTANT_AIM
    wt_use_hsv: bool = WT_DEFAULT_USE_HSV
    wt_hsv_h_low1: int = WT_DEFAULT_HSV_H_LOW1
    wt_hsv_h_high1: int = WT_DEFAULT_HSV_H_HIGH1
    wt_hsv_h_low2: int = WT_DEFAULT_HSV_H_LOW2
    wt_hsv_h_high2: int = WT_DEFAULT_HSV_H_HIGH2
    wt_hsv_s_min: int = WT_DEFAULT_HSV_S_MIN
    wt_hsv_v_min: int = WT_DEFAULT_HSV_V_MIN
    hotkeys: dict = field(default_factory=lambda: {
        "toggle": "f6", "auto_scan": "f7", "save": "f11", "quit": "f12",
        "set_x_start": "f8", "set_x_end": "f9", "set_scan_y": "f10",
        "set_cap_tl": "f2", "set_cap_br": "f3",
        "captcha_test": "f4", "debug": "f5",
        "wt_toggle": "f1",
    })
    # status
    screen_w: int = 1920
    screen_h: int = 1080

    def apply_relative_defaults(self, w: int, h: int) -> None:
        """Setzt Bar- und Captcha-Default-Werte relativ zur Bildschirmgroesse."""
        self.screen_w, self.screen_h = w, h
        self.scan_y = int(h * DEFAULT_REL_SCAN_Y)
        self.x_start = int(w * DEFAULT_REL_X_START)
        self.x_end = int(w * DEFAULT_REL_X_END)
        self.cap_x1 = int(w * DEFAULT_REL_CAP_X1)
        self.cap_x2 = int(w * DEFAULT_REL_CAP_X2)
        self.cap_y1 = int(h * DEFAULT_REL_CAP_Y1)
        self.cap_y2 = int(h * DEFAULT_REL_CAP_Y2)
        self.wt_scan_x1 = int(w * WT_DEFAULT_REL_X1)
        self.wt_scan_y1 = int(h * WT_DEFAULT_REL_Y1)
        self.wt_scan_x2 = int(w * WT_DEFAULT_REL_X2)
        self.wt_scan_y2 = int(h * WT_DEFAULT_REL_Y2)

    def to_ini(self, path: str) -> None:
        cp = configparser.ConfigParser()
        cp["scan"] = {
            "scan_y": str(self.scan_y),
            "x_start": str(self.x_start),
            "x_end": str(self.x_end),
            "scan_fps": str(self.scan_fps),
            "scan_band": str(self.scan_band),
            "monitor_index": str(self.monitor_index),
        }
        cp["colors"] = {
            "green_rgb": ",".join(map(str, self.green_rgb)),
            "cursor_rgb": ",".join(map(str, self.cursor_rgb)),
            "threshold": str(self.threshold),
        }
        cp["click"] = {
            "second_click_delay": str(self.second_click_delay),
            "post_cycle_cooldown": str(self.post_cycle_cooldown),
            "input_lag_ms": str(self.input_lag_ms),
            "click_hold_ms": str(self.click_hold_ms),
            "auto_timing_enabled": str(self.auto_timing_enabled),
            "timing_safety_ms": str(self.timing_safety_ms),
            "end_zone_boost_ms": str(self.end_zone_boost_ms),
            "green_inner_ratio": str(self.green_inner_ratio),
        }
        cp["captcha"] = {
            "cap_x1": str(self.cap_x1),
            "cap_y1": str(self.cap_y1),
            "cap_x2": str(self.cap_x2),
            "cap_y2": str(self.cap_y2),
            "check_interval": str(self.captcha_check_interval),
            "enabled": str(self.captcha_enabled),
            "type_mode": self.type_mode,
            "tesseract_path": self.tesseract_path,
        }
        cp["features"] = {
            "sound_enabled": str(self.sound_enabled),
            "anti_afk_enabled": str(self.anti_afk_enabled),
            "anti_afk_interval_sec": str(self.anti_afk_interval_sec),
            "auto_pause_on_focus_loss": str(self.auto_pause_on_focus_loss),
            "focus_window_keyword": self.focus_window_keyword,
            "discord_webhook_url": self.discord_webhook_url,
            "theme": self.theme,
            "hud_color": self.hud_color,
            "overlay_enabled": str(self.overlay_enabled),
            "overlay_capture_mode": self.overlay_capture_mode,
            "overlay_opacity": str(self.overlay_opacity),
        }
        cp["waffentraining"] = {
            "enabled": str(self.wt_enabled),
            "target_rgb": ",".join(map(str, self.wt_target_rgb)),
            "threshold": str(self.wt_threshold),
            "min_target_pixels": str(self.wt_min_target_pixels),
            "scan_x1": str(self.wt_scan_x1),
            "scan_y1": str(self.wt_scan_y1),
            "scan_x2": str(self.wt_scan_x2),
            "scan_y2": str(self.wt_scan_y2),
            "shot_delay": str(self.wt_shot_delay),
            "aim_settle_ms": str(self.wt_aim_settle_ms),
            "shot_hold_ms": str(self.wt_shot_hold_ms),
            "scan_interval": str(self.wt_scan_interval),
            "instant_aim": str(self.wt_instant_aim),
            "use_hsv": str(self.wt_use_hsv),
            "hsv_h_low1": str(self.wt_hsv_h_low1),
            "hsv_h_high1": str(self.wt_hsv_h_high1),
            "hsv_h_low2": str(self.wt_hsv_h_low2),
            "hsv_h_high2": str(self.wt_hsv_h_high2),
            "hsv_s_min": str(self.wt_hsv_s_min),
            "hsv_v_min": str(self.wt_hsv_v_min),
        }
        cp["hotkeys"] = {k: v for k, v in self.hotkeys.items()}
        with open(path, "w", encoding="utf-8") as f:
            cp.write(f)

    @classmethod
    def from_ini(cls, path: str, screen_w: int, screen_h: int) -> "BotConfig":
        cfg = cls()
        cfg.apply_relative_defaults(screen_w, screen_h)
        if not os.path.exists(path):
            return cfg
        cp = configparser.ConfigParser()
        try:
            cp.read(path, encoding="utf-8")
            cfg.scan_y = cp.getint("scan", "scan_y", fallback=cfg.scan_y)
            cfg.x_start = cp.getint("scan", "x_start", fallback=cfg.x_start)
            cfg.x_end = cp.getint("scan", "x_end", fallback=cfg.x_end)
            cfg.scan_fps = cp.getint("scan", "scan_fps", fallback=cfg.scan_fps)
            cfg.scan_band = cp.getint("scan", "scan_band", fallback=cfg.scan_band)
            cfg.monitor_index = cp.getint("scan", "monitor_index", fallback=cfg.monitor_index)
            cfg.threshold = cp.getint("colors", "threshold", fallback=cfg.threshold)
            cfg.green_rgb = _parse_rgb(cp.get("colors", "green_rgb", fallback=""), cfg.green_rgb)
            cfg.cursor_rgb = _parse_rgb(cp.get("colors", "cursor_rgb", fallback=""), cfg.cursor_rgb)
            cfg.second_click_delay = cp.getfloat("click", "second_click_delay", fallback=cfg.second_click_delay)
            cfg.post_cycle_cooldown = cp.getfloat("click", "post_cycle_cooldown", fallback=cfg.post_cycle_cooldown)
            cfg.input_lag_ms = cp.getint("click", "input_lag_ms", fallback=cfg.input_lag_ms)
            cfg.click_hold_ms = cp.getint("click", "click_hold_ms", fallback=cfg.click_hold_ms)
            cfg.auto_timing_enabled = cp.getboolean("click", "auto_timing_enabled", fallback=cfg.auto_timing_enabled)
            cfg.timing_safety_ms = cp.getfloat("click", "timing_safety_ms", fallback=cfg.timing_safety_ms)
            cfg.end_zone_boost_ms = cp.getfloat("click", "end_zone_boost_ms", fallback=cfg.end_zone_boost_ms)
            cfg.green_inner_ratio = cp.getfloat("click", "green_inner_ratio", fallback=cfg.green_inner_ratio)
            cfg.cap_x1 = cp.getint("captcha", "cap_x1", fallback=cfg.cap_x1)
            cfg.cap_y1 = cp.getint("captcha", "cap_y1", fallback=cfg.cap_y1)
            cfg.cap_x2 = cp.getint("captcha", "cap_x2", fallback=cfg.cap_x2)
            cfg.cap_y2 = cp.getint("captcha", "cap_y2", fallback=cfg.cap_y2)
            cfg.captcha_check_interval = cp.getfloat("captcha", "check_interval", fallback=cfg.captcha_check_interval)
            cfg.captcha_enabled = cp.getboolean("captcha", "enabled", fallback=cfg.captcha_enabled)
            cfg.type_mode = cp.get("captcha", "type_mode", fallback=cfg.type_mode)
            cfg.tesseract_path = cp.get("captcha", "tesseract_path", fallback="")
            cfg.sound_enabled = cp.getboolean("features", "sound_enabled", fallback=cfg.sound_enabled)
            cfg.anti_afk_enabled = cp.getboolean("features", "anti_afk_enabled", fallback=cfg.anti_afk_enabled)
            cfg.anti_afk_interval_sec = cp.getint("features", "anti_afk_interval_sec", fallback=cfg.anti_afk_interval_sec)
            cfg.auto_pause_on_focus_loss = cp.getboolean("features", "auto_pause_on_focus_loss", fallback=cfg.auto_pause_on_focus_loss)
            cfg.focus_window_keyword = cp.get("features", "focus_window_keyword", fallback=cfg.focus_window_keyword)
            cfg.discord_webhook_url = cp.get("features", "discord_webhook_url", fallback=cfg.discord_webhook_url)
            cfg.theme = cp.get("features", "theme", fallback=cfg.theme)
            cfg.hud_color = cp.get("features", "hud_color", fallback=cfg.hud_color)
            cfg.overlay_enabled = cp.getboolean("features", "overlay_enabled", fallback=cfg.overlay_enabled)
            cfg.overlay_capture_mode = cp.get("features", "overlay_capture_mode", fallback=cfg.overlay_capture_mode)
            cfg.overlay_opacity = cp.getfloat("features", "overlay_opacity", fallback=cfg.overlay_opacity)
            if cp.has_section("waffentraining"):
                cfg.wt_enabled = cp.getboolean("waffentraining", "enabled", fallback=cfg.wt_enabled)
                cfg.wt_target_rgb = _parse_rgb(cp.get("waffentraining", "target_rgb", fallback=""), cfg.wt_target_rgb)
                cfg.wt_threshold = cp.getint("waffentraining", "threshold", fallback=cfg.wt_threshold)
                cfg.wt_min_target_pixels = cp.getint("waffentraining", "min_target_pixels", fallback=cfg.wt_min_target_pixels)
                cfg.wt_scan_x1 = cp.getint("waffentraining", "scan_x1", fallback=cfg.wt_scan_x1)
                cfg.wt_scan_y1 = cp.getint("waffentraining", "scan_y1", fallback=cfg.wt_scan_y1)
                cfg.wt_scan_x2 = cp.getint("waffentraining", "scan_x2", fallback=cfg.wt_scan_x2)
                cfg.wt_scan_y2 = cp.getint("waffentraining", "scan_y2", fallback=cfg.wt_scan_y2)
                cfg.wt_shot_delay = cp.getfloat("waffentraining", "shot_delay", fallback=cfg.wt_shot_delay)
                cfg.wt_aim_settle_ms = cp.getint("waffentraining", "aim_settle_ms", fallback=cfg.wt_aim_settle_ms)
                cfg.wt_shot_hold_ms = cp.getint("waffentraining", "shot_hold_ms", fallback=cfg.wt_shot_hold_ms)
                cfg.wt_scan_interval = cp.getfloat("waffentraining", "scan_interval", fallback=cfg.wt_scan_interval)
                cfg.wt_instant_aim = cp.getboolean("waffentraining", "instant_aim", fallback=cfg.wt_instant_aim)
                cfg.wt_use_hsv = cp.getboolean("waffentraining", "use_hsv", fallback=cfg.wt_use_hsv)
                cfg.wt_hsv_h_low1 = cp.getint("waffentraining", "hsv_h_low1", fallback=cfg.wt_hsv_h_low1)
                cfg.wt_hsv_h_high1 = cp.getint("waffentraining", "hsv_h_high1", fallback=cfg.wt_hsv_h_high1)
                cfg.wt_hsv_h_low2 = cp.getint("waffentraining", "hsv_h_low2", fallback=cfg.wt_hsv_h_low2)
                cfg.wt_hsv_h_high2 = cp.getint("waffentraining", "hsv_h_high2", fallback=cfg.wt_hsv_h_high2)
                cfg.wt_hsv_s_min = cp.getint("waffentraining", "hsv_s_min", fallback=cfg.wt_hsv_s_min)
                cfg.wt_hsv_v_min = cp.getint("waffentraining", "hsv_v_min", fallback=cfg.wt_hsv_v_min)
            if cp.has_section("hotkeys"):
                for k in cfg.hotkeys.keys():
                    cfg.hotkeys[k] = cp.get("hotkeys", k, fallback=cfg.hotkeys[k])
        except (configparser.Error, ValueError):
            pass
        return cfg


def _parse_rgb(raw: str, fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if not raw:
        return fallback
    try:
        parts = [int(p.strip()) for p in raw.split(",")]
        if len(parts) == 3:
            return (parts[0], parts[1], parts[2])
    except ValueError:
        pass
    return fallback


# ============================================================
# BAR-DETECTION
# ============================================================

def color_match_mask(rgb: np.ndarray, target: Tuple[int, int, int], tol: int) -> np.ndarray:
    lower = np.array([max(0, c - tol) for c in target], dtype=np.uint8)
    upper = np.array([min(255, c + tol) for c in target], dtype=np.uint8)
    return cv2.inRange(rgb, lower, upper) > 0


def auto_scan_bar(cfg: BotConfig, sct: mss.mss) -> bool:
    """Vollbildscan: findet Zeile mit Cyan + Gruen."""
    monitor = sct.monitors[1]
    raw = np.array(sct.grab(monitor))
    rgb = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGB)
    h, w, _ = rgb.shape
    cyan = color_match_mask(rgb, cfg.cursor_rgb, cfg.threshold)
    green = color_match_mask(rgb, cfg.green_rgb, cfg.threshold)
    rows = np.where(np.any(cyan, axis=1) & np.any(green, axis=1))[0]
    if len(rows) == 0:
        print("[AUTO-SCAN] Keine Bar gefunden. Stelle sicher dass das Minigame sichtbar ist.")
        return False
    cfg.scan_y = int(rows[len(rows) // 2])
    line_mask = cyan[cfg.scan_y] | green[cfg.scan_y]
    xs = np.where(line_mask)[0]
    if len(xs) < 2:
        return False
    cfg.x_start = max(0, int(xs.min()) - 300)
    cfg.x_end = min(w, int(xs.max()) + 300)
    print(f"[AUTO-SCAN] OK -> SCAN_Y={cfg.scan_y}  X={cfg.x_start}..{cfg.x_end}")
    return True


# ============================================================
# CAPTCHA-DETECTION + OCR
# ============================================================

def grab_captcha_region(cfg: BotConfig, sct: mss.mss) -> Optional[np.ndarray]:
    w = cfg.cap_x2 - cfg.cap_x1
    h = cfg.cap_y2 - cfg.cap_y1
    if w < 10 or h < 10:
        return None
    region = {"left": cfg.cap_x1, "top": cfg.cap_y1, "width": w, "height": h}
    raw = np.array(sct.grab(region))
    return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)


def looks_like_captcha(img_bgr: np.ndarray) -> Tuple[bool, float]:
    """
    Heuristik: Captcha-Box hat hohen Kontrast + viele schwarz/weiss-Pixel.
    Normaler Spiel-Hintergrund (Wasser/Sand) hat geringeren Kontrast.

    Returns (is_captcha, score 0..1)
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # Score = Anteil sehr dunkler ODER sehr heller Pixel
    very_dark = (gray < 50).sum()
    very_bright = (gray > 220).sum()
    total = gray.size
    contrast_ratio = (very_dark + very_bright) / total
    # Standardabweichung als zusaetzliches Indiz
    std = float(gray.std())
    score = min(1.0, contrast_ratio * 2.5 + (std / 200.0))
    return contrast_ratio > 0.18 and std > 55, score


def preprocess_for_ocr(img_bgr: np.ndarray) -> list:
    """Erstellt MEHRERE Preprocessing-Varianten fuer Multi-Pass-OCR.
    Tesseract bekommt jede Variante - das Voting nimmt das haeufigste Ergebnis.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Upscale fuer mehr Detail
    scale = max(3, 200 // max(1, h))
    big = cv2.resize(gray, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)

    variants = []

    # Variante 1: Otsu Threshold
    _, v1 = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("otsu", v1))

    # Variante 2: Inverted Otsu (falls heller Text auf dunklem Grund)
    variants.append(("otsu_inv", 255 - v1))

    # Variante 3: Adaptive Threshold
    blur = cv2.GaussianBlur(big, (3, 3), 0)
    v3 = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 21, 10)
    variants.append(("adaptive", v3))

    # Variante 4: Sharpen + Otsu
    kernel_sharp = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharp = cv2.filter2D(big, -1, kernel_sharp)
    _, v4 = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("sharp_otsu", v4))

    return variants


def _ocr_single(prepped: np.ndarray, psm: int = 7) -> str:
    """Einzelner OCR-Lauf mit definiertem PSM-Modus."""
    try:
        text = pytesseract.image_to_string(
            prepped,
            config=(
                f"--psm {psm} --oem 3 "
                "-c tessedit_char_whitelist="
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            ),
        )
        return "".join(c for c in text if c.isalnum())
    except (pytesseract.TesseractNotFoundError, RuntimeError, OSError):
        return ""


def ocr_captcha(img_bgr: np.ndarray, tesseract_path: str = "") -> Optional[str]:
    """Multi-Pass-OCR mit Voting: tippt sich nicht vertippen.
    Liefert nur das Ergebnis, das mehrfach uebereinstimmend gelesen wurde.
    """
    if not _OCR_AVAILABLE:
        return None
    if tesseract_path and os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    try:
        variants = preprocess_for_ocr(img_bgr)
    except cv2.error as exc:
        print(f"[OCR] Preprocessing-Fehler: {exc}")
        return None

    # Sammle Lesungen mit verschiedenen PSM-Modi
    # PSM 7 = single line, PSM 8 = single word, PSM 6 = uniform block
    results: dict = {}
    for name, img in variants:
        for psm in (7, 8, 6):
            text = _ocr_single(img, psm=psm)
            if 3 <= len(text) <= 12:  # plausible Captcha-Laenge
                results[text] = results.get(text, 0) + 1

    if not results:
        return None

    # Voting: nimm das haeufigste Ergebnis
    sorted_results = sorted(results.items(), key=lambda x: -x[1])
    best_text, best_count = sorted_results[0]

    # Nur nehmen wenn mind. 2 OCR-Laeufe das gleiche sahen
    # (verhindert Tippfehler durch einzelne Fehlleistung)
    if best_count < 2:
        # Liefere trotzdem das laengste plausible (Notnagel)
        candidates = sorted(results.keys(), key=lambda t: -len(t))
        if candidates:
            print(f"[OCR] Niedrige Konfidenz - kein Voting-Sieger. Verwende: '{candidates[0]}'")
            return candidates[0]
        return None

    if len(sorted_results) > 1:
        print(f"[OCR] Voting: '{best_text}' x{best_count}, andere: {sorted_results[1:4]}")
    return best_text


def type_captcha_solution(text: str, mode: str) -> None:
    """Tippt die OCR-Loesung - sauber und langsam genug, um Vertipper zu vermeiden."""
    # Kleine Wartezeit damit Spiel-Fenster ready ist
    time.sleep(0.15)

    if mode == "chat":
        # Chat oeffnen
        keyboard.press_and_release("t")
        time.sleep(0.35)  # warte bis Chat offen ist
        # Falls Chat noch was enthaelt -> komplett leeren
        keyboard.press_and_release("ctrl+a")
        time.sleep(0.05)
        keyboard.press_and_release("delete")
        time.sleep(0.10)
        # Zeichenweise tippen mit konstantem Delay
        for ch in text:
            keyboard.write(ch)
            time.sleep(0.06)
        time.sleep(0.20)
        keyboard.press_and_release("enter")
    elif mode == "direct":
        for ch in text:
            keyboard.write(ch)
            time.sleep(0.06)
        time.sleep(0.15)
        keyboard.press_and_release("enter")
    # mode == "none" -> nichts tippen


def save_captcha_log(img_bgr: np.ndarray, ocr_result: Optional[str]) -> str:
    cdir = _captcha_dir()
    os.makedirs(cdir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    fname = os.path.join(cdir, f"captcha_{ts}_{ocr_result or 'noocr'}.png")
    cv2.imwrite(fname, img_bgr)
    return fname


# ============================================================
# BOT-STATE
# ============================================================

class BotState:
    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self.running = False
        self.quit = False
        self.debug = False
        self.last_cycle_end = 0.0
        self.last_captcha_check = 0.0
        self.last_debug_print = 0.0
        self.last_bar_seen = time.time()
        self.last_anti_afk = time.time()
        self.last_focus_check = 0.0
        self.last_hourly_report = time.time()
        self.captcha_active = False
        self.lock = threading.Lock()
        self.request_auto_scan = False
        self.request_captcha_test = False
        self.stats_hits = 0
        self.stats_captchas = 0
        self.session_start = time.time()
        # Cursor-History fuer Velocity-Prediction
        self.cursor_history: list = []
        # Live-Visualizer-Daten (von der GUI gepollt)
        self.last_green_range: Tuple[int, int] = (0, 0)
        self.last_cursor_x: int = 0
        self.last_predicted_x: int = 0
        self.last_velocity: float = 0.0
        self.last_scan_ts: float = 0.0
        self.last_scan_ms: float = 0.0
        self.last_reaction_ms: float = 0.0
        self.avg_click_ms: float = float(max(1, cfg.click_hold_ms))
        self.avg_loop_ms: float = 1.0
        self.last_timing_ms: float = float(cfg.input_lag_ms)
        self.last_time_to_hit_ms: float = 0.0
        self.last_end_boost_ms: float = 0.0
        self.last_in_green: bool = False
        self.last_detection_text: str = "idle"
        # FPS-Tracking
        self._fps_counter: int = 0
        self._fps_window_start: float = time.time()
        self.actual_fps: float = 0.0
        # Auto-Pause State (sich gemerkt running-Status)
        self._auto_paused = False
        # Waffentraining State
        self.wt_running = False
        self.wt_stats_shots = 0
        self.wt_stats_hits = 0
        self.wt_last_target_pos: Optional[Tuple[int, int]] = None
        self.wt_last_scan_ms: float = 0.0
        self.wt_last_detection_text: str = "idle"
        self.wt_fps: float = 0.0
        self._wt_fps_counter: int = 0
        self._wt_fps_window_start: float = time.time()

    def toggle(self):
        with self.lock:
            self.running = not self.running
            if self.running:
                self.captcha_active = False  # nach manuellem Solving zuruecksetzen
            print(f"\n[F6] Bot {'AKTIV' if self.running else 'PAUSIERT'}  "
                  f"(Hits: {self.stats_hits}, Captchas: {self.stats_captchas})")

    def toggle_debug(self):
        self.debug = not self.debug
        print(f"\n[F5] DEBUG-Modus {'AN' if self.debug else 'AUS'}")

    def trigger_quit(self):
        with self.lock:
            self.quit = True
            self.running = False
        print("\n[F12] Beende...")

    def trigger_auto_scan(self):
        self.request_auto_scan = True

    def set_x_start(self):
        x, _ = get_cursor_pos()
        self.cfg.x_start = x
        print(f"[F8] X_START = {x}")

    def set_x_end(self):
        x, _ = get_cursor_pos()
        self.cfg.x_end = x
        print(f"[F9] X_END = {x}")

    def set_scan_y(self):
        _, y = get_cursor_pos()
        self.cfg.scan_y = y
        print(f"[F10] SCAN_Y = {y}")

    def set_cap_top_left(self):
        x, y = get_cursor_pos()
        self.cfg.cap_x1, self.cfg.cap_y1 = x, y
        print(f"[F2] Captcha oben-links = ({x}, {y})")

    def set_cap_bottom_right(self):
        x, y = get_cursor_pos()
        self.cfg.cap_x2, self.cfg.cap_y2 = x, y
        print(f"[F3] Captcha unten-rechts = ({x}, {y})")

    def trigger_captcha_test(self):
        self.request_captcha_test = True

    def toggle_wt(self):
        with self.lock:
            self.wt_running = not self.wt_running
            if self.wt_running:
                self.running = False
            print(f"\n[F1] Waffentraining {'AKTIV' if self.wt_running else 'PAUSIERT'}  "
                  f"(Schuesse: {self.wt_stats_shots}, Treffer: {self.wt_stats_hits})")

    def save_config(self):
        try:
            path = _config_path()
            self.cfg.to_ini(path)
            print(f"[F11] Konfig gespeichert -> {path}")
        except OSError as exc:
            print(f"[F11] Fehler: {exc}")


# ============================================================
# KLICK + CAPTCHA HANDLING
# ============================================================

def _right_click_hold(hold_ms: int = DEFAULT_CLICK_HOLD_MS) -> float:
    """Rechtsklick mit definiertem Hold (zuverlaessiger fuer Minecraft).
    Probiert mehrere Methoden falls eine fehlschlaegt.
    """
    try:
        # Methode 1: rightDown / rightUp (pydirectinput nativ)
        down_start = time.perf_counter()
        pydirectinput.rightDown()
        down_ms = (time.perf_counter() - down_start) * 1000.0
        time.sleep(hold_ms / 1000.0)
        pydirectinput.rightUp()
        return down_ms
    except (AttributeError, TypeError):
        pass
    try:
        # Methode 2: mouseDown / mouseUp mit button-Parameter
        down_start = time.perf_counter()
        pydirectinput.mouseDown(button="right")
        down_ms = (time.perf_counter() - down_start) * 1000.0
        time.sleep(hold_ms / 1000.0)
        pydirectinput.mouseUp(button="right")
        return down_ms
    except (AttributeError, TypeError):
        pass
    # Methode 3: Fallback einfacher rightClick
    click_start = time.perf_counter()
    pydirectinput.rightClick()
    return (time.perf_counter() - click_start) * 1000.0


def perform_click_cycle(cfg: BotConfig) -> float:
    print("  -> HIT! Rechtsklick #1 (fangen)", flush=True)
    first_click_ms = _right_click_hold(cfg.click_hold_ms)
    time.sleep(cfg.second_click_delay)
    print("  -> Rechtsklick #2 (auswerfen)", flush=True)
    _right_click_hold(cfg.click_hold_ms)
    return first_click_ms


def perform_anti_afk() -> None:
    """Mini-Mausbewegung um AFK-Kick zu vermeiden (1px nach rechts/wieder zurueck)."""
    try:
        x, y = get_cursor_pos()
        # Win32 SetCursorPos statt pydirectinput, damit Spiel-Kamera nicht zuckt
        ctypes.windll.user32.SetCursorPos(x + 1, y)
        time.sleep(0.05)
        ctypes.windll.user32.SetCursorPos(x, y)
    except OSError:
        pass


def check_focus_window(cfg: BotConfig) -> bool:
    """True wenn Spielfenster im Vordergrund ist (oder Feature deaktiviert)."""
    if not cfg.auto_pause_on_focus_loss:
        return True
    title = get_foreground_title()
    if not title:
        return True
    return cfg.focus_window_keyword.lower() in title.lower()


def estimate_click_timing_ms(state: BotState) -> float:
    """Schaetzt, wie weit der Bot vorhalten muss, bis der Klick im Spiel ankommt."""
    cfg = state.cfg
    manual_ms = float(cfg.input_lag_ms)
    if not cfg.auto_timing_enabled:
        return max(0.0, manual_ms)
    measured_ms = (
        (state.last_scan_ms * 0.5)
        + state.avg_loop_ms
        + state.avg_click_ms
        + float(cfg.click_hold_ms)
        + float(cfg.timing_safety_ms)
    )
    # input_lag_ms bleibt als Feinjustierung erhalten: + frueher, - spaeter.
    return max(0.0, measured_ms + manual_ms)


def end_zone_timing_boost_ms(cfg: BotConfig, green_min: int, green_max: int,
                             bar_width: int, velocity_px_per_sec: float) -> float:
    """Gibt extra Vorhaltezeit, wenn die Trefferzone am Ende der Laufbahn liegt."""
    if bar_width <= 1 or velocity_px_per_sec == 0:
        return 0.0
    if velocity_px_per_sec > 0:
        # Cursor laeuft nach rechts: rechte/hintere Trefferzonen brauchen mehr Vorhalt.
        end_ratio = green_max / max(1, bar_width)
    else:
        # Cursor laeuft nach links: linkes Ende ist dann die knappe Endzone.
        end_ratio = 1.0 - (green_min / max(1, bar_width))
    if end_ratio <= 0.62:
        return 0.0
    pressure = min(1.0, (end_ratio - 0.62) / 0.38)
    return float(cfg.end_zone_boost_ms) * pressure


def time_until_range_ms(pos: int, velocity_px_per_sec: float, left: int, right: int) -> float:
    if left <= pos <= right:
        return 0.0
    if velocity_px_per_sec > 0 and pos < left:
        return ((left - pos) / velocity_px_per_sec) * 1000.0
    if velocity_px_per_sec < 0 and pos > right:
        return ((pos - right) / abs(velocity_px_per_sec)) * 1000.0
    return float("inf")


# ============================================================
# WAFFENTRAINING DETECTION + AIM
# ============================================================

def wt_detect_target(cfg: BotConfig, sct: mss.mss) -> Optional[Tuple[int, int]]:
    """Erkennt rote Ziele auf dem gesamten Bildschirm und gibt den Mittelpunkt zurueck."""
    try:
        mon = sct.monitors[cfg.monitor_index]
    except (IndexError, KeyError):
        mon = sct.monitors[1]
    region = {
        "left": mon.get("left", 0),
        "top": mon.get("top", 0),
        "width": mon.get("width", cfg.screen_w),
        "height": mon.get("height", cfg.screen_h),
    }
    try:
        raw = np.array(sct.grab(region))
    except (OSError, mss.exception.ScreenShotError):
        return None

    if cfg.wt_use_hsv:
        bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(
            hsv,
            np.array([cfg.wt_hsv_h_low1, cfg.wt_hsv_s_min, cfg.wt_hsv_v_min]),
            np.array([cfg.wt_hsv_h_high1, 255, 255]),
        )
        mask2 = cv2.inRange(
            hsv,
            np.array([cfg.wt_hsv_h_low2, cfg.wt_hsv_s_min, cfg.wt_hsv_v_min]),
            np.array([cfg.wt_hsv_h_high2, 255, 255]),
        )
        mask = mask1 | mask2
    else:
        rgb = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGB)
        mask = color_match_mask(rgb, cfg.wt_target_rgb, cfg.wt_threshold).astype(np.uint8) * 255

    pixel_count = int(np.sum(mask > 0))
    if pixel_count < cfg.wt_min_target_pixels:
        return None

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < cfg.wt_min_target_pixels:
        return None

    M = cv2.moments(largest)
    if M["m00"] == 0:
        return None
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])

    abs_x = cx
    abs_y = cy
    return (abs_x, abs_y)


def wt_move_and_shoot(cfg: BotConfig, target_x: int, target_y: int) -> float:
    """Bewegt die Maus zum Ziel und schiesst. Gibt Klick-Dauer in ms zurueck."""
    if cfg.wt_instant_aim:
        try:
            ctypes.windll.user32.SetCursorPos(target_x, target_y)
        except OSError:
            pydirectinput.moveTo(target_x, target_y)
    else:
        pydirectinput.moveTo(target_x, target_y)

    if cfg.wt_aim_settle_ms > 0:
        time.sleep(cfg.wt_aim_settle_ms / 1000.0)

    return _right_click_hold(cfg.wt_shot_hold_ms)


def wt_loop(state: BotState) -> None:
    """Waffentraining-Hauptschleife: erkennt rote Ziele, zielt und schiesst."""
    cfg = state.cfg
    with mss.mss() as sct:
        while not state.quit:
            if not state.wt_running:
                time.sleep(0.05)
                continue

            scan_start = time.perf_counter()
            target = wt_detect_target(cfg, sct)
            state.wt_last_scan_ms = (time.perf_counter() - scan_start) * 1000.0

            now = time.time()
            state._wt_fps_counter += 1
            if (now - state._wt_fps_window_start) >= 1.0:
                state.wt_fps = state._wt_fps_counter / (now - state._wt_fps_window_start)
                state._wt_fps_counter = 0
                state._wt_fps_window_start = now

            if target is None:
                state.wt_last_target_pos = None
                state.wt_last_detection_text = "kein Ziel"
                time.sleep(cfg.wt_scan_interval)
                continue

            tx, ty = target
            state.wt_last_target_pos = (tx, ty)
            state.wt_last_detection_text = f"Ziel @ ({tx}, {ty})"
            state.wt_stats_shots += 1

            click_ms = wt_move_and_shoot(cfg, tx, ty)
            state.wt_stats_hits += 1

            print(
                f"[WT #{state.wt_stats_hits}] Ziel@({tx},{ty}) "
                f"scan={state.wt_last_scan_ms:.1f}ms click={click_ms:.1f}ms",
                flush=True,
            )

            if cfg.wt_shot_delay > 0:
                time.sleep(cfg.wt_shot_delay)


def handle_captcha(state: BotState, sct: mss.mss) -> None:
    cfg = state.cfg
    if not cfg.captcha_enabled:
        return
    img = grab_captcha_region(cfg, sct)
    if img is None:
        return

    is_cap, score = looks_like_captcha(img)
    if not is_cap:
        return

    state.captcha_active = True
    state.stats_captchas += 1
    print(f"\n[CAPTCHA] !!! Erkannt (score={score:.2f}) -> versuche OCR ...")
    beep_alert(cfg.sound_enabled)
    if cfg.discord_webhook_url:
        send_discord(cfg.discord_webhook_url,
                     f":robot: Captcha erkannt! (#{state.stats_captchas}, score={score:.2f})")

    ocr_text = ocr_captcha(img, cfg.tesseract_path) if _OCR_AVAILABLE else None
    saved_path = save_captcha_log(img, ocr_text)
    print(f"[CAPTCHA] Screenshot gespeichert: {saved_path}")

    if ocr_text and len(ocr_text) >= 3:
        print(f"[CAPTCHA] OCR-Ergebnis: '{ocr_text}' -> tippe ein ({cfg.type_mode}-Modus)")
        time.sleep(0.4)
        type_captcha_solution(ocr_text, cfg.type_mode)
        time.sleep(2.0)
        # Nach Eingabe weiterscannen - falls falsch, taucht Captcha wieder auf
        state.captcha_active = False
        print("[CAPTCHA] Eingabe gesendet, scanne weiter.")
    else:
        print("[CAPTCHA] OCR fehlgeschlagen oder Tesseract nicht installiert.")
        print("[CAPTCHA] Bitte MANUELL loesen und F6 zum Weitermachen druecken.")
        with state.lock:
            state.running = False


# ============================================================
# MAIN LOOP
# ============================================================

def main_loop(state: BotState) -> None:
    cfg = state.cfg
    last_loop_perf = time.perf_counter()
    with mss.mss() as sct:
        # Erster Auto-Scan
        if auto_scan_bar(cfg, sct):
            print("[INFO] Auto-Scan beim Start: erfolgreich.")

        while not state.quit:
            loop_perf = time.perf_counter()
            loop_ms = (loop_perf - last_loop_perf) * 1000.0
            last_loop_perf = loop_perf
            if loop_ms < 250.0:
                state.avg_loop_ms = (state.avg_loop_ms * 0.85) + (loop_ms * 0.15)

            if state.request_auto_scan:
                state.request_auto_scan = False
                auto_scan_bar(cfg, sct)

            if state.request_captcha_test:
                state.request_captcha_test = False
                if not cfg.captcha_enabled:
                    print("\n[F4] Captcha ist deaktiviert.")
                    continue
                img = grab_captcha_region(cfg, sct)
                if img is not None:
                    is_cap, score = looks_like_captcha(img)
                    path = save_captcha_log(img, "test")
                    txt = ocr_captcha(img, cfg.tesseract_path)
                    print(f"\n[F4] is_captcha={is_cap} score={score:.2f} OCR='{txt}' -> {path}")
                    # Volle Loesung: tippen wenn OCR was gefunden hat
                    if txt and len(txt) >= 3 and cfg.type_mode != "none":
                        print(f"[F4] tippe '{txt}' im {cfg.type_mode}-Modus...")
                        time.sleep(0.4)
                        type_captcha_solution(txt, cfg.type_mode)
                        print("[F4] Eingabe gesendet.")

            now = time.time()

            # AUTO-PAUSE: pausiere/resume basierend auf Fenster-Fokus
            if (now - state.last_focus_check) > 1.0:
                state.last_focus_check = now
                in_focus = check_focus_window(cfg)
                if not in_focus and state.running:
                    state._auto_paused = True
                    state.running = False
                    print("[AUTO-PAUSE] Spielfenster verlassen -> Bot pausiert.")
                elif in_focus and state._auto_paused and not state.running:
                    state._auto_paused = False
                    state.running = True
                    print("[AUTO-PAUSE] Spielfenster wieder aktiv -> Bot laeuft weiter.")

            if not state.running:
                time.sleep(0.05)
                continue

            # ANTI-AFK
            if cfg.anti_afk_enabled and (now - state.last_anti_afk) > cfg.anti_afk_interval_sec:
                state.last_anti_afk = now
                # Nicht direkt waehrend Klick-Cooldown ausloesen
                if (now - state.last_cycle_end) > 1.0:
                    perform_anti_afk()
                    print("[ANTI-AFK] Mini-Mausbewegung gesendet")

            # Stuendlicher Webhook-Report (optional)
            if cfg.discord_webhook_url and (now - state.last_hourly_report) > 3600:
                state.last_hourly_report = now
                runtime_min = int((now - state.session_start) / 60)
                send_discord(cfg.discord_webhook_url,
                             f":bar_chart: Status: {state.stats_hits} Hits, "
                             f"{state.stats_captchas} Captchas, Runtime {runtime_min}min")

            # Captcha-Check periodisch
            if cfg.captcha_enabled and now - state.last_captcha_check > cfg.captcha_check_interval:
                state.last_captcha_check = now
                handle_captcha(state, sct)
                if not state.running:
                    continue

            # Cooldown nach Klick
            if now - state.last_cycle_end < cfg.post_cycle_cooldown:
                time.sleep(0.01)
                continue

            # Bar-Scan (Multi-Line: ganzer Streifen statt nur 1 Pixelzeile)
            width = cfg.x_end - cfg.x_start
            if width <= 1:
                time.sleep(0.1)
                continue

            band_h = max(4, cfg.scan_band)
            band_top = max(0, cfg.scan_y - band_h // 2)
            # Multi-Monitor Support
            try:
                mon = sct.monitors[cfg.monitor_index]
            except (IndexError, KeyError):
                mon = sct.monitors[1]
            mon_left = mon.get("left", 0)
            mon_top = mon.get("top", 0)
            region = {
                "left": cfg.x_start + mon_left,
                "top": band_top + mon_top,
                "width": width,
                "height": band_h,
            }
            scan_start = time.perf_counter()
            raw = np.array(sct.grab(region))                     # band_h x W x 4
            band_rgb = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGB)     # band_h x W x 3

            # Vektorisiert: Maske ueber den ganzen Streifen,
            # dann horizontal kollabieren -> "an dieser X-Position gibt es Gruen/Cyan"
            green_band = color_match_mask(band_rgb, cfg.green_rgb, cfg.threshold)
            cursor_band = color_match_mask(band_rgb, cfg.cursor_rgb, cfg.threshold)
            green_cols = np.any(green_band, axis=0)              # W boolean
            cursor_cols = np.any(cursor_band, axis=0)            # W boolean

            green_xs = np.where(green_cols)[0]
            cursor_xs = np.where(cursor_cols)[0]
            state.last_scan_ms = (time.perf_counter() - scan_start) * 1000.0

            # DEBUG: alle 0.5 s Status ausgeben
            if state.debug and (now - state.last_debug_print) > 0.5:
                state.last_debug_print = now
                if len(green_xs) == 0 and len(cursor_xs) == 0:
                    msg = (f"DBG: NICHTS gesehen im Band Y={band_top}..{band_top+band_h} "
                           f"X={cfg.x_start}..{cfg.x_end}")
                elif len(green_xs) == 0:
                    msg = f"DBG: cursor @ X={int(cursor_xs.mean())} aber KEIN GRUEN"
                elif len(cursor_xs) == 0:
                    msg = f"DBG: gruen @ X=[{green_xs.min()}..{green_xs.max()}] aber KEIN CURSOR"
                else:
                    cc = int((cursor_xs.min() + cursor_xs.max()) // 2)
                    msg = (f"DBG: cursor@{cc} ({len(cursor_xs)}px) "
                           f"gruen=[{green_xs.min()}..{green_xs.max()}] ({len(green_xs)}px)")
                print(msg, flush=True)

            if len(green_xs) == 0:
                # Bar nicht aktiv -> History resetten
                state.cursor_history.clear()
                state.last_green_range = (0, 0)
                state.last_cursor_x = 0
                state.last_predicted_x = 0
                state.last_in_green = False
                state.last_detection_text = "bar not visible"
                time.sleep(1.0 / cfg.scan_fps)
                continue

            # Bar wurde gesehen
            state.last_bar_seen = now

            if len(cursor_xs) < DEFAULT_MIN_CURSOR_PIXELS:
                state.last_green_range = (int(green_xs.min()), int(green_xs.max()))
                state.last_cursor_x = 0
                state.last_predicted_x = 0
                state.last_in_green = False
                state.last_detection_text = "green visible, cursor lost"
                time.sleep(1.0 / cfg.scan_fps)
                continue

            # ----------------------------------------------------------
            # VELOCITY-PREDICTION
            # ----------------------------------------------------------
            cursor_center = int((cursor_xs.min() + cursor_xs.max()) // 2)
            sample_ts = time.perf_counter()
            state.cursor_history.append((sample_ts, cursor_center))
            if len(state.cursor_history) > VELOCITY_WINDOW:
                state.cursor_history.pop(0)

            velocity_px_per_sec = 0.0
            if len(state.cursor_history) >= 2:
                t0, x0 = state.cursor_history[0]
                t1, x1 = state.cursor_history[-1]
                dt = t1 - t0
                if dt > 0:
                    velocity_px_per_sec = (x1 - x0) / dt

            # Inner-Green-Zone: nur mittig klicken, nicht am Rand.
            green_min, green_max = int(green_xs.min()), int(green_xs.max())
            green_width = green_max - green_min
            inner_pad = int(green_width * cfg.green_inner_ratio)
            inner_left = green_min + inner_pad + DEFAULT_HIT_TOLERANCE_PX
            inner_right = green_max - inner_pad - DEFAULT_HIT_TOLERANCE_PX
            if inner_left > inner_right:
                inner_left, inner_right = green_min, green_max

            end_boost_ms = end_zone_timing_boost_ms(
                cfg, green_min, green_max, width, velocity_px_per_sec
            )
            timing_ms = estimate_click_timing_ms(state) + end_boost_ms
            predicted_pos = cursor_center + int(velocity_px_per_sec * (timing_ms / 1000.0))

            in_green_now = inner_left <= cursor_center <= inner_right
            predicted_in_inner = inner_left <= predicted_pos <= inner_right
            time_to_hit_ms = time_until_range_ms(cursor_center, velocity_px_per_sec, inner_left, inner_right)

            should_click = predicted_in_inner or time_to_hit_ms <= timing_ms

            # Live-Visualizer-Daten in State schreiben (fuer GUI)
            state.last_green_range = (green_min, green_max)
            state.last_cursor_x = cursor_center
            state.last_predicted_x = predicted_pos
            state.last_velocity = velocity_px_per_sec
            state.last_timing_ms = timing_ms
            state.last_end_boost_ms = end_boost_ms
            state.last_time_to_hit_ms = 0.0 if time_to_hit_ms == float("inf") else time_to_hit_ms
            state.last_scan_ts = now
            state.last_in_green = should_click
            state.last_detection_text = "locked: hit window" if should_click else "tracking"

            # FPS-Tracking
            state._fps_counter += 1
            if (now - state._fps_window_start) >= 1.0:
                state.actual_fps = state._fps_counter / (now - state._fps_window_start)
                state._fps_counter = 0
                state._fps_window_start = now

            if should_click:
                state.last_reaction_ms = (time.perf_counter() - scan_start) * 1000.0
                state.stats_hits += 1
                print(
                    f"\n[HIT #{state.stats_hits}] cursor@{cursor_center} "
                    f"vel={velocity_px_per_sec:+.0f}px/s "
                    f"pred@{predicted_pos} "
                    f"eta={time_to_hit_ms:.1f}ms "
                    f"lead={timing_ms:.1f}ms "
                    f"boost={end_boost_ms:.1f}ms "
                    f"green=[{green_min}..{green_max}]",
                    flush=True,
                )
                first_click_ms = perform_click_cycle(cfg)
                state.avg_click_ms = (state.avg_click_ms * 0.7) + (first_click_ms * 0.3)
                state.last_cycle_end = time.time()
                state.cursor_history.clear()
                continue

            # Wenn Bar aktiv ist: kein Sleep -> maximale Scan-Frequenz
            # (nur ein winziges yield, damit andere Threads laufen koennen)
            time.sleep(0.0005)


# ============================================================
# ENTRY POINT
# ============================================================

def detect_screen_size() -> Tuple[int, int]:
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def print_banner(cfg: BotConfig) -> None:
    print("=" * 70)
    print("  MINECRAFT FISHING BOT  v3   (Bar + Captcha)")
    print("=" * 70)
    print(f"  Bildschirm: {cfg.screen_w} x {cfg.screen_h}")
    print(f"  Bar:     SCAN_Y={cfg.scan_y}  X={cfg.x_start}..{cfg.x_end}")
    print(f"  Captcha: ({cfg.cap_x1},{cfg.cap_y1}) -> ({cfg.cap_x2},{cfg.cap_y2})")
    print(f"  Farben:  Cursor{cfg.cursor_rgb}  Green{cfg.green_rgb}  TOL={cfg.threshold}")
    auto_timing = "AN" if cfg.auto_timing_enabled else "AUS"
    print(f"  Timing:  AutoTiming={auto_timing}  InputLag={cfg.input_lag_ms}ms  "
          f"Safety={cfg.timing_safety_ms}ms  EndBoost={cfg.end_zone_boost_ms}ms  "
          f"InnerRatio={cfg.green_inner_ratio}  ScanFPS={cfg.scan_fps}")
    print(f"  OCR verfuegbar: {_OCR_AVAILABLE}    Type-Mode: {cfg.type_mode}")
    print("-" * 70)
    print("  HOTKEYS")
    print("    F2/F3  Captcha-Bereich kalibrieren (oben-links / unten-rechts)")
    print("    F4     Captcha-Test (macht Screenshot + OCR)")
    print("    F5     DEBUG-Modus an/aus (zeigt was der Bot sieht)")
    print("    F6     Bot Start/Stop          F12  Beenden")
    print("    F7     Auto-Scan Bar")
    print("    F8/F9  X_START / X_END         F10  SCAN_Y")
    print("    F11    Konfig speichern (config.ini)")
    print("=" * 70)
    print("  Status: PAUSIERT - druecke F6 zum Starten")
    print("=" * 70)


def main() -> None:
    sw, sh = detect_screen_size()
    config_path = _config_path()
    cfg = BotConfig.from_ini(config_path, sw, sh)
    print(f"[INFO] App-Ordner: {_app_dir()}")
    if os.path.exists(config_path):
        print(f"[INFO] Konfig geladen aus: {config_path}")
    else:
        print(f"[INFO] Keine Konfig gefunden ({config_path}) - verwende Defaults")

    # Tesseract Pfad probieren falls leer
    if _OCR_AVAILABLE and not cfg.tesseract_path:
        for guess in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.exists(guess):
                cfg.tesseract_path = guess
                break

    print_banner(cfg)
    if not _OCR_AVAILABLE:
        print("[WARN] pytesseract nicht installiert -> Captchas nur manuell loesbar.")
    elif not cfg.tesseract_path:
        print("[WARN] tesseract.exe nicht gefunden. Installiere von:")
        print("       https://github.com/UB-Mannheim/tesseract/wiki")
        print("       Dann Pfad in config.ini eintragen oder via [F11] speichern.")

    state = BotState(cfg)

    keyboard.add_hotkey("f1", state.toggle_wt)
    keyboard.add_hotkey("f2", state.set_cap_top_left)
    keyboard.add_hotkey("f3", state.set_cap_bottom_right)
    keyboard.add_hotkey("f4", state.trigger_captcha_test)
    keyboard.add_hotkey("f5", state.toggle_debug)
    keyboard.add_hotkey("f6", state.toggle)
    keyboard.add_hotkey("f7", state.trigger_auto_scan)
    keyboard.add_hotkey("f8", state.set_x_start)
    keyboard.add_hotkey("f9", state.set_x_end)
    keyboard.add_hotkey("f10", state.set_scan_y)
    keyboard.add_hotkey("f11", state.save_config)
    keyboard.add_hotkey("f12", state.trigger_quit)

    worker = threading.Thread(target=main_loop, args=(state,), daemon=True)
    worker.start()
    wt_worker = threading.Thread(target=wt_loop, args=(state,), daemon=True)
    wt_worker.start()

    try:
        while not state.quit:
            time.sleep(0.1)
    except KeyboardInterrupt:
        state.trigger_quit()

    time.sleep(0.3)
    print(f"\n[OK] Beendet. Hits: {state.stats_hits}, Captchas: {state.stats_captchas}")
    sys.exit(0)


if __name__ == "__main__":
    main()
