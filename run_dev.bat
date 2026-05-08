@echo off
REM Schnelltest: GUI direkt starten (ohne EXE-Build)
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

python gui.py
pause
endlocal
