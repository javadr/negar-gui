"""setup.py: setuptools control."""

import re
from setuptools import setup

version = re.search(
    r'(__version__ = "(\d\.\d(\.\d+)?)")',
    open("negar_gui/constants.py", encoding="utf8").read(),
    re.M,
).group(2)

setup(
    name="negar-gui",
    version=version,
    author="Javad Razavian",
    author_email="javadr@gmail.com",
    include_package_data=True,
    packages=["negar_gui"],
    install_requires=[
        "python-negar>=1.2.12",
        "PyQt6",
        "pyperclip",
        "pyuca",
        "redlines",
        "regex",
        "requests",
        "qrcode",
        "docopt",
        "Image",
        "pyqtdarktheme",
        "toml",
    ],
    python_requires=">=3.8",
    package_dir={"negar_gui": "negar_gui"},
    description="Graphical User Interface for Negar -- Persian Text Editor",
    license="GPLv3",
    keywords="Spellcheck Persian Text-Editor",
    url="http://github.com/javadr/negar-gui",
    entry_points={
        "console_scripts": [
            "negar-gui-od = negar_gui.gui:main",
            "negar-gui = negar_gui.main:main",
        ],
    },
    long_description_content_type="text/markdown",
    long_description=open("README.md", encoding="utf8").read(),
)
