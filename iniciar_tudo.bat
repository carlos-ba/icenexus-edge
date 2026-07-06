@echo off
title IceNexus Edge — Inicializacao Completa
color 0B
cd /d "%~dp0"

echo.
echo  ============================================================
echo   ICE NEXUS EDGE — Subindo todos os servicos
echo  ============================================================
echo.

echo  [1/3] Encerrando instancias anteriores...
taskkill /f /im python.exe  >nul 2>&1
taskkill /f /im uvicorn.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo  [OK]
echo.

echo  [2/3] Emulador PCT-122E...
findstr /c:"\"emulador\": true" "%~dp0config\client_config.json" >nul 2>&1
if %errorlevel%==0 (
    if exist "C:\projetos\Emulador\start.bat" (
        start "" "C:\projetos\Emulador\start.bat"
        timeout /t 3 /nobreak >nul
        echo  [OK] Emulador iniciado na porta 8000.
    ) else (
        echo  [AVISO] Emulador habilitado no config mas nao instalado.
    )
) else (
    echo  [--] Emulador desabilitado no config — nao sera iniciado.
)
echo.

echo  [3/3] Servidor IceNexus Edge...
start "" "%~dp0start.bat"
echo  [OK] Dashboard: http://localhost:8100
echo.

echo  ============================================================
echo   TUDO PRONTO!
echo  ============================================================
echo.
pause
