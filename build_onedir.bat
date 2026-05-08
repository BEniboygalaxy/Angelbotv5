@echo off
REM ============================================================
REM  Build im ONEDIR Modus - wird seltener vom Antivirus geflaggt
REM  Output: dist\MinecraftFishingBot\  (ein Ordner, EXE liegt drin)
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if "%PY_CMD%"=="" where python >nul 2>nul && set "PY_CMD=python"
if "%PY_CMD%"=="" (
    echo [FEHLER] Python nicht gefunden!
    pause
    exit /b 1
)

if not exist venv (
    %PY_CMD% -m venv venv
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip wheel setuptools
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist MinecraftFishingBot.spec del /q MinecraftFishingBot.spec

echo [Bauen im ONEDIR Modus...]
pyinstaller --onedir --name MinecraftFishingBot --windowed ^
    --collect-all keyboard ^
    --collect-all pydirectinput ^
    --collect-all mss ^
    --collect-all pytesseract ^
    --collect-all customtkinter ^
    --collect-submodules cv2 ^
    --collect-submodules numpy ^
    gui.py

if errorlevel 1 (echo [FEHLER] Build & pause & exit /b 1)

echo.
echo ============================================================
echo  FERTIG!  Starte:  dist\MinecraftFishingBot\MinecraftFishingBot.exe
echo ============================================================
echo  Wenn Antivirus weiterhin meckert -> Ordner als Ausnahme hinzufuegen.
echo.
pause
endlocal
