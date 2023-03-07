# $constFile = Get-ChildItem -Path "." -File -Filter "constants.py" -Recurse | Select-Object -First 1
Get-ChildItem | Write-Host

$versionStr = Get-Content -Path ".\negar_gui\constants.py" | Where-Object { $_.StartsWith("__version__")  }
$versionStr = $versionStr.Split("=")[1].Trim().Trim('"')
$Env:CURRENT_VERSION = $versionStr
& "python" -m PyInstaller -p negar_gui --onefile --windowed --clean --collect-data pyuca --noupx negar_gui/main.py -n "negar-gui-v$versionStr" --add-data "./python-negar/negar/data/untouchable.dat;negar\data" --icon ".\negar_gui\icons\logo.png"
