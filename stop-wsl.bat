@echo off
setlocal
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
for /f "usebackq delims=" %%i in (`wsl wslpath -a "%PROJECT_DIR%"`) do set "WSL_DIR=%%i"
echo [Nexus] Stopping stack...
wsl -e bash -lc "cd '%WSL_DIR%' && docker compose -f docker-compose.yml down"
echo [Nexus] Stopped.
endlocal
