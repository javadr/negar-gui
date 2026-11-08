"""AI dialogs: layouts live in ui/provider.ui, ui/promptedit.ui, ui/prompts.ui, ui/usage.ui (see `make compile-ui`)."""

from datetime import datetime

from PyQt6.QtCore import QCoreApplication, QPoint, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QCursor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QListWidgetItem,
    QMessageBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidgetItem,
    QToolTip,
)

from negar_gui import llm_providers, usage_log
from negar_gui.ui.Ui_promptedit import Ui_PromptEditDialog
from negar_gui.ui.Ui_prompts import Ui_PromptsDialog
from negar_gui.ui.Ui_provider import Ui_ProviderDialog
from negar_gui.ui.Ui_usage import Ui_UsageDialog

_translate = QCoreApplication.translate
MAX_LABEL = 22  # characters of a prompt/provider name shown in a chart label
CHART_FONT_PT = 11  # HIG minimum for desktop text is 10 pt (typography.md)
# Chart colours by role: success, failure, text, and a categorical set for pies; each >= 3:1 against its background.
_DARK = {
    "fg": "#e6e6e6",
    "ok": "#4cc38a",
    "failed": "#ff8a65",
    "cats": ["#5aa9ff", "#ffb454", "#4cc38a", "#c792ea", "#ff7b8a", "#5fd3d3"],
}
_LIGHT = {
    "fg": "#222222",
    "ok": "#1f8a5b",
    "failed": "#c2410c",
    "cats": ["#1f6fd1", "#b45f06", "#1f8a5b", "#8a4fc9", "#c93a4d", "#0e8a8a"],
}


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


def _show_tip(hovering, tip):
    QToolTip.showText(QCursor.pos(), tip) if hovering else QToolTip.hideText()


def _is_persian(window):
    return window.settings.get("settings", {}).get("language") == "Persian"


def _palette(widget):
    """Chart colours for the theme actually drawn (qdarktheme is a stylesheet, so the palette can't tell)."""
    bg = widget.grab().toImage().pixelColor(2, 2)
    dark = bg.lightness() < 128
    colors = _DARK if dark else _LIGHT
    return {
        "dark": dark,
        "bg": bg,
        **{k: QColor(v) if isinstance(v, str) else [QColor(c) for c in v] for k, v in colors.items()},
    }


def _chart_view(widget, pal, series_list, axes=(), name="", description=""):
    """A chart view holding `series_list`; `axes` are (axis, alignment) pairs."""
    from PyQt6.QtCharts import QChart, QChartView

    fg = pal["fg"]
    grid = QColor(fg.red(), fg.green(), fg.blue(), 45)
    font = QFont()
    font.setPointSize(CHART_FONT_PT)
    chart = QChart()
    chart.setTheme(QChart.ChartTheme.ChartThemeDark if pal["dark"] else QChart.ChartTheme.ChartThemeLight)
    chart.setBackgroundVisible(False)
    chart.legend().setLabelColor(fg)
    chart.legend().setFont(font)
    for series in series_list:
        chart.addSeries(series)
        for pie_slice in getattr(series, "slices", list)():
            pie_slice.setLabelColor(fg)
            pie_slice.setLabelFont(font)
            pie_slice.setLabelArmLengthFactor(0.15)
    for axis, align in axes:
        chart.addAxis(axis, align)
        axis.setLabelsColor(fg)
        axis.setLabelsFont(font)
        axis.setGridLineColor(grid)
        axis.setLinePenColor(grid)
        for series in series_list:
            series.attachAxis(axis)
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setAccessibleName(name)
    view.setAccessibleDescription(description)
    return view


