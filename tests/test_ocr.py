import shutil
import subprocess

import pytest
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

from negar_gui import ocr

pytestmark = pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")


def render(text, dark=False):
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    img = QImage(900, 80, QImage.Format.Format_RGB32)
    img.fill(QColor("black" if dark else "white"))
    p = QPainter(img)
    p.setPen(QColor("white" if dark else "black"))
    p.setFont(QFont("DejaVu Sans", 22))
    p.drawText(img.rect(), 0x84, text)  # AlignCenter
    p.end()
    return img


def need(lang):
    if (
        lang
        not in subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=False).stdout.split()
    ):
        pytest.skip(f"{lang} data missing")


@pytest.mark.parametrize(
    "lang,text,dark",
    [
        ("eng", "Hello world screen reader", False),
        ("eng", "Hello world screen reader", True),
        ("deu", "Größe Straße Übung", False),
    ],
)
def test_read_text(lang, text, dark):
    need(lang)
    assert ocr.read_text(render(text, dark), [lang]) == text


def test_persian_returns_arabic_script():
    need("fas")  # Tesseract's fas is weak: only check the script, not the words
    out = ocr.read_text(render("سلام دنیا، این یک آزمایش است. متن فارسی برای تست خواندن از صفحه"), ["fas"])
    assert any("\u0600" <= c <= "\u06ff" for c in out)


def test_missing_tesseract(monkeypatch):
    monkeypatch.setattr(ocr, "_engine", lambda: (_ for _ in ()).throw(ocr.OCRError("x")))
    with pytest.raises(ocr.OCRError):
        ocr.read_text(render("x"))


def test_selector_maps_logical_drag_to_physical_pixels():
    from PyQt6.QtCore import QRect
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841
    shot = QImage(3200, 1800, QImage.Format.Format_RGB32)  # 1.25x HiDPI screen of 2560x1440
    sel = ocr.RegionSelector(shot, _FakeScreen(2560, 1440))
    assert sel._crop_rect(QRect(100, 100, 400, 200)) == QRect(125, 125, 500, 250)


class _FakeScreen:
    def __init__(self, w, h):
        from PyQt6.QtCore import QRect

        self._g = QRect(0, 0, w, h)

    def geometry(self):
        return self._g
