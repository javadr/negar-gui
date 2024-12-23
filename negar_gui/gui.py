#!/usr/bin/env python

import sys
from pathlib import Path
from pyuca import Collator
from pyperclip import copy
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtCore import Qt, QAbstractTableModel, QSize
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QTableView, QHeaderView, QCheckBox,
                            QSlider, QLabel, QTextEdit, QLineEdit, QGroupBox, QGridLayout, QTabWidget,
                            QWidget, QHBoxLayout, QVBoxLayout, QFileDialog)
sys.path.append(Path(__file__).parent.parent.as_posix()) # https://stackoverflow.com/questions/16981921
from negar.virastar import PersianEditor, ImmutableWords
from negar.constants import INFO
from negar_gui.constants import __version__, LOGO


collator = Collator()

class TableModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignVCenter
        elif role == Qt.ItemDataRole.BackgroundRole:
            if index.row()%2:
                return QColor("gray")
        elif role == Qt.ItemDataRole.ForegroundRole:
            if index.row()%2:
                return QColor("white")
        elif role == Qt.ItemDataRole.DisplayRole:
            try:
                return self._data[index.row()][index.column()]
            except:
                return ""
        return None

    def rowCount(self, index):
        """Return the length of the outer list."""
        del index
        return len(self._data)

    def columnCount(self, index):
        """Return the length of the first sub-list.
        
        This method assumes that all sub-lists (rows) are of equal length.
        """
        del index
        return len(self._data[0])

    def headerData(self, section, orientation, role):
        # section is the index of the column/row.
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return ""
            if orientation == Qt.Orientation.Vertical:
                return str(section+1)
        return None

