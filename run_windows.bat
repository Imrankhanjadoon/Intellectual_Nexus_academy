@echo off
setlocal
cd /d "%~dp0"
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :folder_failed
set "nexus_python="
if exist ".venv312\Scripts\python.exe" (
    ".venv312\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
    if not errorlevel 1 set "nexus_python=.venv312\Scripts\python.exe"
)
if defined nexus_python goto :run
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
    if not errorlevel 1 set "nexus_python=.venv\Scripts\python.exe"
)
if defined nexus_python goto :run
set "nexus_exit=1"
echo A working Python 3.12 environment was not found.
echo Run setup_windows.bat first. It prepares .venv312 and preserves other environments.
echo Python 3.14 environments are not used by this launcher.
pause
exit /b %nexus_exit%

:folder_failed
echo Could not open the project folder. Extract the complete project to a local folder.
pause
exit /b %nexus_exit%

:run
"%nexus_python%" main.py %*
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" (
    echo The application stopped with exit code %nexus_exit%. See the error above.
    echo If a dependency is missing, run setup_windows.bat again.
    pause
)
exit /b %nexus_exit%
