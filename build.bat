@echo off
REM Build script for RoK Automation Bot
REM Double-click this file to build the application

echo.
echo ============================================
echo   RoK Automation Bot - Build Script
echo ============================================
echo.

REM Check if virtual environment exists and activate it
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
)

REM Run the Python build script
python build.py %*

REM Keep window open if there was an error
if errorlevel 1 (
    echo.
    echo Build failed! See errors above.
    pause
    exit /b 1
)

echo.
echo Build complete!
echo.
pause
