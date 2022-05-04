#!/usr/bin/env python
# @Date    : 2022-04-28
# @Author  : Javad Razavian
# @Link    : https://github.com/javadr/negar-gui
# @Version : Python3.6

import re
import sys
from pathlib import Path
from pyuca import Collator

from PyQt5.QtCore import QTranslator, QUrl, QThread, pyqtSignal, Qt, QAbstractTableModel, QSize
from PyQt5.QtWidgets import QWidget, QApplication, QMainWindow, QFileDialog, QMessageBox, QHeaderView
from PyQt5.QtGui import QDesktopServices, QIcon, QColor

sys.path.append(Path(__file__).parent.parent.as_posix()) # https://stackoverflow.com/questions/16981921
from negar.virastar import PersianEditor, UnTouchable
from negar.constants import INFO
from negar_gui.constants import __version__, LOGO
from negar_gui.Ui_mwin import Ui_MainWindow
from negar_gui.Ui_uwin import Ui_uwWindow

NEGARGUIPATH = Path(__file__).parent.as_posix()

collator = Collator()

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
    def __init__(self, parent=None):
        self.parent = parent
        super(UntouchWindow, self).__init__(parent)
        self.setupUi(self)
        if parent: self.centralwidget.setLayoutDirection(parent.layoutDirection())
        self.setup_table()
        self.connectSlots()

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
        if len(word_list) == 1:
            self.untouch_button.setEnabled(True)
        else:
            self.untouch_button.setEnabled(False)

    def untouch_add(self):
        """Adds a new word into untouchable words"""
        word = [self.untouch_word.text()]
        UnTouchable.add(word)
        self.untouch_word.clear()
        #self.edit_text()  # retouches the input text
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
        if self.parent: self.parent.show()


class MyWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MyWindow, self).__init__(parent)
        self.setupUi(self)
        try:
            with open(f"{NEGARGUIPATH}/style.qss") as style:
                self.setStyleSheet(style.read())
        except:
            print("open stylesheet error")
        self.setWindowIcon(QIcon(LOGO))
        self.input_editor.setFocus(True)
        #  Translator
        self.trans = QTranslator()
        # destination language
        self.dest = "en"
        # ui language : 0->en, 1->fa
        self.lan = 'English'
        self.editing_options = []
        self.clipboard = QApplication.clipboard()
        self.fileDialog = QFileDialog()
        self.connectSlots()

    def connectSlots(self):
        self.autoedit_handler()
        # connect to slots
        self.clipboard.dataChanged.connect(self.onClipboradChanged)
        self.autoedit_chkbox.stateChanged.connect(self.autoedit_handler)
        self.edit_btn.clicked.connect(self.edit_text)
        self.actionOpen.triggered.connect(self.openFileSlot)
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

        self.actionNegar_Help.setShortcut("F1")
        self.actionNegar_Help.triggered.connect(lambda: self.input_editor.setText(INFO) )
        self.actionAbout.setShortcut("CTRL+H")
        self.actionAbout.triggered.connect(
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

        self.actionUntouchable_Words.triggered.connect(lambda: (UntouchWindow(self).show(), MainWindow.hide()))

    def openFileSlot(self):
        filename, filetype = self.fileDialog.getOpenFileName(self, "Open File - A Plain Text", ".")
        if filename:
            print(filename)
            with open(filename, encoding="utf-8") as f:
                try:
                    self.input_editor.setPlainText(str(f.read()))
                except Exception as e:
                    self.input_editor.setPlainText(e.args[1])

    def exportFileSlot(self):
        if not self.output_editor.toPlainText():
            return
        filename, filetype = self.fileDialog.getSaveFileName(self, "Save File", ".", "*.txt;;*")
        if filename:
            with open(filename, "w", encoding="utf-8") as f:
                try:
                    f.write(self.output_editor.toPlainText())
                except Exception as e:
                    self.output_editor.setPlainText(e.args[1])

    def changeLanguage(self, lan):
        """
        change ui language
        """
        if lan=='Persian' and self.lan!='Persian':
            self.lan = 'Persian'
            self.trans.load("fa", directory=f"{NEGARGUIPATH}/ts")
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.centralwidget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        elif lan=='English' and self.lan!='English':
            self.lan = 'English'
            self.trans.load("en")
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.centralwidget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
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

    def onClipboradChanged(self):
        text = self.clipboard.text()
        if text:
            self.input_editor.setPlainText(text)
            self._set_font_size()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            sanitizedText = self.output_editor.toPlainText()
            if sanitizedText:
                self.destroyed.connect(lambda: QApplication.clipboard().setText(sanitizedText) )
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

    def edit_text(self):
        self.output_editor.clear()
        run_PE = PersianEditor(self.input_editor.toPlainText(), *self.editing_options)
        self.output_editor.append(run_PE.cleanup())

def main():
    app = QApplication(sys.argv)
    global MainWindow
    MainWindow = MyWindow()
    MainWindow.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
