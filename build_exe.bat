@echo off
echo Building Rise of Kingdoms Automation Executable
echo =============================================
echo.

REM Check if src directory exists
if not exist "src" (
    echo ERROR: src directory not found!
    echo Make sure you run this script from the project root directory.
    pause
    exit /b 1
)

REM Check if config.ini exists in src directory
if not exist "src\config.ini" (
    echo ERROR: config.ini not found in src directory!
    echo Make sure your config.ini file is in the src folder.
    pause
    exit /b 1
)

REM Create assets directory if it doesn't exist
if not exist "assets" (
    echo Creating assets directory...
    mkdir assets
)

REM Check if we have an icon file, create a placeholder if needed
if not exist "assets\rok_icon.ico" (
    echo No icon file found. The executable will use the default icon.
)

REM Install required packages
echo Installing required packages...
pip install pyinstaller opencv-python numpy pytesseract pillow

REM Build the executable
echo Building executable...
pyinstaller --clean rok_automation.spec

REM Check if build was successful
if not exist "dist\RoK Automation\RoK Automation.exe" (
    echo ERROR: Build failed! Executable was not created.
    pause
    exit /b 1
)

echo.
echo Build completed successfully!
echo Executable is located in: "dist\RoK Automation" folder.
echo.
echo Next steps:
echo 1. Include Tesseract OCR with your distribution
echo 2. Test the executable
echo 3. Create a ZIP package for distribution
echo.

REM Copy config.ini to the dist folder if it wasn't copied by PyInstaller
if not exist "dist\RoK Automation\config.ini" (
    echo Copying config.ini to the dist folder...
    copy "src\config.ini" "dist\RoK Automation\"
)

pause