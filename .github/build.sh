#!/bin/bash
# Usage: build.sh basic|ocr|ocr-tts
#   basic   - no bundled Tesseract and no voice
#   ocr     - Tesseract (fas, eng, deu) bundled for the screen reader
#   ocr-tts - ocr plus the Tiny Ava voice for Read Aloud (no torch-based voice)
set -e
variant=${1:?usage: build.sh basic|ocr|ocr-tts}
case "$variant" in basic | ocr | ocr-tts) ;; *) echo "unknown variant $variant" >&2; exit 1 ;; esac

version=$(grep -oE "[0-9]+\.[0-9]+(\.[0-9]+)?" ./negar_gui/constants.py)
export CURRENT_VERSION="$version"
args=()

if [ "$variant" != basic ]; then
	# Bundle Tesseract (binary, shared libs, fas/eng/deu data) for the screen reader: the exe then needs nothing installed
	tess=$(command -v tesseract) || { echo "tesseract is not installed" >&2; exit 1; }
	tessdata=$(tesseract --list-langs 2>&1 | sed -n '1s/.*in "\(.*\)".*/\1/p' | sed 's:/*$::')
	args+=(--add-binary "$tess:tesseract")
	while read -r lib; do args+=(--add-binary "$lib:tesseract"); done < <(
		ldd "$tess" | awk '/=> \// && $3 !~ /\/(libc|libm|libpthread|libdl|librt|libresolv)\.so/ {print $3}')
	for lang in fas eng deu; do
		[ -f "$tessdata/$lang.traineddata" ] || { echo "missing $lang.traineddata in $tessdata" >&2; exit 1; }
		args+=(--add-data "$tessdata/$lang.traineddata:tesseract/tessdata")
	done
fi

if [ "$variant" = ocr-tts ]; then
	# Tiny Ava (~30 MB, onnxruntime, CC BY 4.0) for Read Aloud
	mkdir -p tinyava-bundle
	for f in tiny-ava-parisa.onnx tiny-ava-parisa.json; do curl -fsSL "https://huggingface.co/mehdi-hf/tiny-ava/resolve/main/onnx/$f" -o "tinyava-bundle/$f"; done
	for f in g2p_encoder.onnx g2p_decoder.onnx; do curl -fsSL "https://raw.githubusercontent.com/mallahyari/tiny-ava/main/demo/assets/g2p/$f" -o "tinyava-bundle/$f"; done
	args+=(--add-data tinyava-bundle:tinyava)
else
	args+=(--exclude-module onnxruntime)
fi

pyinstaller -p negar_gui --onefile --windowed --clean -i"negar_gui/resources/icons/logo.ico" \
	--collect-data pyuca --collect-data qdarktheme --noupx negar_gui/main.py -n "negar-gui-v$version-$variant" \
	--add-data ./python-negar/negar/data/immutable.words:negar/data \
	--add-data negar_gui/resources/ts/fa.qm:ts \
	--add-data negar_gui/resources/help:help \
	--add-data negar_gui/resources/icons:icons \
	--exclude-module torch --exclude-module pocket_tts --exclude-module chatterbox --exclude-module huggingface_hub \
	"${args[@]}"

chmod +x "dist/negar-gui-v$version-$variant"

# Cleanup after build
rm -rf python-negar tinyava-bundle
