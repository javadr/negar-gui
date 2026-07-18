#!/usr/bin/env python3

"""negar-gui.

Usage:
    negar-gui -h
    negar-gui -v
    negar-gui

Options:
    -h, --help          Show this screen.
    -v, --version       Show version and exit
"""

# Standard library imports
import asyncio
import json
import logging
import re
import sys
import tempfile
from pathlib import Path
from threading import Thread


# Third-party library import
import qdarktheme
import requests
import toml
from docopt import docopt

from pyperclip import copy as pyclipcopy
from PyQt6.QtCore import (
    QAbstractTableModel,
    QByteArray,
    QCoreApplication,
    QPoint,
    QSize,
    Qt,
    QTimer,
    QTranslator,
    QUrl,
)
from PyQt6 import QtGui
from PyQt6.QtGui import QColor, QDesktopServices, QGuiApplication, QIcon, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSpacerItem,
)
from pyuca import Collator
from qrcode import ERROR_CORRECT_L, QRCode
from redlines import Redlines

from negar_gui import llm_providers

# Local application imports
# The following is neccessary for ICONs
import negar_gui.resource_rc  # noqa: F401
from negar.constants import INFO, __version__ as negar__version
from negar.virastar import ImmutableWords, PersianEditor
from negar_gui.constants import LOGO, SETTING_FILE, __version__
from negar_gui.Ui_hwin import Ui_Dialog
from negar_gui.Ui_mwin import Ui_MainWindow
from negar_gui.Ui_uwin import Ui_uwWindow


_translate = QCoreApplication.translate
NEGARGUIPATH = Path(__file__).parent.as_posix()

collator = Collator()

