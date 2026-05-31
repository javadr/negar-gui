VER=$(shell grep __version__ negar_gui/constants.py|cut -d= -f2|tr -d '\" ')

# Detect whether 'uv' is available; otherwise, fall back to 'pip'
PKG_TOOL := $(shell command -v uv >/dev/null 2>&1 && echo uv pip || echo pip)

# Check whether Make is running inside a virtual environment
VENV:=$(shell echo "$${VIRTUAL_ENV-}")
NEGAR:=$(if $(VENV),$(VIRTUAL_ENV)/bin/negar-gui,$(HOME)/.local/bin/negar-gui)
APP_DESKTOP:="$(HOME)/.local/share/applications/negar.desktop"

.ONESHELL:

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

ver: ## Show the version number
	@echo negar-gui, Ver. $(VER)

.PHONY: generate_desktop_file
generate_desktop_file: ## Generate a desktop icon for the GUI app
	@cp negar_gui/icons/logo.png $(HOME)/.local/share/icons/negar.png
	@echo "Generating the desktop file..."
	cat <<EOF > $(APP_DESKTOP)
	[Desktop Entry]
	Name=Negar
	Exec=$(NEGAR)
	Icon=negar.png
	Version=$(VER)
	Hidden=false
	Terminal=false
	Type=Application
	Categories=Utility;
	Comment=Graphical User Interface for Negar -- Persian Text Editor
	EOF
	@chmod +x $(APP_DESKTOP)
	@echo "Desktop file generated successfully."

.PHONY: uninstall
uninstall: ## Uninstall negar-gui
	@echo "Uninstalling negar-gui ..."
	@$(PKG_TOOL) uninstall negar-gui
	@echo "Removing the desktop file and its icon ..."
	rm -fv $(APP_DESKTOP) $(HOME)/.local/share/icons/negar.png
	@echo "Desktop file removed successfully."

setup: ver ## Build source and wheel distribution packages
	python -m build

lins: generate_desktop_file ## Install negar-gui locally in editable/development mode
	@$(PKG_TOOL) install -e .

pins: ver generate_desktop_file ## Install negar-gui from PyPI using the current version
	@$(PKG_TOOL) install negar-gui==$(VER)

upypi: setup ## Publish the package to PyPI
	twine upload "dist/negar_gui-$(VER).tar.gz"

utest: setup ## Publish the package to TestPyPI
	twine upload -r testpypi "dist/negar_gui-$(VER).tar.gz"

upload: setup upypi utest ## Publish the package to both PyPI and TestPyPI

nuCompile: setup ver ## Build a standalone binary with nuitka3
	nuitka3 negar_gui/main.py --standalone --onefile --linux-onefile-icon=negar_gui/icons/logo.png \
	--enable-plugin=pyqt5 --nofollow-import-to=tkinter --lto=no \
	-o dist/negar-gui-v$(VER).bin \
	--output-dir=dist --remove-output \
	--include-data-file=.negar/lib/python3.12/site-packages/pyuca/allkeys-9.0.0.txt=pyuca/allkeys-9.0.0.txt \
	--include-data-file=.negar/lib/python3.12/site-packages/negar/data/untouchable.dat=negar/data/untouchable.dat
	# --include-data-dir=.negar/lib/python3.12/site-packages/negar=negar/data \
	# --module python-negar --include-package=python-negar
	# --include-package-data=python-negar=*.dat \

	ls -lh dist

piCompile: setup ver ## Build a standalone binary with PyInstaller
	@rm build/gui/ -rfv
	pyinstaller -p negar_gui --onefile --windowed --clean -i"negar_gui/icons/logo.ico" \
	--collect-data pyuca --noupx negar_gui/main.py -n negar-gui-v$(VER) \
	--add-data negar_gui/ts/fa.qm:ts \
	--add-data ../python-negar/negar/data/untouchable.dat:negar/data # &> pyins.out
	ls -lh dist

trans: ver ## Update and compile Qt translation files using PyQt tools
	pylupdate5 -verbose negar_gui/Ui_mwin.py -ts negar_gui/ts/fa-uimwin.ts
	pylupdate5 -verbose negar_gui/Ui_uwin.py -ts negar_gui/ts/fa-uiuwin.ts
	pylupdate5 -verbose negar_gui/Ui_hwin.py -ts negar_gui/ts/fa-uihwin.ts
	pylupdate5 -verbose negar_gui/main.py -ts negar_gui/ts/fa-main.ts
	lrelease negar_gui/ts/fa-*.ts -qm negar_gui/ts/fa.qm

res: ver ## Compile the Qt resource file using PyQt tools
	pyrcc5 negar_gui/resource.qrc -o negar_gui/resource_rc.py
	sed "s/PyQt5/PyQt6/g" -i negar_gui/resource_rc.py

ui: ver ## Convert Qt UI files to Python scripts using PyQt6
	pyuic6 negar_gui/mwin.ui -xo negar_gui/Ui_mwin.py
	pyuic6 negar_gui/uwin.ui -xo negar_gui/Ui_uwin.py
	pyuic6 negar_gui/hwin.ui -xo negar_gui/Ui_hwin.py


sres: ver ## Compile the Qt resource file using PySide2 tools
	pyside2-rcc negar_gui/resource.qrc -o negar_gui/resource_rc.py

sui: ver ## Convert Qt UI files to Python scripts using PySide2
	pyside2-uic --from-imports negar_gui/mwin.ui -o negar_gui/Ui_mwin.py
	pyside2-uic --from-imports negar_gui/uwin.ui -o negar_gui/Ui_uwin.py

strans: ver ## Update and compile Qt translation files using PySide2 tools
	pyside2-lupdate -verbose negar_gui/Ui_mwin.py -ts negar_gui/ts/fa-uimwin.ts
	pyside2-lupdate -verbose negar_gui/Ui_uwin.py -ts negar_gui/ts/fa-uiuwin.ts
	pyside2-lupdate -verbose negar_gui/main.py -ts negar_gui/ts/fa-main.ts
	pyside2-lrelease negar_gui/ts/fa-*.ts -qm negar_gui/ts/fa.qm

clean: ver ## Clean build artifacts
	@rm negar_gui.egg-info/ -rfv
	@rm build/ -rfv
	@rm dist/ -rfv
	@rm gui.build/ -rfv
	@rm gui.dist/ -rfv
	@rm negar*.spec -rfv
	@rm negar_gui/__pycache__ -rfv
