# AngelBot V5 - Fishing Bot + Waffentraining

Automatisierter Minecraft Fishing-Bot mit integriertem **Waffentraining-Modul** fuer 100% Treffergenauigkeit.

---

## Inhaltsverzeichnis

1. [Features](#features)
2. [Installation](#installation)
3. [Schnellstart](#schnellstart)
4. [Tabs & Einstellungen](#tabs--einstellungen)
   - [Bar (Scan)](#bar-scan)
   - [Klick / Timing](#klick--timing)
   - [Captcha](#captcha)
   - [Waffentraining (NEU)](#waffentraining-neu)
   - [HUD](#hud)
5. [Waffentraining - 100% Treffergenauigkeit](#waffentraining---100-treffergenauigkeit)
6. [Hotkeys](#hotkeys)
7. [Konfigurationsdatei (config.ini)](#konfigurationsdatei-configini)
8. [Code-Architektur](#code-architektur)
9. [Fehlerbehebung](#fehlerbehebung)

---

## Features

- **Fishing-Bot**: Automatisches Angeln mit Bar-Erkennung, Velocity-Prediction und praezisem Klick-Timing
- **Waffentraining-Bot**: Automatisches Erkennen und Treffen roter Ziele im Waffentraining-Minigame
- **Captcha-Erkennung**: Automatische OCR-basierte Captcha-Loesung (optional, benoetigt Tesseract)
- **Live-Preview**: Echtzeit-Visualisierung der Bar- und Captcha-Erkennung
- **Lizenz-Verwaltung**: Admin-Panel zum Generieren, Anzeigen, Verlaengern und Loeschen von Lizenzcodes
- **Profil-System**: Mehrere Konfigurationsprofile speicherbar
- **Hotkey-System**: Alle Funktionen per Hotkey steuerbar (anpassbar)
- **HUD/Overlay**: In-Game Overlay mit Status-Anzeige
- **Anti-AFK**: Verhindert AFK-Kick durch Mini-Mausbewegungen
- **Discord-Webhook**: Optionale Status-Benachrichtigungen via Discord

---

## Installation

### Voraussetzungen

- Python 3.10+
- Windows 10/11 (wegen pydirectinput und ctypes.windll)

### Abhaengigkeiten installieren

```bash
pip install -r requirements.txt
```

### Starten

```bash
python gui.py
```

Oder ohne GUI (Konsolen-Modus):

```bash
python main.py
```

### Als EXE bauen

```bash
build_onedir.bat
```

---

## Schnellstart

1. Bot starten (`python gui.py`)
2. Lizenz eingeben (oder Admin-Login)
3. Im **Bar**-Tab den Scan-Bereich kalibrieren (oder F7 fuer Auto-Scan)
4. **F6** druecken zum Starten des Fishing-Bots
5. Fuer Waffentraining: Im **Waffentraining**-Tab die Einstellungen anpassen, dann **F1** druecken

---

## Tabs & Einstellungen

### Bar (Scan)

Konfiguration des Scan-Bereichs fuer die Fishing-Bar.

| Einstellung | Beschreibung | Empfohlen |
|---|---|---|
| SCAN_Y | Y-Position der Scan-Linie | Auto-Scan (F7) |
| X_START | Linker Rand der Bar | Auto-Scan (F7) |
| X_END | Rechter Rand der Bar | Auto-Scan (F7) |
| Scan-Band Hoehe | Hoehe des Scan-Streifens in Pixeln | 20-40 |
| Threshold | Farbtoleranz fuer Erkennung | 20-40 |

### Klick / Timing

Feinabstimmung des Klick-Timings.

| Einstellung | Beschreibung | Empfohlen |
|---|---|---|
| Auto-Timing | Automatische Timing-Berechnung | AN |
| Input-Lag (ms) | Manueller Lag-Ausgleich (+ frueher, - spaeter) | 0-20 |
| Klick-Hold (ms) | Dauer des Rechtsklick-Haltens | 5-15 |
| Timing-Safety (ms) | Sicherheitspuffer fuer Timing | 1.0-3.0 |
| End-Zone Boost (ms) | Extra Vorhalt bei Endzonen | 5.0-10.0 |
| Inner-Ratio | Nur im inneren Bereich der Gruen-Zone klicken | 0.05-0.15 |
| 2. Klick Delay (s) | Verzoegerung zwischen Fangen und Auswerfen | 1.0-1.5 |
| Cooldown (s) | Wartezeit nach Klick-Zyklus | 1.5-3.0 |

### Captcha

Captcha-Erkennung und automatische Eingabe.

| Einstellung | Beschreibung |
|---|---|
| Captcha aktiv | Captcha-Erkennung ein/aus |
| Cap X1/Y1, X2/Y2 | Captcha-Bereich (F2/F3 zum Setzen) |
| Type-Modus | `chat` (T+Text+Enter), `direct` (nur Text), `none` (nur erkennen) |

### Waffentraining (NEU)

Automatisierung des Waffentraining-Minigames. Scannt den **gesamten Bildschirm** nach roten Zielen, bewegt die Maus dorthin und schiesst per **Rechtsklick**.

| Einstellung | Beschreibung | Empfohlen fuer 100% |
|---|---|---|
| **Waffentraining aktivieren** | Feature ein/aus | AN |
| **Farb-Toleranz** | Wie stark die Farbe vom Ziel-Rot abweichen darf | 40-80 |
| **Min. Pixel** | Mindestanzahl roter Pixel damit ein Ziel zaehlt | 20-50 |
| **Schuss-Delay (s)** | Wartezeit nach jedem Schuss (fuer Animation/Nachladen) | 0.05-0.15 |
| **Aim-Settle (ms)** | Wartezeit nach Mausbewegung bevor geschossen wird | 3-10 |
| **Schuss-Hold (ms)** | Klick-Dauer | 30-80 |
| **Scan-Intervall (s)** | Wie oft nach neuen Zielen gescannt wird | 0.01-0.03 |
| **HSV-Modus** | HSV-basierte Farberkennung (robuster bei Beleuchtung) | AN |
| **HSV H Low1/High1** | Erster Hue-Bereich fuer Rot (0-10) | 0 / 10 |
| **HSV H Low2/High2** | Zweiter Hue-Bereich fuer Rot (160-180) | 160 / 180 |
| **HSV S Min** | Minimale Saettigung | 80 |
| **HSV V Min** | Minimale Helligkeit | 80 |
| **Instant-Aim** | Maus springt direkt zum Ziel (schneller) | AN |

---

## Waffentraining - 100% Treffergenauigkeit

### So erreichst du 100% Treffergenauigkeit:

#### 1. Bildschirm-Scan

Der Bot scannt automatisch den **gesamten Bildschirm** nach roten Zielen. Es ist kein manuelles Einstellen eines Scan-Bereichs noetig.

**Tipp:** Stelle sicher, dass keine anderen roten UI-Elemente sichtbar sind, die als Ziel erkannt werden koennten.

#### 2. HSV-Modus verwenden

Der HSV-Modus erkennt Rot zuverlaessiger als RGB, da er unabhaengig von Beleuchtungsaenderungen arbeitet. Die Standard-Werte (H: 0-10 und 160-180, S>=80, V>=80) decken die meisten Rot-Toene ab.

**Wenn Ziele nicht erkannt werden:**
- `HSV S Min` reduzieren (z.B. auf 50) fuer blassere Rot-Toene
- `HSV V Min` reduzieren (z.B. auf 50) fuer dunklere Rot-Toene
- `Farb-Toleranz` erhoehen

**Wenn Fehlerkennungen auftreten:**
- `HSV S Min` erhoehen (z.B. auf 120)
- `Min. Pixel` erhoehen (z.B. auf 80-100)
- Scan-Bereich verkleinern

#### 3. Timing optimieren

- **Instant-Aim AN**: Die Maus springt direkt zum Zielmittelpunkt. Das ist schneller und praeziser als interpolierte Bewegung.
- **Aim-Settle 3-5ms**: Kurze Pause nach Mausbewegung, damit das Spiel die Position registriert.
- **Schuss-Delay 0.05-0.10s**: Wartezeit nach jedem Schuss. Zu kurz = Schuss wird nicht registriert. Zu lang = naechstes Ziel wird verpasst.
- **Scan-Intervall 0.01-0.02s**: So schnell wie moeglich scannen (50-100 FPS).

#### 4. Zusammenfassung der optimalen Einstellungen

```
Waffentraining aktivieren:  AN
HSV-Modus:                  AN
HSV H Low1 / High1:         0 / 10
HSV H Low2 / High2:         160 / 180
HSV S Min:                  80
HSV V Min:                  80
Farb-Toleranz:              60
Min. Pixel:                 30
Schuss-Delay:               0.08s
Aim-Settle:                 5ms
Schuss-Hold:                50ms
Scan-Intervall:             0.02s
Instant-Aim:                AN
```

### Ablauf der Automatisierung

1. **Scan**: Der Bot macht einen Screenshot des Scan-Bereichs
2. **Farberkennung**: HSV- oder RGB-Farbmaske erkennt rote Pixel
3. **Contour-Detection**: OpenCV findet zusammenhaengende rote Bereiche (Ziele)
4. **Groesstes Ziel**: Das groesste zusammenhaengende rote Objekt wird als Ziel gewaehlt
5. **Mittelpunkt berechnen**: Der Schwerpunkt (Moment) des Ziels wird berechnet
6. **Maus bewegen**: Die Maus wird zum Zielmittelpunkt bewegt (Instant oder interpoliert)
7. **Schuss**: Rechtsklick wird ausgefuehrt
8. **Delay**: Kurze Wartezeit fuer Nachladen/Animation
9. **Zurueck zu Schritt 1**

---

## Hotkeys

| Taste | Funktion |
|---|---|
| **F1** | Waffentraining Start/Stop |
| **F2** | Captcha-Bereich oben-links setzen |
| **F3** | Captcha-Bereich unten-rechts setzen |
| **F4** | Captcha-Test (Screenshot + OCR) |
| **F5** | Debug-Modus an/aus |
| **F6** | Fishing-Bot Start/Stop |
| **F7** | Auto-Scan Bar |
| **F8** | X_START setzen (aktuelle Mausposition) |
| **F9** | X_END setzen (aktuelle Mausposition) |
| **F10** | SCAN_Y setzen (aktuelle Mausposition) |
| **F11** | Konfiguration speichern |
| **F12** | Beenden |

Alle Hotkeys sind im Hotkey-Editor anpassbar (Button in der GUI).

---

## Konfigurationsdatei (config.ini)

Die Konfiguration wird automatisch unter `%APPDATA%/AngelBot_v3/config.ini` gespeichert. Alle Einstellungen aus der GUI werden hier persistent abgelegt.

### Sektionen

```ini
[scan]
scan_y = 540
x_start = 192
x_end = 1728
scan_fps = 120
scan_band = 20
monitor_index = 1

[colors]
green_rgb = 85,255,85
cursor_rgb = 0,255,255
threshold = 25

[click]
second_click_delay = 1.0
post_cycle_cooldown = 2.0
input_lag_ms = 0
click_hold_ms = 8
auto_timing_enabled = True
timing_safety_ms = 2.0
end_zone_boost_ms = 8.0
green_inner_ratio = 0.08

[captcha]
cap_x1 = ...
cap_y1 = ...
cap_x2 = ...
cap_y2 = ...
check_interval = 3.0
enabled = True
type_mode = chat
tesseract_path =

[features]
sound_enabled = True
anti_afk_enabled = True
...

[waffentraining]
enabled = False
target_rgb = 255,0,0
threshold = 60
min_target_pixels = 30
scan_x1 = 192
scan_y1 = 108
scan_x2 = 1728
scan_y2 = 918
shot_delay = 0.08
aim_settle_ms = 5
shot_hold_ms = 50
scan_interval = 0.02
instant_aim = True
use_hsv = True
hsv_h_low1 = 0
hsv_h_high1 = 10
hsv_h_low2 = 160
hsv_h_high2 = 180
hsv_s_min = 80
hsv_v_min = 80

[hotkeys]
toggle = f6
wt_toggle = f1
auto_scan = f7
save = f11
quit = f12
...
```

---

## Code-Architektur

### main.py - Bot-Kern

| Bereich | Beschreibung |
|---|---|
| `BotConfig` | Dataclass mit allen Einstellungen, `to_ini()`/`from_ini()` fuer Persistenz |
| `BotState` | Laufzeit-Zustand des Bots (Running, Stats, Cursor-History, WT-State) |
| `color_match_mask()` | Erstellt eine Farbmaske (RGB-Differenz < Threshold) |
| `auto_scan_bar()` | Erkennt die Fishing-Bar automatisch |
| `wt_detect_target()` | **NEU**: Erkennt rote Ziele im Waffentraining via HSV/RGB + Contour-Detection |
| `wt_move_and_shoot()` | **NEU**: Bewegt Maus zum Ziel und fuehrt Klick aus |
| `wt_loop()` | **NEU**: Waffentraining-Hauptschleife (laeuft als eigener Thread) |
| `main_loop()` | Fishing-Bot Hauptschleife mit Velocity-Prediction |
| `handle_captcha()` | Captcha-Erkennung und OCR-Eingabe |
| `perform_click_cycle()` | Rechtsklick-Sequenz (Fangen + Auswerfen) |

### gui.py - Benutzeroberflaeche

| Bereich | Beschreibung |
|---|---|
| `FishingBotGUI` | Haupt-GUI mit Tabs, Live-Preview, Konsole |
| `_build_tab_bar()` | Bar/Scan-Einstellungen |
| `_build_tab_click()` | Klick/Timing-Einstellungen |
| `_build_tab_captcha()` | Captcha-Einstellungen |
| `_build_tab_wt()` | **NEU**: Waffentraining-Einstellungen (Scan-Bereich, Farbe, Timing, HSV) |
| `_build_tab_hud()` | HUD/Overlay-Einstellungen |
| `LicenseGate` | Lizenz-Abfrage beim Start |
| `AdminTool` | **ERWEITERT**: Lizenz-Generator + Lizenz-Verwaltung (Anzeigen, Loeschen, Verlaengern) |
| `ScanOverlay` | In-Game Overlay |
| `HotkeyEditor` | Hotkey-Anpassung |

### Waffentraining-Algorithmus im Detail

```
wt_detect_target(cfg, sct):
  1. Screenshot des gesamten Bildschirms
  2. Konvertierung zu HSV (oder RGB falls HSV deaktiviert)
  3. Farbmaske erstellen:
     - HSV: Zwei Bereiche fuer Rot (H: 0-10 UND H: 160-180)
     - RGB: Euklidische Distanz < Threshold
  4. cv2.findContours() findet zusammenhaengende Bereiche
  5. Groesster Bereich = Ziel (wenn >= min_target_pixels)
  6. cv2.moments() berechnet den Schwerpunkt
  7. Rueckgabe: (abs_x, abs_y) in Bildschirmkoordinaten

wt_move_and_shoot(cfg, target_x, target_y):
  1. Maus zum Ziel bewegen (SetCursorPos oder pydirectinput.moveTo)
  2. Kurze Pause (aim_settle_ms) damit Spiel Position registriert
  3. Rechtsklick ausfuehren (mit konfigurierbarer Hold-Dauer)
```

---

## Fehlerbehebung

### Waffentraining erkennt keine Ziele

1. **Debug-Modus aktivieren** (F5) und Log pruefen
2. **HSV-Werte anpassen**: S Min und V Min reduzieren
4. **Min. Pixel reduzieren**: Auf 10-20 setzen
5. **Farb-Toleranz erhoehen**: Auf 80-100

### Waffentraining erkennt zu viel (False Positives)

1. **Andere rote UI-Elemente ausblenden** falls moeglich
2. **Min. Pixel erhoehen**: Auf 80-150
3. **HSV S Min erhoehen**: Auf 120-150
4. **Farb-Toleranz reduzieren**: Auf 30-40

### Schuesse werden nicht registriert

1. **Aim-Settle erhoehen**: Auf 10-20ms
2. **Schuss-Hold erhoehen**: Auf 80-150ms
3. **Schuss-Delay erhoehen**: Auf 0.15-0.3s

### Fishing-Bot Probleme

1. **Auto-Scan** (F7) verwenden
2. **Debug-Modus** (F5) aktivieren
3. **Threshold** anpassen (20-40 ist optimal)
4. **Scan-Band Hoehe** auf 20-40 setzen

### Allgemein

- Spiel im **Fenstermodus** oder **Randlos-Fenster** spielen (kein Vollbild)
- Bot als **Administrator** starten falls Klicks nicht registriert werden
- **Anti-Virus** kann pydirectinput blockieren - Ausnahme hinzufuegen

---

## Admin-Panel: Lizenzverwaltung

Das Admin-Panel (erreichbar ueber den Admin-Login) hat jetzt zwei Tabs:

### Generator
Wie bisher: HWID eingeben, Stunden waehlen, Code generieren. Generierte Codes werden automatisch in der Lizenz-Registry gespeichert.

### Lizenzen verwalten

| Funktion | Beschreibung |
|---|---|
| **Aktualisieren** | Liste der Lizenzen neu laden |
| **Abgelaufene entfernen** | Alle abgelaufenen Lizenzen automatisch loeschen |
| **Ausgewaehlte loeschen** | Markierte Lizenzen loeschen |
| **Ausgewaehlte verlaengern** | Markierte Lizenzen um X Stunden verlaengern (neuer Code wird generiert) |

Jede Lizenz zeigt: HWID, Code, Erstellungsdatum, Ablaufdatum und Status (Aktiv/Abgelaufen).

Die Lizenz-Registry wird unter `%APPDATA%/AngelBot_v3/license_registry.json` gespeichert.
