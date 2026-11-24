import sys
import textwrap
import threading
import time

import pytest

from negar_gui.services import tts


def fake(monkeypatch, tmp_path, body):
    script = tmp_path / "fake_worker.py"
    body = textwrap.indent(textwrap.dedent(body), "    ")  # runs once per request, like the real engine
    script.write_text(
        "import json, os, sys, time\n"
        "for line in sys.stdin:\n" + body + "\n"
        "    print('@@' + json.dumps({'done': 1}), flush=True)\n"
    )
    monkeypatch.setattr(tts, "_CMD", [sys.executable, str(script)])
    monkeypatch.setattr(tts, "available", lambda: True)
    tts.shutdown()


def run(tmp_path, stop=None, progress=lambda d, t: None, text="سلام"):
    return list(tts.synthesize(text, stop or threading.Event(), progress, str(tmp_path)))


def test_protocol_progress_and_files(monkeypatch, tmp_path):
    fake(
        monkeypatch,
        tmp_path,
        """
        print("stray library output", flush=True)
        print("@@" + json.dumps({"p": [5, 10]}), flush=True)
        print("@@" + json.dumps({"wav": "a.wav"}), flush=True)
        print("@@" + json.dumps({"wav": "b.wav"}), flush=True)
    """,
    )
    seen = []
    assert run(tmp_path, progress=lambda d, t: seen.append((d, t))) == [("a.wav", 0), ("b.wav", 0)]
    assert seen == [(5, 10)]


def test_segments_offsets():
    text = "سلام. حال شما چطور است؟\n  خوب!"
    assert [text[a:b] for a, b in tts.segments(text)] == ["سلام.", "حال شما چطور است؟", "خوب!"]


def test_engine_is_reused_between_requests(monkeypatch, tmp_path):
    fake(monkeypatch, tmp_path, """print("@@" + json.dumps({"wav": str(os.getpid())}), flush=True)""")
    first, second = run(tmp_path), run(tmp_path)
    assert first == second  # (path, segment) of the same pid  # same process: the model was not loaded again
    tts.shutdown()
    assert run(tmp_path) != first  # after a shutdown a fresh one starts


def test_stop_after_the_reading_keeps_the_engine(monkeypatch, tmp_path):
    fake(monkeypatch, tmp_path, """print("@@" + json.dumps({"wav": str(os.getpid())}), flush=True)""")
    for _ in range(5):  # the window sets stop when a reading ends; the reaper must not take it for a cancel
        stop = threading.Event()
        first = run(tmp_path, stop)
        stop.set()
        time.sleep(0.4)
        assert run(tmp_path) == first


def test_error_message_is_shown_as_is(monkeypatch, tmp_path):
    fake(monkeypatch, tmp_path, """print("@@" + json.dumps({"err": "gated, log in"}), flush=True)""")
    with pytest.raises(tts.TTSError, match="gated, log in"):
        run(tmp_path)


def test_child_crash_does_not_kill_the_caller(monkeypatch, tmp_path):
    fake(
        monkeypatch,
        tmp_path,
        """
        import os, signal
        sys.stderr.write("boom in libtriton\\n"); sys.stderr.flush()
        os.kill(os.getpid(), signal.SIGSEGV) if hasattr(signal, "SIGSEGV") else sys.exit(139)
    """,
    )
    with pytest.raises(tts.TTSError, match=r"(?s)stopped unexpectedly.*boom in libtriton"):
        run(tmp_path)


def test_stop_kills_a_stuck_child_quickly(monkeypatch, tmp_path):
    fake(monkeypatch, tmp_path, "time.sleep(60)\n")
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    t = time.time()
    assert run(tmp_path, stop) == []
    assert time.time() - t < 5


@pytest.fixture(autouse=True)
def _no_engine_left():
    yield
    tts.shutdown()


def test_missing_packages_give_install_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "available", lambda: False)
    with pytest.raises(tts.TTSError, match="pocket-tts"):
        run(tmp_path)


@pytest.mark.skipif(not tts.available(), reason="pocket-tts not installed")
def test_real_synthesis(tmp_path):
    try:
        paths = run(tmp_path)
    except tts.TTSError as e:
        pytest.skip(str(e))  # gated / not downloaded yet
    assert paths


def test_preload_starts_the_engine_only_when_the_model_is_cached(monkeypatch, tmp_path):
    fake(monkeypatch, tmp_path, """print("@@" + json.dumps({"wav": str(os.getpid())}), flush=True)""")
    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    tts.preload()
    time.sleep(0.5)
    assert tts._proc is None  # not downloaded: nothing starts
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *a, **k: "cached")
    tts.preload()
    for _ in range(50):
        if tts._proc:
            break
        time.sleep(0.1)
    pid = tts._proc.pid
    assert run(tmp_path) == [(str(pid), 0)]  # the request is served by the preloaded process


def test_frozen_build_has_only_tiny_ava(monkeypatch):
    monkeypatch.setattr(tts, "FROZEN", True)
    assert tts.available("tiny-ava") and not tts.available("cilla")
    assert "pip" in tts.install_hint("cilla")


def test_set_engine_switches_and_restarts(monkeypatch):
    monkeypatch.setattr(tts, "_engine", "cilla")
    tts.set_engine("chatterbox")
    assert tts.engine() == "chatterbox" and "chatterbox-tts" in tts.install_hint()
    tts.set_engine("nonsense")
    assert tts.engine() == "chatterbox"
    assert "pocket-tts" in tts.install_hint("cilla")
    assert tts.localized(tts.install_hint("cilla"), True) != tts.install_hint("cilla")
