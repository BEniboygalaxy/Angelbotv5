@echo off
REM ============================================================
REM  PORTABLE MODUS - Startet den Bot OHNE EXE-Build
REM  Funktioniert garantiert, da nichts kompiliert wird.
REM
REM  Voraussetzung: Python 3.10+ installiert (mit "Add to PATH")
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo  Minecraft Fishing Bot - PORTABLE Modus
echo ============================================================
echo.

REM Python finden
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if "%PY_CMD%"=="" where python >nul 2>nul && set "PY_CMD=python"
if "%PY_CMD%"=="" (
    echo [FEHLER] Python nicht gefunden!
    echo.
    echo Installiere Python 3.10 oder neuer von:
    echo   https://www.python.org/downloads/
    echo.
    echo WICHTIG bei der Installation:
    echo   - "Add Python to PATH" anhaken
    echo   - "Install for all users" empfohlen
    echo.
    pause
    exit /b 1
)

echo [OK] Python:
%PY_CMD% --version
echo.

REM venv beim ersten Mal anlegen
if not exist venv (
    echo [Setup] Erstelle virtuelle Umgebung und installiere Pakete...
    echo Das dauert beim ersten Start ca. 2-4 Minuten...
    echo.
    %PY_CMD% -m venv venv
    if errorlevel 1 (
        echo [FEHLER] venv konnte nicht erstellt werden.
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip wheel setuptools
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [FEHLER] Paket-Installation fehlgeschlagen.
        pause
        exit /b 1
    )
    echo.
    echo [Setup] Fertig!
    echo.
) else (
    call venv\Scripts\activate.bat
)

echo.
echo ============================================================
echo  STARTE BOT-GUI...
echo ============================================================
echo.
echo  HINWEIS: Damit Hotkeys + Mausklicks im Spiel funktionieren,
echo  starte dieses Fenster als ADMINISTRATOR!
echo  (Rechtsklick auf start_portable.bat -^> Als Admin ausfuehren)
echo.

python gui.py

if errorlevel 1 (
    echo.
    echo [FEHLER] Bot beendet mit Fehler.
    echo.
)

pause
endlocal
