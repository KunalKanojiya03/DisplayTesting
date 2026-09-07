"""
pilot_lcd.py

Author: Kunal Kanojiya
Date: 03/10/2024
Date modified: 23/05/25
Description:
    This script serves as the main entry point for the image processing application.
    It imports necessary functions and configurations, validates key paths,
    and initiates the main processing loop. It also handles cleanup on exit.

Functionality:
    - Prints configuration values for YOLOv5 and model paths, and the COM port.
    - Validates that critical configuration paths are set before proceeding.
    - Calls the MainLcd function to start the main processing loop.
    - Handles interruptions gracefully, ensuring proper resource cleanup.

"""

from config_files.config import config
from general.functions_mod import MainLcd

# def Reload():
#     importlib.reload(functions)


def StartLcd():
    # Reload()
    # Print the values directly before validation
    print(f"Com port: '{config['COM_PORT']}'", flush=True)
    try:
        MainLcd()
    except KeyboardInterrupt:
        print("Program interrupted by user.")
