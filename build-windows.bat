@echo off
rem Build the self-contained Windows program: dist\MapsStudio.exe
setlocal
cd /d "%~dp0"
py -3 -m pip install -r requirements-build.txt || goto :error
py -3 -m PyInstaller --clean --noconfirm MapsStudio.spec || goto :error
echo.
echo Built dist\MapsStudio.exe
pause
exit /b 0
:error
echo Build failed. Install Python 3.11 or newer from python.org (tick "tcl/tk and IDLE").
pause
exit /b 1
