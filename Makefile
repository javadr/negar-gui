VER=$(shell grep __version__ negar_gui/constants.py|cut -d= -f2|tr -d '\" ')

PKG_TOOL := $(shell command -v uv >/dev/null 2>&1 && echo uv pip || echo pip)

VENV:=$(shell echo "$${VIRTUAL_ENV-}")
NEGAR:=$(if $(VENV),$(VIRTUAL_ENV)/bin/negar-gui,$(HOME)/.local/bin/negar-gui)
APP_DESKTOP:=$(HOME)/.local/share/applications/negar.desktop

.ONESHELL:

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

ver: ## Show the version number
	@echo negar-gui, Ver. $(VER)

.PHONY: install-desktop-file
install-desktop-file: ## Generate a desktop icon for the GUI app
	@cp negar_gui/icons/logo.png $(HOME)/.local/share/icons/negar.png
	@echo "Generating the desktop file..."
	cat <<EOF > $(APP_DESKTOP).tmp
	[Desktop Entry]
	Name=Negar
	Name[fa]=نگار
	Keywords=Negar;نگار;Persian;فارسی;
	Exec=$(NEGAR)
	Icon=negar
	Version=1.5
	Hidden=false
	Terminal=false
	Type=Application
	Categories=Utility;
	Comment=Graphical User Interface for Negar -- Persian Text Editor
	EOF
	mv $(APP_DESKTOP).tmp $(APP_DESKTOP)
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

.PHONY: install-dev
install-dev: install-desktop-file ## Install negar-gui locally in editable/development mode
	@$(PKG_TOOL) install -e .

.PHONY: install-pypi
install-pypi: ver install-desktop-file ## Install negar-gui from PyPI using the current version
	@$(PKG_TOOL) install negar-gui==$(VER)

.PHONY: publish-pypi
publish-pypi: setup ## Publish the package to PyPI
	twine upload "dist/negar_gui-$(VER).tar.gz"

.PHONY: publish-testpypi
publish-testpypi: setup ## Publish the package to TestPyPI
	twine upload -r testpypi "dist/negar_gui-$(VER).tar.gz"

upload: setup publish-pypi publish-testpypi ## Publish the package to both PyPI and TestPyPI

.PHONY: compile-nuitka
compile-nuitka: setup ver ## Build a standalone binary with nuitka3
	nuitka3 negar_gui/main.py --standalone --onefile --linux-onefile-icon=negar_gui/icons/logo.png \
	--enable-plugin=pyqt5 --nofollow-import-to=tkinter --lto=no \
	-o dist/negar-gui-v$(VER).bin \
	--output-dir=dist --remove-output \
	--include-data-file=.negar/lib/python3.12/site-packages/pyuca/allkeys-9.0.0.txt=pyuca/allkeys-9.0.0.txt \
	--include-data-file=.negar/lib/python3.12/site-packages/negar/data/untouchable.dat=negar/data/untouchable.dat
	ls -lh dist

.PHONY: compile-pyinstaller
compile-pyinstaller: setup ver ## Build a standalone binary with PyInstaller
	@rm build/gui/ -rfv
	pyinstaller -p negar_gui --onefile --windowed --clean -i"negar_gui/icons/logo.ico" \
	--collect-data pyuca --noupx negar_gui/main.py -n negar-gui-v$(VER) \
	--add-data negar_gui/ts/fa.qm:ts \
	--add-data ../python-negar/negar/data/untouchable.dat:negar/data
	ls -lh dist

.PHONY: update-translations
update-translations: ver ## Update and compile Qt translation files using PyQt tools
	pylupdate5 -verbose negar_gui/Ui_mwin.py -ts negar_gui/ts/fa-uimwin.ts
	pylupdate5 -verbose negar_gui/Ui_uwin.py -ts negar_gui/ts/fa-uiuwin.ts
	pylupdate5 -verbose negar_gui/Ui_hwin.py -ts negar_gui/ts/fa-uihwin.ts
	pylupdate5 -verbose negar_gui/main.py -ts negar_gui/ts/fa-main.ts
	lrelease negar_gui/ts/fa-*.ts -qm negar_gui/ts/fa.qm

