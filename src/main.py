#!/usr/bin/env python3
import os
import logging
import tkinter as tk
from tkinter import messagebox


def setup_environment():
    """Setup environment, create necessary directories and check dependencies"""
    # Create logs directory if not exists
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Setup logging
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

    try:
        # Import modules here to catch any import errors
        from bluestacks_manager_gui import RiseOfKingdomsManagerGUI

        # Create the main application window
        root = tk.Tk()
        app = RiseOfKingdomsManagerGUI(root)

        # Set window icon if available
        try:
            root.iconbitmap("assets/rok_icon.ico")
        except:
            logger.warning("Could not load application icon")

        # Start the main loop
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