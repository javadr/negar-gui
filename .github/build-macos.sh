#!/bin/bash
# Builds Negar.app and packs it into a DMG in dist/. Run after the pip installs and the python-negar clone.
# One-file mode is deprecated for macOS apps, so this builds a normal .app bundle.
# Only the basic variant: Tesseract's dylibs are not relocatable without install_name_tool work, so no bundled OCR yet.
set -euo pipefail

version=$(grep -oE "[0-9]+\.[0-9]+(\.[0-9]+)?" ./negar_gui/constants.py)
export CURRENT_VERSION="$version"

pyinstaller -p negar_gui --windowed --clean --noupx -i negar_gui/resources/icons/logo.png \
	--osx-bundle-identifier io.github.javadr.negar-gui \
	--collect-data pyuca --collect-data qdarktheme negar_gui/main.py -n Negar \
	--add-data ./python-negar/negar/data/immutable.words:negar/data \
	--add-data negar_gui/resources/ts/fa.qm:ts \
	--add-data negar_gui/resources/help:help \
	--add-data negar_gui/resources/icons:icons \
	--exclude-module torch --exclude-module pocket_tts --exclude-module chatterbox --exclude-module huggingface_hub \
	--exclude-module onnxruntime

codesign --force --deep --sign - dist/Negar.app   # ad-hoc: Apple Silicon refuses unsigned binaries

# A DMG with an Applications shortcut: the user drags the app across. ditto keeps the bundle's symlinks and permissions.
stage=$(mktemp -d)
ditto dist/Negar.app "$stage/Negar.app"
ln -s /Applications "$stage/Applications"
hdiutil create -volname Negar -srcfolder "$stage" -ov -format UDZO "dist/negar-gui-v$version-basic-macos-$(uname -m).dmg"
rm -rf "$stage"
rm -rf python-negar
