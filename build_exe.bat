@echo off
chcp 65001 >nul
title Creation de ObservatoireMeteo.exe
cd /d "%~dp0"

echo ==============================================
echo   Observatoire Meteo - creation du .exe
echo ==============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Python est introuvable. Installe Python 3.10+ et coche "Add Python to PATH".
    pause
    exit /b 1
)

echo [1/3] Installation des dependances...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [ERREUR] Installation des dependances impossible.
    pause
    exit /b 1
)

echo.
echo [2/3] Compilation avec PyInstaller (1 a 3 minutes)...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name ObservatoireMeteo ^
    --collect-all customtkinter ^
    gui.py
if errorlevel 1 (
    echo [ERREUR] La compilation a echoue.
    pause
    exit /b 1
)

echo.
echo [3/3] Finalisation...
copy /Y "dist\ObservatoireMeteo.exe" "ObservatoireMeteo.exe" >nul
rmdir /S /Q build 2>nul
del /Q ObservatoireMeteo.spec 2>nul

echo.
echo ==============================================
echo   Termine !  ->  %~dp0ObservatoireMeteo.exe
echo   La base meteo.db sera creee a cote du .exe.
echo ==============================================
pause