# Configure the logging module
logging.basicConfig(
    level=logging.INFO,
    format=r"[%(asctime)s-%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def init_decorator(func):
    def wrapper(*args, **kwargs):
        func(*args, **kwargs)
        self, parent = args[0], kwargs.pop("parent", None)
        # Maximize Frame Size if either height or width exceeds real screen dimensions
        # screen = QApplication.desktop().screenGeometry()
        screen = QApplication.primaryScreen().geometry()
        h, w = screen.height(), screen.width()
        if self.width() > w or self.height() > h:
            self.showMaximized()
        # set layout direction automatically
        if parent:
            try:
                self.centralwidget.setLayoutDirection(parent.layoutDirection())
            except:  # QDialog  has no centralwidget
                pass
        # connect widgets to their proper slot
        self.connectSlots()

    return wrapper


class TableModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignVCenter
        elif role == Qt.ItemDataRole.BackgroundRole:
            if index.row() % 2:
                return QColor("gray")
        elif role == Qt.ItemDataRole.ForegroundRole:
            if index.row() % 2:
                return QColor("white")
        elif role == Qt.ItemDataRole.DisplayRole:
            try:
                return self._data[index.row()][index.column()]
            except:
                return ""
        return None

    def rowCount(self, index):
        del index
        return len(self._data)

    def columnCount(self, index):
        """Take the first sub-list, and returns the length.

        (only works if all rows are an equal length).
        """
        del index
        return len(self._data[0])

    def headerData(self, section, orientation, role):
        """Section is the index of the column/row."""
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return ""
            if orientation == Qt.Orientation.Vertical:
                return str(section + 1)
        return None


class WindowSettings(QMainWindow):
    _settings = {}

    @property
    def settings(self):
        return self._settings

    @settings.setter
    def settings(self, value):
        self._settings = value

    def __save_settings(self):
        self.settings.update(
            {
                "window_size": {"width": self.width(), "height": self.height()},
                "window_position": {"x": self.x(), "y": self.y()},
            }
        )

        with SETTING_FILE.open("w") as toml_file:
            toml.dump(self.settings, toml_file)

        logging.info("Settings Saved on Close!")

    def __load_settings(self):
        try:
            with SETTING_FILE.open() as toml_file:
                self.settings.update(toml.load(toml_file))
            window_size = QSize(
                self.settings["window_size"]["width"],
                self.settings["window_size"]["height"],
            )
            window_position = QPoint(
                self.settings["window_position"]["x"],
                self.settings["window_position"]["y"],
            )
            self.resize(window_size)
            self.move(window_position)
        except FileNotFoundError:
            logging.error("Settings File Not Found!")
        except KeyError as err:
            logging.error("KeyError[%s]: Settings File Broken!" % err)

    def closeEvent(self, event):
        del event
        self.__save_settings()

    def showEvent(self, event):
        # This method is called when the window is being shown
        # You can perform initialization tasks here
        del event
        self.__load_settings()


class ImmutableWordsWindow(QMainWindow, Ui_uwWindow):
    @init_decorator
    def __init__(self, parent=None):
        self.parent = parent
        super().__init__(parent)
        self.setupUi(self)
        self.setup_table()
        # if parent: self.centralwidget.setLayoutDirection(parent.layoutDirection())

    def setup_table(self, col=8):
        self.untouch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        data = sorted(list(ImmutableWords().get()), key=collator.sort_key)
        data = [data[i * col : (i + 1) * col] for i in range(int(len(data) // col) + 1)]
        model = TableModel(data)
        self.untouch_table.setModel(model)

    def connectSlots(self):
        self.untouch_word.textChanged.connect(self.untouch_add_enabler)
        self.untouch_button.clicked.connect(self.untouch_add)

    def untouch_add_enabler(self):
        """Enable `Add` button when a single word is entered in the immutable text input."""
        word_list = self.untouch_word.text().split()
        self.untouch_button.setEnabled(len(word_list) == 1)

    def untouch_add(self):
        """Add a new word into immutable words."""
        word = [self.untouch_word.text().strip()]
        ImmutableWords.add(word)
        self.untouch_word.clear()
        self.setup_table()  # updates immutable words list

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_F11:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        del event
        if self.parent:
            self.parent.show()
            self.parent.edit_text()


class HelpWindow(QDialog, Ui_Dialog):
    @init_decorator
    def __init__(self, parent=None, title=None, label=None):
        self.parent = parent
        super().__init__(parent)
        self.setupUi(self)
        self.buttonBox.buttons()[0].setText(_translate("Dialog", "Close"))
        self.setWindowTitle(title)

        if isinstance(label, str):
            self.label.setText(label)
        if isinstance(label, QPixmap):
            self.label.setPixmap(label)
            # self.setFixedSize(QSize(600,600))

    def connectSlots(self):
        pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class MyWindow(WindowSettings, QMainWindow, Ui_MainWindow):
    @init_decorator
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.input_editor.setStyleSheet("border: 1px solid #d89e76;")
        self.output_editor.setStyleSheet("border: 1px solid #d89e76;")
        self.setWindowIcon(QIcon(LOGO))
        _ai_icon = QIcon(str(Path(NEGARGUIPATH) / "icons/ai.svg"))
        self.llm_btn.setIcon(_ai_icon)
        # self.input_editor.setFocus(True)
        self.input_editor.setFocus(Qt.FocusReason.OtherFocusReason)
        # Translator
        # main language is defined via self.settings["settings"]["language"] by WindowsSettings
        self.trans = QTranslator()
        self.editing_options = []
        self.current_llm_prompt_key = "fix_grammar"
        self.clipboard = QApplication.clipboard()
        self.fileDialog = QFileDialog()
        self.filename = None  # will be defined later
        self.cleaned_text = ""  # Stores the cleaned text, as output_editor may also contain comparative text
        self._llm_nam = QNetworkAccessManager()
        self._llm_icon_base = self.llm_btn.icon().pixmap(32, 32)
        self._llm_spin_angle = 0
        self._llm_spin_timer = QTimer()
        self._llm_spin_timer.setInterval(100)
        self._llm_spin_timer.timeout.connect(self._llm_spin_tick)
        self._status_label = QLabel()
        self.statusBar.addWidget(self._status_label, 1)
        self._statusBar()
        # Checks for new release
        Thread(target=lambda: asyncio.run(self.updateCheck()), daemon=True).start()

        self.options_action_menu = (
            self.actionFix_Dashes,
            self.actionFix_three_dots,
            self.actionFix_English_quotes,
            self.actionFix_hamzeh,
            self.actionUse_Persian_yeh_to_show_hamzeh,
            self.actionFix_spacing_braces_and_quotes,
            self.actionFix_Arabic_numbers,
            self.actionFix_English_numbers,
            self.actionFix_non_Persian_chars,
            self.actionFix_prefix_spacing,
            self.actionFix_prefix_separating,
            self.actionFix_suffix_spacing,
            self.actionFix_suffix_separating,
            self.actionFix_aggressive_punctuation,
            self.actionCleanup_kashidas,
            self.actionCleanup_extra_marks,
            self.actionCleanup_spacing,
            self.actionTrim_Leading_Trailing_Whitespaces,
            self.actionExaggerating_ZWNJ,
        )

    async def updateCheck(self):
        nurl = "https://raw.github.com/shahinism/python-negar/master/negar/constants.py"
        ngurl = "https://raw.github.com/javadr/negar-gui/master/negar_gui/constants.py"

        async def get(link):
            with requests.get(link) as response:
                VERSION_PATTERN = r'(__version__ = "(\d\.\d(\.\d+)?)")'
                return re.search(VERSION_PATTERN, response.text, re.M).group(2)

        try:
            requests.get("https://github.com")  # check the internet connection
            negar_t = asyncio.create_task(get(nurl))
            negargui_t = asyncio.create_task(get(ngurl))
            negar_v = await negar_t
            negargui_v = await negargui_t
        except:
            negar_v, negargui_v = "0.0", "0.0"

        def version(v):
            return list(map(int, v.split(".")))

        negar_nv, negargui_nv = (version(i) for i in (negar_v, negargui_v))
        negar_ov, negargui_ov = (version(i) for i in (negar__version, __version__))
        notification = ""
        message = "New version is available for {}. Use `pip install --upgrade {}` to update"
        if negar_nv > negar_ov:
            notification = message.format("negar", "python-negar")
        if negargui_nv > negargui_ov:
            notification = message.format("negar-gui", "negar-gui")
        self._statusBar(f"{notification}" if notification != message else "")

    def connectSlots(self):
        self.autoedit_handler()
        # connect to slots
        self.autoedit_chkbox.stateChanged.connect(self.autoedit_handler)
        self.comparative_output_chkbox.stateChanged.connect(self.autoedit_handler)
        self.edit_btn.clicked.connect(self.edit_text)
        self.actionOpen.triggered.connect(self.open_file_slot)
        self.actionSave.triggered.connect(self.save_file_slot)
        self.actionExport.triggered.connect(self.export_file_slot)
        self.actionExit.triggered.connect(self.close)
        self.font_slider.valueChanged.connect(self._set_font_size)
        self.actionIncrease_Font_Size.triggered.connect(
            lambda: (
                self.font_slider.setValue(self.font_slider.value() + 1),
                self._set_font_size(),
            ),
        )
        self.actionDecrease_Font_Size.triggered.connect(
            lambda: (
                self.font_slider.setValue(self.font_slider.value() - 1),
                self._set_font_size(),
            )
        )
        self.actionPersian.triggered.connect(
            lambda: (
                self.settings.update({"settings": {"language": "Persian"}}),
                self.set_ui_language(),
            )
        )
        self.actionEnglish.triggered.connect(
            lambda: (
                self.settings.update({"settings": {"language": "English"}}),
                self.set_ui_language(),
            )
        )

        self.actionNegar_Help.triggered.connect(
            lambda: (
                self.input_editor.setText(INFO),  # puth the info in the input editor
                self.autoedit_handler(),  # auto adjust the font size
            )
        )
        self.actionAbout_Negar.setShortcut("CTRL+H")
        self.actionAbout_Negar.triggered.connect(
            lambda: HelpWindow(
                parent=self,
                title=_translate("Dialog", "About Negar"),
                label=self.edit_text(INFO),
            ).show()
        )
        self.actionAbout_Negar_GUI.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/javadr/negar-gui")),
        )
        self.actionDonate.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/javadr/negar-gui#donation")),
        )
        self.actionReport_Bugs.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/javadr/negar-gui/issues")),
        )
        # connecting the option menu items to their handlers
        for menu_item in self.options_action_menu:
            menu_item.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))

        self.actionUntouchable_Words.triggered.connect(
            lambda: (ImmutableWordsWindow(parent=self).show(), MAIN_WINDOW.hide())
        )
        self._build_llm_menu()
        self.llm_btn.clicked.connect(self.llm_fix_text_slot)
        self.llm_btn.setShortcut("Ctrl+Shift+A")
        self.actionCopy.triggered.connect(self.copy_slot)
        self.copy_btn.clicked.connect(self.copy_slot)

        self.actionInteractive_Clipboard.triggered.connect(
            lambda: (
                self.clipboard.dataChanged.connect(self.onClipboardChanged)
                if self.actionInteractive_Clipboard.isChecked()
                else self.clipboard.dataChanged.disconnect(self.onClipboardChanged)
            )
        )
        self.actionQr_Code.triggered.connect(self.qrcode)

        self.vertical_btn.clicked.connect(
            lambda: (
                self.actionSide_by_Side_View.setChecked(True),
                self._grid_layout("v"),
            )
        )
        self.horizontal_btn.clicked.connect(
            lambda: (
                self.actionSide_by_Side_View.setChecked(False),
                self._grid_layout("h"),
            )
        )
        # fmt: off
        self.actionSide_by_Side_View.triggered.connect(
            lambda: self._grid_layout("v")
            if self.actionSide_by_Side_View.isChecked()
            else self._grid_layout("h")
        )
        # fmt: on
        self.actionFull_Screen_Input.triggered.connect(self.full_screen_input_slot)

        self.action_dark.triggered.connect(
            lambda: (
                qdarktheme.setup_theme(
                    "dark",
                    custom_colors={
                        "[dark]": {
                            "primary": "#D0BCFF",
                            "primary>button.hoverBackground": "#ffffff",
                        },
                    },
                ),
                self.settings.update({"view": {"theme": "dark"}}),
            )
        )
        self.action_Light.triggered.connect(
            lambda: (
                qdarktheme.setup_theme("light"),
                self.settings.update({"view": {"theme": "light"}}),
            )
        )
        self.action_Auto.triggered.connect(
            lambda: (
                qdarktheme.setup_theme("auto"),
                self.settings.update({"view": {"theme": "auto"}}),
            )
        )

        self.input_editor.verticalScrollBar().valueChanged.connect(self._sync_inout_scroll)
        self.output_editor.verticalScrollBar().valueChanged.connect(self._sync_inout_scroll)

        def check(value: bool):
            return lambda: (
                [checkbox.setChecked(value) for checkbox in self.options_action_menu],
                self.option_control(),
                self.autoedit_handler(),
            )

        self.actionSelect_All.triggered.connect(check(True))
        self.actionUnselect_All.triggered.connect(check(False))
        # fmt: off
        self.actionInvert_Selection.triggered.connect(
            lambda: (
                [
                    checkbox.setChecked(not checkbox.isChecked())
                    for checkbox in self.options_action_menu
                ],
                self.option_control(),
                self.autoedit_handler(),
            )
        )
        # fmt: on

    ####################### SLOTs ###############################
    def _sync_inout_scroll(self, value):
        max_in_scroll = self.input_editor.verticalScrollBar().maximum()
        max_out_scroll = self.output_editor.verticalScrollBar().maximum()
        sender = self.sender()
        if sender == self.input_editor.verticalScrollBar() and max_in_scroll != 0:
            new_value = int(value / max_in_scroll * max_out_scroll)
            self.output_editor.verticalScrollBar().valueChanged.disconnect(self._sync_inout_scroll)
            self.output_editor.verticalScrollBar().setValue(new_value)
            self.output_editor.verticalScrollBar().valueChanged.connect(self._sync_inout_scroll)

        elif sender == self.output_editor.verticalScrollBar() and max_out_scroll != 0:
            new_value = int(value / max_out_scroll * max_in_scroll)
            self.input_editor.verticalScrollBar().valueChanged.disconnect(self._sync_inout_scroll)
            self.input_editor.verticalScrollBar().setValue(new_value)
            self.input_editor.verticalScrollBar().valueChanged.connect(self._sync_inout_scroll)

    def full_screen_input_slot(self):
        (
            self._grid_full_input()
            if self.actionFull_Screen_Input.isChecked()
            else self._grid_layout("v")
            if self.actionSide_by_Side_View.isChecked()
            else self._grid_layout("h")
        )

    # Change GridLayout Orientation
    def _grid_layout(self, layout="h"):
        assert layout in ("v", "h"), "Layout must be 'v' or 'h'"
        if layout == "v":
            self.gridLayout.setHorizontalSpacing(5)
        elif layout == "h":
            self.gridLayout.setVerticalSpacing(0)
        widgets = (
            self.input_editor_label,
            self.input_editor,
            self.output_editor,
        )
        for widget in widgets:
            self.gridLayout.removeWidget(widget)
            widget.setParent(None)
        self.horizontalLayout.setParent(None)
        self.output_lbl_comp_chk_layout.setParent(None)
        # (row, col, rowspan, colspan)
        elements = {
            "v": (  # VERTICAL
                (0, 0, 1, 1),
                (1, 0, 1, 1),
                (1, 1, 1, 1),
            ),
            "h": (  # HORIZONTAL
                (0, 0, 1, 2),
                (1, 0, 1, 2),
                (3, 0, 1, 2),
            ),
        }
        for i, widget in enumerate(widgets):
            self.gridLayout.addWidget(widget, *elements[layout][i])

        self.horizontalLayout = QHBoxLayout()
        spacerMin = QSpacerItem(7, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        spacerMax = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.horizontalLayout.addWidget(self.output_editor_label)
        self.horizontalLayout.addItem(spacerMin)
        self.horizontalLayout.addWidget(self.comparative_output_chkbox)
        self.horizontalLayout.addItem(spacerMax)
        span = {"v": (0, 1, 1, 2), "h": (2, 1, 1, 1)}
        self.gridLayout.addLayout(self.horizontalLayout, *span[layout])

    def _grid_full_input(self):
        widgets = (self.output_editor_label, self.output_editor)
        for widget in widgets:
            self.gridLayout.removeWidget(widget)
            widget.setParent(None)

    def qrcode(self):
        # Check if Shift is held when button clicked
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            text = self.input_editor.toPlainText().strip()
            qr_text = text
        else:
            text = self.output_editor.toPlainText().strip()
            qr_text = self.cleaned_text

        if len(text) == 0:
            if self.settings["settings"]["language"] == "Persian":
                statusbar_timeout(self, "هیچ متنی برای نمایش از طریق کد QR وجود ندارد!")
            else:  # English
                statusbar_timeout(self, "There is no text to be fed to the QR Code!")
            return
        qr = QRCode(
            version=1,
            error_correction=ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        # qr.add_data(self.output_editor.toPlainText())
        qr.add_data(qr_text)
        qr.make(fit=True)
        img = qr.make_image()
        temp_path = Path(tempfile.gettempdir())
        img.save(temp_path / "negar-gui_qrcode.png")
        pixmap = QPixmap(f"{(temp_path / 'negar-gui_qrcode.png').absolute()}")
        # screen = QApplication.desktop().screenGeometry()
        screen = QApplication.primaryScreen().geometry()
        w = min(screen.height(), screen.width())
        if w - 90 < img.size[0]:
            # pixmap = pixmap.scaled(w - 90, w - 90, Qt.KeepAspectRatio)
            pixmap = pixmap.scaled(w - 90, w - 90, Qt.AspectRatioMode.KeepAspectRatio)

        qr_window = HelpWindow(parent=self, title="QR Code", label=pixmap)
        qr_window.buttonBox.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
            if self.layoutDirection() == Qt.LayoutDirection.LeftToRight
            else Qt.LayoutDirection.LeftToRight
        )
        qr_window.show()

        (Path(temp_path) / "negar-gui_qrcode.png").unlink()

    def _statusBar(self, notification="", timeout=0):
        prefix = f"Negar v{negar__version} [[Negar-GUI v{__version__}]]"
        is_persian = self.settings.get("settings", {}).get("language") == "Persian"
        message = f"\u202b{prefix} {notification}\u202c" if is_persian else f"{prefix} {notification}"
        self._status_label.setText(message)
        if timeout:
            QTimer.singleShot(timeout, self._status_label.clear)
        self._last_notification = notification
        self._last_timeout = timeout

    def _statusBar_tr(self, context, source, timeout=0, *args):
        text = _translate(context, source)
        if args:
            text = text.format(*args)
        self._last_tr = (context, source, args, timeout)
        self._statusBar(text, timeout)

    def open_file_slot(self):
        filename, _ = self.fileDialog.getOpenFileName(
            self,
            "Open File - A Plain Text",
            ".",
            "Text Files (*.txt);;All Files (*)",
        )
        if filename:
            with Path(filename).open(encoding="utf-8") as f:
                try:
                    self.input_editor.setPlainText(str(f.read()))
                    self.filename = Path(filename)
                    MAIN_WINDOW.setWindowTitle(f"Negar - {self.filename.name}")
                    statusbar_timeout(self, "File Opened.")
                except Exception as e:
                    self.input_editor.setPlainText(e.args[1])

    def save_file_slot(self):
        if not self.output_editor.toPlainText():
            return
        if hasattr(self, "filename") and self.filename:
            with open(self.filename, "w", encoding="utf-8") as f:
                try:
                    f.write(self.output_editor.toPlainText())
                    statusbar_timeout(self, "File Saved.")
                except Exception as e:
                    self.output_editor.setPlainText(e.args[1])
        else:
            self.export_file_slot()

    def export_file_slot(self):
        if not self.output_editor.toPlainText():
            return
        filename, ext_type = self.fileDialog.getSaveFileName(
            self,
            "Save File",
            ".",
            "Text Files (*.txt);;All Files (*)",
        )
        ext = ".txt" if ext_type.find(".txt") and not filename.endswith(".txt") else ""
        if filename:
            with Path(f"{filename}{ext}").open("w", encoding="utf-8") as f:
                try:
                    f.write(self.output_editor.toPlainText())
                    self.filename = Path(f"{filename}{ext}")
                    MAIN_WINDOW.setWindowTitle(f"Negar - {self.filename.name}")
                    statusbar_timeout(self, "File Saved.")
                except Exception as exception:
                    self.output_editor.setPlainText(exception.args[1])

    def set_ui_language(self):
        """Change ui language."""
        if self.settings["settings"]["language"] == "Persian":
            self.trans.load("fa", directory=f"{NEGARGUIPATH}/ts")
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.centralwidget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.autoedit_chkbox.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.statusBar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        elif self.settings["settings"]["language"] == "English":
            self.trans.load("en")
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.centralwidget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.autoedit_chkbox.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.statusBar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self._status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            return
        _app = QApplication.instance()
        _app.installTranslator(self.trans)
        self.retranslateUi(self)
        self._build_llm_menu()
        if not self.llm_btn.isEnabled() and hasattr(self, "_llm_pending_prompt"):
            prompt_name = _translate("MainWindow", self._llm_pending_prompt["name"])
            self._statusBar_tr("MainWindow", "Running {}...", 0, prompt_name)
        elif hasattr(self, "_last_tr"):
            ctx, src, args, to = self._last_tr
            self._statusBar_tr(ctx, src, to, *args)

    # def retranslateUi(self, MyWindow):
    # super(MyWindow, self).retranslateUi()
    # _translate = QtCore.QCoreApplication.translate
    # MyWindow.fileDialog.setText(_translate(self.fileDialog.name(), "Open File - A Plain Text"))

    def copy_slot(self):
        # output = self.output_editor.toPlainText()
        output = self.cleaned_text
        if output:
            # QApplication.clipboard().setText(output)
            QGuiApplication.clipboard().setText(output)
        return output

    ####################### EVENTs ###############################
    def onClipboardChanged(self):
        text = self.clipboard.text()
        if text:
            self.input_editor.setPlainText(text)
            self._set_font_size()

    def closeEvent(self, event):
        self.__save_settings()
        WindowSettings.closeEvent(self, event)
        del event
        # event = QEvent(QEvent.Clipboard)
        # QApplication.sendEvent(QApplication.clipboard(), event)
        pyclipcopy(self.copy_slot())
        # Exit the application when the main window is closed
        QApplication.instance().quit()

    def showEvent(self, event):
        WindowSettings.showEvent(self, event)
        del event
        self.__load_settings()

    def __load_settings(self):
        try:
            # view menu
            self.actionSide_by_Side_View.setChecked(self.settings["view"]["side-by-side"])
            self.actionFull_Screen_Input.setChecked(self.settings["view"]["full-screen-input"])
            self.full_screen_input_slot()
            self.font_slider.setValue(self.settings["view"]["font-size"])
            self.autoedit_chkbox.setChecked(self.settings["view"]["real-time-edit"])
            self.comparative_output_chkbox.setChecked(self.settings["view"]["comparative-mode"])
            qdarktheme.setup_theme(self.settings["view"]["theme"])
            # settings menu
            # fmt: off
            self.actionInteractive_Clipboard.setChecked(
                self.settings["settings"]["interactive-clipboard"]
            )
            # fmt: on
            self.set_ui_language()
            # connect interactive clipboard slot if it is checked
            if self.actionInteractive_Clipboard.isChecked():
                self.clipboard.dataChanged.connect(self.onClipboardChanged)
            # settings.editing-options
            sdict = self.settings["settings"]["editing-option"]
            self.actionFix_Dashes.setChecked(sdict["fix-dashes"])
            self.actionFix_three_dots.setChecked(sdict["fix-three-dots"])
            self.actionFix_English_quotes.setChecked(sdict["fix-english-quotes"])
            self.actionFix_hamzeh.setChecked(sdict["fix-hamzeh"])
            self.actionUse_Persian_yeh_to_show_hamzeh.setChecked(sdict["hamzeh-with-yeh"])
            self.actionFix_spacing_braces_and_quotes.setChecked(sdict["fix-spacing-bq"])
            self.actionFix_Arabic_numbers.setChecked(sdict["fix-arabic-num"])
            self.actionFix_English_numbers.setChecked(sdict["fix-english-num"])
            self.actionFix_non_Persian_chars.setChecked(sdict["fix-non-persian-chars"])
            self.actionFix_prefix_spacing.setChecked(sdict["fix-p-spacing"])
            self.actionFix_prefix_separating.setChecked(sdict["fix-p-separate"])
            self.actionFix_suffix_spacing.setChecked(sdict["fix-s-spacing"])
            self.actionFix_suffix_separating.setChecked(sdict["fix-s-separate"])
            self.actionFix_aggressive_punctuation.setChecked(sdict["aggressive"])
            self.actionCleanup_kashidas.setChecked(sdict["cleanup-kashidas"])
            self.actionCleanup_extra_marks.setChecked(sdict["cleanup-ex-marks"])
            self.actionCleanup_spacing.setChecked(sdict["cleanup-spacing"])
            self.actionTrim_Leading_Trailing_Whitespaces.setChecked(sdict["trim-lt-whitespaces"])
            self.actionExaggerating_ZWNJ.setChecked(sdict["exaggerating-zwnj"])
        except KeyError as err:
            self.settings.update({"settings": {"language": "English"}})
            logging.error("KeyError[%s]: Settings File Broken!" % err)

    def __save_settings(self):
        settings = {
            "view": {
                "side-by-side": self.actionSide_by_Side_View.isChecked(),
                "full-screen-input": self.actionFull_Screen_Input.isChecked(),
                "font-size": self.font_slider.value(),
                "real-time-edit": self.autoedit_chkbox.isChecked(),
                "comparative-mode": self.comparative_output_chkbox.isChecked(),
                "theme": self.settings.get("view", {"theme": "dark"})["theme"],
            },
            "settings": {
                "interactive-clipboard": self.actionInteractive_Clipboard.isChecked(),
                "language": self.settings.get("settings", {"language": "English"})["language"],
                "editing-option": {
                    "fix-dashes": self.actionFix_Dashes.isChecked(),
                    "fix-three-dots": self.actionFix_three_dots.isChecked(),
                    "fix-english-quotes": self.actionFix_English_quotes.isChecked(),
                    "fix-hamzeh": self.actionFix_hamzeh.isChecked(),
                    "hamzeh-with-yeh": self.actionUse_Persian_yeh_to_show_hamzeh.isChecked(),
                    "fix-spacing-bq": self.actionFix_spacing_braces_and_quotes.isChecked(),
                    "fix-arabic-num": self.actionFix_Arabic_numbers.isChecked(),
                    "fix-english-num": self.actionFix_English_numbers.isChecked(),
                    "fix-non-persian-chars": self.actionFix_non_Persian_chars.isChecked(),
                    "fix-p-spacing": self.actionFix_prefix_spacing.isChecked(),
                    "fix-p-separate": self.actionFix_prefix_separating.isChecked(),
                    "fix-s-spacing": self.actionFix_suffix_spacing.isChecked(),
                    "fix-s-separate": self.actionFix_suffix_separating.isChecked(),
                    "aggressive": self.actionFix_aggressive_punctuation.isChecked(),
                    "cleanup-kashidas": self.actionCleanup_kashidas.isChecked(),
                    "cleanup-ex-marks": self.actionCleanup_extra_marks.isChecked(),
                    "cleanup-spacing": self.actionCleanup_spacing.isChecked(),
                    "trim-lt-whitespaces": self.actionTrim_Leading_Trailing_Whitespaces.isChecked(),
                    "exaggerating-zwnj": self.actionExaggerating_ZWNJ.isChecked(),
                },
            },
        }
        self.settings.update(settings)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_F11:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
        elif event.key() == Qt.Key.Key_S and event.modifiers() == (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
        ):
            self.input_editor.setText(json.dumps(self.settings, indent=4))
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        # modifiers = QApplication.keyboardModifiers()
        modifiers = event.modifiers()
        # if modifiers == Qt.ControlModifier:
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            delta_notches = int(event.angleDelta().y() / 120)
            self.font_slider.setValue(self.font_slider.value() + delta_notches)
            self._set_font_size()

    def autoedit_handler(self):
        """Edits the input text automatically if `autoedit` is checked."""
        if self.autoedit_chkbox.isChecked():
            self.edit_btn.setEnabled(False)
            self.input_editor.textChanged.connect(self.edit_text)
        else:
            self.edit_btn.setEnabled(True)
            # This line will disconnect autoedit signal and will disable autoamtic edit option
            try:
                self.input_editor.textChanged.disconnect(self.edit_text)
            except:
                pass
        self._set_font_size()

    def _set_font_size(self):
        size = self.font_slider.value()
        self.input_editor.setFontPointSize(size)
        self.output_editor.setFontPointSize(size)
        lines = self.input_editor.toPlainText()
        self.input_editor.clear()
        self.input_editor.append(lines)
        self.edit_text()

        html_content = self.output_editor.toHtml()  # Get current content
        # Replace font-size values with new size
        new_html = re.sub(r"font-size:(\d+)pt", f"font-size:{size}pt", html_content)
        self.output_editor.setHtml(new_html)  # Update content

    def option_control(self):
        """Enable/Disable Editing features."""
        self.editing_options = []
        if not self.actionFix_Dashes.isChecked():
            self.editing_options.append("fix-dashes")
        if not self.actionFix_three_dots.isChecked():
            self.editing_options.append("fix-three-dots")
        if not self.actionFix_English_quotes.isChecked():
            self.editing_options.append("fix-english-quotes")
        if not self.actionFix_hamzeh.isChecked():
            self.editing_options.append("fix-hamzeh")
        if not self.actionUse_Persian_yeh_to_show_hamzeh.isChecked():
            self.editing_options.append("hamzeh-with-yeh")
        if not self.actionFix_spacing_braces_and_quotes.isChecked():
            self.editing_options.append("fix-spacing-bq")
        if not self.actionFix_Arabic_numbers.isChecked():
            self.editing_options.append("fix-arabic-num")
        if not self.actionFix_English_numbers.isChecked():
            self.editing_options.append("fix-english-num")
        if not self.actionFix_non_Persian_chars.isChecked():
            self.editing_options.append("fix-non-persian-chars")
        if not self.actionFix_prefix_spacing.isChecked():
            self.editing_options.append("fix-p-spacing")
        if not self.actionFix_prefix_separating.isChecked():
            self.editing_options.append("fix-p-separate")
        if not self.actionFix_suffix_spacing.isChecked():
            self.editing_options.append("fix-s-spacing")
        if not self.actionFix_suffix_separating.isChecked():
            self.editing_options.append("fix-s-separate")
        if not self.actionFix_aggressive_punctuation.isChecked():
            self.editing_options.append("aggressive")
        if not self.actionCleanup_kashidas.isChecked():
            self.editing_options.append("cleanup-kashidas")
        if not self.actionCleanup_extra_marks.isChecked():
            self.editing_options.append("cleanup-ex-marks")
        if not self.actionCleanup_spacing.isChecked():
            self.editing_options.append("cleanup-spacing")
        if not self.actionTrim_Leading_Trailing_Whitespaces.isChecked():
            self.editing_options.append("trim-lt-whitespaces")
        if not self.actionExaggerating_ZWNJ.isChecked():
            self.editing_options.append("exaggerating-zwnj")

    def edit_text(self, text=None):
        if text:
            return PersianEditor(text, *self.editing_options).cleanup()

        self.output_editor.clear()
        persian_editor = PersianEditor(
            self.input_editor.toPlainText(),
            *self.editing_options,
        )
        # self.output_editor.append(persian_editor.cleanup())
        self.cleaned_text = persian_editor.cleanup()
        if self.comparative_output_chkbox.isChecked():
            colorized_text = Redlines(
                re.sub(r"\s*?\n", " <br> ", self.input_editor.toPlainText().strip()),
                self.cleaned_text.strip().replace("\n", " <br> "),
            )
            try:
                self.output_editor.append(
                    re.sub(r"\s*?<br>\s*?", "<br>", colorized_text.output_markdown)  # noqa: COM812
                )
            except:  # noqa: E722
                pass
        else:
            self.output_editor.append(persian_editor.cleanup())

    ####################### LLM ###############################
    def _build_llm_menu(self):
        self.menuLLM.clear()
        self._llm_prompt_actions = {}
        first = True
        for key, prompt in llm_providers.PROMPTS.items():
            action = QtGui.QAction(_translate("MainWindow", prompt["name"]), self)
            action.setCheckable(True)
            action.setChecked(first and key == self.current_llm_prompt_key)
            action.triggered.connect(lambda checked, k=key: self._set_llm_prompt(k))
            self.menuLLM.addAction(action)
            self._llm_prompt_actions[key] = action
            first = False

    def _set_llm_prompt(self, key):
        self.current_llm_prompt_key = key
        for k, action in self._llm_prompt_actions.items():
            action.setChecked(k == key)

    def _llm_spin_tick(self):
        self._llm_spin_angle = (self._llm_spin_angle + 45) % 360
        t = QtGui.QTransform().rotate(self._llm_spin_angle)
        pix = self._llm_icon_base.transformed(t, Qt.TransformationMode.SmoothTransformation)
        self.llm_btn.setIcon(QIcon(pix))

    def _llm_spin_stop(self):
        self._llm_spin_timer.stop()
        self.llm_btn.setIcon(QIcon(self._llm_icon_base))

    def llm_fix_text_slot(self):
        text = self.input_editor.toPlainText()
        if not text.strip():
            return
        self.llm_btn.setEnabled(False)
        self._llm_spin_timer.start()
        self._llm_retries = 2
        self._llm_pending_text = text
        prompt_key = self.current_llm_prompt_key
        self._llm_pending_prompt = llm_providers.PROMPTS[prompt_key]
        self._statusBar_tr("MainWindow", "Running {}...", 0, _translate("MainWindow", self._llm_pending_prompt["name"]))
        self.statusBar.repaint()
        self._llm_send()

    def _llm_send(self):
        payload = json.dumps(
            {
                "model": "openai",
                "messages": [
                    {"role": "system", "content": self._llm_pending_prompt["system_prompt"]},
                    {"role": "user", "content": f"{self._llm_pending_prompt['prefix']}{self._llm_pending_text}"},
                ],
                "temperature": 0.0,
            }
        )

        url = QUrl(llm_providers.POLLINATIONS_URL)
        req = QNetworkRequest(url)
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")

        self._llm_reply = self._llm_nam.post(req, QByteArray(payload.encode()))
        self._llm_reply.finished.connect(self._on_llm_reply)

    def _on_llm_reply(self):
        self._llm_reply.finished.disconnect()
        data = self._llm_reply.readAll().data().decode()
        status = self._llm_reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)

        ok = False
        if status and status != 200:
            err = f"HTTP {status}: {data[:200]}"
        else:
            try:
                msg = json.loads(data)["choices"][0]["message"]
                import re as _re

                result = (msg.get("content") or "").strip()
                if not result:
                    result = (msg.get("reasoning") or "").strip()
                m = _re.search(r"<corrected\s*text>(.*?)</corrected\s*text>", result, _re.DOTALL)
                if m:
                    result = m.group(1).strip()
                if not result:
                    raise KeyError("content")
                ok = True
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                err = f"LLM response parse failed: {e}"

        if ok:
            self._llm_spin_stop()
            self.output_editor.setPlainText(result)
            self.cleaned_text = result
            self.llm_btn.setEnabled(True)
            self._statusBar_tr("MainWindow", "Grammar fix complete.")
            self._llm_reply.deleteLater()
            return

        if self._llm_retries > 0:
            self._llm_retries -= 1
            self._statusBar_tr("MainWindow", "Retrying...")
            self._llm_reply.deleteLater()
            QTimer.singleShot(1000, self._llm_send)
            return

        self._llm_spin_stop()
        self.llm_btn.setEnabled(True)
        self.output_editor.setPlainText(_translate("MainWindow", "AI Error: {}").format(err))
        self._statusBar_tr("MainWindow", "AI Error: {}", 10000, err)
        self._llm_reply.deleteLater()


def statusbar_timeout(self, notification, timeout=5000):
    self._status_label.setText(notification)
    if timeout:
        QTimer.singleShot(timeout, self._status_label.clear)


def main(args=docopt(__doc__)):
    """Program entry point."""
    if args["--version"]:
        print(f"negar-gui, Version {__version__}")  # noqa
        sys.exit()

    global MAIN_WINDOW
    try:
        qdarktheme.enable_hi_dpi()
    except AttributeError:
        qdarktheme.setup_theme = lambda x, **kw: ()
    app = QApplication(sys.argv)
    qdarktheme.setup_theme("dark")
    MAIN_WINDOW = MyWindow()
    MAIN_WINDOW.show()
    # sys.exit(app.exec_())
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
