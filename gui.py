"""
GUI fuer den Minecraft Fishing Bot.
Mit Live-Bar-Preview, Hotkey-Editor und Captcha-Solver-Hotkey.

Hotkeys (auch wenn Fenster im Hintergrund):
    F2/F3   Captcha-Bereich kalibrieren
    F4      Captcha LESEN + EINTIPPEN
    F5      Debug an/aus
    F6      Bot Start/Stop
    F7      Auto-Scan
    F8/F9   X_START / X_END
    F10     SCAN_Y
    F11     Konfig speichern
    F12     Beenden
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
import ctypes
import datetime as _dt
import hashlib
import hmac
import json
import random
import uuid
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk
import cv2
import keyboard
import mss
import numpy as np
from PIL import Image

import main as botcore


ACCENT_COLORS = {
    "Ice": "#77b7d9",
    "Lime": "#7fa66a",
    "Amethyst": "#9b7ad9",
    "Redstone": "#b85454",
    "Gold": "#c9a35a",
}
BG = "#111111"
PANEL = "#242424"
PANEL_2 = "#303030"
PANEL_3 = "#3b3b3b"
LINE = "#4a4a4a"
TEXT_MUTED = "#b8b8b8"

# License secrets loaded from environment variables.
# Set ANGELBOT_ADMIN_HASH and ANGELBOT_LICENSE_SECRET before running.
# Defaults are dev-only placeholders.
ADMIN_PASSWORD_HASH = os.environ.get("ANGELBOT_ADMIN_HASH", "")
LICENSE_SECRET = os.environ.get("ANGELBOT_LICENSE_SECRET", "change-me").encode("utf-8")
LICENSE_FILE = "license.json"


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        value = "8b5cf6"
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _blend(a: str, b: str, t: float) -> str:
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    return f"#{int(ar + (br - ar) * t):02x}{int(ag + (bg - ag) * t):02x}{int(ab + (bb - ab) * t):02x}"


def _set_capture_mode(window: tk.Toplevel, stream_safe: bool) -> None:
    if os.name != "nt":
        return
    try:
        hwnd = int(window.winfo_id())
        affinity = 0x11 if stream_safe else 0x00  # WDA_EXCLUDEFROMCAPTURE / none
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, affinity)
    except (AttributeError, OSError, ValueError):
        pass


def _license_path() -> str:
    return os.path.join(botcore._app_dir(), LICENSE_FILE)


def get_hwid() -> str:
    raw = f"{uuid.getnode()}|{os.environ.get('COMPUTERNAME', '')}|angelbotv4"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def _admin_ok(password: str) -> bool:
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, ADMIN_PASSWORD_HASH)


def generate_license_code(hwid: str, hours: int) -> str:
    clean_hwid = "".join(ch for ch in hwid.upper() if ch.isalnum())[:16] or "ANY"
    expiry = (_dt.datetime.now() + _dt.timedelta(hours=max(1, int(hours)))).strftime("%Y%m%d%H")
    payload = f"AB4|{clean_hwid}|{expiry}"
    sig = hmac.new(LICENSE_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:18].upper()
    return f"AB4-{clean_hwid}-{expiry}-{sig}"


def validate_license_code(code: str, hwid: Optional[str] = None) -> tuple[bool, str]:
    hwid = (hwid or get_hwid()).upper()
    parts = code.strip().upper().replace(" ", "").split("-")
    if len(parts) != 4 or parts[0] != "AB4":
        return False, "Format ungueltig"
    _, code_hwid, expiry, sig = parts
    if code_hwid not in (hwid, "ANY"):
        return False, "Code ist fuer eine andere HWID"
    try:
        if len(expiry) == 8:
            exp_dt = _dt.datetime.strptime(expiry, "%Y%m%d")
        else:
            exp_dt = _dt.datetime.strptime(expiry, "%Y%m%d%H")
    except ValueError:
        return False, "Ablaufdatum ungueltig"
    if exp_dt < _dt.datetime.now():
        return False, "Code ist abgelaufen"
    payload = f"AB4|{code_hwid}|{expiry}"
    expected = hmac.new(LICENSE_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:18].upper()
    if not hmac.compare_digest(sig, expected):
        return False, "Signatur ungueltig"
    return True, f"OK bis {exp_dt.strftime('%Y-%m-%d %H:00')}"


def load_saved_license() -> str:
    try:
        with open(_license_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("code", ""))
    except (OSError, json.JSONDecodeError):
        return ""


def save_license(code: str) -> None:
    try:
        with open(_license_path(), "w", encoding="utf-8") as f:
            json.dump({"code": code.strip(), "activated_at": time.time()}, f, indent=2)
    except OSError:
        pass


def _make_galaxy_image(width: int, height: int, accent: str) -> Image.Image:
    rng = random.Random(44)
    img = Image.new("RGB", (width, height), BG)
    px = img.load()
    ar, ag, ab = _hex_to_rgb(accent)
    for y in range(height):
        for x in range(width):
            nx = x / max(1, width - 1)
            ny = y / max(1, height - 1)
            edge = 1.0 if (x < 6 or y < 6 or x > width - 7 or y > height - 7) else 0.0
            slot = 0.18 if ((x // 42) % 2 == 0 and (y // 42) % 2 == 0) else 0.0
            glow = max(0.0, 1.0 - (((nx - 0.2) ** 2) / 0.11 + ((ny - 0.45) ** 2) / 0.42))
            r = int(24 + slot * 28 + edge * 42 + ar * glow * 0.10)
            g = int(24 + slot * 28 + edge * 42 + ag * glow * 0.10)
            b = int(24 + slot * 28 + edge * 42 + ab * glow * 0.10)
            px[x, y] = (min(255, r), min(255, g), min(255, b))
    for _ in range(170):
        x = rng.randrange(width)
        y = rng.randrange(height)
        bright = rng.randrange(75, 150)
        size = 1 if rng.random() < 0.9 else 2
        for yy in range(y, min(height, y + size)):
            for xx in range(x, min(width, x + size)):
                px[xx, yy] = (bright, bright, min(255, bright + rng.randrange(0, 25)))
    return img


# ============================================================
# stdout -> Queue
# ============================================================

class _QueueWriter:
    def __init__(self, q: queue.Queue, mirror=None):
        self.q = q
        self.mirror = mirror

    def write(self, msg: str):
        if msg:
            self.q.put(msg)
        if self.mirror:
            try:
                self.mirror.write(msg)
            except (ValueError, OSError):
                pass

    def flush(self):
        if self.mirror:
            try:
                self.mirror.flush()
            except (ValueError, OSError):
                pass


def _bot_worker(state: botcore.BotState):
    botcore.main_loop(state)


def _wt_worker(state: botcore.BotState):
    botcore.wt_loop(state)


# ============================================================
# Hotkey-Recorder Dialog
# ============================================================

class HotkeyDialog(ctk.CTkToplevel):
    """Wartet auf Tastendruck und speichert ihn."""

    def __init__(self, parent, action_label: str, current_key: str):
        super().__init__(parent)
        self.title("Hotkey aufnehmen")
        self.geometry("380x200")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[str] = None

        ctk.CTkLabel(self, text=action_label,
                     font=ctk.CTkFont(size=12),
                     text_color="#9ca3af").pack(pady=(20, 4))
        ctk.CTkLabel(self, text="Druecke jetzt die neue Taste...",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(0, 8))
        self.key_label = ctk.CTkLabel(self, text=current_key.upper(),
                                      font=ctk.CTkFont(size=28, weight="bold"),
                                      text_color="#22c55e")
        self.key_label.pack(pady=8)
        self.bind("<Key>", self._on_key)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=10)
        ctk.CTkButton(btns, text="Speichern", width=110,
                      command=self._save).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Abbrechen", width=110, fg_color="#6b7280",
                      command=self.destroy).pack(side="left", padx=6)
        self.focus_set()

    def _on_key(self, event):
        if event.keysym:
            self.result = event.keysym.lower()
            self.key_label.configure(text=self.result.upper())

    def _save(self):
        if not self.result:
            messagebox.showwarning("Hotkey", "Bitte zuerst eine Taste druecken.")
            return
        self.destroy()


# ============================================================
# Hotkey-Editor Window
# ============================================================

HOTKEY_LABELS = {
    "toggle":       "Bot Start / Stop",
    "auto_scan":    "Auto-Scan Bar",
    "save":         "Konfig speichern",
    "quit":         "Beenden",
    "set_x_start":  "X_START setzen",
    "set_x_end":    "X_END setzen",
    "set_scan_y":   "SCAN_Y setzen",
    "set_cap_tl":   "Captcha oben-links",
    "set_cap_br":   "Captcha unten-rechts",
    "captcha_test": "Captcha lesen + tippen",
    "debug":        "Debug-Modus",
}


class HotkeyEditor(ctk.CTkToplevel):
    def __init__(self, parent_gui):
        super().__init__(parent_gui)
        self.title("Hotkeys aendern")
        self.geometry("440x520")
        self.transient(parent_gui)
        self.grab_set()
        self.parent_gui = parent_gui
        self.cfg = parent_gui.cfg
        self.buttons: dict = {}

        ctk.CTkLabel(self, text="HOTKEYS",
                     font=ctk.CTkFont(size=18, weight="bold")
                     ).pack(pady=(16, 6))
        ctk.CTkLabel(self,
                     text="Klick auf eine Taste um sie zu aendern",
                     text_color="#9ca3af",
                     font=ctk.CTkFont(size=11)).pack(pady=(0, 12))

        body = ctk.CTkScrollableFrame(self, height=360)
        body.pack(fill="both", expand=True, padx=20, pady=4)

        for key_id, label in HOTKEY_LABELS.items():
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=label, width=220, anchor="w"
                         ).pack(side="left", padx=(4, 8))
            btn = ctk.CTkButton(row, text=self.cfg.hotkeys.get(key_id, "").upper(),
                                width=120,
                                command=lambda k=key_id, lab=label: self._rebind(k, lab))
            btn.pack(side="left")
            self.buttons[key_id] = btn

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=12)
        ctk.CTkButton(bottom, text="Zuruecksetzen (Defaults)",
                      command=self._reset_defaults, fg_color="#6b7280"
                      ).pack(side="left", padx=4)
        ctk.CTkButton(bottom, text="Schliessen",
                      command=self.destroy).pack(side="right", padx=4)

    def _rebind(self, key_id: str, label: str):
        dlg = HotkeyDialog(self, label, self.cfg.hotkeys.get(key_id, ""))
        self.wait_window(dlg)
        if dlg.result:
            self.cfg.hotkeys[key_id] = dlg.result
            self.buttons[key_id].configure(text=dlg.result.upper())
            self.parent_gui.reregister_hotkeys()
            print(f"[HOTKEY] {label} -> {dlg.result.upper()}")

    def _reset_defaults(self):
        defaults = {
            "toggle": "f6", "auto_scan": "f7", "save": "f11", "quit": "f12",
            "set_x_start": "f8", "set_x_end": "f9", "set_scan_y": "f10",
            "set_cap_tl": "f2", "set_cap_br": "f3",
            "captcha_test": "f4", "debug": "f5",
        }
        self.cfg.hotkeys = dict(defaults)
        for k, btn in self.buttons.items():
            btn.configure(text=defaults[k].upper())
        self.parent_gui.reregister_hotkeys()
        print("[HOTKEY] Auf Defaults zurueckgesetzt.")


# ============================================================
# License Gate + Admin Tool
# ============================================================

class AdminTool(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("AngelBot Admin Tool")
        self.geometry("560x360")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.transient(parent)

        ctk.CTkLabel(self, text="LICENSE GENERATOR",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=ACCENT_COLORS["Ice"]).pack(pady=(18, 4))
        ctk.CTkLabel(self, text="HWID vom Nutzer eintragen oder eigene uebernehmen.",
                     text_color=TEXT_MUTED).pack(pady=(0, 14))

        body = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=8, border_width=1, border_color=LINE)
        body.pack(fill="both", expand=True, padx=18, pady=8)

        self.hwid_entry = ctk.CTkEntry(body, width=390)
        self.hwid_entry.insert(0, get_hwid())
        self.hwid_entry.grid(row=0, column=1, padx=10, pady=(18, 8), sticky="ew")
        ctk.CTkLabel(body, text="HWID", width=90, anchor="w").grid(row=0, column=0, padx=(16, 0), pady=(18, 8))

        self.hours_entry = ctk.CTkEntry(body, width=120)
        self.hours_entry.insert(0, "24")
        self.hours_entry.grid(row=1, column=1, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(body, text="Stunden", width=90, anchor="w").grid(row=1, column=0, padx=(16, 0), pady=8)

        quick = ctk.CTkFrame(body, fg_color="transparent")
        quick.grid(row=1, column=1, padx=(140, 10), pady=8, sticky="w")
        for label, hours in (("1h", 1), ("6h", 6), ("24h", 24), ("7d", 168), ("30d", 720)):
            ctk.CTkButton(quick, text=label, width=46, height=28,
                          fg_color=PANEL_3, hover_color=LINE,
                          command=lambda h=hours: self._set_hours(h)).pack(side="left", padx=3)

        self.output = ctk.CTkTextbox(body, height=84, font=ctk.CTkFont("Consolas", 12))
        self.output.grid(row=2, column=0, columnspan=2, padx=16, pady=12, sticky="ew")
        self.output.configure(state="disabled")

        ctk.CTkButton(body, text="Code generieren", height=36,
                      fg_color=ACCENT_COLORS["Ice"],
                      command=self._generate).grid(row=3, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="ew")
        body.grid_columnconfigure(1, weight=1)

    def _generate(self):
        try:
            hours = int(self.hours_entry.get().strip())
        except ValueError:
            hours = 24
        code = generate_license_code(self.hwid_entry.get().strip(), hours)
        self.output.configure(state="normal")
        self.output.delete("0.0", "end")
        self.output.insert("end", code)
        self.output.configure(state="disabled")

    def _set_hours(self, hours: int):
        self.hours_entry.delete(0, "end")
        self.hours_entry.insert(0, str(hours))


class LicenseGate(ctk.CTk):
    def __init__(self, cfg: botcore.BotConfig):
        super().__init__()
        self.cfg = cfg
        self.authorized = False
        self.is_admin = False
        self.title("AngelBot v4 - License")
        self.geometry("640x520")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        self._hero_img = ctk.CTkImage(
            light_image=_make_galaxy_image(640, 190, cfg.hud_color),
            dark_image=_make_galaxy_image(640, 190, cfg.hud_color),
            size=(640, 190),
        )
        hero = ctk.CTkLabel(self, image=self._hero_img, text="")
        hero.pack(fill="x")

        panel = ctk.CTkFrame(self, fg_color=PANEL, border_width=1, border_color=LINE, corner_radius=8)
        panel.pack(fill="both", expand=True, padx=22, pady=18)

        ctk.CTkLabel(panel, text="ANGELBOT V4",
                     font=ctk.CTkFont(size=28, weight="bold"),
                     text_color=cfg.hud_color).pack(pady=(18, 2))
        ctk.CTkLabel(panel, text=f"HWID: {get_hwid()}",
                     font=ctk.CTkFont("Consolas", 12),
                     text_color=TEXT_MUTED).pack(pady=(0, 14))
        ctk.CTkButton(panel, text="HWID kopieren", width=150, height=30,
                      fg_color=PANEL_3, hover_color=LINE,
                      command=self._copy_hwid).pack(pady=(0, 10))

        self.license_entry = ctk.CTkEntry(panel, width=470, placeholder_text="License Code")
        self.license_entry.pack(pady=6)
        saved = load_saved_license()
        if saved:
            ok, _ = validate_license_code(saved)
            if ok:
                self.license_entry.insert(0, saved)

        self.admin_entry = ctk.CTkEntry(panel, width=470, placeholder_text="Admin Passwort", show="*")
        self.admin_entry.pack(pady=6)
        self.status = ctk.CTkLabel(panel, text="", text_color=TEXT_MUTED)
        self.status.pack(pady=(2, 10))

        btns = ctk.CTkFrame(panel, fg_color="transparent")
        btns.pack(fill="x", padx=48, pady=4)
        ctk.CTkButton(btns, text="Mit License starten", height=38,
                      fg_color=cfg.hud_color,
                      command=self._license_login).pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(btns, text="Admin Login", height=38,
                      fg_color=ACCENT_COLORS["Ice"],
                      command=self._admin_login).pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(panel, text="Admin Tool oeffnen", height=34,
                      fg_color=PANEL_2, hover_color=_blend(PANEL_2, "#ffffff", 0.08),
                      command=self._open_admin_tool).pack(fill="x", padx=52, pady=(8, 0))

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _license_login(self):
        code = self.license_entry.get().strip()
        ok, msg = validate_license_code(code)
        if not ok:
            self.status.configure(text=msg, text_color="#f43f5e")
            return
        save_license(code)
        self.authorized = True
        self.is_admin = False
        self.destroy()

    def _admin_login(self):
        if not _admin_ok(self.admin_entry.get()):
            self.status.configure(text="Admin Passwort falsch", text_color="#f43f5e")
            return
        self.authorized = True
        self.is_admin = True
        self.destroy()

    def _open_admin_tool(self):
        if not _admin_ok(self.admin_entry.get()):
            self.status.configure(text="Admin Passwort fuer Generator eingeben", text_color="#f59e0b")
            return
        AdminTool(self)

    def _copy_hwid(self):
        self.clipboard_clear()
        self.clipboard_append(get_hwid())
        self.status.configure(text="HWID kopiert", text_color=ACCENT_COLORS["Lime"])


# ============================================================
# Bildschirm-Overlay
# ============================================================

class ScanOverlay(ctk.CTkToplevel):
    """Transparenter HUD-Layer fuer Scan-Band, Captcha-Area und Detection-State."""

    def __init__(self, parent_gui):
        super().__init__(parent_gui)
        self.parent_gui = parent_gui
        self.bot = parent_gui.bot
        self.cfg = parent_gui.cfg
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", max(0.2, min(1.0, self.cfg.overlay_opacity)))
        try:
            self.attributes("-transparentcolor", "black")
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self._visible = False
        self._sync_geometry()
        self.after(80, self._tick)

    def _monitor(self):
        try:
            return self.parent_gui._sct.monitors[self.cfg.monitor_index]
        except (IndexError, KeyError, AttributeError):
            return {"left": 0, "top": 0, "width": self.cfg.screen_w, "height": self.cfg.screen_h}

    def _sync_geometry(self):
        mon = self._monitor()
        w = int(mon.get("width", self.cfg.screen_w))
        h = int(mon.get("height", self.cfg.screen_h))
        left = int(mon.get("left", 0))
        top = int(mon.get("top", 0))
        self.geometry(f"{w}x{h}+{left}+{top}")
        self.canvas.configure(width=w, height=h)
        self.update_idletasks()
        _set_capture_mode(self, self.cfg.overlay_capture_mode == "stream_safe")

    def _tick(self):
        enabled = bool(self.cfg.overlay_enabled)
        if enabled and not self._visible:
            self.deiconify()
            self._visible = True
            self._sync_geometry()
        elif not enabled and self._visible:
            self.withdraw()
            self._visible = False

        if enabled:
            self.attributes("-alpha", max(0.2, min(1.0, self.cfg.overlay_opacity)))
            self._draw()
        if not self.bot.quit:
            self.after(80, self._tick)

    def _draw(self):
        cfg = self.cfg
        accent = cfg.hud_color
        self.canvas.delete("all")
        w = max(1, cfg.x_end - cfg.x_start)
        band_h = max(4, cfg.scan_band)
        band_top = max(0, cfg.scan_y - band_h // 2)
        band_bottom = band_top + band_h

        self.canvas.create_rectangle(
            cfg.x_start, band_top, cfg.x_end, band_bottom,
            fill=_blend(accent, "#000000", 0.45), stipple="gray25", outline="",
        )
        self.canvas.create_rectangle(
            cfg.x_start, band_top, cfg.x_end, band_bottom,
            outline=accent, width=2,
        )
        self.canvas.create_text(
            cfg.x_start + 10, max(18, band_top - 18),
            text=f"SCAN BAND  {w}x{band_h}px  {self.bot.last_scan_ms:.1f}ms",
            fill=accent, anchor="w", font=("Consolas", 11, "bold"),
        )

        gmin, gmax = self.bot.last_green_range
        cur = self.bot.last_cursor_x
        pred = self.bot.last_predicted_x
        if gmax > gmin:
            self.canvas.create_rectangle(
                cfg.x_start + gmin, band_top - 6, cfg.x_start + gmax, band_bottom + 6,
                outline="#22c55e", width=2,
            )
        if cur:
            x = cfg.x_start + cur
            self.canvas.create_line(x, band_top - 12, x, band_bottom + 12, fill="#f43f5e", width=2)
        if pred:
            px = cfg.x_start + pred
            self.canvas.create_line(px, band_top - 10, px, band_bottom + 10, fill="#f59e0b", width=1, dash=(4, 3))

        if cfg.cap_x2 > cfg.cap_x1 and cfg.cap_y2 > cfg.cap_y1:
            self.canvas.create_rectangle(
                cfg.cap_x1, cfg.cap_y1, cfg.cap_x2, cfg.cap_y2,
                outline="#06b6d4", width=2, dash=(7, 4),
            )
            self.canvas.create_text(
                cfg.cap_x1 + 10, max(16, cfg.cap_y1 - 16),
                text="CAPTCHA AREA", fill="#06b6d4", anchor="w",
                font=("Consolas", 10, "bold"),
            )

        status = "ACTIVE" if self.bot.running else "PAUSED"
        state_color = "#22c55e" if self.bot.last_in_green else accent
        self.canvas.create_text(
            28, 34,
            text=(f"ANGELBOT HUD  {status}  "
                  f"FPS {self.bot.actual_fps:.0f}  "
                  f"react {self.bot.last_reaction_ms:.1f}ms  "
                  f"{self.bot.last_detection_text}"),
            fill=state_color, anchor="w", font=("Consolas", 13, "bold"),
        )


# ============================================================
# GUI
# ============================================================

class FishingBotGUI(ctk.CTk):
    def __init__(self, state: botcore.BotState, log_queue: queue.Queue, is_admin: bool = False):
        super().__init__()

        self.bot = state
        self.cfg = state.cfg
        self.is_admin = is_admin
        self.log_queue = log_queue
        self._start_time: Optional[float] = None
        self._registered: list = []

        # eigener mss-Sammler nur fuer GUI-Live-Preview
        self._sct = mss.mss()
        self._preview_image: Optional[ctk.CTkImage] = None
        self._captcha_image: Optional[ctk.CTkImage] = None
        self._galaxy_image: Optional[ctk.CTkImage] = None
        self._accent_widgets: list = []
        self._panel_widgets: list = []
        self.overlay: Optional[ScanOverlay] = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("AngelBot v4 - Inventory HUD")
        self.geometry("940x960")
        self.minsize(860, 860)
        self.configure(fg_color=BG)

        self._build_layout()
        self.overlay = ScanOverlay(self)
        self._register_hotkeys()
        self._poll_log()
        self._poll_status()
        self._poll_preview()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------
    def _build_layout(self):
        body = ctk.CTkScrollableFrame(self, fg_color=BG, scrollbar_button_color=PANEL_3,
                                      scrollbar_button_hover_color=LINE)
        body.pack(fill="both", expand=True)
        self.body = body

        self._galaxy_image = ctk.CTkImage(
            light_image=_make_galaxy_image(940, 170, self.cfg.hud_color),
            dark_image=_make_galaxy_image(940, 170, self.cfg.hud_color),
            size=(940, 170),
        )
        self.galaxy_label = ctk.CTkLabel(body, image=self._galaxy_image, text="")
        self.galaxy_label.pack(fill="x", padx=0, pady=(0, 0))

        # Header
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(12, 6))

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left")
        self.title_label = ctk.CTkLabel(title_box, text="ANGELBOT V4",
                                        font=ctk.CTkFont("Roboto", 28, "bold"),
                                        text_color=self.cfg.hud_color)
        self.title_label.pack(anchor="w")
        ctk.CTkLabel(title_box, text="INVENTORY SCAN HUD",
                     font=ctk.CTkFont("Consolas", 12, "bold"),
                     text_color=TEXT_MUTED).pack(anchor="w")

        self.status_dot = ctk.CTkLabel(header, text="●", text_color="#ff8c00",
                                       font=ctk.CTkFont(size=28))
        self.status_dot.pack(side="right", padx=(0, 8))
        self.status_dot.configure(text="●")
        self.status_label = ctk.CTkLabel(header, text="PAUSIERT",
                                         text_color="#ff8c00",
                                         font=ctk.CTkFont(size=16, weight="bold"))
        self.status_label.pack(side="right")
        if self.is_admin:
            ctk.CTkButton(header, text="Admin Tool", width=110,
                          fg_color=ACCENT_COLORS["Ice"],
                          command=lambda: AdminTool(self)).pack(side="right", padx=(0, 14))

        # Stats
        stats = ctk.CTkFrame(body, fg_color=PANEL, border_width=1,
                             border_color=LINE, corner_radius=8)
        stats.pack(fill="x", padx=20, pady=8)
        for i in range(6):
            stats.grid_columnconfigure(i, weight=1)

        self.stat_hits = self._make_stat(stats, 0, "Treffer", "0")
        self.stat_caps = self._make_stat(stats, 1, "Captchas", "0")
        self.stat_run = self._make_stat(stats, 2, "Laufzeit", "00:00")
        self.stat_rate = self._make_stat(stats, 3, "Hits/min", "0.0")
        self.stat_fps = self._make_stat(stats, 4, "Scan FPS", "0")
        self.stat_react = self._make_stat(stats, 5, "Reaktion", "0.0ms")

        # Live-Preview Bar
        prev_frame = ctk.CTkFrame(body, fg_color=PANEL, border_width=1,
                                  border_color=LINE, corner_radius=8)
        prev_frame.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(prev_frame, text="LIVE BAR PREVIEW",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=TEXT_MUTED, anchor="w"
                     ).pack(fill="x", padx=10, pady=(6, 0))
        self.preview_label = ctk.CTkLabel(prev_frame, text="(warte auf Bar...)",
                                          width=720, height=80,
                                          fg_color=("#090d1d", "#090d1d"),
                                          corner_radius=6)
        self.preview_label.pack(padx=10, pady=8)
        self.preview_info = ctk.CTkLabel(prev_frame, text="—",
                                         font=ctk.CTkFont("Consolas", 10),
                                         text_color="#6b7280", anchor="w")
        self.preview_info.pack(fill="x", padx=14, pady=(0, 6))

        # Live-Preview Captcha
        cap_frame = ctk.CTkFrame(body, fg_color=PANEL, border_width=1,
                                 border_color=LINE, corner_radius=8)
        cap_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(cap_frame, text="LIVE CAPTCHA PREVIEW",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=TEXT_MUTED, anchor="w"
                     ).pack(fill="x", padx=10, pady=(6, 0))
        self.captcha_label = ctk.CTkLabel(cap_frame, text="(Bereich nicht gesetzt)",
                                          width=400, height=120,
                                          fg_color=("#090d1d", "#090d1d"),
                                          corner_radius=6)
        self.captcha_label.pack(padx=10, pady=8)
        self.captcha_info = ctk.CTkLabel(cap_frame, text="—",
                                         font=ctk.CTkFont("Consolas", 10),
                                         text_color="#6b7280", anchor="w")
        self.captcha_info.pack(fill="x", padx=14, pady=(0, 6))

        # Buttons
        btns = ctk.CTkFrame(body, fg_color=PANEL, border_width=1,
                            border_color=LINE, corner_radius=8)
        btns.pack(fill="x", padx=20, pady=8)
        for i in range(6):
            btns.grid_columnconfigure(i, weight=1)

        self.toggle_btn = ctk.CTkButton(
            btns, text="START  (F6)", fg_color="#16a34a", hover_color="#15803d",
            font=ctk.CTkFont(size=14, weight="bold"), height=42,
            command=self._on_toggle,
        )
        self.toggle_btn.grid(row=0, column=0, padx=4, pady=8, sticky="ew")

        ctk.CTkButton(btns, text="Auto-Scan (F7)", height=42,
                      fg_color=PANEL_3, hover_color=LINE,
                      command=self._on_auto_scan
                      ).grid(row=0, column=1, padx=4, pady=8, sticky="ew")
        ctk.CTkButton(btns, text="Captcha JETZT (F4)", height=42,
                      fg_color=PANEL_3, hover_color=LINE,
                      command=self._on_cap_solve
                      ).grid(row=0, column=2, padx=4, pady=8, sticky="ew")
        ctk.CTkButton(btns, text="Hotkeys", height=42,
                      fg_color=PANEL_3, hover_color=LINE,
                      command=self._open_hotkey_editor
                      ).grid(row=0, column=3, padx=4, pady=8, sticky="ew")
        ctk.CTkButton(btns, text="Speichern (F11)", height=42,
                      fg_color=PANEL_3, hover_color=LINE,
                      command=self._on_save
                      ).grid(row=0, column=4, padx=4, pady=8, sticky="ew")
        ctk.CTkButton(btns, text="Beenden (F12)", height=42,
                      fg_color="#b91c1c", hover_color="#7f1d1d",
                      command=self._on_close
                      ).grid(row=0, column=5, padx=4, pady=8, sticky="ew")

        # Tabs
        tabs = ctk.CTkTabview(body, fg_color=PANEL, segmented_button_fg_color=PANEL_2,
                              segmented_button_selected_color=self.cfg.hud_color,
                              segmented_button_selected_hover_color=_blend(self.cfg.hud_color, "#ffffff", 0.12))
        tabs.pack(fill="x", padx=20, pady=8)
        self._build_tab_bar(tabs.add("Bar"))
        self._build_tab_click(tabs.add("Klick / Timing"))
        self._build_tab_captcha(tabs.add("Captcha"))
        self._build_tab_wt(tabs.add("Waffentraining"))
        self._build_tab_hud(tabs.add("HUD"))

        # Konsole
        ctk.CTkLabel(body, text="LOG", font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").pack(fill="x", padx=20, pady=(8, 0))
        self.console = ctk.CTkTextbox(body, height=140,
                                      font=ctk.CTkFont("Consolas", 11))
        self.console.pack(fill="x", padx=20, pady=(2, 16))
        self.console.configure(state="disabled")

    def _make_stat(self, parent, col, label, value):
        f = ctk.CTkFrame(parent, fg_color=PANEL_2, border_width=1,
                         border_color=_blend(self.cfg.hud_color, LINE, 0.72),
                         corner_radius=8)
        f.grid(row=0, column=col, padx=6, pady=6, sticky="ew")
        ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).pack(pady=(8, 0))
        v = ctk.CTkLabel(f, text=value, font=ctk.CTkFont(size=22, weight="bold"),
                         text_color="#f8fafc")
        v.pack(pady=(0, 8))
        return v

    def _build_tab_bar(self, parent):
        self._slider_row(parent, "SCAN_Y", self.cfg.scan_y,
                         0, max(1, self.cfg.screen_h),
                         lambda v: self._set_cfg("scan_y", int(v)))
        self._slider_row(parent, "X_START", self.cfg.x_start,
                         0, max(1, self.cfg.screen_w),
                         lambda v: self._set_cfg("x_start", int(v)))
        self._slider_row(parent, "X_END", self.cfg.x_end,
                         0, max(1, self.cfg.screen_w),
                         lambda v: self._set_cfg("x_end", int(v)))
        self._slider_row(parent, "Scan-Band Hoehe (px)", self.cfg.scan_band, 4, 80,
                         lambda v: self._set_cfg("scan_band", int(v)))
        self._slider_row(parent, "Threshold", self.cfg.threshold, 5, 80,
                         lambda v: self._set_cfg("threshold", int(v)))

    def _build_tab_click(self, parent):
        self.auto_timing_var = ctk.BooleanVar(value=self.cfg.auto_timing_enabled)
        ctk.CTkSwitch(
            parent, text="Auto-Timing berechnen", variable=self.auto_timing_var,
            progress_color=self.cfg.hud_color,
            command=lambda: self._set_cfg("auto_timing_enabled", bool(self.auto_timing_var.get())),
        ).pack(fill="x", padx=10, pady=(10, 4))
        self._slider_row(parent, "Input-Lag (ms)", self.cfg.input_lag_ms, -50, 80,
                         lambda v: self._set_cfg("input_lag_ms", int(v)))
        self._slider_row(parent, "Klick-Hold (ms)", self.cfg.click_hold_ms, 1, 50,
                         lambda v: self._set_cfg("click_hold_ms", int(v)))
        self._slider_row(parent, "Timing-Safety (ms)", self.cfg.timing_safety_ms, 0.0, 8.0,
                         lambda v: self._set_cfg("timing_safety_ms", round(float(v), 1)),
                         is_float=True)
        self._slider_row(parent, "End-Zone Boost (ms)", self.cfg.end_zone_boost_ms, 0.0, 20.0,
                         lambda v: self._set_cfg("end_zone_boost_ms", round(float(v), 1)),
                         is_float=True)
        self._slider_row(parent, "Inner-Ratio", self.cfg.green_inner_ratio, 0.0, 0.4,
                         lambda v: self._set_cfg("green_inner_ratio",
                                                 round(float(v), 2)),
                         is_float=True)
        self._slider_row(parent, "2. Klick Delay (s)", self.cfg.second_click_delay,
                         0.5, 3.0,
                         lambda v: self._set_cfg("second_click_delay",
                                                 round(float(v), 2)),
                         is_float=True)
        self._slider_row(parent, "Cooldown nach Klick (s)", self.cfg.post_cycle_cooldown,
                         0.5, 5.0,
                         lambda v: self._set_cfg("post_cycle_cooldown",
                                                 round(float(v), 2)),
                         is_float=True)

    def _build_tab_captcha(self, parent):
        self.captcha_enabled_var = ctk.BooleanVar(value=self.cfg.captcha_enabled)
        ctk.CTkSwitch(
            parent, text="Captcha-Erkennung aktiv", variable=self.captcha_enabled_var,
            progress_color=self.cfg.hud_color,
            command=lambda: self._set_cfg("captcha_enabled", bool(self.captcha_enabled_var.get())),
        ).pack(fill="x", padx=10, pady=(10, 4))

        ctk.CTkLabel(
            parent, justify="left", anchor="w",
            text=("Captcha-Bereich (unten links)\n"
                  "F2 = oben-links, F3 = unten-rechts setzen\n"
                  "F4 = Captcha JETZT lesen + tippen"),
        ).pack(fill="x", padx=10, pady=(8, 4))

        self._slider_row(parent, "Cap X1", self.cfg.cap_x1, 0, max(1, self.cfg.screen_w),
                         lambda v: self._set_cfg("cap_x1", int(v)))
        self._slider_row(parent, "Cap Y1", self.cfg.cap_y1, 0, max(1, self.cfg.screen_h),
                         lambda v: self._set_cfg("cap_y1", int(v)))
        self._slider_row(parent, "Cap X2", self.cfg.cap_x2, 0, max(1, self.cfg.screen_w),
                         lambda v: self._set_cfg("cap_x2", int(v)))
        self._slider_row(parent, "Cap Y2", self.cfg.cap_y2, 0, max(1, self.cfg.screen_h),
                         lambda v: self._set_cfg("cap_y2", int(v)))

        mode_frame = ctk.CTkFrame(parent, fg_color="transparent")
        mode_frame.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(mode_frame, text="Type-Modus:").pack(side="left", padx=(0, 8))
        self.type_mode_var = ctk.StringVar(value=self.cfg.type_mode)
        ctk.CTkOptionMenu(mode_frame, values=["chat", "direct", "none"],
                          variable=self.type_mode_var,
                          command=lambda v: self._set_cfg("type_mode", v)
                          ).pack(side="left")

    def _build_tab_wt(self, parent):
        # Aktivierung
        self.wt_enabled_var = ctk.BooleanVar(value=self.cfg.wt_enabled)
        ctk.CTkSwitch(
            parent, text="Waffentraining aktivieren (F1)",
            variable=self.wt_enabled_var,
            progress_color=self.cfg.hud_color,
            command=lambda: self._set_cfg("wt_enabled", bool(self.wt_enabled_var.get())),
        ).pack(fill="x", padx=10, pady=(10, 4))

        ctk.CTkLabel(
            parent, justify="left", anchor="w",
            text=("Scan-Bereich: Region in der nach roten Zielen gesucht wird.\n"
                  "F1 = Waffentraining Start/Stop"),
        ).pack(fill="x", padx=10, pady=(4, 4))

        self._slider_row(parent, "Scan X1", self.cfg.wt_scan_x1,
                         0, max(1, self.cfg.screen_w),
                         lambda v: self._set_cfg("wt_scan_x1", int(v)))
        self._slider_row(parent, "Scan Y1", self.cfg.wt_scan_y1,
                         0, max(1, self.cfg.screen_h),
                         lambda v: self._set_cfg("wt_scan_y1", int(v)))
        self._slider_row(parent, "Scan X2", self.cfg.wt_scan_x2,
                         0, max(1, self.cfg.screen_w),
                         lambda v: self._set_cfg("wt_scan_x2", int(v)))
        self._slider_row(parent, "Scan Y2", self.cfg.wt_scan_y2,
                         0, max(1, self.cfg.screen_h),
                         lambda v: self._set_cfg("wt_scan_y2", int(v)))

        self._slider_row(parent, "Farb-Toleranz", self.cfg.wt_threshold,
                         5, 150,
                         lambda v: self._set_cfg("wt_threshold", int(v)))
        self._slider_row(parent, "Min. Pixel", self.cfg.wt_min_target_pixels,
                         5, 500,
                         lambda v: self._set_cfg("wt_min_target_pixels", int(v)))
        self._slider_row(parent, "Schuss-Delay (s)", self.cfg.wt_shot_delay,
                         0.0, 1.0,
                         lambda v: self._set_cfg("wt_shot_delay", round(float(v), 3)),
                         is_float=True)
        self._slider_row(parent, "Aim-Settle (ms)", self.cfg.wt_aim_settle_ms,
                         0, 50,
                         lambda v: self._set_cfg("wt_aim_settle_ms", int(v)))
        self._slider_row(parent, "Schuss-Hold (ms)", self.cfg.wt_shot_hold_ms,
                         10, 200,
                         lambda v: self._set_cfg("wt_shot_hold_ms", int(v)))
        self._slider_row(parent, "Scan-Intervall (s)", self.cfg.wt_scan_interval,
                         0.005, 0.2,
                         lambda v: self._set_cfg("wt_scan_interval", round(float(v), 3)),
                         is_float=True)

        # HSV-Modus
        self.wt_hsv_var = ctk.BooleanVar(value=self.cfg.wt_use_hsv)
        ctk.CTkSwitch(
            parent, text="HSV-Modus (robustere Rot-Erkennung)",
            variable=self.wt_hsv_var,
            progress_color=self.cfg.hud_color,
            command=lambda: self._set_cfg("wt_use_hsv", bool(self.wt_hsv_var.get())),
        ).pack(fill="x", padx=10, pady=(8, 4))

        self._slider_row(parent, "HSV H Low1", self.cfg.wt_hsv_h_low1,
                         0, 180,
                         lambda v: self._set_cfg("wt_hsv_h_low1", int(v)))
        self._slider_row(parent, "HSV H High1", self.cfg.wt_hsv_h_high1,
                         0, 180,
                         lambda v: self._set_cfg("wt_hsv_h_high1", int(v)))
        self._slider_row(parent, "HSV H Low2", self.cfg.wt_hsv_h_low2,
                         0, 180,
                         lambda v: self._set_cfg("wt_hsv_h_low2", int(v)))
        self._slider_row(parent, "HSV H High2", self.cfg.wt_hsv_h_high2,
                         0, 180,
                         lambda v: self._set_cfg("wt_hsv_h_high2", int(v)))
        self._slider_row(parent, "HSV S Min", self.cfg.wt_hsv_s_min,
                         0, 255,
                         lambda v: self._set_cfg("wt_hsv_s_min", int(v)))
        self._slider_row(parent, "HSV V Min", self.cfg.wt_hsv_v_min,
                         0, 255,
                         lambda v: self._set_cfg("wt_hsv_v_min", int(v)))

        # Instant-Aim
        self.wt_instant_var = ctk.BooleanVar(value=self.cfg.wt_instant_aim)
        ctk.CTkSwitch(
            parent, text="Instant-Aim (sofort zum Ziel springen)",
            variable=self.wt_instant_var,
            progress_color=self.cfg.hud_color,
            command=lambda: self._set_cfg("wt_instant_aim", bool(self.wt_instant_var.get())),
        ).pack(fill="x", padx=10, pady=(8, 4))

    def _build_tab_hud(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 4))

        self.overlay_var = ctk.BooleanVar(value=self.cfg.overlay_enabled)
        ctk.CTkSwitch(
            top, text="Overlay anzeigen", variable=self.overlay_var,
            progress_color=self.cfg.hud_color,
            command=lambda: self._set_cfg("overlay_enabled", bool(self.overlay_var.get())),
        ).pack(side="left", padx=(0, 18))

        self.capture_var = ctk.StringVar(value=self.cfg.overlay_capture_mode)
        ctk.CTkSegmentedButton(
            top, values=["visible", "stream_safe"], variable=self.capture_var,
            selected_color=self.cfg.hud_color,
            command=lambda v: self._set_cfg("overlay_capture_mode", v),
        ).pack(side="left", padx=4)

        color_row = ctk.CTkFrame(parent, fg_color="transparent")
        color_row.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(color_row, text="HUD-Farbe", width=180, anchor="w").pack(side="left")
        for name, color in ACCENT_COLORS.items():
            ctk.CTkButton(
                color_row, text=name, width=86, height=30,
                fg_color=color, hover_color=_blend(color, "#ffffff", 0.16),
                command=lambda c=color: self._set_hud_color(c),
            ).pack(side="left", padx=4)

        self._slider_row(parent, "Overlay Deckkraft", self.cfg.overlay_opacity,
                         0.25, 1.0,
                         lambda v: self._set_cfg("overlay_opacity", round(float(v), 2)),
                         is_float=True)

    def _slider_row(self, parent, label, init, mn, mx, on_change, is_float=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=4)
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=label, width=180, anchor="w"
                     ).grid(row=0, column=0, padx=(0, 8))
        val = ctk.CTkLabel(row, text=(f"{init:.2f}" if is_float else str(init)),
                           width=70, anchor="e",
                           font=ctk.CTkFont(family="Consolas", size=12, weight="bold"))
        val.grid(row=0, column=2, padx=(8, 0))
        steps = max(1, int((mx - mn) * 100) if is_float else int(mx - mn))
        slider = ctk.CTkSlider(row, from_=mn, to=mx, number_of_steps=steps)
        slider.set(init)
        slider.grid(row=0, column=1, sticky="ew")

        def _cb(v, lbl_widget=val):
            on_change(v)
            lbl_widget.configure(text=(f"{v:.2f}" if is_float else str(int(v))))
        slider.configure(command=_cb)

    # ------------------------------------------------------------
    def _set_cfg(self, key, value):
        setattr(self.cfg, key, value)

    def _set_hud_color(self, color: str):
        self.cfg.hud_color = color
        self.title_label.configure(text_color=color)
        self._galaxy_image = ctk.CTkImage(
            light_image=_make_galaxy_image(940, 170, color),
            dark_image=_make_galaxy_image(940, 170, color),
            size=(940, 170),
        )
        self.galaxy_label.configure(image=self._galaxy_image)
        if hasattr(self, "overlay_var"):
            # CustomTkinter switch colors are static after creation in some versions,
            # so the live accent is most visible in title, tabs, preview and overlay.
            pass

    def _on_toggle(self):
        self.bot.toggle()

    def _on_auto_scan(self):
        self.bot.trigger_auto_scan()

    def _on_cap_solve(self):
        self.bot.trigger_captcha_test()

    def _on_save(self):
        self.bot.save_config()

    def _on_close(self):
        try:
            self._sct.close()
        except (AttributeError, OSError):
            pass
        self.bot.trigger_quit()
        self.after(300, self.destroy)

    def _open_hotkey_editor(self):
        HotkeyEditor(self)

    # ------------------------------------------------------------
    def _register_hotkeys(self):
        hk = self.cfg.hotkeys
        mapping = {
            hk["set_cap_tl"]:    self.bot.set_cap_top_left,
            hk["set_cap_br"]:    self.bot.set_cap_bottom_right,
            hk["captcha_test"]:  self.bot.trigger_captcha_test,
            hk["debug"]:         self.bot.toggle_debug,
            hk["toggle"]:        self.bot.toggle,
            hk["wt_toggle"]:     self.bot.toggle_wt,
            hk["auto_scan"]:     self.bot.trigger_auto_scan,
            hk["set_x_start"]:   self.bot.set_x_start,
            hk["set_x_end"]:     self.bot.set_x_end,
            hk["set_scan_y"]:    self.bot.set_scan_y,
            hk["save"]:          self.bot.save_config,
            hk["quit"]:          self._on_close,
        }
        for key, cb in mapping.items():
            try:
                handle = keyboard.add_hotkey(key, cb)
                self._registered.append(handle)
            except (ValueError, KeyError) as exc:
                print(f"[GUI] Hotkey '{key}' Fehler: {exc}")

    def _unregister_hotkeys(self):
        for h in self._registered:
            try:
                keyboard.remove_hotkey(h)
            except (KeyError, ValueError):
                pass
        self._registered.clear()

    def reregister_hotkeys(self):
        self._unregister_hotkeys()
        self._register_hotkeys()

    # ------------------------------------------------------------
    def _poll_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._append_console(msg)
        except queue.Empty:
            pass
        self.after(120, self._poll_log)

    def _append_console(self, msg: str):
        self.console.configure(state="normal")
        self.console.insert("end", msg)
        if len(self.console.get("0.0", "end")) > 4000:
            self.console.delete("0.0", "end-3500c")
        self.console.see("end")
        self.console.configure(state="disabled")

    def _poll_status(self):
        if self.bot.running:
            if self._start_time is None:
                self._start_time = time.time()
            self.status_dot.configure(text_color="#22c55e")
            self.status_label.configure(text="AKTIV", text_color="#22c55e")
            self.toggle_btn.configure(
                text=f"STOP  ({self.cfg.hotkeys['toggle'].upper()})",
                fg_color="#b91c1c", hover_color="#7f1d1d")
        else:
            self.status_dot.configure(text_color="#ff8c00")
            self.status_label.configure(text="PAUSIERT", text_color="#ff8c00")
            self.toggle_btn.configure(
                text=f"START  ({self.cfg.hotkeys['toggle'].upper()})",
                fg_color="#16a34a", hover_color="#15803d")

        self.stat_hits.configure(text=str(self.bot.stats_hits))
        self.stat_caps.configure(text=str(self.bot.stats_captchas))
        self.stat_fps.configure(text=f"{self.bot.actual_fps:.0f}")
        self.stat_react.configure(text=f"{self.bot.last_reaction_ms:.1f}ms")
        if self._start_time and self.bot.running:
            sec = int(time.time() - self._start_time)
            self.stat_run.configure(text=f"{sec // 60:02d}:{sec % 60:02d}")
            rate = (self.bot.stats_hits / sec * 60) if sec > 0 else 0.0
            self.stat_rate.configure(text=f"{rate:.1f}")

        if not self.bot.quit:
            self.after(250, self._poll_status)

    # ------------------------------------------------------------
    # Live-Preview vom Scan-Band + Captcha
    # ------------------------------------------------------------
    def _poll_preview(self):
        try:
            self._capture_preview()
            self._capture_captcha_preview()
        except (OSError, ValueError, AttributeError) as exc:
            print(f"[GUI] Preview-Fehler: {exc}")
        if not self.bot.quit:
            # 50ms = ~20 FPS visible refresh rate
            self.after(50, self._poll_preview)

    def _capture_preview(self):
        cfg = self.cfg
        width = cfg.x_end - cfg.x_start
        if width <= 4:
            self.preview_label.configure(image=None, text="(Bar nicht konfiguriert)")
            return

        band_h = max(20, cfg.scan_band)
        band_top = max(0, cfg.scan_y - band_h // 2)
        try:
            mon = self._sct.monitors[cfg.monitor_index]
        except (IndexError, KeyError):
            mon = self._sct.monitors[1]
        region = {
            "left": cfg.x_start + mon.get("left", 0),
            "top": band_top + mon.get("top", 0),
            "width": width,
            "height": band_h,
        }

        try:
            raw = np.array(self._sct.grab(region))
        except (OSError, mss.exception.ScreenShotError):
            return

        bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        # Auf feste Display-Hoehe skalieren
        target_h = 70
        scale = target_h / max(1, band_h)
        target_w = int(width * scale)
        max_w = 760
        if target_w > max_w:
            scale2 = max_w / target_w
            target_w = max_w
            target_h = max(40, int(target_h * scale2))
            display_scale = max_w / width
        else:
            display_scale = scale

        small = cv2.resize(rgb, (target_w, target_h), interpolation=cv2.INTER_NEAREST)

        # DEUTLICHE Markierungen einzeichnen
        gmin, gmax = self.bot.last_green_range
        cur = self.bot.last_cursor_x

        if gmax > gmin:
            x1 = int(gmin * display_scale)
            x2 = int(gmax * display_scale)
            # Dicker grueneklicht-Rahmen + halbtransparente Fuellung
            overlay = small.copy()
            cv2.rectangle(overlay, (x1, 0), (x2, target_h - 1),
                          (50, 255, 80), -1)
            small = cv2.addWeighted(overlay, 0.25, small, 0.75, 0)
            cv2.rectangle(small, (x1, 0), (x2, target_h - 1),
                          (50, 255, 80), 3)

        if cur:
            cx = int(cur * display_scale)
            # Dicke rote Linie fuer Cursor
            cv2.line(small, (cx, 0), (cx, target_h - 1), (255, 80, 80), 3)
            # Pfeile oben+unten
            cv2.drawMarker(small, (cx, 8), (255, 80, 80),
                           markerType=cv2.MARKER_TRIANGLE_DOWN, markerSize=10, thickness=2)
            cv2.drawMarker(small, (cx, target_h - 8), (255, 80, 80),
                           markerType=cv2.MARKER_TRIANGLE_UP, markerSize=10, thickness=2)

        # Rand-Markierungen X_START / X_END (weiss tick)
        cv2.line(small, (0, 0), (0, target_h - 1), (255, 255, 255), 1)
        cv2.line(small, (target_w - 1, 0), (target_w - 1, target_h - 1),
                 (255, 255, 255), 1)

        pil = Image.fromarray(small)
        self._preview_image = ctk.CTkImage(light_image=pil, dark_image=pil,
                                           size=(target_w, target_h))
        self.preview_label.configure(image=self._preview_image, text="")

        in_green = (gmax > gmin and gmin <= cur <= gmax)
        info = (f"X={cfg.x_start}..{cfg.x_end}  "
                f"cursor@{cur}  green=[{gmin}..{gmax}]  "
                f"vel={self.bot.last_velocity:+.0f}px/s  "
                f"FPS={self.bot.actual_fps:.0f}  "
                f"scan={self.bot.last_scan_ms:.1f}ms  "
                f"react={self.bot.last_reaction_ms:.1f}ms  "
                f"lead={self.bot.last_timing_ms:.1f}ms  "
                f"boost={self.bot.last_end_boost_ms:.1f}ms  "
                f"eta={self.bot.last_time_to_hit_ms:.1f}ms  "
                f"{self.bot.last_detection_text}  "
                f"{'IN GREEN' if in_green else '...'}")
        self.preview_info.configure(text=info,
                                    text_color="#22c55e" if in_green else "#6b7280")

    def _capture_captcha_preview(self):
        cfg = self.cfg
        cw = cfg.cap_x2 - cfg.cap_x1
        ch = cfg.cap_y2 - cfg.cap_y1
        if cw < 10 or ch < 10:
            self.captcha_label.configure(image=None,
                                         text="(Bereich nicht gesetzt - F2/F3)")
            self.captcha_info.configure(text="—", text_color="#6b7280")
            return

        try:
            mon = self._sct.monitors[cfg.monitor_index]
        except (IndexError, KeyError):
            mon = self._sct.monitors[1]
        region = {
            "left": cfg.cap_x1 + mon.get("left", 0),
            "top": cfg.cap_y1 + mon.get("top", 0),
            "width": cw,
            "height": ch,
        }
        try:
            raw = np.array(self._sct.grab(region))
        except (OSError, mss.exception.ScreenShotError):
            return

        bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        # Auf max 380x180 skalieren mit Aspect Ratio
        max_w, max_h = 380, 180
        sw = max_w / cw
        sh = max_h / ch
        scl = min(sw, sh)
        tw = max(40, int(cw * scl))
        th = max(40, int(ch * scl))
        small = cv2.resize(rgb, (tw, th), interpolation=cv2.INTER_LINEAR)

        # weisser Rand zur Erkennung
        cv2.rectangle(small, (0, 0), (tw - 1, th - 1), (255, 255, 255), 1)

        pil = Image.fromarray(small)
        self._captcha_image = ctk.CTkImage(light_image=pil, dark_image=pil,
                                           size=(tw, th))
        self.captcha_label.configure(image=self._captcha_image, text="")
        self.captcha_info.configure(
            text=f"({cfg.cap_x1},{cfg.cap_y1}) -> ({cfg.cap_x2},{cfg.cap_y2})  "
                 f"{cw}x{ch}px  Mode: {cfg.type_mode}  -> F4 zum Lesen + Tippen",
            text_color="#9ca3af",
        )


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    sw, sh = botcore.detect_screen_size()
    cfg = botcore.BotConfig.from_ini(botcore._config_path(), sw, sh)
    cfg.overlay_enabled = False

    gate = LicenseGate(cfg)
    gate.mainloop()
    if not gate.authorized:
        return

    state = botcore.BotState(cfg)

    log_q: queue.Queue = queue.Queue()
    real_stdout = sys.stdout
    sys.stdout = _QueueWriter(log_q, mirror=real_stdout)

    print(f"[INFO] App-Ordner: {botcore._app_dir()}")
    cp = botcore._config_path()
    if os.path.exists(cp):
        print(f"[INFO] Konfig geladen aus: {cp}")
    else:
        print(f"[INFO] Keine Konfig - verwende Defaults ({cp})")

    if not botcore._OCR_AVAILABLE:
        print("[WARN] pytesseract nicht installiert -> Captcha nur manuell loesbar.")
    if botcore._OCR_AVAILABLE and not cfg.tesseract_path:
        for guess in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.exists(guess):
                cfg.tesseract_path = guess
                print(f"[INFO] Tesseract automatisch gefunden: {guess}")
                break

    worker = threading.Thread(target=_bot_worker, args=(state,), daemon=True)
    worker.start()
    wt_worker = threading.Thread(target=_wt_worker, args=(state,), daemon=True)
    wt_worker.start()

    app = FishingBotGUI(state, log_q, is_admin=gate.is_admin)
    app.mainloop()

    state.trigger_quit()
    sys.stdout = real_stdout
    time.sleep(0.2)


if __name__ == "__main__":
    main()
