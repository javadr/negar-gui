from pathlib import Path
import platform

__version__ = "0.7.5"

if platform.system() == 'Windows':
    LOGO = ":/images/icons/logo_small.png"
else:
    LOGO = ":/images/icons/logo.png"
    # (Path(__file__).parent.absolute() / "icons/logo.png").as_posix()
