@echo off
:: Check for admin privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [++] Running with admin privileges...
) else (
    echo [--] Error: Please right-click this run.bat file and select "Run as administrator"!
    pause
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0clean.ps1"
pause
