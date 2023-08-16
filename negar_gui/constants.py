import platform
from pathlib import Path

__version__ = "0.8"

APPDATA = "AppData/Roaming/" if platform.system() == "Windows" else "."
SETTING_FILE = Path.home() / f"{APPDATA}negar-gui/settings.toml"

if platform.system() == "Windows":
    LOGO = ":/images/icons/logo_small.png"
else:
    LOGO = ":/images/icons/logo.png"
