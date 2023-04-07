from pathlib import Path
import platform

__version__ = "0.7.1"

if platform.system() == 'Windows':
    LOGO = ":/images/icons/logo_small.png"
else:
    LOGO = (Path(__file__).parent.absolute() / "icons/logo.png").as_posix()
