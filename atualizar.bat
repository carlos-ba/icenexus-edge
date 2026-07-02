@echo off
title IceNexus Edge — Atualizacao
color 0B
cd /d "%~dp0"

set VENV=%~dp0.venv
set REPO=https://github.com/carlos-ba/icenexus-edge.git

echo.
echo  ============================================================
echo   ICE NEXUS EDGE — Atualizacao
echo  ============================================================
echo.

echo  [1/4] Baixando codigo do GitHub...
git fetch %REPO% main && git reset --hard FETCH_HEAD
if errorlevel 1 ( echo  [ERRO] Falha no git. & pause & exit /b 1 )
echo  [OK]
echo.

echo  [2/4] Atualizando dependencias...
"%VENV%\Scripts\pip.exe" install -r requirements.txt --quiet
echo  [OK]
echo.

echo  [3/4] Encerrando servidor anterior...
taskkill /f /im python.exe  >nul 2>&1
taskkill /f /im uvicorn.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo  [OK]
echo.

echo  [4/4] Iniciando servidor...
start "" "%~dp0start.bat"
echo  [OK]
echo.

echo  ============================================================
echo   Pronto! Dashboard: http://localhost:8100
echo  ============================================================
echo.
pause
