@echo off
title IceNexus Edge — Atualizacao
color 0B
cls

echo.
echo  ============================================================
echo   ICE NEXUS EDGE — Atualizacao do Servidor
echo  ============================================================
echo.

set DEST=C:\projetos\SitradColetor
set VENV=%DEST%\.venv

cd /d "%DEST%"

echo  [1/3] Baixando atualizacoes do GitHub...
git pull origin main
if errorlevel 1 (
    echo  [ERRO] Falha ao baixar atualizacoes.
    pause
    exit /b 1
)
echo  [OK] Codigo atualizado.
echo.

echo  [2/3] Atualizando dependencias...
"%VENV%\Scripts\pip.exe" install -r requirements.txt --quiet
echo  [OK] Dependencias atualizadas.
echo.

echo  [3/3] Reiniciando servidor...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im uvicorn.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start "" "%DEST%\start.bat"
echo  [OK] Servidor reiniciado.
echo.

echo  ============================================================
echo   ATUALIZACAO CONCLUIDA!
echo  ============================================================
echo.
echo  Dashboard: http://localhost:8100
echo.
pause
