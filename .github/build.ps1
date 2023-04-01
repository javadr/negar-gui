# build.ps1
# This script file is supposed to build the negar-gui using PyInstaller and gets
# executable output from it.
# The executable output will be placed at dist/ directory and later on
# will be consumed by other tasks as artifact and finally gets uploaded to
# the github servers.

$versionStr = Get-Content -Path ".\negar_gui\constants.py" | Where-Object { $_.StartsWith("__version__")  }
$versionStr = $versionStr.Split("=")[1].Trim('"', ' ')
$Env:CURRENT_VERSION = $versionStr
& "python" -m PyInstaller -p negar_gui --onefile --windowed --clean --collect-data pyuca `
    --noupx negar_gui/main.py -n "negar-gui-v$versionStr" `
    --add-data "./python-negar/negar/data/untouchable.dat;negar\data" `
    --add-data "./negar-gui/ts/fa.qm;negar-gui\ts"
    --icon ".\negar_gui\icons\logo.png"

# Cleanup after build
Remove-Item -Path ".\python-negar" -Force -Recurse -ErrorAction "SilentlyContinue"
