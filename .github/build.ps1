# build.ps1 basic|ocr|ocr-tts
# Builds the Windows executable with PyInstaller into dist/ (consumed later as an artifact and uploaded to the release).
#   basic   - no bundled Tesseract and no voice
#   ocr     - Tesseract (fas, eng, deu) bundled for the screen reader
#   ocr-tts - ocr plus the Tiny Ava voice for Read Aloud (no torch-based voice)
param([Parameter(Mandatory = $true)][ValidateSet("basic", "ocr", "ocr-tts")][string]$Variant)
$ErrorActionPreference = "Stop"

$versionStr = Get-Content -Path ".\negar_gui\constants.py" | Where-Object { $_.StartsWith("__version__")  }
$versionStr = $versionStr.Split("=")[1].Trim('"', ' ')
$Env:CURRENT_VERSION = $versionStr
$extra = @()

if ($Variant -ne "basic") {
    # Bundle Tesseract (exe, DLLs, fas/eng/deu data) for the screen reader: the exe then needs nothing installed
    $tessDir = "C:\Program Files\Tesseract-OCR"
    if (-not (Test-Path "$tessDir\tesseract.exe")) { throw "Tesseract is not installed in $tessDir" }
    $tessData = Join-Path $PWD "tessdata-bundle"
    New-Item -ItemType Directory -Force -Path $tessData | Out-Null
    foreach ($lang in "fas", "eng", "deu") {
        # the *_fast models keep the executable small
        Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_fast/raw/main/$lang.traineddata" -OutFile "$tessData\$lang.traineddata"
    }
    $extra += @("--add-binary", "$tessDir\tesseract.exe;tesseract", "--add-data", "$tessData;tesseract\tessdata")
    Get-ChildItem "$tessDir\*.dll" | ForEach-Object { $extra += @("--add-binary", "$($_.FullName);tesseract") }
}

if ($Variant -eq "ocr-tts") {
    # Tiny Ava (~30 MB, onnxruntime, CC BY 4.0) for Read Aloud
    $tiny = Join-Path $PWD "tinyava-bundle"
    New-Item -ItemType Directory -Force -Path $tiny | Out-Null
    foreach ($f in "tiny-ava-parisa.onnx", "tiny-ava-parisa.json") { Invoke-WebRequest "https://huggingface.co/mehdi-hf/tiny-ava/resolve/main/onnx/$f" -OutFile "$tiny\$f" }
    foreach ($f in "g2p_encoder.onnx", "g2p_decoder.onnx") { Invoke-WebRequest "https://raw.githubusercontent.com/mallahyari/tiny-ava/main/demo/assets/g2p/$f" -OutFile "$tiny\$f" }
    $extra += @("--add-data", "$tiny;tinyava")
} else {
    $extra += @("--exclude-module", "onnxruntime")
}

& "python" -m PyInstaller -p negar_gui --onefile --windowed --clean --collect-data pyuca --collect-data qdarktheme `
    --noupx negar_gui/main.py -n "negar-gui-v$versionStr-$Variant" `
    --add-data "./python-negar/negar/data/immutable.words;negar\data" `
    --add-data "negar_gui/resources/ts/fa.qm;ts" `
    --add-data "negar_gui/resources/help;help" `
    --add-data "negar_gui/resources/icons;icons" `
    --exclude-module torch --exclude-module pocket_tts --exclude-module chatterbox --exclude-module huggingface_hub `
    --icon ".\negar_gui\resources\icons\logo.png" `
    @extra
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

# Cleanup after build
Remove-Item -Path ".\tinyava-bundle", ".\tessdata-bundle", ".\python-negar" -Force -Recurse -ErrorAction "SilentlyContinue"
