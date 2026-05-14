@echo off
setlocal enabledelayedexpansion
title Prompt Evaluator Launcher

:: Change directory to where the script is located
cd /d "%~dp0"

echo ========================================================
echo   Prompt Evaluator - Environment Setup and Launcher
echo ========================================================
echo.

:: 1. Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.10+ from python.org and try again.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Check if a virtual environment exists; if not, create one
if not exist "venv\Scripts\python.exe" (
    echo [INFO] No virtual environment found. Creating one now...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. 
        pause
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created.
) else (
    echo [INFO] Virtual environment found.
)

:: 3. Activate the virtual environment
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

:: 4. Check for .env file
if not exist ".env" (
    echo [WARNING] No .env file found. Copying from .example.env...
    if exist ".example.env" (
        copy .example.env .env >nul
        echo [INFO] Created .env file. Please edit it to add your API_KEY.
    ) else (
        echo [ERROR] Could not find .example.env to create .env. The app might fail without an API Key.
    )
)

:: 5. Install or update required dependencies silently-ish
echo [INFO] Validating and installing dependencies (this may take a moment)...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Environment is ready.
echo ========================================================
echo   Starting Application Console...
echo ========================================================
echo.

:: 6. Launch the Streamlit application
streamlit run app.py

:: 7. Keep console open if Streamlit crashes
if errorlevel 1 (
    echo.
    echo [ERROR] The application terminated unexpectedly.
    pause
)

endlocal