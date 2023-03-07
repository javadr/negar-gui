#!/bin/bash

version=$(grep -oE "([0-9]*\.[0-9]*\.[0-9]*)" ./negar_gui/constants.py)

pyinstaller -p negar_gui --onefile --windowed --clean -i"negar_gui/icons/logo.ico" \
	--collect-data pyuca --noupx negar_gui/main.py -n negar-gui-v$(VER) \
	--add-data ./python-negar/negar/data/untouchable.dat:negar/data