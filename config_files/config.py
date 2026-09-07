"""
Date modified: 23/05/25
"""

import json
import os


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# Default values if config.json doesn't exist
DEFAULTS = {
    "COM_PORT": "COM3",
    "BAUD_RATE": "19200",
    "DATA_BITS": "8",
    "PARITY": "N",
    "STOP_BITS": "2",
    "TIMEOUT": "0.02",
    "FILE_NAME": "",
    "DISPLAY_TYPE": "LCD",
    "PAGE_COUNT": 7,
    "WHITE_DISPLAY": False,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    else:
        return DEFAULTS.copy()


def save_config(data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)


# Global config dict loaded at import
config = load_config()
