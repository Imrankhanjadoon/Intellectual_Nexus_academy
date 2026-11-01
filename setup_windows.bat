@echo off
setlocal
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo Install Python 3.12 from python.org with the Python Launcher enabled, then try again.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.lock
if errorlevel 1 (
    echo Setup failed. Check the error above and your internet connection.
    pause
    exit /b 1
)
echo Setup complete. Open run_windows.bat or run main.py in PyCharm.
pause
