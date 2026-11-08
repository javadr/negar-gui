"""AI dialogs: layouts live in ui/provider.ui, ui/promptedit.ui, ui/prompts.ui, ui/usage.ui (see `make compile-ui`)."""

from PyQt6.QtCore import QCoreApplication, QPoint, QSize, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QListWidgetItem,
    QMessageBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidgetItem,
)

from negar_gui import llm_providers, usage_log
from negar_gui.ui.Ui_promptedit import Ui_PromptEditDialog
from negar_gui.ui.Ui_prompts import Ui_PromptsDialog
from negar_gui.ui.Ui_provider import Ui_ProviderDialog
from negar_gui.ui.Ui_usage import Ui_UsageDialog

_translate = QCoreApplication.translate


def setup_buttons(dialog, box):
    """Wire an OK/Cancel box with translated labels (Qt's stock ones stay English with only our .qm loaded)."""
    box.button(QDialogButtonBox.StandardButton.Ok).setText(_translate("MainWindow", "OK"))
    box.button(QDialogButtonBox.StandardButton.Cancel).setText(_translate("MainWindow", "Cancel"))
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)


def localize_digits(window, text):
    """Persian digits when the app language is Persian."""
    if window.settings.get("settings", {}).get("language") == "Persian":
        return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    return str(text)


class LLMProviderDialog(QDialog, Ui_ProviderDialog):
    """Pick the LLM provider and enter its API key and model; edits `llm` (the settings dict) on OK."""

    def __init__(self, parent, llm):
        super().__init__(parent)
        self.setupUi(self)
        setup_buttons(self, self.buttonBox)
        self.llm = llm
        self.keys = dict(llm.get("keys", {}))
        self.models = dict(llm.get("models", {}))
        for key, prov in llm_providers.PROVIDERS.items():
            self.provider.addItem(prov["name"], key)
        self._current = None
        self.provider.currentIndexChanged.connect(self._switch)
        self.provider.setCurrentIndex(max(0, self.provider.findData(llm.get("provider"))))
        self._switch()

    def _stash(self):
        # remember what was typed for the provider being left, so switching back keeps it
        if self._current:
            self.keys[self._current] = self.api_key.text().strip()
            self.models[self._current] = self.model.text().strip()

    def _switch(self):
        self._stash()
        key = self.provider.currentData()
        prov = llm_providers.PROVIDERS[key]
        self._current = key
        self.api_key.setText(self.keys.get(key, ""))
        self.api_key.setEnabled(bool(prov["key_url"]))
        self.model.setText(self.models.get(key, ""))
        self.model.setPlaceholderText(prov["model"])
        self.key_link.setText(
            f'<a href="{prov["key_url"]}">{_translate("MainWindow", "Get an API key")}</a>' if prov["key_url"] else ""
        )

    def accept(self):
        self._stash()
        self.llm.update(provider=self._current, keys=self.keys, models=self.models)
        super().accept()


class PromptEditDialog(QDialog, Ui_PromptEditDialog):
    """Name + instruction for one user prompt."""

    def __init__(self, parent, prompt=None):
        super().__init__(parent)
        self.setupUi(self)
        setup_buttons(self, self.buttonBox)
        prompt = prompt or {}
        self.name.setText(prompt.get("name", ""))
        self.name_fa.setText(prompt.get("name_fa", ""))
        self.text.setPlainText(prompt.get("system_prompt", ""))
        # fixed per field, whatever the app language: English left/LTR, Persian right/RTL
        self.name.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.name.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.name_fa.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        # Qt mirrors Left/Right in an RTL widget, so Leading = right here
        self.name_fa.setAlignment(Qt.AlignmentFlag.AlignLeading)

    def accept(self):
        if self.name.text().strip() and self.text.toPlainText().strip():
            super().accept()

    def result_prompt(self):
        return {
            "name": self.name.text().strip(),
            "name_fa": self.name_fa.text().strip(),
            "system_prompt": self.text.toPlainText().strip(),
        }


class GripDelegate(QStyledItemDelegate):
    """List rows with a dotted grip on the leading edge, hinting that they can be dragged."""

    GRIP = 28

    def paint(self, painter, option, index):
        rtl = option.direction == Qt.LayoutDirection.RightToLeft
        rect = option.rect
        text_rect = rect.adjusted(0, 0, -self.GRIP, 0) if rtl else rect.adjusted(self.GRIP, 0, 0, 0)
        opt = QStyleOptionViewItem(option)
        opt.rect = text_rect
        super().paint(painter, opt, index)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(option.palette.mid())
        x0 = rect.right() - self.GRIP + 8 if rtl else rect.left() + 8
        for dx in (0, 6):
            for dy in (-6, 0, 6):
                painter.drawEllipse(QPoint(x0 + dx + 2, rect.center().y() + dy), 2, 2)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width() + self.GRIP, max(size.height(), 34))


