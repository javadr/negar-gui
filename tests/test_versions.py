from negar_gui.services import versions


def test_requirements_come_from_the_package_metadata():
    names = {n.lower() for n, _ in versions.requirements()}
    assert {"pyqt6", "rich", "python-negar"} <= names


def test_installed_and_missing():
    assert versions.installed("rich")
    assert versions.installed("no-such-package-xyz") is None


def test_show_prints_a_table(capsys):
    versions.show()
    out = capsys.readouterr().out
    assert "Dependency" in out and "Installed" in out and "PyQt6" in out and "chatterbox-tts" in out


def test_about_has_python_and_platform_and_the_logo_fits_a_terminal():
    rows = dict(versions.about())
    assert rows["Python"].startswith(__import__("platform").python_version())
    assert {"Negar-GUI", "Qt", "Platform"} <= rows.keys()


def test_logo_is_six_rows_and_renders():
    assert len(versions._NEGAR) == 6
    plain = versions.logo().plain
    assert "█" in plain
    assert max(map(len, plain.splitlines())) <= versions.logo_width() <= 64


def test_narrow_terminal_still_prints(monkeypatch, capsys):
    monkeypatch.setenv("COLUMNS", "60")
    versions.show()
    assert "Dependency" in capsys.readouterr().out
