#!/usr/bin/env python3
"""
Build Script for RoK Automation Bot

This script automates the build process:
1. Cleans previous build artifacts
2. Runs PyInstaller to create the executable
3. Creates a versioned ZIP file for distribution

Usage:
    python build.py              # Build and create ZIP
    python build.py --clean      # Clean only
    python build.py --no-zip     # Build without creating ZIP
    python build.py --version X.Y.Z  # Specify version number
"""

import os
import sys
import shutil
import subprocess
import zipfile
import argparse
from datetime import datetime
from pathlib import Path


# Configuration
APP_NAME = "RoK Automation"
SPEC_FILE = "rok_automation.spec"
DIST_DIR = "dist"
BUILD_DIR = "build"
OUTPUT_DIR = "releases"

# Default version (can be overridden via command line)
DEFAULT_VERSION = "1.0.4"


class BuildError(Exception):
    """Custom exception for build errors"""
    pass


def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_step(text):
    """Print a step indicator"""
    print(f"\n>> {text}")


def print_success(text):
    """Print success message"""
    print(f"   [OK] {text}")


def print_error(text):
    """Print error message"""
    print(f"   [ERROR] {text}")


def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.resolve()


def clean_build_artifacts(project_root):
    """Remove previous build artifacts"""
    print_step("Cleaning previous build artifacts...")

    dirs_to_clean = [
        project_root / DIST_DIR,
        project_root / BUILD_DIR,
    ]

    # Also clean __pycache__ directories
    for pycache in project_root.rglob("__pycache__"):
        if ".venv" not in str(pycache):
            dirs_to_clean.append(pycache)

    cleaned_count = 0
    for dir_path in dirs_to_clean:
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
                print_success(f"Removed {dir_path.name}")
                cleaned_count += 1
            except Exception as e:
                print_error(f"Failed to remove {dir_path}: {e}")

    if cleaned_count == 0:
        print_success("Nothing to clean")
    else:
        print_success(f"Cleaned {cleaned_count} directories")


def check_dependencies():
    """Check if required tools are available"""
    print_step("Checking dependencies...")

    # Check PyInstaller
    try:
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print_success(f"PyInstaller {version}")
        else:
            raise BuildError("PyInstaller not found. Install with: pip install pyinstaller")
    except FileNotFoundError:
        raise BuildError("PyInstaller not found. Install with: pip install pyinstaller")

    # Check if spec file exists
    project_root = get_project_root()
    spec_path = project_root / SPEC_FILE
    if not spec_path.exists():
        raise BuildError(f"Spec file not found: {spec_path}")
    print_success(f"Spec file found: {SPEC_FILE}")


def run_pyinstaller(project_root):
    """Run PyInstaller to build the executable"""
    print_step("Running PyInstaller...")

    spec_path = project_root / SPEC_FILE

    # Run PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_path)
    ]

    print(f"   Command: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            check=True
        )
        print_success("PyInstaller completed successfully")
    except subprocess.CalledProcessError as e:
        raise BuildError(f"PyInstaller failed with exit code {e.returncode}")


def verify_build(project_root):
    """Verify the build output exists"""
    print_step("Verifying build output...")

    dist_path = project_root / DIST_DIR / APP_NAME
    if not dist_path.exists():
        raise BuildError(f"Build output not found: {dist_path}")

    # Check for main executable
    exe_name = f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME
    exe_path = dist_path / exe_name
    if not exe_path.exists():
        raise BuildError(f"Executable not found: {exe_path}")

    # Count files
    file_count = sum(1 for _ in dist_path.rglob("*") if _.is_file())
    dir_size = sum(f.stat().st_size for f in dist_path.rglob("*") if f.is_file())
    size_mb = dir_size / (1024 * 1024)

    print_success(f"Executable found: {exe_name}")
    print_success(f"Total files: {file_count}")
    print_success(f"Total size: {size_mb:.1f} MB")

    return dist_path


def create_zip(project_root, dist_path, version):
    """Create a ZIP file of the distribution"""
    print_step("Creating ZIP archive...")

    # Create releases directory
    releases_dir = project_root / OUTPUT_DIR
    releases_dir.mkdir(exist_ok=True)

    # Generate filename with version and date
    date_str = datetime.now().strftime("%Y%m%d")
    zip_name = f"{APP_NAME.replace(' ', '_')}_v{version}_{date_str}.zip"
    zip_path = releases_dir / zip_name

    # Remove existing ZIP if present
    if zip_path.exists():
        zip_path.unlink()
        print_success(f"Removed existing: {zip_name}")

    # Create ZIP
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in dist_path.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(dist_path.parent)
                zf.write(file_path, arcname)

    # Get ZIP size
    zip_size = zip_path.stat().st_size / (1024 * 1024)
    print_success(f"Created: {zip_name}")
    print_success(f"ZIP size: {zip_size:.1f} MB")
    print_success(f"Location: {zip_path}")

    return zip_path


def create_version_file(project_root, version):
    """Create a version file in the dist directory"""
    dist_path = project_root / DIST_DIR / APP_NAME
    version_file = dist_path / "VERSION.txt"

    with open(version_file, 'w') as f:
        f.write(f"Version: {version}\n")
        f.write(f"Build Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Python: {sys.version.split()[0]}\n")

    print_success(f"Created VERSION.txt")


def main():
    """Main build function"""
    parser = argparse.ArgumentParser(description="Build RoK Automation Bot")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts only")
    parser.add_argument("--no-zip", action="store_true", help="Skip ZIP creation")
    parser.add_argument("--version", type=str, default=DEFAULT_VERSION, help="Version number (e.g., 1.0.0)")
    args = parser.parse_args()

    project_root = get_project_root()

    print_header(f"Building {APP_NAME} v{args.version}")
    print(f"   Project: {project_root}")
    print(f"   Python: {sys.version.split()[0]}")
    print(f"   Platform: {sys.platform}")

    try:
        # Clean previous builds
        clean_build_artifacts(project_root)

        if args.clean:
            print_header("Clean completed")
            return 0

        # Check dependencies
        check_dependencies()

        # Run PyInstaller
        run_pyinstaller(project_root)

        # Verify build
        dist_path = verify_build(project_root)

        # Create version file
        create_version_file(project_root, args.version)

        # Create ZIP
        if not args.no_zip:
            zip_path = create_zip(project_root, dist_path, args.version)

        print_header("Build completed successfully!")
        print(f"\n   Output: {dist_path}")
        if not args.no_zip:
            print(f"   Release: {zip_path}")
        print()

        return 0

    except BuildError as e:
        print_header("Build failed!")
        print_error(str(e))
        return 1
    except KeyboardInterrupt:
        print("\n\nBuild cancelled by user")
        return 1
    except Exception as e:
        print_header("Build failed!")
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