class UsageReportDialog(QDialog, Ui_UsageDialog):
    """Requests per day and provider, from the usage log (DuckDB)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setupUi(self)
        try:
            rows = usage_log.report()
        except Exception as e:  # missing DuckDB or an unreadable log
            return self._show_message(_translate("MainWindow", "Cannot read the usage log: {}").format(e))
        if not rows:
            return self._show_message(_translate("MainWindow", "No AI requests logged yet."))
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(localize_digits(parent, value)))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.total.setText(self.total.text().format(localize_digits(parent, sum(row[2] for row in rows))))

    def _show_message(self, text):
        self.table.hide()
        self.total.hide()
        self.message.setText(text)
        self.message.show()


class PromptsDialog(QDialog, Ui_PromptsDialog):
    """Add / edit / delete user prompts; edits the `prompts` list in place."""

    def __init__(self, parent, prompts):
        super().__init__(parent)
        self.setupUi(self)
        self.prompts = prompts
        self.list.setItemDelegate(GripDelegate(self.list))
        for btn, slot in (
            (self.add_btn, self._add),
            (self.edit_btn, self._edit),
            (self.delete_btn, self._delete),
            (self.restore_btn, self._restore_defaults),
        ):
            btn.clicked.connect(slot)
        self.list.itemDoubleClicked.connect(lambda _: self._edit())
        # shortcuts, not keyPressEvent: the list swallows arrow keys before the dialog sees them
        for seq, step in (("Alt+Up", -1), ("Alt+Down", 1)):
            QShortcut(QKeySequence(seq), self, activated=lambda step=step: self._move(step))
        self.list.model().rowsMoved.connect(self._sync_order)
        self._refresh()

    def _refresh(self, row=-1):
        self.list.clear()
        for i, p in enumerate(self.prompts):
            item = QListWidgetItem(self.parent().prompt_title(p))
            item.setData(Qt.ItemDataRole.UserRole, i)  # index in self.prompts before any drag
            self.list.addItem(item)
        self.list.setCurrentRow(row)

    def _sync_order(self):
        order = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        self.prompts[:] = [self.prompts[i] for i in order]
        for i in range(self.list.count()):
            self.list.item(i).setData(Qt.ItemDataRole.UserRole, i)

    def _move(self, step):
        i, j = self.list.currentRow(), self.list.currentRow() + step
        if i >= 0 and 0 <= j < len(self.prompts):
            self.prompts[i], self.prompts[j] = self.prompts[j], self.prompts[i]
            self._refresh(j)

    def _ask(self, prompt=None, skip=-1):
        dlg = PromptEditDialog(self, prompt)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        new = dlg.result_prompt()
        taken = {p["name"] for i, p in enumerate(self.prompts) if i != skip}
        if new["name"] in taken:
            QMessageBox.warning(self, self.windowTitle(), _translate("MainWindow", "This name is already used."))
            return self._ask(new, skip)
        return new

    def _add(self):
        if new := self._ask():
            self.prompts.append(new)
            self._refresh()

    def _edit(self):
        i = self.list.currentRow()
        if i >= 0 and (new := self._ask(self.prompts[i], i)):
            self.prompts[i] = new
            self._refresh()

    def _restore_defaults(self):
        box = QMessageBox(
            QMessageBox.Icon.Question,
            self.windowTitle(),
            _translate(
                "MainWindow",
                "Restore the prompts that come with Negar? Missing ones are added back and edited ones return to "
                "their original text. Your own prompts are kept.",
            ),
            parent=self,
        )
        yes = box.addButton(_translate("MainWindow", "Restore"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(_translate("MainWindow", "Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        by_name = {p["name"]: i for i, p in enumerate(self.prompts)}
        for default in llm_providers.DEFAULT_USER_PROMPTS:
            if default["name"] in by_name:
                self.prompts[by_name[default["name"]]] = dict(default)
            else:
                self.prompts.append(dict(default))
        self._refresh()

    def _delete(self):
        i = self.list.currentRow()
        if i >= 0:
            del self.prompts[i]
            self._refresh()
