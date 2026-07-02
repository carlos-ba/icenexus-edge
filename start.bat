@echo off
cd /d "%~dp0"

set PYTHON=C:\projetos\Emulador\.venv\Scripts\python.exe
set UVICORN=C:\projetos\Emulador\.venv\Scripts\uvicorn.exe

echo ============================================================
echo  Sitrad Coletor Dashboard
echo  http://localhost:8100
echo ============================================================

%UVICORN% src.main:app --host 0.0.0.0 --port 8100 --reload
pause
