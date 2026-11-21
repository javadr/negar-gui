"""`negar-gui --version`: a table of every required package and the version installed."""

import platform
import re
import sys
from importlib import metadata

from negar_gui.constants import __version__

# Catppuccin Mocha: https://catppuccin.com/palette
TEXT, SUBTEXT, MUTED, GREEN, RED = "#cdd6f4", "#a6adc8", "#7f849c", "#a6e3a1", "#f38ba8"
ACCENT = "#cba6f7"  # mauve: the middle of the logo gradient
# "NEGAR" in figlet's "ANSI Shadow" font: █ is the face, box-drawing lines are the shadow.
_GLYPHS = [
    ("███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"),  # N
    ("███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"),  # E
    (" ██████╗ ", "██╔════╝ ", "██║  ███╗", "██║   ██║", "╚██████╔╝", " ╚═════╝ "),  # G
    (" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"),  # A
    ("██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"),  # R
]
_NEGAR = ["".join(g[r] + " " for g in _GLYPHS).rstrip() for r in range(6)]
_GRADIENT = ("#f5c2e7", "#cba6f7", "#89b4fa")  # pink, mauve, blue: left to right
_SHADE = "#313244"  # the shadow is the face colour pulled this far toward the dark
OPTIONAL = ("torch", "pocket-tts")  # Read Aloud, see the README


def requirements():
    """(name, specifier) of the packages negar-gui declares, read from its installed metadata."""
    out = []
    for line in metadata.requires("negar-gui") or []:
        if "extra ==" in line:
            continue
        m = re.match(r"([A-Za-z0-9_.-]+)\s*(?:\[[^\]]*\])?\s*\(?([^;)]*)", line)
        out.append((m[1], m[2].strip() or "any"))
    return out


def installed(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def about():
    """(label, value) rows about the running environment."""
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

        qt = f"{QT_VERSION_STR} (PyQt6 {PYQT_VERSION_STR})"
    except ImportError:
        qt = "-"
    return [
        ("Negar-GUI", __version__),
        ("Negar", installed("python-negar") or "-"),
        ("Python", f"{platform.python_version()} ({platform.python_implementation()})"),
        ("Qt", qt),
        ("Platform", f"{platform.system()} {platform.release()} {platform.machine()}"),
        ("Executable", sys.executable),
    ]


def _rgb(c):
    return tuple(int(c[i : i + 2], 16) for i in (1, 3, 5))


def _mix(c1, c2, t):
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(_rgb(c1), _rgb(c2)))


def _gradient(t):
    return _mix(_GRADIENT[0], _GRADIENT[1], t * 2) if t < 0.5 else _mix(_GRADIENT[1], _GRADIENT[2], t * 2 - 1)


def logo_width():
    return max(map(len, _NEGAR))


def logo(shadow=True):
    """NEGAR in ANSI-Shadow letters: a pink-to-blue gradient on the face, the same hue dimmed on the shadow lines."""
    from rich.style import Style
    from rich.text import Text

    w = logo_width()
    out = Text()
    for y, row in enumerate(_NEGAR):
        for x, c in enumerate(row):
            face = _gradient((x / (w - 1)) * 0.85 + (y / 5) * 0.15)
            tone = face if c == "█" else _mix(face, _SHADE, 0.45)
            out.append(c, Style(color=tone) if c != " " else None)
        out.append("\n")
    out.rstrip()
    return out


def _summary():
    try:
        return metadata.metadata("negar-gui")["Summary"].split("--")[-1].strip()
    except (metadata.PackageNotFoundError, KeyError):
        return "Persian text editor"


def show():
    from rich import box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.padding import Padding
    from rich.table import Table
    from rich.text import Text

    console = Console()
    mono = console.color_system is None
    info = Table.grid(padding=(0, 2))
    info.style = TEXT
    for label, value in about()[2:]:  # the versions are in the heading
        info.add_row(Text(label, style=MUTED), value)
    head = Group(
        Text.assemble((f"Negar-GUI {__version__}", f"bold {TEXT}")),
        Text(f"Persian text editor · Negar {installed('python-negar') or '-'}", style=SUBTEXT),
        "",
        info,
    )
    art = logo(shadow=not mono)  # without colour a shadow would only fatten the letters
    banner = Table.grid(padding=(0, 4))
    if console.width >= logo_width() + 4 + 52:  # art + gap + info
        banner.add_row(art, Align(head, vertical="middle"))
    else:
        banner.add_row(art)
        banner.add_row(head)
    pkgs = Table(box=box.SIMPLE_HEAD, header_style=f"bold {ACCENT}", pad_edge=False, show_edge=False, style=TEXT)
    for col in ("Dependency", "Required", "Installed", "Status"):
        pkgs.add_column(col)
    for name, spec in sorted(requirements(), key=lambda r: r[0].lower()):
        v = installed(name)
        pkgs.add_row(name, Text(spec, style=MUTED), v or "-", f"[{GREEN}]ok" if v else f"[bold {RED}]missing")
    for name in OPTIONAL:  # the Read Aloud extras are not dependencies: set them apart and dim
        v = installed(name)
        pkgs.add_row(
            Text(name, style=MUTED),
            Text("optional", style=MUTED),
            v or "-",
            f"[{GREEN}]ok" if v else f"[{MUTED}]not installed",
        )
    console.print(Padding(Group(banner, "", Align.left(pkgs)), (1, 2)))
