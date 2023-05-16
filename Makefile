VER=$(shell grep __version__ negar_gui/constants.py|cut -d= -f2|tr -d '\" ')

# Check if running inside a virtual environment
VENV:=$(shell echo "$${VIRTUAL_ENV-}")
# Virtual environment Python interpreter
NEGAR:=$(if $(VENV),$(VIRTUAL_ENV)/bin/negar-gui,$(HOME)/.local/bin/negar-gui)
APP_DESKTOP:="$(HOME)/.local/share/applications/negar.desktop"

.ONESHELL:

ver:
	@echo negar-gui, Ver. $(VER)
	@echo $(VENV)
	@echo $(NEGAR)
	@echo $(APP_DESKTOP)

.PHONY: generate_desktop_file
generate_desktop_file:
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
uninstall:
	@echo "Uninstalling negar-gui ..."
	pip uninstall negar-gui
	@echo "Removing the desktop file and its icon ..."
	rm -fv $(APP_DESKTOP) $(HOME)/.local/share/icons/negar.png
	@echo "Desktop file removed successfully."

setup: ver
	python setup.py sdist
	python setup.py bdist_wheel

lins: ver generate_desktop_file
	python setup.py install

pins: ver generate_desktop_file
	pip install negar-gui==$(VER)

upypi: setup
	twine upload "dist/negar-gui-$(VER).tar.gz"

utest: setup
	twine upload -r testpypi "dist/negar-gui-$(VER).tar.gz"

upload: setup upypi utest

nuCompile: setup ver
	nuitka3 negar_gui/main.py --standalone --onefile --linux-onefile-icon=negar_gui/icons/logo.png \
	--enable-plugin=pyqt5 --nofollow-import-to=tkinter --lto=no \
	-o dist/negar-gui-v$(VER).bin \
	--output-dir=dist --remove-output \
	--include-data-file=.negar/lib/python3.10/site-packages/pyuca/allkeys-9.0.0.txt=pyuca/allkeys-9.0.0.txt \
	--include-data-file=.negar/lib/python3.10/site-packages/negar/data/untouchable.dat=negar/data/untouchable.dat
	# --include-data-dir=.negar/lib/python3.10/site-packages/negar=negar/data \
	# --module python-negar --include-package=python-negar
	# --include-package-data=python-negar=*.dat \

	ls -lh dist

piCompile: setup ver
	@rm build/gui/ -rfv
	pyinstaller -p negar_gui --onefile --windowed --clean -i"negar_gui/icons/logo.ico" \
	--collect-data pyuca --noupx negar_gui/main.py -n negar-gui-v$(VER) \
	--add-data negar_gui/ts/fa.qm:ts \
	--add-data ../python-negar/negar/data/untouchable.dat:negar/data # &> pyins.out
	ls -lh dist

trans: ver
	pylupdate5 -verbose negar_gui/Ui_mwin.py -ts negar_gui/ts/fa-uimwin.ts
	pylupdate5 -verbose negar_gui/Ui_uwin.py -ts negar_gui/ts/fa-uiuwin.ts
	pylupdate5 -verbose negar_gui/Ui_hwin.py -ts negar_gui/ts/fa-uihwin.ts
	pylupdate5 -verbose negar_gui/main.py -ts negar_gui/ts/fa-main.ts
	lrelease negar_gui/ts/fa-*.ts -qm negar_gui/ts/fa.qm

res: ver
	pyrcc5 negar_gui/resource.qrc -o negar_gui/resource_rc.py

ui: ver
	pyuic5 --from-imports negar_gui/mwin.ui -xo negar_gui/Ui_mwin.py
	pyuic5 --from-imports negar_gui/uwin.ui -xo negar_gui/Ui_uwin.py

sres: ver
	pyside2-rcc negar_gui/resource.qrc -o negar_gui/resource_rc.py

sui: ver
	pyside2-uic --from-imports negar_gui/mwin.ui -o negar_gui/Ui_mwin.py
	pyside2-uic --from-imports negar_gui/uwin.ui -o negar_gui/Ui_uwin.py

strans: ver
	pyside2-lupdate -verbose negar_gui/Ui_mwin.py -ts negar_gui/ts/fa-uimwin.ts
	pyside2-lupdate -verbose negar_gui/Ui_uwin.py -ts negar_gui/ts/fa-uiuwin.ts
	pyside2-lupdate -verbose negar_gui/main.py -ts negar_gui/ts/fa-main.ts
	pyside2-lrelease negar_gui/ts/fa-*.ts -qm negar_gui/ts/fa.qm

clean: ver
	@rm negar_gui.egg-info/ -rfv
	@rm build/ -rfv
	@rm dist/ -rfv
	@rm gui.build/ -rfv
	@rm gui.dist/ -rfv
	@rm negar*.spec -rfv
	@rm negar_gui/__pycache__ -rfv
