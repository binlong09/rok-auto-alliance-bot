#!/usr/bin/env python3
import os
import logging
import tkinter as tk
from tkinter import messagebox
import argparse


def setup_environment():
    """Setup environment, create necessary directories and check dependencies"""
    # Create logs directory if not exists
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Create instances directory if not exists
    if not os.path.exists("instances"):
        os.makedirs("instances")

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

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Rise of Kingdoms Automation Tool")
    parser.add_argument("--single", action="store_true", help="Launch single instance mode")
    parser.add_argument("--multi", action="store_true", help="Launch multi-instance mode (default)")
    args = parser.parse_args()

    # Determine mode - default to multi-instance
    use_single_mode = args.single
    if args.multi:
        use_single_mode = False

    try:
        # Import modules here to catch any import errors
        if use_single_mode:
            from bluestacks_manager_gui import RiseOfKingdomsManagerGUI
            logger.info("Starting in single instance mode")

            # Create the main application window
            root = tk.Tk()
            app = RiseOfKingdomsManagerGUI(root)
        else:
            from multi_instance_manager_gui import MultiInstanceManagerGUI
            logger.info("Starting in multi-instance mode")

            # Create the multi-instance manager window
            root = tk.Tk()
            app = MultiInstanceManagerGUI(root)

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