class UsageReportDialog(QDialog, Ui_UsageDialog):
    """Usage per day / provider / prompt from the usage log (DuckDB): a summary, charts (PyQt6-Charts), a table."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setupUi(self)
        self._load(parent)

    def _load(self, parent):
        def digits(x):
            return localize_digits(parent, x)

        try:
            rows = usage_log.report()
        except Exception as e:  # noqa: BLE001  # missing DuckDB or an unreadable log
            return self._show_message(_translate("MainWindow", "Cannot read the usage log: {}").format(e))
        if not rows:
            return self._show_message(
                _translate("MainWindow", "No AI requests yet. Press the AI button to get started.")
            )
        today = datetime.now().astimezone().date().isoformat()
        ok = sum(r[2] for r in rows)
        failed = sum(r[3] for r in rows)
        self.headline.setText(
            _translate("MainWindow", "Requests today: {}").format(digits(sum(r[2] for r in rows if r[0] == today)))
        )
        self.subtitle.setText(
            _translate("MainWindow", "All time: {}, success rate: {}%").format(
                digits(ok + failed), digits(round(100 * ok / (ok + failed)))
            )
        )
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(digits(value))
                if c >= 2:  # counts: centred, so they read the same in either text direction
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, c, item)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        try:
            self._add_charts(parent)
        except ImportError:  # PyQt6-Charts missing or built for another Qt: keep the table
            for tab in (self.tab_daily, self.tab_provider, self.tab_prompt, self.tab_rate):
                self.tabs.removeTab(self.tabs.indexOf(tab))

    def _add_charts(self, window):
        from PyQt6.QtCharts import (
            QBarCategoryAxis,
            QBarSet,
            QLineSeries,
            QPieSeries,
            QStackedBarSeries,
            QValueAxis,
        )

        def digits(x):
            return localize_digits(window, x)

        def title(tab):
            return self.tabs.tabText(self.tabs.indexOf(tab))

        pal = _palette(self)
        rtl = _is_persian(window)
        days = usage_log.daily()
        if rtl:  # time runs in the reading direction: oldest on the right
            days = days[::-1]
        categories = [digits(d[5:]) for d, _, _ in days]  # MM-DD: the year does not fit the axis
        bottom = Qt.AlignmentFlag.AlignBottom
        side = Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        day_tips = [
            _translate("MainWindow", "{}: {} succeeded, {} failed").format(digits(d), digits(o), digits(f))
            for d, o, f in days
        ]
        rate_tips = [
            _translate("MainWindow", "{}: {}% succeeded").format(digits(d), digits(round(100 * o / (o + f))))
            for d, o, f in days
        ]

        # daily requests: succeeded + failed stacked; failed is hatched so colour is not the only cue
        bars = QStackedBarSeries()
        for column, color, style in (
            (1, pal["ok"], Qt.BrushStyle.SolidPattern),
            (2, pal["failed"], Qt.BrushStyle.BDiagPattern),
        ):
            bar_set = QBarSet(self.table.horizontalHeaderItem(column + 1).text())
            bar_set.append([float(d[column]) for d in days])
            bar_set.setBrush(QBrush(color, style))
            bar_set.setPen(QPen(pal["bg"] if column == 1 else color, 1))
            bars.append(bar_set)
        bars.hovered.connect(lambda hovering, i, _set: _show_tip(hovering, day_tips[i]))
        y = QValueAxis()
        y.setLabelFormat("%d")
        y.setRange(0, max(ok + failed for _, ok, failed in days))
        y.applyNiceNumbers()
        x = QBarCategoryAxis()
        x.append(categories)
        x.setLabelsAngle(-90)  # vertical: horizontal MM-DD labels get elided
        self.daily_layout.addWidget(
            _chart_view(self, pal, [bars], [(x, bottom), (y, side)], title(self.tab_daily), "; ".join(day_tips))
        )

        # success rate per day: fixed 0-100 axis, points on the line so single days are visible
        line = QLineSeries()
        line.setName(title(self.tab_rate))
        line.setPen(QPen(pal["ok"], 3))  # also sizes the point markers
        line.setPointsVisible(True)
        for i, (_, ok, failed) in enumerate(days):
            line.append(i, 100 * ok / (ok + failed))
        line.hovered.connect(lambda point, hovering: _show_tip(hovering, rate_tips[round(point.x())]))
        x = QBarCategoryAxis()
        x.append(categories)
        x.setLabelsAngle(-90)  # vertical: horizontal MM-DD labels get elided
        y = QValueAxis()
        y.setRange(0, 100)
        y.setLabelFormat("%d%%")
        self.rate_layout.addWidget(
            _chart_view(self, pal, [line], [(x, bottom), (y, side)], title(self.tab_rate), "; ".join(rate_tips))
        )

        # shares of successful requests; long names are shortened, the tooltip has the full one
        for layout, tab, column in (
            (self.provider_layout, self.tab_provider, "provider"),
            (self.prompt_layout, self.tab_prompt, "prompt"),
        ):
            pie, tips = QPieSeries(), []
            rows = usage_log.share(column)
            total = sum(n for _, n in rows)
            for i, (name, n) in enumerate(rows):
                short = name if len(name) <= MAX_LABEL else name[: MAX_LABEL - 1] + "…"
                pie_slice = pie.append(f"{short} ({digits(n)})", n)
                pie_slice.setBrush(pal["cats"][i % len(pal["cats"])])
                pie_slice.setBorderColor(pal["bg"])
                tips.append(f"{name}\n{digits(n)} ({digits(round(100 * n / total))}%)")
            pie.setLabelsVisible(True)
            view = _chart_view(self, pal, [pie], name=title(tab), description="; ".join(tips))
            layout.addWidget(view)
            for pie_slice, tip in zip(pie.slices(), tips):
                pie_slice.hovered.connect(lambda hovering, tip=tip: _show_tip(hovering, tip))
            for marker, tip in zip(view.chart().legend().markers(pie), tips):
                marker.hovered.connect(lambda hovering, tip=tip: _show_tip(hovering, tip))

    def _show_message(self, text):
        self.tabs.hide()
        self.headline.hide()
        self.subtitle.hide()
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
