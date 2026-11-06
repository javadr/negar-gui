import json

import pytest

from negar_gui import keyboard_layout as kl


@pytest.fixture
def fake_run(monkeypatch):
    """Replace command execution: reply with the first response whose key is an argument."""
    calls = []

    def install(responses):
        def run(*cmd):
            calls.append(cmd)
            return next((out for key, out in responses.items() if key in cmd), "")

        monkeypatch.setattr(kl, "_run", run)
        return calls

    return install


def test_is_persian():
    assert kl._is_persian("ir") and kl._is_persian("ir+pes_keypad") and kl._is_persian("ir(winkeys)")
    assert not kl._is_persian("us") and not kl._is_persian("iq")


def test_gnome_switches_and_restores(fake_run):
    calls = fake_run({"currentLayout": "(<'us'>,)", "availableLayouts": "(<['us', 'ir+pes_keypad', 'de']>,)"})
    restore = kl._gnome()
    assert calls[-1][-1] == "ir+pes_keypad"
    restore()
    assert calls[-1][-1] == "us"


def test_gnome_without_extension_or_persian(fake_run, monkeypatch):
    monkeypatch.setattr(kl, "_run", lambda *cmd: None)
    assert kl._gnome() is None
    fake_run({"currentLayout": "(<'us'>,)", "availableLayouts": "(<['us', 'de']>,)"})
    assert kl._gnome() is None


def test_kde_switches_and_restores(fake_run):
    calls = fake_run(
        {
            "org.kde.KeyboardLayouts.getLayoutsList": "([('us', '', 'English (US)'), ('ir', '', 'Persian')],)",
            "org.kde.KeyboardLayouts.getLayout": "(uint32 0,)",
        }
    )
    restore = kl._kde()
    assert calls[-1][-1] == "1"
    restore()
    assert calls[-1][-1] == "0"  # not the "32" of "uint32"


def test_sway_switches_and_restores(fake_run):
    inputs = [
        {"type": "pointer"},
        {"type": "keyboard", "xkb_layout_names": ["English (US)", "Persian"], "xkb_active_layout_index": 0},
    ]
    calls = fake_run({"get_inputs": json.dumps(inputs)})
    restore = kl._sway()
    assert calls[-1][-1] == "1"
    restore()
    assert calls[-1][-1] == "0"


def test_failing_backend_does_not_raise(monkeypatch):
    monkeypatch.setattr(kl.sys, "platform", "linux")
    monkeypatch.setattr(kl, "_linux_backends", lambda: [lambda: 1 / 0])
    assert kl.switch_to_persian() is None
