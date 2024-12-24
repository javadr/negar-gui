#!/bin/bash

version=$(grep -oE "[0-9]+\.[0-9]+(\.[0-9]+)?" ./negar_gui/constants.py)
export CURRENT_VERSION="$version"
pyinstaller -p negar_gui --onefile --windowed --clean -i"negar_gui/icons/logo.ico" \
	--collect-data pyuca --noupx negar_gui/main.py -n "negar-gui-v$version" \
	--add-data ./python-negar/negar/data/immutable.words:negar/data \
	--add-data negar_gui/ts/fa.qm:ts

chmod +x "dist/negar-gui-v$version"

# Cleanup after build
rm -rf '.\python-negar' 2>&1
