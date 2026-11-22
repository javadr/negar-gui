"""Screen reader: pick a screen region, OCR it with Tesseract (Persian, English, German)."""

import os
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QObject, QRect, Qt, QUrl, pyqtSignal, pyqtSlot

try:
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage
except ImportError:  # QtDBus only ships in the Linux wheels; the portal is only used on Wayland
    QDBusConnection = QDBusMessage = None
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter
from PyQt6.QtWidgets import QWidget

_dbus_slot = pyqtSlot(QDBusMessage) if QDBusMessage else lambda f: f
LANGS = ("fas", "eng", "deu")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console flash from the windowed exe


def _tr(text):
    return QCoreApplication.translate("MainWindow", text)


class OCRError(RuntimeError):
    """A problem to show the user as is."""


def _run(cmd, env=None, timeout=30):
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=timeout,
            creationflags=_NO_WINDOW,
            stdin=subprocess.DEVNULL,  # a windowed exe has no stdin: the child would fail with "invalid handle"
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise OCRError(f"{Path(cmd[0]).name}: {e}") from e


@lru_cache(maxsize=1)
def _engine():
    """Return (tesseract command, env, installed LANGS): the copy bundled in the exe, else the one on PATH."""
    env = os.environ.copy()
    exe = None
    if hasattr(sys, "_MEIPASS"):
        root = Path(sys._MEIPASS) / "tesseract"
        cand = root / ("tesseract.exe" if os.name == "nt" else "tesseract")
        if cand.exists():
            exe = str(cand)
            env["TESSDATA_PREFIX"] = str(root / "tessdata")
            env["LD_LIBRARY_PATH"] = os.pathsep.join([str(root), env.get("LD_LIBRARY_PATH", "")])  # its bundled libs
    elif "LD_LIBRARY_PATH_ORIG" in env:  # PyInstaller's own libs must not leak into a system tesseract
        env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
    # GUI apps on macOS/Windows don't see the shell PATH, so also look where the installers put it
    extra = ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin", r"C:\Program Files\Tesseract-OCR"]
    extra.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR"))
    exe = exe or shutil.which("tesseract", path=os.pathsep.join([env.get("PATH", ""), *extra]))
    if not exe:
        raise OCRError(_tr("Tesseract is not installed. Install it with its fas, eng and deu language data."))
    have = _run([exe, "--list-langs"], env, 15).stdout.split()
    return exe, env, [lang for lang in LANGS if lang in have]


def read_text(image: QImage, langs=LANGS) -> str:
    """OCR a QImage in the given languages (fewer = more accurate) and return the text ('' when nothing is found)."""
    exe, env, have = _engine()
    langs = "+".join(lang for lang in langs if lang in have)
    if not langs:
        raise OCRError(_tr("Tesseract is missing the language data for the selected languages."))
    # 2x upscale helps small UI text; Tesseract needs dark text on a light background
    img = image.scaled(
        image.width() * 2,
        image.height() * 2,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ).convertToFormat(QImage.Format.Format_Grayscale8)
    if (
        img.scaled(1, 1, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        .pixelColor(0, 0)
        .value()
        < 128
    ):
        img.invertPixels()
    with tempfile.TemporaryDirectory() as d:
        png = os.path.join(d, "region.png")
        if not img.save(png):
            raise OCRError(_tr("Could not save the captured region."))
        r = _run([exe, png, "stdout", "-l", langs], env)
    if r.returncode:
        raise OCRError(r.stderr.strip() or _tr("Tesseract failed."))
    return r.stdout.strip()


class RegionSelector(QWidget):
    """Fullscreen overlay over a screenshot of one screen; drag to select. Emits the cropped QImage, or None on Esc/tiny."""

    done = pyqtSignal(object)

    def __init__(self, shot: QImage, screen):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self._shot = shot
        self._dpr = shot.width() / screen.geometry().width()  # physical pixels per logical pixel
        self._origin = self._rect = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())

    def _crop_rect(self, r):
        return QRect(*(round(v * self._dpr) for v in r.getRect()))

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawImage(self.rect(), self._shot)
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if self._rect:
            p.drawImage(self._rect, self._shot, self._crop_rect(self._rect))
            p.setPen(QColor("#d89e76"))
            p.drawRect(self._rect)

    def mousePressEvent(self, e):
        self._origin = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self._origin:
            self._rect = QRect(self._origin, e.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, _):
        r = self._rect
        self._finish(self._shot.copy(self._crop_rect(r)) if r and r.width() > 4 and r.height() > 4 else None)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._finish(None)

    def _finish(self, img):
        self.close()
        self.done.emit(img)


_PORTAL = "org.freedesktop.portal.Desktop"


class _PortalShot(QObject):
    """Screenshot through xdg-desktop-portal (the only way on Wayland); async, result via Response.

    Silent full-desktop capture needs a stored permission; apps with an app id (desktop launcher) don't have
    one on GNOME and get "failed", so then the portal's own interactive picker is used instead.
    """

    def __init__(self, on_shot, on_error):
        super().__init__()
        self._on_shot, self._on_error, self._interactive = on_shot, on_error, False
        self._request()

    def _request(self):
        bus = QDBusConnection.sessionBus()
        token = f"negar{os.getpid()}{int(self._interactive)}"
        path = f"/org/freedesktop/portal/desktop/request/{bus.baseService()[1:].replace('.', '_')}/{token}"
        bus.connect(_PORTAL, path, "org.freedesktop.portal.Request", "Response", self._response)
        msg = QDBusMessage.createMethodCall(
            _PORTAL, "/org/freedesktop/portal/desktop", "org.freedesktop.portal.Screenshot", "Screenshot"
        )
        msg.setArguments(["", {"handle_token": token, "interactive": self._interactive}])
        reply = bus.call(msg)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            raise OCRError(_tr("Could not take a screenshot: {}").format(reply.errorMessage()))

    @_dbus_slot
    def _response(self, msg):
        code, results = msg.arguments()
        if code == 2 and not self._interactive:
            self._interactive = True
            try:
                return self._request()
            except OCRError as e:
                return self._on_error(e)
        if code:  # 1 = cancelled, 2 = failed
            return (
                self._on_shot(None)
                if code == 1
                else self._on_error(OCRError(_tr("Could not take a screenshot: {}").format(code)))
            )
        path = QUrl(results.get("uri", "")).toLocalFile()
        img = QImage(path)
        if path:
            Path(path).unlink(missing_ok=True)  # the portal saves a copy in ~/Pictures
        if img.isNull():
            return self._on_error(OCRError(_tr("Could not take a screenshot: {}").format("no image")))
        self._on_shot(img, self._interactive)


def _is_wayland():
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


_keep = None  # keeps the portal request / overlay alive while in use


def capture(on_done, on_error):
    """Let the user pick a screen region: on_done(QImage), or on_done(None) if cancelled; on_error(OCRError) on failure."""
    global _keep
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def select(shot, picked=False):  # picked: the portal's own picker already cropped it
        global _keep
        if shot is None or picked:
            return on_done(shot)
        if _is_wayland():  # the portal returns the whole desktop; keep this screen's part
            v, g = screen.virtualGeometry(), screen.geometry()
            k = shot.width() / v.width()
            shot = shot.copy(QRect(*(round(n * k) for n in (g.x() - v.x(), g.y() - v.y(), g.width(), g.height()))))
        _keep = RegionSelector(shot, screen)
        _keep.done.connect(on_done)
        _keep.showFullScreen()

    if _is_wayland():
        _keep = _PortalShot(select, on_error)
    else:
        select(screen.grabWindow(0).toImage())