class Form(QMainWindow):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.editing_options = []

        self.table = QTableView(layoutDirection=Qt.LayoutDirection.RightToLeft)
        self.setup_table()

        self.setupUi()

    def setup_table(self, col=8):
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        data = sorted(list(ImmutableWords().get()), key=collator.sort_key)
        data = [data[i*col:(i+1)*col] for i in range(int(len(data)//col)+1)]
        model = TableModel(data)
        self.table.setModel(model)

    def setupUi(self):
        self.edit_btn = QPushButton(self.tr("&Edit"))
        self.edit_btn.setEnabled(False)
        reset_btn = QPushButton(self.tr("&Reset"))
        quit_btn = QPushButton(self.tr("&Quit"))
        import_btn = QPushButton(self.tr("Im&port"))
        copy_btn = QPushButton(QIcon(LOGO), "")
        copy_btn.setIconSize(QSize(24,24))
        copy_btn.setToolTip(self.tr("Click to Copy Sanitized Output"))
        copy_btn.setStyleSheet("QPushButton {border-style: outset; border-width: 0px;}")
        self.autoedit_chkbox = QCheckBox(self.tr("&Automatic edit"))
        self.autoedit_chkbox.setChecked(True)
        self.font_slider = QSlider(orientation=Qt.Orientation.Horizontal,
            minimum=10, maximum=40, value=18)
        font_slider_label = QLabel(self.tr("&Font Size"))
        font_slider_label.setBuddy(self.font_slider)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.autoedit_chkbox)
        btn_layout.addStretch()
        btn_layout.addWidget(font_slider_label)
        btn_layout.addWidget(self.font_slider)
        btn_layout.addStretch()
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(reset_btn)
        btn_layout.addWidget(quit_btn)

        self.input_editor = QTextEdit()
        input_editor_label = QLabel(self.tr("&Input Box"))
        input_editor_label.setBuddy(self.input_editor)
        self.output_editor = QTextEdit()
        output_editor_label = QLabel(self.tr("&Output Box"))
        output_editor_label.setBuddy(self.output_editor)

        # Options:
        self.f_dashes = QCheckBox(self.tr("Fix &Dashes"), checked=True)
        self.f_three_dots = QCheckBox(self.tr("Fix &three dots"), checked=True)
        self.f_english_quotes = QCheckBox(self.tr("Fix English &quotes"), checked=True)
        self.f_hamzeh = QCheckBox(self.tr("Fix &hamzeh"), checked=True)
        self.hamzeh_yeh = QCheckBox(self.tr("Use 'Persian &yeh' to show hamzeh"), checked=True)
        self.f_spacing_bq = QCheckBox(self.tr("Fix &spacing braces and qoutes"), checked=True)
        self.f_arab_num = QCheckBox(self.tr("Fix Arabic &numbers"), checked=True)
        self.f_eng_num = QCheckBox(self.tr("Fix &English numbers"), checked=True)
        self.f_non_persian_ch = QCheckBox(self.tr("Fix non Persian &chars"), checked=True)
        self.f_p_spacing = QCheckBox(self.tr("Fix &prefix spacing"), checked=True)
        self.f_p_separate = QCheckBox(self.tr("Fix p&refix separating"), checked=True)
        self.f_s_spacing = QCheckBox(self.tr("Fix su&ffix spacing"), checked=True)
        self.f_s_separate = QCheckBox(self.tr("Fix s&uffix separating"), checked=True)
        self.aggressive = QCheckBox(self.tr("Fix a&ggressive punctuation"), checked=True)
        self.clnup_kashidas = QCheckBox(self.tr("Cleanup &kashidas"), checked=True)
        self.clnup_ex_marks = QCheckBox(self.tr("Cleanup e&xtra marks"), checked=True)
        self.clnup_spacing = QCheckBox(self.tr("C&leanup spacing"), checked=True)
        self.trim_lt_whitespaces = QCheckBox(self.tr("Tr&im Leading/Trailing Whitespaces"), checked=True)
        self.exaggeragin_zwnj = QCheckBox(self.tr("Exaggerating &ZWNJ"), checked=True)

        # Add to immutable list:
        self.untouch_word = QLineEdit()
        untouch_label = QLabel(self.tr("Add a &word to untouchable list"))
        untouch_label.setBuddy(self.untouch_word)
        self.untouch_button = QPushButton(self.tr("&Add"), enabled=False)
        untouch_box = QGroupBox(self.tr("Untouchable words"))
        untouch_layout = QGridLayout()
        untouch_layout.addWidget(untouch_label, 0, 0)
        untouch_layout.addWidget(self.untouch_word, 1, 0)
        untouch_layout.addWidget(self.untouch_button, 1, 1)
        untouch_layout.addWidget(self.table, 2,0,1,2)
        untouch_box.setLayout(untouch_layout)

        # Options Box:
        config_box = QGroupBox(self.tr("Options"))
        config_layout = QGridLayout()
        config_layout.addWidget(self.f_dashes, 0, 0)
        config_layout.addWidget(self.f_three_dots, 1, 0)
        config_layout.addWidget(self.f_english_quotes, 0, 2)
        config_layout.addWidget(self.f_arab_num, 0, 1)
        config_layout.addWidget(self.f_eng_num, 1, 1)
        config_layout.addWidget(self.f_non_persian_ch, 1, 2)
        config_layout.addWidget(self.f_hamzeh, 2, 0)
        config_layout.addWidget(self.f_p_separate, 2, 1)
        config_layout.addWidget(self.f_s_separate, 2, 2)
        config_layout.addWidget(self.f_s_spacing, 3, 1)
        config_layout.addWidget(self.f_p_spacing, 3, 2)
        config_layout.addWidget(self.aggressive, 3, 3)
        config_layout.addWidget(self.exaggeragin_zwnj, 3, 5)
        config_layout.addWidget(self.f_spacing_bq, 0, 3, 1, 2)
        config_layout.addWidget(self.hamzeh_yeh, 1, 3, 1, 2)
        config_layout.addWidget(self.trim_lt_whitespaces, 2, 3, 1, 2)
        config_layout.addWidget(self.clnup_spacing, 0, 5)
        config_layout.addWidget(self.clnup_ex_marks, 1, 5)
        config_layout.addWidget(self.clnup_kashidas, 2, 5)
        config_box.setLayout(config_layout)

        # Tab widgets initializing:
        tab_widget = QTabWidget()
        main_tab = QWidget()
        config_tab = QWidget()

        # Config tab widgets layout:
        ct_layout = QVBoxLayout(config_tab)
        ct_layout.addWidget(config_box)
        ct_layout.addWidget(untouch_box)
        # ct_layout.addStretch()

        # layout for input_label + import button
        input_layout = QHBoxLayout()
        input_layout.addWidget(input_editor_label)
        input_layout.addStretch()
        input_layout.addWidget(import_btn)

        # layout for output_label + copy button
        output_layout = QHBoxLayout()
        output_layout.addWidget(output_editor_label)
        output_layout.addStretch()
        output_layout.addWidget(copy_btn)

        # Main Tab widgets layouts:
        mt_layout = QGridLayout(main_tab)
        mt_layout.addLayout(input_layout, 0, 0)
        mt_layout.addWidget(self.input_editor, 1, 0)
        mt_layout.addLayout(output_layout, 2,0)
        mt_layout.addWidget(self.output_editor, 3, 0)
        mt_layout.addLayout(btn_layout, 4, 0)

        # Main tab widget control:
        tab_widget.addTab(main_tab, self.tr("&Main"))
        tab_widget.addTab(config_tab, self.tr("&Config"))

        # Main window configs:
        self.setCentralWidget(tab_widget)
        self.resize(800, 600)
        self.setWindowIcon(QIcon(LOGO))
        self.setWindowTitle(self.tr(f"Negar {__version__}"))

        # Signal control:
        # first of all negar have to check the default state of automatic edit feature.
        self.autoedit_handler()
        quit_btn.clicked.connect(QApplication.instance().quit)
        reset_btn.clicked.connect(self.text_box_reset)
        self.edit_btn.clicked.connect(self.edit_text)

        import_btn.clicked.connect(self.file_dialog)
        copy_btn.clicked.connect(self.save_to_clipboard)
        # if autoedit_chkboxs state's changed, then autoedit_handler have to call again.
        self.autoedit_chkbox.stateChanged.connect(self.autoedit_handler)

        self.font_slider.valueChanged.connect(self._set_font_size)
        self.untouch_word.textChanged.connect(self.untouch_add_enabler)
        self.untouch_button.clicked.connect(self.untouch_add)

        # Option checkbox lists signal control
        _options = [self.f_dashes, self.f_three_dots, self.f_english_quotes, self.f_hamzeh,
                    self.hamzeh_yeh, self.f_spacing_bq, self.f_arab_num, self.f_eng_num,
                    self.f_non_persian_ch, self.f_p_spacing, self.f_p_separate, self.f_s_spacing,
                    self.f_s_separate, self.aggressive, self.clnup_kashidas, self.clnup_ex_marks,
                    self.clnup_spacing, self.trim_lt_whitespaces, self.exaggeragin_zwnj,
                    ]
        for opt in _options:
            opt.stateChanged.connect(self.option_control)

    def keyPressEvent(self, event):
        """KeyPress event handler."""
        if event.key() == Qt.Key.Key_Escape:
            self.save_to_clipboard()
            self.close()
        elif event.key() == Qt.Key.Key_F1:
            self.input_editor.clear()
            self.input_editor.setText(INFO)
        else:
            super().keyPressEvent(event)

    def _set_font_size(self):
        size = self.font_slider.value()
        self.input_editor.setFontPointSize(size)
        self.output_editor.setFontPointSize(size)
        lines = self.input_editor.toPlainText()
        self.input_editor.clear()
        self.input_editor.append(lines)
        self.edit_text()

    def untouch_add_enabler(self):
        """Enable the 'Add' button if a single word is entered in the text input."""
        word_list = self.untouch_word.text().split(" ")
        if len(word_list) == 1:
            self.untouch_button.setEnabled(True)
        else:
            self.untouch_button.setEnabled(False)

    def untouch_add(self):
        """Add a new word into untouchable words."""
        word = [self.untouch_word.text()]
        ImmutableWords.add(word)
        self.untouch_word.clear()
        self.edit_text()  # retouches the input text
        self.setup_table() # updates immutable words list

    def autoedit_handler(self):
        """Edit the input text automatically if `autoedit` is checked."""
        if self.autoedit_chkbox.isChecked():
            self.edit_btn.setEnabled(False)
            self.input_editor.textChanged.connect(self.edit_text)
        else:
            self.edit_btn.setEnabled(True)
            # This line will disconnect autoedit signal and will disable autoamtic edit option
            self.input_editor.textChanged.disconnect(self.edit_text)
        self._set_font_size()

    def text_box_reset(self):
        """Clear input/output editor boxes."""
        self.input_editor.clear()
        self.output_editor.clear()

    def option_control(self):
        """Enable/Disable Editing features."""
        options = [(self.f_dashes, "fix-dashes"), (self.f_three_dots, "fix-three-dots"),
                    (self.f_english_quotes, "fix-english-quotes"), (self.f_hamzeh, "fix-hamzeh"),
                    (self.hamzeh_yeh, "hamzeh-with-yeh"), (self.f_spacing_bq, "fix-spacing-bq"),
                    (self.f_arab_num, "fix-arabic-num"), (self.f_eng_num, "fix-english-num"),
                    (self.f_non_persian_ch, "fix-non-persian-chars"), (self.f_p_spacing, "fix-p-spacing"),
                    (self.f_p_separate, "fix-p-separate"), (self.f_s_spacing, "fix-s-spacing"),
                    (self.f_s_separate, "fix-s-separate"), (self.aggressive, "aggressive"),
                    (self.clnup_kashidas, "cleanup-kashidas"), (self.clnup_ex_marks, "cleanup-ex-marks"),
                    (self.clnup_spacing, "cleanup-spacing"), (self.trim_lt_whitespaces, "trim-lt-whitespaces"),
                    (self.exaggeragin_zwnj, "exaggerating-zwnj")]
        for obj, opt in options:
            if not obj.isChecked(): self.editing_options.append(opt)

    def file_dialog(self):
        """Open file for importing text."""
        fname, _ = QFileDialog.getOpenFileName(self, "Open File - A Plain Text")
        try:
            with open(fname, encoding="utf8") as file_:
                self.input_editor.setText(file_.read())
        except:
            pass

    def edit_text(self):
        """Edit input text."""
        self.output_editor.clear()
        persian_editor = PersianEditor(self.input_editor.toPlainText(), *self.editing_options)
        self.output_editor.append(persian_editor.cleanup())

    def save_to_clipboard(self):
        """Save edited text to clipboard."""
        sanitized_text = self.output_editor.toPlainText()
        if sanitized_text:
            copy(sanitized_text)

def main():
    """Program entry point."""
    app = QApplication(sys.argv)
    run = Form()
    run.show()
    run.input_editor.setFocus() # set focus on input box
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
