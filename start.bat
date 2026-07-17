@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title iLink Proxy

:: Double-click: reopen self with cmd /k so the window NEVER auto-closes
if /i not "%~1"=="_run" (
    cmd /k "%~f0" _run
    exit /b
)

echo ========================================
echo    iLink Proxy starting...
echo ========================================
echo.
echo Proxy:  127.0.0.1:8888
echo Panel:  http://127.0.0.1:8889
echo Ctrl+C to stop
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found in PATH
    goto :end
)

python main.py start --compiled
echo.
echo [INFO] process exited, code=%ERRORLEVEL%

:end
echo.
echo Window stays open. Type exit or close this window.
echo ========================================
