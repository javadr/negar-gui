#!/bin/bash
# Usage: appimage.sh basic|ocr|ocr-tts  (run after build.sh: wraps dist/negar-gui-v<ver>-<variant> into an AppImage)
set -e
variant=${1:?usage: appimage.sh basic|ocr|ocr-tts}
version=$(grep -oE "[0-9]+\.[0-9]+(\.[0-9]+)?" ./negar_gui/constants.py)
exe="negar-gui-v$version-$variant"

appdir=$(mktemp -d)/negar-gui.AppDir
mkdir -p "$appdir/usr/bin"
cp "dist/$exe" "$appdir/usr/bin/negar-gui"
cp negar_gui/resources/icons/logo.png "$appdir/negar-gui.png"
cat > "$appdir/negar-gui.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Negar GUI
Exec=negar-gui
Icon=negar-gui
Categories=Utility;TextTools;
DESKTOP
printf '#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/usr/bin/negar-gui" "$@"\n' > "$appdir/AppRun"
chmod +x "$appdir/AppRun"

curl -fsSL https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage -o appimagetool
chmod +x appimagetool
# --appimage-extract-and-run: CI runners have no FUSE
ARCH=x86_64 ./appimagetool --appimage-extract-and-run "$appdir" "dist/$exe-x86_64.AppImage"
rm -f appimagetool
