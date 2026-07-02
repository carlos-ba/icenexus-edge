@echo off
setlocal EnableDelayedExpansion
title IceNexus — Montar Pen Drive
color 0B
cls

echo.
echo  ============================================================
echo   ICENEXUS EDGE — Montagem do Pen Drive de Campo
echo  ============================================================
echo.

set PROJETO=C:\projetos\SitradColetor
set SETUP=%PROJETO%\setup

REM ── Escolhe a letra do pen drive ─────────────────────────────────────────────
echo  Drives disponiveis:
echo.
wmic logicaldisk where "DriveType=2" get DeviceID,VolumeName 2>nul
echo.
set /p DRIVE=  Digite a letra do pen drive (ex: E):
set DRIVE=%DRIVE::=%
set PENDRIVE=%DRIVE%:\IceNexus

echo.
echo  Destino: %PENDRIVE%
echo.

if not exist "%DRIVE%:\" (
    echo  [ERRO] Drive %DRIVE%: nao encontrado.
    pause
    exit /b 1
)

REM ── Limpa e recria pasta ──────────────────────────────────────────────────────
if exist "%PENDRIVE%" (
    set /p CONFIRMA=  Ja existe conteudo em %PENDRIVE%. Substituir? (S/N):
    if /i not "!CONFIRMA!"=="S" exit /b 0
    rd /s /q "%PENDRIVE%"
)
mkdir "%PENDRIVE%"

REM ── 1. Configurador ───────────────────────────────────────────────────────────
echo  [1/4] Copiando configurador...
copy /Y "%SETUP%\dist\IceNexus_Configurador.exe" "%PENDRIVE%\" >nul
if errorlevel 1 echo  [AVISO] Configurador nao encontrado — execute o build primeiro.

REM ── 2. SitradColetor (sem venv e sem dados) ───────────────────────────────────
echo  [2/4] Copiando SitradColetor...
robocopy "%PROJETO%" "%PENDRIVE%\SitradColetor" /E /NFL /NDL /NJH /NJS ^
    /XD ".venv" "__pycache__" "data" "build" "dist" "setup" ".claude" ^
    /XF "*.pyc" "*.db" "*.log" "*.spec" >nul

REM ── 3. Config do cliente (se existir) ─────────────────────────────────────────
echo  [3/4] Copiando config do cliente...
if exist "%PROJETO%\config\client_config.json" (
    if not exist "%PENDRIVE%\config" mkdir "%PENDRIVE%\config"
    copy /Y "%PROJETO%\config\client_config.json" "%PENDRIVE%\config\" >nul
    echo  [OK] client_config.json incluido.
) else (
    echo  [INFO] Nenhum client_config.json encontrado — modo automatico sera usado.
)

REM ── 4. Script de instalacao ───────────────────────────────────────────────────
echo  [4/4] Copiando instalador...
copy /Y "%PROJETO%\instalar.bat" "%PENDRIVE%\" >nul

REM ── README ────────────────────────────────────────────────────────────────────
(
    echo IceNexus Edge — Pen Drive de Campo
    echo ====================================
    echo.
    echo ORDEM DE USO NO SERVIDOR EDGE:
    echo.
    echo PASSO 1 — Instalar o IceNexus
    echo   Execute: instalar.bat
    echo   Isso instala Python deps e configura o servidor.
    echo.
    echo PASSO 2 — Configurar o Sitrad
    echo   Execute: IceNexus_Configurador.exe
    echo   Siga as etapas na tela para configurar o Sitrad
    echo   e conectar os instrumentos.
    echo.
    echo PASSO 3 — Acessar o dashboard
    echo   Abra no navegador: http://localhost:8100
    echo   Ou use o atalho "IceNexus Edge" na area de trabalho.
    echo.
    echo Suporte: carlos.etr.ba@gmail.com
) > "%PENDRIVE%\LEIA-ME.txt"

REM ── Resultado ─────────────────────────────────────────────────────────────────
echo.
echo  ============================================================
echo   PEN DRIVE MONTADO COM SUCESSO!
echo  ============================================================
echo.
echo  Conteudo em %PENDRIVE%:
dir /b "%PENDRIVE%"
echo.

REM Tamanho total
for /f "tokens=3" %%s in ('dir /s /-c "%PENDRIVE%" ^| find "arquivo(s)"') do set SIZE=%%s
echo  Tamanho total: %SIZE% bytes
echo.
pause
