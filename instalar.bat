@echo off
setlocal EnableDelayedExpansion
title IceNexus Edge — Instalador
color 0B
cls

echo.
echo  ============================================================
echo   ICE NEXUS EDGE — Instalacao do Servidor de Monitoramento
echo  ============================================================
echo.

REM ── Verifica Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado neste computador.
    echo.
    echo  Instale o Python 3.11 ou superior antes de continuar:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANTE: Marque a opcao "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER% encontrado.
echo.

REM ── Define destino ────────────────────────────────────────────────────────────
set DEST=C:\projetos\SitradColetor
set VENV=%DEST%\.venv

echo  Destino da instalacao: %DEST%
echo.

REM ── Copia arquivos ────────────────────────────────────────────────────────────
echo  [1/4] Copiando arquivos do IceNexus...
if not exist "C:\projetos" mkdir "C:\projetos"

REM Copia a pasta SitradColetor do pen drive para C:\projetos\
set SOURCE=%~dp0SitradColetor
if not exist "%SOURCE%" (
    echo  [ERRO] Pasta SitradColetor nao encontrada no pen drive.
    echo  Verifique se o pen drive esta correto.
    pause
    exit /b 1
)

robocopy "%SOURCE%" "%DEST%" /E /NFL /NDL /NJH /NJS /NC /NS /XD ".venv" "__pycache__" "data" >nul
echo  [OK] Arquivos copiados.
echo.

REM ── Copia config do cliente se existir ────────────────────────────────────────
set CONFIG_SRC=%~dp0config\client_config.json
if exist "%CONFIG_SRC%" (
    if not exist "%DEST%\config" mkdir "%DEST%\config"
    copy /Y "%CONFIG_SRC%" "%DEST%\config\client_config.json" >nul
    echo  [OK] Configuracao do cliente copiada.
    echo.
)

REM ── Cria ambiente virtual ──────────────────────────────────────────────────────
echo  [2/4] Criando ambiente virtual Python...
if exist "%VENV%" (
    echo  [OK] Ambiente virtual ja existe — pulando criacao.
) else (
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo  [ERRO] Falha ao criar ambiente virtual.
        pause
        exit /b 1
    )
    echo  [OK] Ambiente virtual criado.
)
echo.

REM ── Instala dependencias ──────────────────────────────────────────────────────
echo  [3/4] Instalando dependencias (pode demorar alguns minutos)...
"%VENV%\Scripts\pip.exe" install --upgrade pip --quiet
"%VENV%\Scripts\pip.exe" install -r "%DEST%\requirements.txt" --quiet
if errorlevel 1 (
    echo  [ERRO] Falha ao instalar dependencias.
    echo  Verifique a conexao com a internet e tente novamente.
    pause
    exit /b 1
)
echo  [OK] Dependencias instaladas.
echo.

REM ── Cria pasta de dados ────────────────────────────────────────────────────────
if not exist "%DEST%\data" mkdir "%DEST%\data"

REM ── Atualiza start.bat com o venv local ────────────────────────────────────────
echo  [4/4] Configurando inicializacao...
(
    echo @echo off
    echo title IceNexus Edge — Servidor de Monitoramento
    echo cd /d "%DEST%"
    echo set PYTHON=%VENV%\Scripts\python.exe
    echo set UVICORN=%VENV%\Scripts\uvicorn.exe
    echo echo Iniciando IceNexus Edge...
    echo "%%UVICORN%%" src.main:app --host 0.0.0.0 --port 8100
    echo pause
) > "%DEST%\start.bat"

REM ── Cria atalho na area de trabalho ───────────────────────────────────────────
set SHORTCUT=%USERPROFILE%\Desktop\IceNexus Edge.lnk
powershell -NoProfile -Command ^
    "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
    "$s.TargetPath='%DEST%\start.bat';" ^
    "$s.WorkingDirectory='%DEST%';" ^
    "$s.Description='IceNexus Edge — Servidor de Monitoramento';" ^
    "$s.Save()"
echo  [OK] Atalho criado na area de trabalho.
echo.

REM ── Conclusao ─────────────────────────────────────────────────────────────────
echo  ============================================================
echo   INSTALACAO CONCLUIDA COM SUCESSO!
echo  ============================================================
echo.
echo  Para iniciar o monitoramento:
echo    1. Clique em "IceNexus Edge" na area de trabalho, ou
echo    2. Execute: %DEST%\start.bat
echo.
echo  Dashboard disponivel em: http://localhost:8100
echo.
set /p INICIAR=  Deseja iniciar o IceNexus agora? (S/N):
if /i "%INICIAR%"=="S" (
    start "" "%DEST%\start.bat"
    timeout /t 6 /nobreak >nul
    start "" "http://localhost:8100"
)

echo.
pause
