#!/usr/bin/env python

import re
import sys
import asyncio
import requests
from threading import Thread
from pathlib import Path
import tempfile
from pyuca import Collator
from pyperclip import copy as pyclipcopy
from qrcode import QRCode, ERROR_CORRECT_L
from PyQt5.QtCore import QTranslator, QUrl, Qt, QAbstractTableModel, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QHeaderView, QDialog
from PyQt5.QtGui import QDesktopServices, QIcon, QColor, QPixmap
import qdarktheme

sys.path.append(Path(__file__).parent.parent.as_posix()) # https://stackoverflow.com/questions/16981921
from negar.virastar import PersianEditor, UnTouchable
from negar.constants import INFO, __version__ as negar__version
from negar_gui.constants import __version__, LOGO
from negar_gui.Ui_mwin import Ui_MainWindow
from negar_gui.Ui_uwin import Ui_uwWindow
from negar_gui.Ui_hwin import Ui_Dialog

# ########################################################################
# # IMPORT Custom widgets
# from Custom_Widgets.Widgets import *
# # INITIALIZE APP SETTINGS
# settings = QSettings()
# ########################################################################

NEGARGUIPATH = Path(__file__).parent.as_posix()

collator = Collator()

def init_decorator(func):
    def wrapper(*args, **kwargs):
        func(*args, **kwargs)
        self, parent = args[0], kwargs.pop('parent', None)
        # it adjusts Frame Size maximized if its height or width would be bigger than its counterpart on the real screen
        screen = QApplication.desktop().screenGeometry()
        h, w = screen.height(), screen.width()
        if self.width() > w or self.height() > h:
            self.showMaximized()
        # set layout direction automatically
        if parent:
            try:
                self.centralwidget.setLayoutDirection(parent.layoutDirection())
            except: # QDialog  has no centralwidget
                pass
        # connect widgets to their proper slot
        self.connectSlots()
    return wrapper

def checkScreenSize(window):
    """it adjusts Frame Size maximized
    if its height or width would be bigger than its counterpart on the real screen"""
    screen = QApplication.desktop().screenGeometry()
    h, w = screen.height(), screen.width()
    if window.width() > w or window.height() > h:
        window.showMaximized()

class TableModel(QAbstractTableModel):
    def __init__(self, data):
        super(TableModel, self).__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.BackgroundRole:
            if index.row()%2:
                return QColor('gray')
        if role == Qt.ItemDataRole.ForegroundRole:
            if index.row()%2:
                return QColor('white')
        if role == Qt.ItemDataRole.DisplayRole:
            try:
                return self._data[index.row()][index.column()]
            except:
                return ''

    def rowCount(self, index):
        # The length of the outer list.
        return len(self._data)

    def columnCount(self, index):
        # The following takes the first sub-list, and returns
        # the length (only works if all rows are an equal length)
        return len(self._data[0])

    def headerData(self, section, orientation, role):
        # section is the index of the column/row.
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return ''
            if orientation == Qt.Orientation.Vertical:
                return str(section+1)

