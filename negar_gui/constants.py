import platform
from pathlib import Path

__version__ = "0.9.7"

APPDATA = "AppData/Roaming/" if platform.system() == "Windows" else "."
SETTING_FILE = Path.home() / f"{APPDATA}negar-gui/settings.toml"
SETTING_FILE.parent.mkdir(parents=True, exist_ok=True)

if platform.system() == "Windows":
    LOGO = ":/images/icons/logo_small.png"
else:
    LOGO = ":/images/icons/logo.png"
