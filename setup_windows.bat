@echo off
setlocal
set "nexus_no_pause="
if /i "%~1"=="--no-pause" set "nexus_no_pause=1"
cd /d "%~dp0"
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :folder_failed
set "nexus_python=.venv312\Scripts\python.exe"
if exist "%nexus_python%" goto :validate_python
if exist ".venv312" goto :incomplete_environment

py -3.12 --version >nul 2>&1
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :launcher_failed
py -3.12 -m venv .venv312
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :creation_failed

:validate_python
"%nexus_python%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :wrong_python
if not exist "requirements.lock" goto :missing_project_file
"%nexus_python%" -m pip --require-virtualenv install -r requirements.lock
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :installation_failed

echo.
echo Setup complete using Python 3.12 in .venv312.
echo Open run_windows.bat, or select .venv312\Scripts\python.exe in PyCharm.
echo Other virtual environments have been left unchanged.
goto :finish

:folder_failed
echo Could not open the project folder. Extract the complete project to a local folder.
goto :finish

:launcher_failed
echo Python 3.12 was not found by the Python Launcher.
echo Install 64-bit Python 3.12 from python.org with the Python Launcher enabled.
echo Your existing virtual environments have not been changed.
goto :finish

:creation_failed
echo Could not create .venv312. Check the error above and folder permissions.
echo Any existing files have been kept. An incomplete folder may need to be renamed before retrying.
goto :finish

:incomplete_environment
set "nexus_exit=1"
echo A .venv312 folder already exists, but its Windows Python executable is missing.
echo The folder has been preserved. Rename it manually to keep its contents, then run setup again.
goto :finish

:wrong_python
echo The existing .venv312 environment is not a working Python 3.12 environment.
echo It has been preserved. Rename it manually to keep its contents, then run setup again.
echo Do not use a Python 3.14 environment for this application's pinned Windows build tools.
goto :finish

:missing_project_file
set "nexus_exit=1"
echo requirements.lock is missing. Download and extract the complete project again.
goto :finish

:installation_failed
echo Dependency installation failed with exit code %nexus_exit%.
echo Check the error above and your internet connection, then run setup again.
goto :finish

:finish
if not defined nexus_no_pause pause
exit /b %nexus_exit%