class UntouchWindow(QMainWindow, Ui_uwWindow):
    @init_decorator
    def __init__(self, parent=None):
        self.parent = parent
        super(UntouchWindow, self).__init__(parent)
        self.setupUi(self)
        self.setup_table()
        # if parent: self.centralwidget.setLayoutDirection(parent.layoutDirection())

    def setup_table(self, col=8):
        self.untouch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        data = sorted(list(UnTouchable().get()), key=collator.sort_key)
        data = [data[i*col:(i+1)*col] for i in range(int(len(data)//col)+1)]
        model = TableModel(data)
        self.untouch_table.setModel(model)

    def connectSlots(self):
        self.untouch_word.textChanged.connect(self.untouch_add_enabler)
        self.untouch_button.clicked.connect(self.untouch_add)

    def untouch_add_enabler(self):
        """Checks untouchable word text input to enable the `Add` button if just one word is typed."""
        word_list = self.untouch_word.text().split()
        self.untouch_button.setEnabled(len(word_list) == 1)

    def untouch_add(self):
        """Adds a new word into untouchable words"""
        word = [self.untouch_word.text().strip()]
        UnTouchable.add(word)
        self.untouch_word.clear()
        self.setup_table() # updates untouchable list

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
        if self.parent:
            self.parent.show()
            self.parent.edit_text()

class HelpWindow(QDialog, Ui_Dialog):
    @init_decorator
    def __init__(self, parent=None, title=None, label=None):
        self.parent = parent
        super(HelpWindow, self).__init__(parent)
        self.setupUi(self)
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


class MyWindow(QMainWindow, Ui_MainWindow):
    @init_decorator
    def __init__(self, parent=None):
        super(MyWindow, self).__init__(parent)
        self.setupUi(self)
        self.input_editor.setStyleSheet("border: 1px solid #d89e76;")
        self.output_editor.setStyleSheet("border: 1px solid #d89e76;")
        self.setWindowIcon(QIcon(LOGO))
        self.input_editor.setFocus(True)
        #  Translator
        self.trans = QTranslator()
        # destination language
        self.dest = "en"
        # ui language : 0->en, 1->fa
        self.lang = 'English'
        self.editing_options = []
        self.clipboard = QApplication.clipboard()
        self.fileDialog = QFileDialog()
        self._statusBar()
        # Checks for new release
        Thread(target=lambda: asyncio.run(self.updateCheck()), daemon=True).start()

    async def updateCheck(self):
        nurl  = 'https://raw.github.com/shahinism/python-negar/master/negar/constants.py'
        ngurl = 'https://raw.github.com/javadr/negar-gui/master/negar_gui/constants.py'
        async def get(link):
            with requests.get(link) as response:
                return re.search(r'(__version__ = "(\d\.\d(\.\d+)?)")', response.text, re.M).group(2)
        try:
            requests.get('https://github.com') # check the internet connection
            negar_t = asyncio.create_task(get(nurl))
            negargui_t = asyncio.create_task(get(ngurl))
            negar_v = await negar_t
            negargui_v = await negargui_t
        except:
            negar_v, negargui_v = '0.0', '0.0'
        version = lambda v: list(map(int,v.split('.')))
        negar_nv, negargui_nv = [version(i) for i in (negar_v, negargui_v)]
        negar_ov, negargui_ov = [version(i) for i in (negar__version, __version__)]
        notification = ''
        message = 'New version is available for {}. Use `pip install --upgrade {}` to update'
        if negar_nv>negar_ov:
            notification = message.format('negar', 'python-negar')
        if negargui_nv>negargui_ov:
            notification = message.format('negar-gui', 'negar-gui')
        self._statusBar(f"{notification}" if notification!=message else '')

    def connectSlots(self):
        self.autoedit_handler()
        # connect to slots
        self.autoedit_chkbox.stateChanged.connect(self.autoedit_handler)
        self.edit_btn.clicked.connect(self.edit_text)
        self.actionOpen.triggered.connect(self.openFileSlot)
        self.actionSave.triggered.connect(self.saveFileSlot)
        self.actionExport.triggered.connect(self.exportFileSlot)
        self.actionExit.triggered.connect(self.close)
        self.font_slider.valueChanged.connect(self._set_font_size)
        self.actionIncrease_Font_Size.triggered.connect(
            lambda: (self.font_slider.setValue(self.font_slider.value()+1), self._set_font_size())
        )
        self.actionDecrease_Font_Size.triggered.connect(
            lambda: (self.font_slider.setValue(self.font_slider.value()-1), self._set_font_size())
        )
        self.actionPersian.triggered.connect(lambda: self.changeLanguage('Persian'))
        self.actionEnglish.triggered.connect(lambda: self.changeLanguage('English'))

        self.actionNegar_Help.triggered.connect(lambda: self.input_editor.setText(INFO) )
        self.actionAbout_Negar.setShortcut("CTRL+H")
        self.actionAbout_Negar.triggered.connect(
            lambda: (HelpWindow(parent=self, title='About Negar', label=self.edit_text(INFO)).show())
        )
        self.actionAbout_Negar_GUI.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/javadr/negar-gui"))
        )
        self.actionDonate.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/javadr/negar-gui#donation"))
        )
        self.actionReport_Bugs.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/javadr/negar-gui/issues"))
        )
        self.actionFix_Dashes.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_three_dots.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_English_quotes.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_hamzeh.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionUse_Persian_yeh_to_show_hamzeh.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_spacing_braces_and_quotes.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_Arabic_numbers.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_English_numbers.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_non_Persian_chars.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_prefix_spacing.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_prefix_separating.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_suffix_spacing.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_suffix_separating.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionFix_aggressive_punctuation.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionCleanup_kashidas.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionCleanup_extra_marks.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionCleanup_spacing.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionTrim_Leading_Trailing_Whitespaces.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))
        self.actionExaggerating_ZWNJ.triggered.connect(lambda: (self.option_control(), self.autoedit_handler()))

        self.actionUntouchable_Words.triggered.connect(lambda: (UntouchWindow(parent=self).show(), MainWindow.hide()))
        self.actionCopy.triggered.connect(self.copySlot)
        self.copy_btn.clicked.connect(self.copySlot)

        self.actionInteractive_Clipboard.triggered.connect(lambda:
            self.clipboard.dataChanged.connect(self.onClipboardChanged) if self.actionInteractive_Clipboard.isChecked()
            else self.clipboard.dataChanged.disconnect(self.onClipboardChanged))
        self.actionQr_Code.triggered.connect(self.qrcode)

        # Change GridLayout Orientation
        def grid_layout(layout='h'):
            if layout=='v':
                self.gridLayout.setHorizontalSpacing(5)
            elif layout == 'h':
                self.gridLayout.setVerticalSpacing(0)
            widgets = (self.input_editor_label, self.input_editor,
                        self.output_editor_label, self.output_editor)
            for widget in widgets:
                self.gridLayout.removeWidget(widget)
                widget.setParent(None)
            elements = (
                (0, 0, 1, 1),  # Position: 0x0 1 rowspan 1 colspan
                (1, 0, 1, 1),  # Position: 1x0 1 rowspan 1 colspan
                (0, 1, 1, 1),  # Position: 0x1 1 rowspan 1 colspan
                (1, 1, 1, 1),  # Position: 1x1 1 rowspan 1 colspan
            ) if layout=='v' else (
                (0, 0, 1, 2),  # Position: 0x0 1 rowspan 2 colspan
                (1, 0, 1, 2),  # Position: 1x0 1 rowspan 2 colspan
                (2, 0, 1, 2),  # Position: 2x0 1 rowspan 2 colspan
                (3, 0, 1, 2),  # Position: 3x0 1 rowspan 2 colspan
            )
            for i, widget in enumerate(widgets):
                self.gridLayout.addWidget(widget, *elements[i])

        self.vertical_btn.clicked.connect(lambda: (self.actionSide_by_Side_View.setChecked(True), grid_layout('v')) )
        self.horizontal_btn.clicked.connect(lambda: (self.actionSide_by_Side_View.setChecked(False), grid_layout('h')) )
        self.actionSide_by_Side_View.triggered.connect(lambda:
            grid_layout('v') if self.actionSide_by_Side_View.isChecked() else grid_layout('h'))

        def grid_full_input():
            widgets = (self.output_editor_label, self.output_editor)
            for widget in widgets:
                self.gridLayout.removeWidget(widget)
                widget.setParent(None)
        self.actionFull_Screen_Input.triggered.connect(lambda: (
            grid_full_input() if self.actionFull_Screen_Input.isChecked() else
                grid_layout('v') if self.actionSide_by_Side_View.isChecked() else grid_layout('h') )
        )

        self.action_dark.triggered.connect(lambda:
            qdarktheme.setup_theme("dark",
            custom_colors={
                "[dark]": {
                    "primary": "#D0BCFF",
                    "primary>button.hoverBackground": "#ffffff",
                }
            },) )
        self.action_Light.triggered.connect(lambda: qdarktheme.setup_theme("light") )
        self.action_Auto.triggered.connect(lambda: qdarktheme.setup_theme("auto") )

    def qrcode(self):
        if len(self.output_editor.toPlainText().strip())==0:
            if self.lang == 'Persian':
                statusBar_Timeout(self, 'هیچ متنی برای نمایش از طریق کد QR وجود ندارد!')
            else: # English
                statusBar_Timeout(self, 'There is no text to be fed to the QR Code!')
            return
        qr = QRCode(
            version = 1,
            error_correction = ERROR_CORRECT_L,
            box_size = 10,
            border = 4
        )
        qr.add_data(self.output_editor.toPlainText())
        qr.make(fit = True)
        img = qr.make_image()
        temp_path = Path(tempfile.gettempdir())
        img.save(temp_path/'negar-gui_qrcode.png')
        pixmap = QPixmap(f"{(temp_path/'negar-gui_qrcode.png').absolute()}")
        screen = QApplication.desktop().screenGeometry()
        w = min(screen.height(), screen.width())
        if w-90 < img.size[0]:
            pixmap = pixmap.scaled(w-90, w-90, Qt.KeepAspectRatio)
        HelpWindow(parent=self, title='QR Code', label=pixmap).show()
        (Path(temp_path)/'negar-gui_qrcode.png').unlink()

    def _statusBar(self, notification='', timeout=0):
        self.statusBar.showMessage(f'Negar v{negar__version} [[Negar-GUI v{__version__}]] {notification}', timeout)

    def openFileSlot(self):
        filename, _ = self.fileDialog.getOpenFileName(self, "Open File - A Plain Text", ".")
        if filename:
            with open(filename, encoding="utf-8") as f:
                try:
                    self.input_editor.setPlainText(str(f.read()))
                    self.filename = Path(filename)
                    MainWindow.setWindowTitle(f"Negar - {self.filename.name}")
                    statusBar_Timeout(self,'File Opened.')
                except Exception as e:
                    self.input_editor.setPlainText(e.args[1])

    def saveFileSlot(self):
        if not self.output_editor.toPlainText():
            return
        if hasattr(self, 'filename') and self.filename:
            with open(self.filename, "w", encoding="utf-8") as f:
                try:
                    f.write(self.output_editor.toPlainText())
                    statusBar_Timeout(self,'File Saved.')
                except Exception as e:
                    self.output_editor.setPlainText(e.args[1])
        else:
            self.exportFileSlot()

    def exportFileSlot(self):
        if not self.output_editor.toPlainText():
            return
        filename, _ = self.fileDialog.getSaveFileName(self, "Save File", ".")
        if filename:
            with open(filename, "w", encoding="utf-8") as f:
                try:
                    f.write(self.output_editor.toPlainText())
                    self.filename = Path(filename)
                    MainWindow.setWindowTitle(f"Negar - {self.filename.name}")
                    statusBar_Timeout(self,'File Saved.')
                except Exception as e:
                    self.output_editor.setPlainText(e.args[1])

    def changeLanguage(self, lang):
        """
        change ui language
        """
        if lang=='Persian' and self.lang!='Persian':
            self.lang = 'Persian'
            self.trans.load("fa", directory=f"{NEGARGUIPATH}/ts")
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.centralwidget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.autoedit_chkbox.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.statusBar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        elif lang=='English' and self.lang!='English':
            self.lang = 'English'
            self.trans.load("en")
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.centralwidget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.autoedit_chkbox.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            return
        _app = QApplication.instance()
        _app.installTranslator(self.trans)
        self.retranslateUi(self)

    # def retranslateUi(self, MyWindow):
        # super(MyWindow, self).retranslateUi()
        # _translate = QtCore.QCoreApplication.translate
        # print(dir(self))
        # MyWindow.fileDialog.setText(_translate(self.fileDialog.name(), "Open File - A Plain Text"))
        # pass

    def copySlot(self):
        s = self.output_editor.toPlainText()
        if s:
            QApplication.clipboard().setText(s)
        return s

    def onClipboardChanged(self):
        text = self.clipboard.text()
        if text:
            self.input_editor.setPlainText(text)
            self._set_font_size()

    def closeEvent(self, event):
        # event = QEvent(QEvent.Clipboard)
        # QApplication.sendEvent(QApplication.clipboard(), event)
        pyclipcopy(self.copySlot())

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

    def wheelEvent(self, event):
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.ControlModifier:
            delta_notches = int(event.angleDelta().y() / 120)
            self.font_slider.setValue(self.font_slider.value()+delta_notches),
            self._set_font_size()

    def autoedit_handler(self):
        """Edits the input text automatically if `autoedit` is checked."""
        if self.autoedit_chkbox.isChecked():
            self.edit_btn.setEnabled(False)
            self.input_editor.textChanged.connect(self.edit_text)
        else:
            self.edit_btn.setEnabled(True)
            # This line will disconnect autoedit signal and will disable autoamtic edit option
            self.input_editor.textChanged.disconnect(self.edit_text)
        self._set_font_size()

    def _set_font_size(self,):
        size = self.font_slider.value()
        self.input_editor.setFontPointSize(size)
        self.output_editor.setFontPointSize(size)
        lines = self.input_editor.toPlainText()
        self.input_editor.clear()
        self.input_editor.append(lines)
        self.edit_text()

    def option_control(self):
        self.editing_options = []
        """Enable/Disable Editing features"""
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
        if not text:
            self.output_editor.clear()
            run_PE = PersianEditor(self.input_editor.toPlainText(), *self.editing_options)
            self.output_editor.append(run_PE.cleanup())
        else:
            return PersianEditor(text, *self.editing_options).cleanup()


def statusBar_Timeout(self, notification, timeout=5000): # Timeout in milliseconds
    self.statusBar.showMessage(notification, timeout)
    timer = QTimer()
    timer.setSingleShot( True )
    timer.timeout.connect( self.statusBar.clearMessage )
    timer.start(timeout)

def main():
    global MainWindow
    qdarktheme.enable_hi_dpi()
    app = QApplication(sys.argv)
    qdarktheme.setup_theme("dark")
    MainWindow = MyWindow()
    MainWindow.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
