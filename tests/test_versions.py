from negar_gui import versions


def test_requirements_come_from_the_package_metadata():
    names = {n.lower() for n, _ in versions.requirements()}
    assert {"pyqt6", "rich", "python-negar"} <= names


def test_installed_and_missing():
    assert versions.installed("rich")
    assert versions.installed("no-such-package-xyz") is None


def test_show_prints_a_table(capsys):
    versions.show()
    out = capsys.readouterr().out
    assert "Package" in out and "Installed" in out and "PyQt6" in out and "pocket-tts" in out


def test_about_has_python_and_platform_and_the_logo_fits_a_terminal():
    rows = dict(versions.about())
    assert rows["Python"].startswith(__import__("platform").python_version())
    assert {"Negar-GUI", "Qt", "Platform"} <= rows.keys()


def test_logo_falls_back_to_a_title_on_a_narrow_terminal(monkeypatch):
    monkeypatch.setenv("COLUMNS", "30")
    assert versions.logo().plain == "NEGAR-GUI"
    monkeypatch.setenv("COLUMNS", "100")
    assert "▀" in versions.logo().plain
