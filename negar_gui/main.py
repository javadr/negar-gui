#!/usr/bin/env python
# @Date    : 2022-04-28
# @Author  : Javad Razavian
# @Link    : https://github.com/javadr/negar-gui
# @Version : Python3.6

import re
import sys
from pyuca import Collator
from pathlib import Path

from Ui_mwin import Ui_MainWindow

from PyQt5.QtCore import QTranslator, QUrl, QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QApplication, QMainWindow, QFileDialog, QMessageBox
from PyQt5.QtGui import QDesktopServices, QPixmap

sys.path.append(Path(__file__).parent.parent.as_posix()) # https://stackoverflow.com/questions/16981921
from negar.virastar import PersianEditor, UnTouchable
from negar.constants import INFO
from negar_gui.constants import __version__, LOGO

GTransData = ""


class MyWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MyWindow, self).__init__(parent)
        self.setupUi(self)
        try:
            with open("style.qss") as f:
                style = f.read()  # 读取样式表
                self.setStyleSheet(style)
        except:
            print("open stylesheet error")
        self.input_editor.setFocus(True)
        # destination language
        self.dest = "en"
        # ui language : 0->en, 1->fa
        self.lan = 0
        self.editing_options = []
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.onClipboradChanged)
        self.connectSlots()

    def connectSlots(self):
        self.autoedit_handler()
        # connect to slots
        self.autoedit_chkbox.stateChanged.connect(self.autoedit_handler)
        self.edit_btn.clicked.connect(self.edit_text)
        self.actionOpen.triggered.connect(self.openFileSlot)
        self.actionExport.triggered.connect(self.exportFileSlot)
        self.actionExit.triggered.connect(self.close)

        # self.actionChinese.triggered.connect(lambda: self.changeLanguage(0))
        # self.actionEnglish.triggered.connect(lambda: self.changeLanguage(1))

        self.actionNegar_Help.setShortcut("F1")
        self.actionNegar_Help.triggered.connect(lambda: self.input_editor.setText(INFO) )
        self.actionAbout.setShortcut("CTRL+H")
        self.actionAbout.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/javadr/python-negar"))
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


    def openFileSlot(self):
        filename, filetype = QFileDialog.getOpenFileName(self, "'Open File - A Plain Text'", ".")
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
        filename, filetype = QFileDialog.getSaveFileName(self, "Save File", ".", "*.txt;;*")
        if filename:
            with open(filename, "w", encoding="utf-8") as f:
                try:
                    f.write(self.output_editor.toPlainText())
                except Exception as e:
                    self.output_editor.setPlainText(e.args[1])

    def changeLanguage(self, lan):
        """:param lan: 0=>English, 1=>Persian
        change ui language
        """
        if lan==0 and self.lan!=0:
            print("[MainWindow] Change to English")
            self.trans.load("en")
        elif lan==1 and self.lan!=1:
            print("[MainWindow] Change to Persian")
            self.trans.load("fa")
        else:
            return
        _app = QApplication.instance()
        _app.installTranslator(self.trans)
        self.retranslateUi(self)

    def transTextToEnglish(self):
        text = self.originText.toPlainText()
        self.originText.setPlainText(text)
        try:
            # self.transText.setPlainText(trans_To_zh_CN(text))
            # self.t = GTranslator(self.dest, text)
            # self.t.start()
            # self.transText.setPlainText("")
            # self.transText.setPlaceholderText("...")
            # self.t.trigger.connect(self.translated)
            pass
        except Exception as e:
            print(e.args[1])
            self.output_editor.setPlainText("error!")

    def copySlot(self):
        s = self.output_editor.toPlainText()
        if s:
            self.isCopyFromTrans = True
            clipboard = QApplication.clipboard()
            clipboard.setText(s)

    def onClipboradChanged(self):
        text = QApplication.clipboard().text()
        if text:
            self.input_editor.setPlainText(str(text))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            sanitizedText = self.output_editor.toPlainText()
            if sanitizedText:
                self.destroyed.connect(lambda: QApplication.clipboard().setText(sanitizedText) )
            self.close()
        else:
            super().keyPressEvent(event)

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

class GTranslator(QThread):
    trigger = pyqtSignal()

    def __init__(self, dest, content):
        super().__init__()
        self.content = content
        self.dest = dest

    def run(self):
        Data = []
        global GTransData
        T = Translator(service_urls=["translate.google.cn"])
        # ts = T.translate(['The quick brown fox', 'jumps over', 'the lazy dog'], dest='zh-CN')
        try:
            ts = T.translate(self.content, dest=self.dest)
            if isinstance(ts.text, list):
                for i in ts:
                    Data.append(i.text)
                GTransData = Data
            else:
                GTransData = ts.text
        except:
            GTransData = "An error happended. Please retry..."
        self.trigger.emit()  # emit signal once translatation is finfished


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MyWindow()
    w.show()
    # clipboard = QApplication.clipboard()
    # clipboard.dataChanged.connect(w.onClipboradChanged)
    sys.exit(app.exec_())
