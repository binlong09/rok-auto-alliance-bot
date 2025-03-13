@echo off
echo Rise of Kingdoms Automation - Distribution Package Creator
echo ========================================================
echo.

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not found in PATH
    echo Please install Python 3.8 or higher.
    pause
    exit /b 1
)

REM Verify src directory exists
if not exist "src" (
    echo ERROR: src directory not found!
    echo Make sure you run this script from the project root directory.
    pause
    exit /b 1
)

REM Create distribution directory structure
echo Setting up distribution environment...

REM Create assets directory if it doesn't exist
if not exist "assets" mkdir assets

REM Create placeholder icon if needed
if not exist "assets\rok_icon.ico" (
    echo Creating placeholder icon...
    python create_placeholder_icon.py
)

REM Check for config.ini in src directory - create a default one if needed
if not exist "src\config.ini" (
    echo Creating default config.ini file in src folder...
    echo [BlueStacks]> src\config.ini
    echo bluestacks_exe_path = C:\Program Files\BlueStacks_nxt\HD-Player.exe>> src\config.ini
    echo bluestacks_instance_name = Nougat64_7>> src\config.ini
    echo adb_path = C:\Program Files\BlueStacks_nxt\HD-Adb.exe>> src\config.ini
    echo wait_for_startup_seconds = 10>> src\config.ini
    echo adb_port = 5555>> src\config.ini
    echo.>> src\config.ini
    echo [RiseOfKingdoms]>> src\config.ini
    echo rok_version = global>> src\config.ini
    echo package_name = com.lilithgame.roc.gp>> src\config.ini
    echo activity_name = com.harry.engine.MainActivity>> src\config.ini
    echo game_load_wait_seconds = 12>> src\config.ini
    echo num_of_characters = 22>> src\config.ini
    echo march_preset = 6>> src\config.ini
    echo character_login_screen_loading_time = 3>> src\config.ini
    echo perform_build = True>> src\config.ini
    echo perform_donation = True>> src\config.ini
    echo.>> src\config.ini
    echo [OCR]>> src\config.ini
    echo tesseract_path = .\Tesseract-OCR\tesseract.exe>> src\config.ini
    echo text_region_x = 200>> src\config.ini
    echo text_region_y = 0>> src\config.ini
    echo text_region_width = 600>> src\config.ini
    echo text_region_height = 150>> src\config.ini
    echo preprocess_image = True>> src\config.ini
    echo.>> src\config.ini
    echo [Navigation]>> src\config.ini
    echo x_increment = 400>> src\config.ini
    echo y_increment = 140>> src\config.ini
    echo click_delay_ms = 1000>> src\config.ini
)

REM Build the executable
echo Building executable with PyInstaller...
call build_exe.bat

REM Check if build was successful
if not exist "dist\RoK Automation\RoK Automation.exe" (
    echo ERROR: Build failed! Cannot continue with distribution packaging.
    pause
    exit /b 1
)

REM Create distribution directory
echo Creating distribution package...
if not exist "distribution" mkdir distribution

REM Clear any existing distribution
if exist "distribution\RoK Automation Tool" (
    rmdir /s /q "distribution\RoK Automation Tool"
)
mkdir "distribution\RoK Automation Tool"

REM Copy executable and files
echo Copying files to distribution package...
xcopy "dist\RoK Automation" "distribution\RoK Automation Tool\RoK Automation\" /E /I /Y

REM Copy documentation
echo Copying documentation...
copy "INSTALL.txt" "distribution\RoK Automation Tool\"
copy "README.md" "distribution\RoK Automation Tool\README.txt"

REM Create a note about Tesseract
echo Creating Tesseract note...
echo =====================================>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo IMPORTANT: TESSERACT OCR INSTALLATION>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo =====================================>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo.>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo This application requires Tesseract OCR to function properly.>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo.>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo Option 1: Include Tesseract with distribution (Recommended)>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo - Download Tesseract OCR from: https://github.com/UB-Mannheim/tesseract/wiki>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo - Install it, then copy the entire Tesseract-OCR folder into>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo   the "RoK Automation Tool" folder alongside the "RoK Automation" folder>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo.>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo Option 2: Require users to install Tesseract separately>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"
echo - Update config.ini with the correct path to tesseract.exe on the user's system>> "distribution\RoK Automation Tool\TESSERACT_NOTE.txt"

echo.
echo Distribution package created successfully!
echo The package is located in: distribution\RoK Automation Tool
echo.
echo IMPORTANT: You still need to include Tesseract OCR with your distribution.
echo See the TESSERACT_NOTE.txt file in the distribution folder for instructions.
echo.

pause