#!/usr/bin/env python3
import argparse
import logging
import os
import tkinter as tk
from tkinter import messagebox


def setup_environment():
    """Setup environment, create necessary directories and check dependencies"""
    if not os.path.exists("logs"):
        os.makedirs("logs")

    if not os.path.exists("instances"):
        os.makedirs("instances")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("logs/rok_automation.log"),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting Rise of Kingdoms Automation Tool")
    return logger


def main():
    """Main entry point of the application"""
    logger = setup_environment()

    parser = argparse.ArgumentParser(description="Rise of Kingdoms Automation Tool")
    parser.add_argument("--single", action="store_true", help="Launch legacy single instance mode")
    parser.add_argument("--multi", action="store_true", help="Launch legacy multi-instance mode")
    args = parser.parse_args()

    try:
        if args.single or args.multi:
            logger.warning("--single/--multi legacy mode removed, starting unified GUI")

        from unified_gui import UnifiedGUI
        logger.info("Starting unified GUI")
        root = tk.Tk()
        UnifiedGUI(root)

        try:
            root.iconbitmap("assets/rok_icon.ico")
        except Exception:
            logger.warning("Could not load application icon")

        root.mainloop()

    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        messagebox.showerror("Import Error",
                             f"Failed to import required modules: {e}\n\n"
                             "Please make sure all dependencies are installed.\n"
                             "Run: pip install -r requirements.txt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.exception("Stack trace:")
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
