Negar-GUI
==============
[![PyPI](https://img.shields.io/pypi/v/negar-gui?style=social)](https://pypi.org/project/negar-gui/)
[![code size](https://img.shields.io/github/languages/code-size/javadr/negar-gui?style=social)](https://github.com/javadr/negar-gui/archive/master.zip)
![GitHub language count](https://img.shields.io/github/languages/count/javadr/negar-gui?style=social)
![GitHub top language](https://img.shields.io/github/languages/top/javadr/negar-gui?style=social)
[![GitHub forks](https://img.shields.io/github/forks/javadr/negar-gui?style=social)](https://github.com/javadr/negar-gui/network/members)
[![GitHub license](https://img.shields.io/github/license/javadr/negar-gui?style=social)](https://github.com/javadr/negar-gui/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/javadr/negar-gui?style=social)](https://github.com/javadr/negar-gui/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/javadr/negar-gui?style=social)](https://github.com/javadr/negar-gui/issues)
[![Downloads](https://pepy.tech/badge/negar-gui)](https://pepy.tech/project/negar-gui)
[![Downloads](https://pepy.tech/badge/negar-gui/month)](https://pepy.tech/project/negar-gui)
![GitHub last commit](https://img.shields.io/github/last-commit/javadr/negar-gui)

Graphical User interface for `negar`


![Negar's English view](https://raw.github.com/javadr/negar-gui/master/images/negar-en.png)
![Negar's Persian view](https://raw.github.com/javadr/negar-gui/master/images/negar-fa.png)

Installation
==============

## PyPi

**python-negar** is available on [PyPi](http://pypi.python.org/pypi/negar-gui):

    $ pip install negar-gui

## Git

You can retrieve the latest stable changes from the GitHub server:

    $ git clone https://github.com/javadr/negar-gui.git
    $ cd negar-gui
    $ python setup.py install

## Zip, Tarball

You can download the latest tarball.

### *nix

Get the latest tarball & install:

    $ wget -O negar-gui-master.tar.gz https://github.com/javadr/negar-gui/archive/master.tar.gz
    $ tar xvzf negar-gui-master.tar.gz && cd negar-gui-master
    $ python setup.py install

### Windows

Download the latest zip archive.

https://github.com/javadr/negar-gui/archive/master.zip

Decompress it, and run the following command in the root directory of `negar-gui`

    $ python setup.py install

#### Requirements
The GUI is relied on `python-negar` as well as `PyQt5/6`, `pyperclip`, `pyuca`, `redlines`, `regex`, `requests`, `qrcode`, `docopt`, `Image`, `pyqtdarktheme`, and `toml`.
If you want to just run it by calling the script, you need to install its dependencies.

    $ pip install python-negar PyQt5 PyQt6 pyuca pyperclip redlines regex requests qrcode docopt Image pyqtdarktheme toml

## Usage
Just use one of the following in your terminal.

    $ negar-gui

or simply

    $ negar

### Persian keyboard on startup
If a Persian keyboard layout is installed, Negar switches to it when it starts and switches back when it closes (turn it off in *Settings → Persian Keyboard on Startup*). This works on Windows, macOS, KDE Plasma, Sway and X11 desktops. GNOME has no built-in way for apps to change the layout, so there you need the [Shyriiwook](https://extensions.gnome.org/extension/6691/shyriiwook/) extension.

### AI grammar fix
The AI button works without setup through Pollinations, which is free but slow and rate-limited. For better results, open *AI → AI Provider...*, pick a provider and paste your own API key. [Google Gemini](https://aistudio.google.com/apikey), [Groq](https://console.groq.com/keys) and [OpenRouter](https://openrouter.ai/settings/keys) give free keys, and [OpenAI](https://platform.openai.com/api-keys) is paid. Keys are stored in plain text in the settings file (on Linux and macOS the file is made readable only by your user).

## Docker

A Docker image is available on [Docker Hub](https://hub.docker.com/r/javadr/negar-gui):

    $ docker pull javadr/negar-gui

Build it locally:

    $ make docker-build

### Run on X11

    $ docker run --rm \
        -e DISPLAY=$DISPLAY \
        -v /tmp/.X11-unix:/tmp/.X11-unix \
        -v $HOME/.config/negar-gui:/home/negar/.config/negar-gui \
        javadr/negar-gui

### Run on Wayland

    $ docker run --rm \
        -e QT_QPA_PLATFORM=wayland \
        -e XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
        -e WAYLAND_DISPLAY=$WAYLAND_DISPLAY \
        -v $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY:$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY \
        --device /dev/dri \
        -v $HOME/.config/negar-gui:/home/negar/.config/negar-gui \
        javadr/negar-gui

### Auto-detect (via Makefile)

    $ make docker-run
