@echo off
setlocal
set "nexus_no_pause="
if /i "%~1"=="--no-pause" set "nexus_no_pause=1"
cd /d "%~dp0"
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :folder_failed

call "%~dp0setup_windows.bat" --no-pause
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :setup_failed

".venv312\Scripts\python.exe" -m pip --require-virtualenv install pyinstaller==6.12.0
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :tools_failed

".venv312\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name "Intellectual Nexus Academy" main.py
set "nexus_exit=%errorlevel%"
if not "%nexus_exit%"=="0" goto :build_failed
if not exist "dist\Intellectual Nexus Academy.exe" goto :missing_executable

echo.
echo Build complete: dist\Intellectual Nexus Academy.exe
echo Test this executable on the academy computer before replacing your previous version.
echo Academy records remain in the external application data folder.
goto :finish

:folder_failed
echo Could not open the project folder. Extract the complete project to a local folder.
goto :finish

:setup_failed
echo Build stopped because Python 3.12 setup failed. See the error above.
goto :finish

:tools_failed
echo PyInstaller installation failed with exit code %nexus_exit%.
echo Check the error above and internet access. The build uses .venv312, never Python 3.14.
goto :finish

:build_failed
echo Executable build failed with exit code %nexus_exit%. See the error above.
echo Keep your previous working executable and backup. Do not distribute an incomplete build.
goto :finish

:missing_executable
set "nexus_exit=1"
echo The build returned without the expected executable. Review the PyInstaller output above.
goto :finish

:finish
if not defined nexus_no_pause pause
exit /b %nexus_exit%