.PHONY: compile-resources
compile-resources: ver ## Compile the Qt resource file using PyQt tools
	pyrcc5 negar_gui/resource.qrc -o negar_gui/resource_rc.py
	sed "s/PyQt5/PyQt6/g" -i negar_gui/resource_rc.py

.PHONY: compile-ui
compile-ui: ver ## Convert Qt UI files to Python scripts using PyQt6
	pyuic6 negar_gui/mwin.ui -xo negar_gui/Ui_mwin.py
	pyuic6 negar_gui/uwin.ui -xo negar_gui/Ui_uwin.py
	pyuic6 negar_gui/hwin.ui -xo negar_gui/Ui_hwin.py

.PHONY: compile-resources-pyside2
compile-resources-pyside2: ver ## Compile the Qt resource file using PySide2 tools
	pyside2-rcc negar_gui/resource.qrc -o negar_gui/resource_rc.py

.PHONY: compile-ui-pyside2
compile-ui-pyside2: ver ## Convert Qt UI files to Python scripts using PySide2
	pyside2-uic --from-imports negar_gui/mwin.ui -o negar_gui/Ui_mwin.py
	pyside2-uic --from-imports negar_gui/uwin.ui -o negar_gui/Ui_uwin.py

.PHONY: update-translations-pyside2
update-translations-pyside2: ver ## Update and compile Qt translation files using PySide2 tools
	pyside2-lupdate -verbose negar_gui/Ui_mwin.py -ts negar_gui/ts/fa-uimwin.ts
	pyside2-lupdate -verbose negar_gui/Ui_uwin.py -ts negar_gui/ts/fa-uiuwin.ts
	pyside2-lupdate -verbose negar_gui/main.py -ts negar_gui/ts/fa-main.ts
	pyside2-lrelease negar_gui/ts/fa-*.ts -qm negar_gui/ts/fa.qm

.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build -t negar-gui:latest -t negar-gui:$(VER) .

.PHONY: docker-run
docker-run: ## Run the Docker container (auto-detects Wayland / X11)
	$(if $(WAYLAND_DISPLAY),\
		docker run --rm \
			-e QT_QPA_PLATFORM=wayland \
			-e XDG_RUNTIME_DIR \
			-e WAYLAND_DISPLAY \
			-v $(XDG_RUNTIME_DIR)/$(WAYLAND_DISPLAY):$(XDG_RUNTIME_DIR)/$(WAYLAND_DISPLAY) \
			--device /dev/dri \
			-v $(HOME)/.config/negar-gui:/home/negar/.config/negar-gui \
			negar-gui:latest,\
		$(if $(DISPLAY),\
			docker run --rm \
				-e DISPLAY \
				-v /tmp/.X11-unix:/tmp/.X11-unix \
				-v $(HOME)/.config/negar-gui:/home/negar/.config/negar-gui \
				negar-gui:latest,\
			@echo "No display server detected (set DISPLAY for X11 or WAYLAND_DISPLAY for Wayland)"))

.PHONY: docker-push
docker-push: docker-build ## Tag and push the Docker image to Docker Hub
	@[ -n "$(DOCKER_USER)" ] || { echo "Usage: make docker-push DOCKER_USER=<your-dockerhub-username>" >&2; exit 1; }
	docker tag negar-gui:latest $(DOCKER_USER)/negar-gui:latest
	docker tag negar-gui:latest $(DOCKER_USER)/negar-gui:$(VER)
	docker push $(DOCKER_USER)/negar-gui:latest
	docker push $(DOCKER_USER)/negar-gui:$(VER)

clean: ver ## Clean build artifacts
	@rm negar_gui.egg-info/ -rfv
	@rm build/ -rfv
	@rm dist/ -rfv
	@rm gui.build/ -rfv
	@rm gui.dist/ -rfv
	@rm negar*.spec -rfv
	@rm negar_gui/__pycache__ -rfv

# Backward-compat aliases
.PHONY: generate_desktop_file lins pins upypi utest nuCompile piCompile
.PHONY: trans res ui sres sui strans
generate_desktop_file: install-desktop-file
lins: install-dev
pins: install-pypi
upypi: publish-pypi
utest: publish-testpypi
nuCompile: compile-nuitka
piCompile: compile-pyinstaller
trans: update-translations
res: compile-resources
ui: compile-ui
sres: compile-resources-pyside2
sui: compile-ui-pyside2
strans: update-translations-pyside2
