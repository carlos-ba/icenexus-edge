@echo off
title IceNexus Edge — Dashboard
color 0B
cd /d "%~dp0"

set VENV=%~dp0.venv

echo.
echo  ============================================================
echo   ICE NEXUS EDGE
echo   Dashboard: http://localhost:8100
echo  ============================================================
echo.

"%VENV%\Scripts\uvicorn.exe" src.main:app --host 0.0.0.0 --port 8100
pause
