#!/bin/bash

version=$(grep -oE "[0-9]+\.[0-9]+(\.[0-9]+)?" ./negar_gui/constants.py)
export CURRENT_VERSION="$version"
# Bundle Tesseract (binary, shared libs, fas/eng/deu data) for the screen reader: the exe then needs nothing installed
set -e
tess=$(command -v tesseract) || { echo "tesseract is not installed" >&2; exit 1; }
tessdata=$(tesseract --list-langs 2>&1 | sed -n '1s/.*in "\(.*\)".*/\1/p' | sed 's:/*$::')
tess_args=(--add-binary "$tess:tesseract")
while read -r lib; do tess_args+=(--add-binary "$lib:tesseract"); done < <(
	ldd "$tess" | awk '/=> \// && $3 !~ /\/(libc|libm|libpthread|libdl|librt|libresolv)\.so/ {print $3}')
for lang in fas eng deu; do
	[ -f "$tessdata/$lang.traineddata" ] || { echo "missing $lang.traineddata in $tessdata" >&2; exit 1; }
	tess_args+=(--add-data "$tessdata/$lang.traineddata:tesseract/tessdata")
done

pyinstaller -p negar_gui --onefile --windowed --clean -i"negar_gui/icons/logo.ico" \
	--collect-data pyuca --noupx negar_gui/main.py -n "negar-gui-v$version" \
	--add-data ./python-negar/negar/data/immutable.words:negar/data \
	--add-data negar_gui/ts/fa.qm:ts \
	--add-data negar_gui/icons:icons \
	"${tess_args[@]}"

chmod +x "dist/negar-gui-v$version"

# Cleanup after build
rm -rf '.\python-negar' 2>&1
