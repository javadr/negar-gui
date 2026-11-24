# build.ps1
# This script file is supposed to build the negar-gui using PyInstaller and gets
# executable output from it.
# The executable output will be placed at dist/ directory and later on
# will be consumed by other tasks as artifact and finally gets uploaded to
# the github servers.

$versionStr = Get-Content -Path ".\negar_gui\constants.py" | Where-Object { $_.StartsWith("__version__")  }
$versionStr = $versionStr.Split("=")[1].Trim('"', ' ')
$Env:CURRENT_VERSION = $versionStr
# Bundle Tesseract (exe, DLLs, fas/eng/deu data) for the screen reader: the exe then needs nothing installed
$tessDir = "C:\Program Files\Tesseract-OCR"
if (-not (Test-Path "$tessDir\tesseract.exe")) { throw "Tesseract is not installed in $tessDir" }
$tessData = Join-Path $PWD "tessdata-bundle"
New-Item -ItemType Directory -Force -Path $tessData | Out-Null
foreach ($lang in "fas", "eng", "deu") {
    # the *_fast models keep the executable small
    Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_fast/raw/main/$lang.traineddata" -OutFile "$tessData\$lang.traineddata"
}
$tessArgs = @("--add-binary", "$tessDir\tesseract.exe;tesseract", "--add-data", "$tessData;tesseract\tessdata")
Get-ChildItem "$tessDir\*.dll" | ForEach-Object { $tessArgs += @("--add-binary", "$($_.FullName);tesseract") }

# Bundle the Tiny Ava voice (~30 MB, onnxruntime, CC BY 4.0) for Read Aloud; torch-based voices stay out
$tiny = Join-Path $PWD "tinyava-bundle"
New-Item -ItemType Directory -Force -Path $tiny | Out-Null
foreach ($f in "tiny-ava-parisa.onnx", "tiny-ava-parisa.json") { Invoke-WebRequest "https://huggingface.co/mehdi-hf/tiny-ava/resolve/main/onnx/$f" -OutFile "$tiny\$f" }
foreach ($f in "g2p_encoder.onnx", "g2p_decoder.onnx") { Invoke-WebRequest "https://raw.githubusercontent.com/mallahyari/tiny-ava/main/demo/assets/g2p/$f" -OutFile "$tiny\$f" }

& "python" -m PyInstaller -p negar_gui --onefile --windowed --clean --collect-data pyuca --collect-data qdarktheme `
    --noupx negar_gui/main.py -n "negar-gui-v$versionStr" `
    --add-data "./python-negar/negar/data/immutable.words;negar\data" `
    --add-data "negar_gui/ts/fa.qm;ts" `
    --add-data "negar_gui/help;help" `
    --add-data "negar_gui/icons;icons" `
    --add-data "$tiny;tinyava" `
    --exclude-module torch --exclude-module pocket_tts --exclude-module chatterbox --exclude-module huggingface_hub `
    --icon ".\negar_gui\icons\logo.png" `
    @tessArgs

# Cleanup after build
Remove-Item -Path ".\tinyava-bundle" -Force -Recurse -ErrorAction "SilentlyContinue"
Remove-Item -Path ".\tessdata-bundle" -Force -Recurse -ErrorAction "SilentlyContinue"
Remove-Item -Path ".\python-negar" -Force -Recurse -ErrorAction "SilentlyContinue"
