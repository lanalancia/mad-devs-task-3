@echo off
setlocal EnableExtensions
cd /d "%~dp0"

:menu
echo.
echo Services:
echo   1. backend+db
echo   2. frontend
echo   3. mock-website
echo.
set /p CHOICE=Start service: 
if "%CHOICE%"=="1" goto start_backend
if "%CHOICE%"=="2" goto start_frontend
if "%CHOICE%"=="3" goto start_mocks
echo Unknown service. Enter 1, 2, or 3.
goto menu

:start_mocks
call :ensure_venv
if errorlevel 1 goto menu
echo Starting mock websites on ports 17781-17784.
.venv\Scripts\python.exe -m mock_sites
echo Mock websites stopped.
goto menu

:start_backend
call :ensure_venv
if errorlevel 1 goto menu
call :ensure_deps
if errorlevel 1 goto menu
call :ensure_db
if errorlevel 1 goto menu
echo Starting backend. The HTTP API uses the port in config.ini.
.venv\Scripts\python.exe -m backend
echo Backend stopped.
goto menu

:start_frontend
where node >nul 2>&1
if errorlevel 1 (
    echo Node.js is required to start the frontend.
    goto menu
)
where npm >nul 2>&1
if errorlevel 1 (
    echo npm is required to start the frontend.
    goto menu
)
if not exist "frontend\node_modules\" (
    echo Installing frontend packages...
    pushd frontend
    call npm install
    if errorlevel 1 (
        echo Failed to install frontend packages.
        popd
        goto menu
    )
    popd
)
echo Starting frontend at http://localhost:17777
pushd frontend
call npm run dev
echo Frontend stopped.
popd
goto menu

:ensure_venv
if exist ".venv\Scripts\python.exe" exit /b 0
echo Creating virtual environment...
where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto try_python
py -3 -m venv .venv
if exist ".venv\Scripts\python.exe" exit /b 0

:try_python
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto need_python
python -m venv .venv
if exist ".venv\Scripts\python.exe" exit /b 0
echo Failed to create the virtual environment.
exit /b 1

:need_python
echo Python 3.10 or newer is required.
exit /b 1

:ensure_deps
.venv\Scripts\python.exe -c "import psycopg" >nul 2>&1
if not errorlevel 1 exit /b 0
echo Installing Python packages...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install Python packages.
    exit /b 1
)
exit /b 0

:ensure_db
docker start mad-devs-postgres >nul 2>&1
if errorlevel 1 (
    echo PostgreSQL container mad-devs-postgres is not available.
    echo Run .venv\Scripts\python.exe install.py and choose the Docker PostgreSQL install.
    exit /b 1
)
set /a TRIES=0

:wait_db
docker exec mad-devs-postgres pg_isready >nul 2>&1
if not errorlevel 1 exit /b 0
set /a TRIES+=1
if %TRIES% GEQ 30 (
    echo PostgreSQL is not accepting connections yet.
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_db
