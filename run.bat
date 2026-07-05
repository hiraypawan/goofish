@echo off
chcp 65001 >nul
title Goofish Login Automation
echo ================================
echo    Goofish (闲鱼) Login
echo ================================
echo.
echo  No Tor - Direct Chrome
echo  Temp profile + history DELETED on close
echo  AI: OpenRouter (FREE vision models)
echo  Malaysian phone numbers + OTP auto
echo.
echo ================================
echo.

cd /d "%~dp0"

echo [1] Start Goofish Login
echo [2] DEBUG MODE (click around, log selectors)
echo [3] Edit settings (open script in Notepad)
echo [4] View screenshots
echo [5] Exit
echo.
set /p choice="Choose: "

if "%choice%"=="1" (
    echo.
    echo Starting Goofish Login...
    echo.
    python run_goofish_login.py
    echo.
    pause
) else if "%choice%"=="2" (
    echo.
    echo Starting DEBUG MODE - click around, log everything...
    echo.
    python debug.py
    echo.
    pause
) else if "%choice%"=="3" (
    notepad run_goofish_login.py
) else if "%choice%"=="4" (
    if exist screenshots (
        explorer screenshots
    ) else (
        echo No screenshots folder yet. Run the login first.
        pause
    )
) else if "%choice%"=="5" (
    exit
) else (
    echo Invalid option
    pause
)
