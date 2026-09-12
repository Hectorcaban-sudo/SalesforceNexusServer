@echo off
setlocal EnableExtensions
REM ============================================================================
REM  Salesforce Nexus AI Server — rebuild image & deploy stack via WSL
REM  Network: Nexus  |  Ports bound to 0.0.0.0
REM ============================================================================
REM  Requirements:
REM    - Docker Engine available inside WSL (docker + docker compose plugin)
REM    - This script lives in the project root (next to docker-compose.yml)
REM ============================================================================

set "COMPOSE_FILE=docker-compose.yml"
set "PROJECT_DIR=%~dp0"
REM strip trailing backslash for wslpath
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

echo.
echo [Nexus] Project directory (Windows): %PROJECT_DIR%
echo [Nexus] Using compose file: %COMPOSE_FILE%
echo.

REM Convert Windows path to WSL path (e.g. C:\Users\... -> /mnt/c/Users/...)
for /f "usebackq delims=" %%i in (`wsl wslpath -a "%PROJECT_DIR%"`) do set "WSL_DIR=%%i"
if not defined WSL_DIR (
  echo [ERROR] Could not convert path with wslpath. Is WSL installed?
  exit /b 1
)

echo [Nexus] Project directory (WSL): %WSL_DIR%
echo.

REM Verify docker is available in WSL
wsl -e bash -lc "command -v docker >/dev/null 2>&1" || (
  echo [ERROR] docker not found inside WSL. Install Docker Engine in your distro.
  exit /b 1
)

wsl -e bash -lc "docker compose version >/dev/null 2>&1" || (
  echo [ERROR] docker compose plugin not found in WSL.
  exit /b 1
)

echo [Nexus] Stopping existing stack (if any)...
wsl -e bash -lc "cd '%WSL_DIR%' && docker compose -f %COMPOSE_FILE% down --remove-orphans"

echo.
echo [Nexus] Building image and starting containers on network Nexus...
wsl -e bash -lc "cd '%WSL_DIR%' && docker compose -f %COMPOSE_FILE% up -d --build --force-recreate"

if errorlevel 1 (
  echo.
  echo [ERROR] Deploy failed. Check output above.
  exit /b 1
)

echo.
echo [Nexus] Waiting for health...
wsl -e bash -lc "cd '%WSL_DIR%' && docker compose -f %COMPOSE_FILE% ps"

echo.
echo ============================================================================
echo  Deploy complete
echo ============================================================================
echo  App:              http://0.0.0.0:8000   (or http://localhost:8000)
echo  RabbitMQ UI:      http://0.0.0.0:15672  (user/pass from .env, default nexus/nexus)
echo  RabbitMQ AMQP:    0.0.0.0:5672
echo  PostgreSQL:       0.0.0.0:5432          (user/db default nexus/nexus)
echo  Docker network:   Nexus
echo.
echo  In Admin Configuration - Message broker, use host: rabbitmq  port: 5672
echo ============================================================================
echo.

endlocal
exit /b 0
