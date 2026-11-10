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
import os
import re
import sys
import tempfile
from pathlib import Path
from threading import Thread


# Third-party library import
import PyQt6.QtCore  # noqa: F401  # first, so qdarktheme binds to PyQt6 and not to an installed PySide6
import qdarktheme
import requests
import toml
from docopt import docopt

from pyperclip import copy as pyclipcopy
from PyQt6.QtCore import (
    QEvent,
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
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
)
from pyuca import Collator
from qrcode import ERROR_CORRECT_L, QRCode
from redlines import Redlines

from negar_gui import keyboard_layout, llm_providers, ocr, usage_log

# Local application imports
# The following is neccessary for ICONs
import negar_gui.resource_rc  # noqa: F401
from negar.constants import INFO, __version__ as negar__version
from negar.virastar import ImmutableWords, PersianEditor
from negar_gui.constants import LOGO, SETTING_FILE, __version__
from negar_gui.dialogs import LLMProviderDialog, PromptsDialog, UsageReportDialog, bidi_text, localize_digits
from negar_gui.ui.Ui_hwin import Ui_Dialog
from negar_gui.ui.Ui_mwin import Ui_MainWindow
from negar_gui.ui.Ui_uwin import Ui_uwWindow


_translate = QCoreApplication.translate
if getattr(sys, "frozen", False):
    NEGARGUIPATH = Path(sys._MEIPASS).as_posix()
else:
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
        # before any showMaximized(): its showEvent already needs the widgets connectSlots() creates
        self.connectSlots()
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

    return wrapper


# In a container "auto" can't see the host theme; `make docker-run` passes it as NEGAR_HOST_THEME.
def _host_aware(setup_theme):
    def wrapper(theme="dark", **kwargs):
        host = os.environ.get("NEGAR_HOST_THEME")
        return setup_theme(host if theme == "auto" and host in ("dark", "light") else theme, **kwargs)

    return wrapper


if hasattr(qdarktheme, "setup_theme"):  # absent in some qdarktheme builds (main() stubs it)
    qdarktheme.setup_theme = _host_aware(qdarktheme.setup_theme)


OCR_CHOICES = (
    ("Persian + English", ["fas", "eng"]),
    ("English", ["eng"]),
    ("Deutsch", ["deu"]),
    ("Persian + English + Deutsch", ["fas", "eng", "deu"]),
)  # fewer languages are more accurate, so no all-in-one default


def _svg_icon(svg):
    pix = QPixmap()
    pix.loadFromData(svg.encode(), "SVG")
    return QIcon(pix)


_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#d89e76" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{}</svg>'
# viewfinder corners with lines of text
_SVG_SCREEN = _SVG.format(
    '<path d="M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M8 9h8M8 12h8M8 15h5"/>'
)
# clipboard holding a picture
_SVG_CLIPBOARD = _SVG.format(
    '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="M8 18l3-4 2 2.5 1.5-2L17 18z"/><circle cx="14.5" cy="10.5" r="1"/>'
)


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
        SETTING_FILE.chmod(0o600)  # it stores LLM API keys

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


# No background/text colours on purpose: qdarktheme (an app stylesheet) supplies them for light and dark.
PROMPT_COMBO_QSS = """
QComboBox {
    border: 1px solid #d89e76; border-radius: 8px; padding: 4px 12px; margin-left: 6px; margin-right: 6px;
    min-height: 24px; font-weight: 600;
}
QComboBox:hover, QComboBox:focus { border: 2px solid #c47d4a; padding: 3px 11px; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
QComboBox QAbstractItemView {
    border: 1px solid #d89e76; border-radius: 6px; outline: 0; padding: 4px;
    selection-background-color: rgba(216, 158, 118, 90);
}
QComboBox QAbstractItemView::item { min-height: 30px; padding: 0 10px; border-radius: 4px; }
"""


