@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto activate

echo Creating virtual environment...

where py >nul 2>&1
if errorlevel 1 goto try_python

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto try_python

py -3 -m venv .venv
if exist ".venv\Scripts\python.exe" goto activate

:try_python
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto need_python

python -m venv .venv
if exist ".venv\Scripts\python.exe" goto activate

echo Failed to create the virtual environment.
pause
exit /b 1

:need_python
echo Python 3.10 or newer is required.
pause
exit /b 1

:activate
call "%~dp0.venv\Scripts\activate.bat"
echo.
echo Virtual environment is active.
echo Run: python install.py
echo.
cmd /k
