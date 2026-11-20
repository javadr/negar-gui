"""`negar-gui --version`: a table of every required package and the version installed."""

import platform
import re
import sys
from importlib import metadata

from negar_gui.constants import __version__

ACCENT = "#d89e76"  # the app's accent colour
# "Negar" and "GUI" as pixel bitmaps (rasterised once from Noto Sans ExtraBold, OFL). Each pixel is half a terminal
# line, so the pixels are square, and every face pixel casts a one-pixel shadow down and to the right.
_NEGAR = """
###....##..................................
####...##..................................
#####..##....####....###.##...####....#..##
#####..##...######..#######...#####...#####
##.###.##..###..##..###..##......###..###..
##..##.##..#######..##...##...######..##...
##..#####..#######..##...##..#######..##...
##...####..###......##...##..##..###..##...
##...####...######..#######..#######..##...
##....###....#####...######..####.##..##...
.........................##................
....................#######................
....................######.................
"""
_GUI = """
..#####...##....##..#####
.#######..###...##..####.
###.......###...##...###.
##........###...##...###.
##..####..###...##...###.
##..####..###...##...###.
##....##..###...##...###.
###...##..###...##...###.
.#######...#######..####.
..######....#####...#####
"""
# (face colour at the top, face colour at the bottom, shadow colour)
_NEGAR_COLORS = ("#ffffff", "#b4b4b4", "#4a4a4a")
_GUI_COLORS = ("#f8d9b8", "#d89e76", "#7a4d30")
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


def _mix(c1, c2, t):
    a, b = (tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in (c1, c2))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def logo():
    """Negar in white and GUI in the accent colour, each casting a coloured shadow; plain text if too narrow."""
    from rich.console import Console
    from rich.style import Style
    from rich.text import Text

    words = [(w.strip().splitlines(), c) for w, c in ((_NEGAR, _NEGAR_COLORS), (_GUI, _GUI_COLORS))]
    gap = 2
    width = sum(len(rows[0]) for rows, _ in words) + gap + 1  # +1: the shadow
    height = max(len(rows) for rows, _ in words) + 1
    console = Console()
    if console.width < width + 4:
        return Text("NEGAR-GUI", style=f"bold {ACCENT}")
    shadows = console.color_system is not None  # without colour a shadow would just fatten the letters
    grid = [[None] * width for _ in range(height)]
    x0 = 0
    for rows, (top, bottom, shade) in words:
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch == "#":
                    if shadows and grid[y + 1][x0 + x + 1] is None:
                        grid[y + 1][x0 + x + 1] = shade
                    grid[y][x0 + x] = _mix(top, bottom, y / max(len(rows) - 1, 1))  # a face pixel wins over a shadow
        x0 += len(rows[0]) + gap
    out = Text()
    for y in range(0, height, 2):
        for x in range(width):
            up = grid[y][x]
            down = grid[y + 1][x] if y + 1 < height else None
            if up and down:
                out.append("▀", Style(color=up, bgcolor=down))
            elif up:
                out.append("▀", Style(color=up))
            elif down:
                out.append("▄", Style(color=down))
            else:
                out.append(" ")
        out.append("\n")
    out.rstrip()
    return out


def show():
    from rich import box
    from rich.console import Console, Group
    from rich.padding import Padding
    from rich.table import Table

    def make(title, *cols):
        t = Table(title=title, title_justify="left", title_style=f"bold {ACCENT}", box=box.ROUNDED, border_style=ACCENT)
        for col in cols:
            t.add_column(col, header_style="bold")
        return t

    env = make("Environment", "Item", "Value")
    for label, value in about():
        env.add_row(label, value)
    pkgs = make("Packages", "Package", "Required", "Installed", "Status")
    for name, spec in sorted(requirements(), key=lambda r: r[0].lower()):
        v = installed(name)
        pkgs.add_row(name, spec, v or "-", "[green]ok" if v else "[red]missing")  # the word carries it, not the colour
    for name in OPTIONAL:
        v = installed(name)
        pkgs.add_row(name, "optional", v or "-", "[green]ok" if v else "[dim]not installed")
    Console().print(Padding(Group(logo(), "", env, "", pkgs), (1, 2)))
