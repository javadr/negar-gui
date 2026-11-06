"""Switch the keyboard to Persian while Negar runs and put the previous layout back on exit.

`switch_to_persian()` returns a callable that restores the previous layout, or None when
no Persian layout is installed or the platform offers no way to switch. It never raises.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys

log = logging.getLogger(__name__)


def _run(*cmd):
    """Run a command and return its stdout, or None on any failure."""
    if not shutil.which(cmd[0]):
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout


def _is_persian(layout):
    # xkb names Persian "ir" (variants: "ir+pes_keypad", "ir(winkeys)", ...)
    return re.match(r"ir\b", layout) is not None


# ---------------------------------------------------------------- GNOME (Wayland and X11)
# GNOME exposes no switching API since 41; the Shyriiwook extension adds one:
# https://extensions.gnome.org/extension/6691/shyriiwook/
_SHYRIIWOOK = ("--dest", "org.gnome.Shell", "--object-path", "/me/madhead/Shyriiwook")


def _gnome():
    def prop(name):
        out = _run(
            "gdbus",
            "call",
            "--session",
            *_SHYRIIWOOK,
            "--method",
            "org.freedesktop.DBus.Properties.Get",
            "me.madhead.Shyriiwook",
            name,
        )
        return re.findall(r"'([^']*)'", out or "")

    def activate(layout):
        _run("gdbus", "call", "--session", *_SHYRIIWOOK, "--method", "me.madhead.Shyriiwook.activate", layout)

    current = prop("currentLayout")
    target = next((x for x in prop("availableLayouts") if _is_persian(x)), None)
    if not current or not target:
        return None
    if current[0] != target:
        activate(target)
    return lambda: activate(current[0])


# ---------------------------------------------------------------- KDE Plasma
_KDE = ("--dest", "org.kde.keyboard", "--object-path", "/Layouts", "--method")


def _kde():
    layouts = _run("gdbus", "call", "--session", *_KDE, "org.kde.KeyboardLayouts.getLayoutsList")
    current = _run("gdbus", "call", "--session", *_KDE, "org.kde.KeyboardLayouts.getLayout")
    if not layouts or not current:
        return None
    names = re.findall(r"\('([^']*)', '[^']*', '[^']*'\)", layouts)
    target = next((i for i, x in enumerate(names) if _is_persian(x)), None)
    previous = int(re.findall(r"\d+", current)[-1])  # reply is "(uint32 N,)"
    if target is None:
        return None

    def activate(index):
        _run("gdbus", "call", "--session", *_KDE, "org.kde.KeyboardLayouts.setLayout", str(index))

    activate(target)
    return lambda: activate(previous)


# ---------------------------------------------------------------- Sway
def _sway():
    out = _run("swaymsg", "-r", "-t", "get_inputs")
    if not out:
        return None
    kbd = next((d for d in json.loads(out) if d.get("type") == "keyboard" and d.get("xkb_layout_names")), None)
    if not kbd:
        return None
    target = next((i for i, x in enumerate(kbd["xkb_layout_names"]) if "Persian" in x), None)
    if target is None:
        return None
    previous = kbd["xkb_active_layout_index"]
    _run("swaymsg", "input", "type:keyboard", "xkb_switch_layout", str(target))
    return lambda: _run("swaymsg", "input", "type:keyboard", "xkb_switch_layout", str(previous))


# ---------------------------------------------------------------- plain X11 (Xfce, Cinnamon, MATE, i3, ...)
def _x11():
    import ctypes
    import ctypes.util

    query = _run("setxkbmap", "-query")
    layouts = re.search(r"^layout:\s*(\S+)", query or "", re.MULTILINE)
    lib = ctypes.util.find_library("X11")
    if not layouts or not lib:
        return None
    target = next((i for i, x in enumerate(layouts.group(1).split(",")) if _is_persian(x)), None)
    if target is None:
        return None
    x11 = ctypes.CDLL(lib)
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XkbGetState.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
    x11.XkbLockGroup.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    x11.XFlush.argtypes = x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    use_core_kbd = 0x100
    display = x11.XOpenDisplay(None)
    if not display:
        return None
    state = ctypes.create_string_buffer(64)  # XkbStateRec; its first byte is the active group
    x11.XkbGetState(display, use_core_kbd, state)
    previous = state.raw[0]

    def lock(group):
        x11.XkbLockGroup(display, use_core_kbd, group)
        x11.XFlush(display)

    lock(target)
    return lambda: (lock(previous), x11.XCloseDisplay(display))


# ---------------------------------------------------------------- Windows
def _windows():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetKeyboardLayout.restype = wintypes.HKL
    user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(wintypes.HKL)]
    user32.ActivateKeyboardLayout.argtypes = [wintypes.HKL, wintypes.UINT]
    user32.ActivateKeyboardLayout.restype = wintypes.HKL

    count = user32.GetKeyboardLayoutList(0, None)
    layouts = (wintypes.HKL * count)()
    user32.GetKeyboardLayoutList(count, layouts)
    persian_langid = 0x0429  # low word of an HKL is its language id
    target = next((h for h in layouts if h and h & 0xFFFF == persian_langid), None)
    if target is None:
        return None
    previous = user32.GetKeyboardLayout(0)  # 0 = this (the GUI) thread
    user32.ActivateKeyboardLayout(target, 0)
    return lambda: user32.ActivateKeyboardLayout(previous, 0)


# ---------------------------------------------------------------- macOS
def _macos():
    import ctypes
    import ctypes.util

    carbon = ctypes.CDLL(ctypes.util.find_library("Carbon"))
    cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
    vp = ctypes.c_void_p
    for name, res, args in (
        ("TISCreateInputSourceList", vp, [vp, ctypes.c_bool]),
        ("TISCopyCurrentKeyboardInputSource", vp, []),
        ("TISGetInputSourceProperty", vp, [vp, vp]),
        ("TISSelectInputSource", ctypes.c_int32, [vp]),
    ):
        getattr(carbon, name).restype, getattr(carbon, name).argtypes = res, args
    cf.CFArrayGetCount.restype, cf.CFArrayGetCount.argtypes = ctypes.c_long, [vp]
    cf.CFArrayGetValueAtIndex.restype, cf.CFArrayGetValueAtIndex.argtypes = vp, [vp, ctypes.c_long]
    cf.CFStringGetCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFRetain.restype, cf.CFRetain.argtypes = vp, [vp]
    cf.CFRelease.argtypes = [vp]
    source_id = vp.in_dll(carbon, "kTISPropertyInputSourceID")
    selectable = vp.in_dll(carbon, "kTISPropertyInputSourceIsSelectCapable")
    true = vp.in_dll(cf, "kCFBooleanTrue").value

    def text(cfstring):
        buf = ctypes.create_string_buffer(256)
        cf.CFStringGetCString(cfstring, buf, 256, 0x08000100)  # kCFStringEncodingUTF8
        return buf.value.decode()

    sources = carbon.TISCreateInputSourceList(None, False)  # enabled sources only
    target = None
    for i in range(cf.CFArrayGetCount(sources)):
        src = cf.CFArrayGetValueAtIndex(sources, i)
        sid = text(carbon.TISGetInputSourceProperty(src, source_id))
        if "Persian" in sid and carbon.TISGetInputSourceProperty(src, selectable) == true:
            target = cf.CFRetain(src)
            break
    cf.CFRelease(sources)
    if target is None:
        return None
    previous = carbon.TISCopyCurrentKeyboardInputSource()
    carbon.TISSelectInputSource(target)
    return lambda: (carbon.TISSelectInputSource(previous), cf.CFRelease(previous), cf.CFRelease(target))


def _linux_backends():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "GNOME" in desktop or "UNITY" in desktop:
        return [_gnome]  # mutter overrides X11 group changes, so the extension is the only way
    if "KDE" in desktop:
        return [_kde]
    if os.environ.get("SWAYSOCK"):
        return [_sway]
    if os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return [_x11]
    return []  # shortcut: other Wayland compositors (Hyprland, ...) unsupported; add a backend on request


def switch_to_persian():
    if sys.platform == "win32":
        backends = [_windows]
    elif sys.platform == "darwin":
        backends = [_macos]
    else:
        backends = _linux_backends()
    for backend in backends:
        try:
            restore = backend()
        except Exception:  # a missing API must never stop the app from starting
            log.exception("keyboard layout: %s failed", backend.__name__)
            continue
        if restore:
            return _safe(restore)
    return None


def _safe(restore):
    def wrapper():
        try:
            restore()
        except Exception:
            log.exception("keyboard layout: restore failed")

    return wrapper
