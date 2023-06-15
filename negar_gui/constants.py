import platform

__version__ = "0.7.8"

if platform.system() == 'Windows':
    LOGO = ":/images/icons/logo_small.png"
else:
    LOGO = ":/images/icons/logo.png"
