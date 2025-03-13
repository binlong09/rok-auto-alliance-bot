# Rise of Kingdoms Automation - Distribution Instructions

This document explains how to prepare the Rise of Kingdoms Automation Tool for distribution to end users.

## Building the Executable

1. Make sure you have all dependencies installed:
   ```
   pip install pyinstaller opencv-python numpy pytesseract pillow
   ```

2. Run the build script:
   ```
   build_exe.bat
   ```

3. The executable and all necessary files will be created in the `dist\RoK Automation` folder.

## Packaging for Distribution

The application has an external dependency on Tesseract OCR that needs to be included. Follow these steps to prepare a complete package:

1. Download the [Tesseract OCR installer](https://github.com/UB-Mannheim/tesseract/wiki) (64-bit recommended)

2. Create a distribution folder with the following structure:
   ```
   RoK Automation Tool/
   ├── RoK Automation/        (contents of dist\RoK Automation folder)
   │   ├── RoK Automation.exe
   │   ├── config.ini
   │   └── ... (other files)
   ├── Tesseract-OCR/         (contents of Tesseract OCR installation)
   │   ├── tesseract.exe
   │   └── ... (other files)
   ├── INSTALL.txt            (installation instructions)
   └── README.txt             (general usage instructions)
   ```

3. Create an INSTALL.txt file that explains that Tesseract is already included and just needs to be configured in the app.

4. Update the config.ini file to point to the relative Tesseract path:
   ```
   [OCR]
   tesseract_path = ./Tesseract-OCR/tesseract.exe
   ```

5. Create a ZIP archive of the entire folder for distribution.

## Alternative: Creating an Installer

For a more professional distribution, consider creating an installer using tools like:
- [NSIS (Nullsoft Scriptable Install System)](https://nsis.sourceforge.io/)
- [Inno Setup](https://jrsoftware.org/isinfo.php)

An installer can:
- Place files in the correct locations
- Set up environment variables if needed
- Create desktop/start menu shortcuts
- Register the application properly

## Important Notes for End Users

Make sure to include these notes in your documentation:

1. The application requires BlueStacks to be installed and configured
2. The application needs to be run with administrator privileges to properly interact with BlueStacks
3. Users should set up their characters in BlueStacks before running the automation
4. Anti-virus software might flag the application - users may need to add an exception