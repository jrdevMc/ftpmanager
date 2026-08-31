@echo off
setlocal

echo ============================================
echo   Web Server Manager - Installation
echo ============================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [Error] Python was not found.
    echo Please install Python 3 from https://www.python.org/downloads/
    echo Important: Check "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

set "INSTALL_DIR=%LOCALAPPDATA%\WebServerManager\app"
echo Installing to: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

xcopy /E /I /Y "%~dp0*.py" "%INSTALL_DIR%\" >nul

echo Creating desktop shortcut...
powershell -NoProfile -Command ^
    "$ws = New-Object -COM WScript.Shell;" ^
    "$s = $ws.CreateShortcut('%USERPROFILE%\Desktop\Web Server Manager.lnk');" ^
    "$s.TargetPath = (Get-Command pythonw.exe).Source;" ^
    "$s.Arguments = '\"%INSTALL_DIR%\main.py\"';" ^
    "$s.WorkingDirectory = '%INSTALL_DIR%';" ^
    "$s.Save()"

echo.
echo Done! You can now find "Web Server Manager" on your desktop.
echo nginx will be downloaded automatically the first time you start an nginx web server.
pause