class PromptCombo(QComboBox):
    """Combo with a drawn chevron (a stylesheet alone can't draw the arrow without an image file)."""

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QColor("#c47d4a"), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        cx = 20 if rtl else self.width() - 20
        cy = self.height() // 2
        p.drawPolyline([QPoint(cx - 5, cy - 2), QPoint(cx, cy + 3), QPoint(cx + 5, cy - 2)])


class MyWindow(WindowSettings, QMainWindow, Ui_MainWindow):
    @init_decorator
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        for menu in self.menubar.findChildren(QMenu):
            menu.installEventFilter(self)
        self.input_editor.viewport().installEventFilter(self)
        self.output_editor.viewport().installEventFilter(self)
        self._restore_keyboard = None
        self.actionPersian_Keyboard = QtGui.QAction(self, checkable=True, checked=True)
        self.menuSetting.insertAction(self.menuLanguage.menuAction(), self.actionPersian_Keyboard)
        self.menuEdit.addSeparator()  # the OCR group sits below the QR code entry
        self.actionScreen_Reader = self.menuEdit.addAction(_svg_icon(_SVG_SCREEN), "")
        self.actionScreen_Reader.setShortcut(QtGui.QKeySequence("Ctrl+Shift+O"))
        self.actionScreen_Reader.triggered.connect(self.read_screen)
        self.actionClipboard_Reader = self.menuEdit.addAction(_svg_icon(_SVG_CLIPBOARD), "")
        self.actionClipboard_Reader.setShortcut(QtGui.QKeySequence("Ctrl+Alt+O"))
        self.actionClipboard_Reader.triggered.connect(self.read_clipboard_image)
        self.menuOCR = self.menuEdit.addMenu(QIcon(":/images/icons/languages.svg"), "")
        self._ocr_group = QtGui.QActionGroup(self)
        for _, langs in OCR_CHOICES:
            a = self.menuOCR.addAction("")
            a.setCheckable(True)
            a.setData(langs)
            self._ocr_group.addAction(a)
        self._ocr_group.actions()[0].setChecked(True)
        self._ocr_group.triggered.connect(lambda a: self.settings["settings"].__setitem__("ocr-language", a.data()))
        self.input_editor.setStyleSheet("border: 1px solid #d89e76;")
        self.output_editor.setStyleSheet("border: 1px solid #d89e76;")
        self.setWindowIcon(QIcon(LOGO))
        _ai_icon = QIcon(":/images/icons/ai.svg")
        self.llm_btn.setIcon(_ai_icon)
        # self.input_editor.setFocus(True)
        self.input_editor.setFocus(Qt.FocusReason.OtherFocusReason)
        # Translator
        # main language is defined via self.settings["settings"]["language"] by WindowsSettings
        self.trans = QTranslator()
        self.editing_options = []
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
        if negar_nv > negar_ov:
            self._statusBar_tr(
                "MainWindow",
                "New version is available for {}. Use `pip install --upgrade {}` to update",
                0,
                "negar",
                "python-negar",
            )
        if negargui_nv > negargui_ov:
            self._statusBar_tr(
                "MainWindow",
                "New version is available for {}. Use `pip install --upgrade {}` to update",
                0,
                "negar-gui",
                "negar-gui",
            )

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.Type.Wheel
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and obj in (self.input_editor.viewport(), self.output_editor.viewport())
        ):
            self.wheelEvent(event)
            return True
        # keep menus open when toggling checkable items; close via ESC/outside click
        if isinstance(obj, QMenu) and event.type() == QEvent.Type.MouseButtonRelease:
            action = obj.actionAt(event.position().toPoint())
            if action and action.isCheckable() and action.isEnabled():
                action.trigger()
                return True
        return super().eventFilter(obj, event)

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
            lambda: self.font_slider.setValue(self.font_slider.value() + 1),
        )
        self.actionDecrease_Font_Size.triggered.connect(
            lambda: self.font_slider.setValue(self.font_slider.value() - 1),
        )
        # keypad "+" sends Key_Plus, not Key_Equal; Qt falls back to non-keypad matches
        self.actionIncrease_Font_Size.setShortcuts(["Ctrl+=", "Ctrl++"])
        # stylesheet-styled QSlider draws only the handle in RTL; keep it LTR (small→big = left→right)
        self.font_slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
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
        self.prompt_combo = PromptCombo()
        self.prompt_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.prompt_combo.setMinimumContentsLength(26)
        self.prompt_combo.setMinimumWidth(260)
        self.prompt_combo.setView(QListView())  # needed for the popup items to take the stylesheet
        self.prompt_combo.setMaxVisibleItems(14)
        self.prompt_combo.setStyleSheet(PROMPT_COMBO_QSS)
        # OCR buttons go right after the QR button: shift the view, AI and prompt widgets to the right
        self.screen_btn, self.clipboard_btn = QPushButton(parent=self.frame_2), QPushButton(parent=self.frame_2)
        for col, btn, action in (
            (4, self.screen_btn, self.actionScreen_Reader),
            (5, self.clipboard_btn, self.actionClipboard_Reader),
        ):
            btn.setIcon(action.icon())
            btn.clicked.connect(action.trigger)
            self.gridLayout_4.addWidget(btn, 0, col, 1, 1)
        for col, w in enumerate((self.vertical_btn, self.horizontal_btn, self.llm_btn, self.prompt_combo), 6):
            self.gridLayout_4.addWidget(w, 0, col, 1, 1)
        self._retranslate_ocr()
        self.prompt_combo.activated.connect(lambda i: self._set_llm_prompt(self.prompt_combo.itemData(i)))
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
        self.actionPersian_Keyboard.toggled.connect(self._persian_keyboard)

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

    def read_screen(self):
        self._ocr_hidden = True
        self.hide()  # keep Negar out of the screenshot
        QTimer.singleShot(300, self._ocr_run)

    def _ocr_run(self):
        try:
            ocr.capture(self._ocr_done, self._ocr_error)
        except ocr.OCRError as e:
            self._ocr_error(e)

    def _ocr_error(self, e):
        self.show()
        QMessageBox.warning(self, "Negar", str(e))

    def read_clipboard_image(self):
        image = self.clipboard.image()
        if image.isNull():
            statusbar_timeout(self, _translate("MainWindow", "There is no image in the clipboard!"))
        else:
            self._ocr_done(image)

    def _ocr_done(self, image):
        self.show()
        self.activateWindow()
        if image is None:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            text = ocr.read_text(image, self._ocr_group.checkedAction().data())
        except ocr.OCRError as e:
            return self._ocr_error(e)
        finally:
            QApplication.restoreOverrideCursor()
        if text:
            self.input_editor.setPlainText(text)
            self.edit_text()
        else:
            statusbar_timeout(self, _translate("MainWindow", "No text found in the selected region!"))

    def _retranslate_ocr(self):
        self.actionScreen_Reader.setText(_translate("MainWindow", "&Read Text from Screen"))
        self.actionClipboard_Reader.setText(_translate("MainWindow", "Read Text from Clipboard &Image"))
        self.screen_btn.setToolTip(_translate("MainWindow", "Read text from screen Ctrl+Shift+O"))
        self.clipboard_btn.setToolTip(_translate("MainWindow", "Read text from clipboard image Ctrl+Alt+O"))
        self.menuOCR.setTitle(_translate("MainWindow", "OCR &Language"))
        for a, (title, _) in zip(self._ocr_group.actions(), OCR_CHOICES):
            a.setText(_translate("MainWindow", title))

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
        _app = QApplication.instance()
        if self.settings["settings"]["language"] == "Persian":
            self.trans.load("fa", directory=f"{NEGARGUIPATH}/ts")
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.centralwidget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.autoedit_chkbox.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.statusBar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.menubar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            for menu in self.menubar.findChildren(QMenu):
                menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            _app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        elif self.settings["settings"]["language"] == "English":
            self.trans.load("en")
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.centralwidget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.autoedit_chkbox.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.statusBar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self._status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.menubar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            for menu in self.menubar.findChildren(QMenu):
                menu.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            _app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        else:
            return
        _app.installTranslator(self.trans)
        self.retranslateUi(self)
        self.actionPersian_Keyboard.setText(_translate("MainWindow", "Persian Keyboard on Startup"))
        self._retranslate_ocr()
        self._build_llm_menu()
        if not self.llm_btn.isEnabled() and hasattr(self, "_llm_pending_prompt"):
            prompt_name = self.prompt_title(self._llm_pending_prompt)
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
            self.edit_text()

    def _persian_keyboard(self, on):
        if on and not self._restore_keyboard:
            self._restore_keyboard = keyboard_layout.switch_to_persian()
        elif not on and self._restore_keyboard:
            self._restore_keyboard()
            self._restore_keyboard = None

    def changeEvent(self, event):
        # switch on first focus, not on show: per-window layouts (GNOME, Windows) apply to the focused window
        if (
            event.type() == QEvent.Type.ActivationChange
            and self.isActiveWindow()
            and not hasattr(self, "_keyboard_initialized")
        ):
            self._keyboard_initialized = True
            on = self.settings.get("settings", {}).get("persian-keyboard", True)
            self.actionPersian_Keyboard.setChecked(on)
            if on:
                self._persian_keyboard(True)
        super().changeEvent(event)

    def closeEvent(self, event):
        self.__save_settings()
        self._persian_keyboard(False)
        WindowSettings.closeEvent(self, event)
        del event
        # event = QEvent(QEvent.Clipboard)
        # QApplication.sendEvent(QApplication.clipboard(), event)
        pyclipcopy(self.copy_slot())
        # Exit the application when the main window is closed
        QApplication.instance().quit()

    def showEvent(self, event):
        if getattr(self, "_ocr_hidden", False):  # shown again after the screenshot: keep the live settings
            self._ocr_hidden = False
            return QMainWindow.showEvent(self, event)
        WindowSettings.showEvent(self, event)
        del event
        self.font_slider.blockSignals(True)  # no zoom popup while restoring settings
        self.__load_settings()
        self._build_llm_menu()  # user prompts / selection come from the loaded settings
        self.font_slider.blockSignals(False)
        self._set_font_size(popup=False)
        # __load_settings rebuilds the grid (setParent(None)), which drops the focus set in __init__
        QTimer.singleShot(0, lambda: self.input_editor.setFocus(Qt.FocusReason.OtherFocusReason))

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
            for a in self._ocr_group.actions():
                a.setChecked(a.data() == self.settings["settings"].get("ocr-language", ["fas", "eng"]))
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
                "ocr-language": self._ocr_group.checkedAction().data(),
                "persian-keyboard": self.actionPersian_Keyboard.isChecked(),
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
            # smooth wheels/touchpads send <120 per event; keep the remainder instead of dropping it
            self._wheel_acc = getattr(self, "_wheel_acc", 0) + event.angleDelta().y()
            notches = int(self._wheel_acc / 120)
            self._wheel_acc -= notches * 120
            if notches:
                self.font_slider.setValue(self.font_slider.value() + notches)

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
        self.edit_text()

    def _set_font_size(self, _value=None, popup=True):
        if not popup:
            self._apply_font_size()
            return
        # relayout of big texts is slow; show the popup now, resize once the wheel/keys pause
        if not hasattr(self, "_font_timer"):
            self._font_timer = QTimer(self, singleShot=True, interval=60)
            self._font_timer.timeout.connect(self._apply_font_size)
        self._font_timer.start()
        self._show_zoom_popup(self.font_slider.value())

    def _apply_font_size(self):
        # widget font = document default font, so all existing and future text follows it
        size = self.font_slider.value()
        for editor in (self.input_editor, self.output_editor):
            font = editor.font()
            font.setPointSize(size)
            editor.setFont(font)

    def _show_zoom_popup(self, size):
        if not hasattr(self, "_zoom_popup"):
            self._zoom_popup = QLabel(self)
            self._zoom_popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._zoom_popup.setStyleSheet(
                "QLabel { background: rgba(40, 32, 28, 225); color: #f6e7dc;"
                " border: 1px solid #d89e76; border-radius: 10px;"
                " padding: 8px 16px; font-size: 13pt; }"
            )
            self._zoom_timer = QTimer(self, singleShot=True, interval=1200)
            self._zoom_timer.timeout.connect(self._zoom_popup.hide)
        default = 20  # slider default in ui/mwin.ui
        self._zoom_popup.setText(
            f"<b>{size}</b> pt&nbsp;&nbsp;<span style='color:#d89e76'>{round(size * 100 / default)}%</span>"
        )
        self._zoom_popup.adjustSize()
        top = self.input_editor.mapTo(self, QPoint(0, 0)).y() + 24  # over the editors, not the toolbar
        self._zoom_popup.move((self.width() - self._zoom_popup.width()) // 2, top)
        self._zoom_popup.raise_()
        self._zoom_popup.show()
        self._zoom_timer.start()

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
        current = self._llm_prompt_key()
        for key, prompt in self._llm_prompts().items():
            action = QtGui.QAction(self.prompt_title(prompt), self)
            action.setCheckable(True)
            action.setChecked(key == current)
            action.triggered.connect(lambda checked, k=key: self._set_llm_prompt(k))
            self.menuLLM.addAction(action)
            self._llm_prompt_actions[key] = action
        self.prompt_combo.clear()
        for key, prompt in self._llm_prompts().items():
            self.prompt_combo.addItem(self.prompt_title(prompt), key)
            self.prompt_combo.setItemData(
                self.prompt_combo.count() - 1, self.prompt_title(prompt), Qt.ItemDataRole.ToolTipRole
            )
        self.prompt_combo.setCurrentIndex(self.prompt_combo.findData(current))
        self.prompt_combo.setToolTip(_translate("MainWindow", "Prompt used by the AI button"))
        self.menuLLM.addSeparator()
        self.menuLLM.addAction(_translate("MainWindow", "Manage Prompts..."), self._manage_prompts)
        self.menuLLM.addAction(_translate("MainWindow", "AI Provider..."), self._llm_provider_dialog)
        self.menuLLM.addAction(_translate("MainWindow", "Usage Report..."), lambda: UsageReportDialog(self).exec())
        self._update_llm_tooltip()

    def _update_llm_tooltip(self):
        provider = self._llm_settings().get("provider", llm_providers.DEFAULT_PROVIDER)
        today, total = usage_log.counts(provider)
        name = llm_providers.PROVIDERS.get(provider, {}).get("name", provider).split(" (")[0]
        self.llm_btn.setToolTip(
            bidi_text(
                self,
                _translate("MainWindow", "{}: {} requests today, {} in total").format(
                    f"\u2068{name}\u2069",  # isolate the Latin name so it can't reorder the Persian around it
                    localize_digits(self, today),
                    localize_digits(self, total),
                ),
            )
        )

    def _llm_settings(self):
        llm = self.settings.setdefault("llm", {"provider": llm_providers.DEFAULT_PROVIDER})
        if not llm.get("seeded"):  # one-time: built-in prompts become ordinary, editable ones
            have = {p["name"] for p in llm.get("prompts", [])}
            llm["prompts"] = [p for p in llm_providers.DEFAULT_USER_PROMPTS if p["name"] not in have] + llm.get(
                "prompts", []
            )
            llm["seeded"] = True
        return llm

    def _llm_provider_dialog(self):
        accepted = LLMProviderDialog(self, self._llm_settings()).exec() == QDialog.DialogCode.Accepted
        self._update_llm_tooltip()
        return accepted

    def prompt_title(self, prompt):
        """Persian name in Persian mode (when set), else the English name."""
        if self.settings.get("settings", {}).get("language") == "Persian" and prompt.get("name_fa"):
            return prompt["name_fa"]
        return prompt["name"]

    def _llm_prompts(self):
        return llm_providers.all_prompts(self._llm_settings().setdefault("prompts", []))

    def _llm_prompt_key(self):
        key = self._llm_settings().get("prompt")
        prompts = self._llm_prompts()
        return key if key in prompts else next(iter(prompts), None)

    def _manage_prompts(self):
        PromptsDialog(self, self._llm_settings().setdefault("prompts", [])).exec()
        self._build_llm_menu()

    def _set_llm_prompt(self, key):
        self._llm_settings()["prompt"] = key
        self.prompt_combo.setCurrentIndex(self.prompt_combo.findData(key))
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
        if not self._llm_prompts():  # user deleted every prompt
            return self._manage_prompts()
        llm = self._llm_settings()
        provider = llm.get("provider", llm_providers.DEFAULT_PROVIDER)
        if provider not in llm_providers.PROVIDERS:
            provider = llm["provider"] = llm_providers.DEFAULT_PROVIDER
        needs_key = llm_providers.PROVIDERS[provider]["key_url"]
        if needs_key and not llm.get("keys", {}).get(provider):
            if not self._llm_provider_dialog():
                return
            return self.llm_fix_text_slot()
        self.llm_btn.setEnabled(False)
        self._llm_spin_timer.start()
        self._llm_retries = 2
        self._llm_pending_text = text
        self._llm_pending_prompt = self._llm_prompts()[self._llm_prompt_key()]
        self._statusBar_tr("MainWindow", "Running {}...", 0, self.prompt_title(self._llm_pending_prompt))
        self.statusBar.repaint()
        self._llm_send()

    def _llm_send(self):
        llm = self._llm_settings()
        provider = llm["provider"]
        self._llm_model = llm.get("models", {}).get(provider) or llm_providers.PROVIDERS[provider]["model"]
        self._llm_provider_name = llm_providers.PROVIDERS[provider]["name"].split(" (")[0]  # drop "(free key)"
        url, headers, payload = llm_providers.build_request(
            self._llm_pending_text,
            self._llm_pending_prompt,
            provider,
            llm.get("keys", {}).get(provider, ""),
            llm.get("models", {}).get(provider, ""),
        )
        req = QNetworkRequest(QUrl(url))
        for name, value in headers.items():
            req.setRawHeader(name.encode(), value.encode())

        self._llm_reply = self._llm_nam.post(req, QByteArray(json.dumps(payload).encode()))
        self._llm_reply.finished.connect(self._on_llm_reply)

    def _on_llm_reply(self):
        self._llm_reply.finished.disconnect()
        data = self._llm_reply.readAll().data().decode()
        status = self._llm_reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)

        ok = False
        retry = True
        if status in (401, 403):
            retry = False
            err = _translate("MainWindow", "{} rejected the API key. Check it in AI → AI Provider...").format(
                self._llm_provider_name
            )
        elif status in (402, 429):
            retry = False  # retrying a rate limit just burns the next free slot
            err = _translate(
                "MainWindow", "{} limit reached. Wait a bit, or pick another provider in AI → AI Provider..."
            ).format(self._llm_provider_name)
        elif status and status != 200:
            err = f"HTTP {status}: {data[:200]}"
        else:
            try:
                result = llm_providers.parse_reply(json.loads(data))
                ok = True
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
                err = f"LLM response parse failed: {e}"

        usage_log.log_request(
            self._llm_settings()["provider"], self._llm_model, self._llm_pending_prompt["name"], status, ok
        )
        self._update_llm_tooltip()
        if ok:
            self._llm_spin_stop()
            self.output_editor.setPlainText(result)
            self.cleaned_text = result
            self.llm_btn.setEnabled(True)
            self._statusBar_tr("MainWindow", "Grammar fix complete.")
            self._llm_reply.deleteLater()
            return

        if retry and self._llm_retries > 0:
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
    app.setApplicationName("negar")  # X11 WM_CLASS
    app.setApplicationDisplayName("Negar")
    app.setDesktopFileName("negar")  # Wayland app_id -> negar.desktop
    qdarktheme.setup_theme("dark")
    MAIN_WINDOW = MyWindow()
    MAIN_WINDOW.show()
    # sys.exit(app.exec_())
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
