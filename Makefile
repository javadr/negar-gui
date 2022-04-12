VER=$(shell grep __version__ negar_gui/constants.py|cut -d= -f2|tr -d '\" ')

.ONESHELL:

ver:
	@echo negar-gui ver. $(VER)

setup: ver
	python setup.py sdist
	python setup.py bdist_wheel

lins: ver
	python setup.py install

pins: ver
	pip install negar-gui==$(VER)

upypi: setup
	twine upload dist/negar-gui-$(VER).tar.gz

utest: setup
	twine upload --repository-url https://test.pypi.org/legacy/  dist/negar-gui-$(VER).tar.gz

upload: setup upypi utest

nuCompile: ver
	nuitka3 negar_gui/gui.py --standalone --onefile --linux-onefile-icon=negar_gui/logo.png \
	--include-data-dir=.negar/lib/python3.10/site-packages/pyuca=pyuca \
	--include-data-dir=.negar/lib/python3.10/site-packages/negar=negar/data \
	-o dist/negar-gui-v$(VER).bin \
	--output-dir=dist --remove-output --enable-plugin=pyqt5
	# --include-data-file=negar/data/untouchable.dat=data/untouchable.dat \

	ls -lh dist

piCompile: ver
	rm build/gui/ -rfv
	# . .negar/bin/activate
	pyinstaller -p negar_gui --onefile \
	--collect-data pyuca --collect-data negar --noupx negar_gui/gui.py -n negar-gui-v$(VER)
	# --add-data negar/data/untouchable.dat:data
	ls -lh dist

clean: ver
	rm negar_gui.egg-info/ -rfv
	rm build/ -rfv
	rm dist/ -rfv
	rm gui.build/ -rfv
	rm gui.dist/ -rfv
	rm negar*.spec -rfv
