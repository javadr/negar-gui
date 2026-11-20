"""Offline Persian text-to-speech: Cilla Mini (mehdi-hf/cilla-mini, pocket-tts based) on CPU.

Synthesis runs in a child process (python -m negar_gui.tts): importing torch inside the Qt process crashed the
whole app (SIGSEGV in libtriton/LLVM) and a busy worker thread starved the UI. The child talks to the app through
"@@{json}" lines on stdout; a crash there only fails the read-aloud request, and cancelling just kills it.

The model repo ships its own text frontend (normalize_fa.py) and sentence pipeline (speak_fa.py); both are
downloaded with the weights and reused here. torch / pocket-tts are optional and imported lazily. The repo is
gated: each user accepts its terms once and logs in to Hugging Face. After the first download it runs offline.
"""

import fnmatch
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

MODEL_ID = "mehdi-hf/cilla-mini"
VOICE = "prompts/parisa.wav"  # bundled in the model repo: a 3-10 s clip ending at a pause, as the model needs
PAUSE_SEC = 0.15  # between sentences
SKIP = ["phonon/*", "samples/*", "prompts/voice*.wav", "*.md", ".gitattributes"]  # Mac/browser runtimes, demos, docs
FROZEN = getattr(sys, "frozen", False)  # PyInstaller build: no torch inside, and sys.executable is Negar itself
INSTALL_HINT = (
    "Read Aloud is not part of the standalone executable.\nInstall Negar-GUI with pip to use it (see the README)."
    if FROZEN
    else "Text-to-speech needs optional packages (Python 3.10+):\n"
    'pip install --extra-index-url https://download.pytorch.org/whl/cpu torch "pocket-tts>=4.0.1"'
)
GATED_HINT = (
    "The voice model is gated. Once, in a browser: open https://huggingface.co/mehdi-hf/cilla-mini and accept the "
    "terms. Then create a Read token at https://huggingface.co/settings/tokens and run:\n"
    "hf auth login --token <your token>\n\n(The model is non-commercial: CC BY-NC 4.0.)"
)


class TTSError(RuntimeError):
    """A problem to show the user as is."""


class Cancelled(Exception):
    pass


def _download(progress, stop, repos=(MODEL_ID,), skip=SKIP):
    """Fetch the model repos into the hub cache, reporting progress(done_bytes, total_bytes). No-op when cached."""
    from huggingface_hub import HfApi, snapshot_download
    from tqdm.auto import tqdm

    try:
        for repo in repos:
            snapshot_download(repo, ignore_patterns=skip, local_files_only=True)
        return
    except Exception:  # noqa: BLE001, S110  # any failure here just means: download
        pass
    api = HfApi()
    total = sum(
        f.size or 0
        for repo in repos
        for f in api.model_info(repo, files_metadata=True).siblings
        if not any(fnmatch.fnmatch(f.rfilename, pat) for pat in skip)
    )
    done = [0]

    class Bar(tqdm):
        def update(self, n=1):
            if stop.is_set():
                raise Cancelled
            # hf_xet adds a "Reconstructing" byte bar that mirrors the download; counting it doubles the total
            if self.unit == "B" and not str(self.desc).startswith("Reconstruct"):
                done[0] += n
                progress(min(done[0], total), total)
            return super().update(n)

    for repo in repos:
        snapshot_download(repo, ignore_patterns=skip, tqdm_class=Bar)


def available():
    return (
        not FROZEN and sys.version_info >= (3, 10) and all(importlib.util.find_spec(p) for p in ("torch", "pocket_tts"))
    )


_CMD = [sys.executable, "-m", "negar_gui.tts"]  # tests replace this with a fake worker
_proc = None  # the engine stays loaded between requests: loading torch and the model takes seconds
_err = None
_lock = threading.Lock()


def _start():
    global _proc, _err
    _err = tempfile.TemporaryFile()  # noqa: SIM115  # stderr of the child, read on failure
    _proc = subprocess.Popen(
        _CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=_err,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUNBUFFERED": "1", "HF_HUB_DISABLE_PROGRESS_BARS": "1"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def segments(text):
    """Split text into sentences as (start, end) offsets, so the caller can highlight what is being read."""
    return [(m.start(1), m.end(1)) for m in re.finditer(r"\s*([^.!?؟؛…\n]*[^\s.!?؟؛…][.!?؟؛…]*)", text)]


def preload():
    """Start loading the engine in the background, but only if the model is already on disk: never download unasked."""

    def go():
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(MODEL_ID, ignore_patterns=SKIP, local_files_only=True)
        except Exception:  # noqa: BLE001  # not downloaded (or hub missing): the first Read Aloud will explain
            return
        with _lock:
            if _proc is None or _proc.poll() is not None:
                _start()

    if available():
        threading.Thread(target=go, daemon=True).start()


def shutdown():
    """Stop the engine (also what cancelling does: the next request starts a fresh one)."""
    global _proc
    proc, _proc = _proc, None
    if proc and proc.poll() is None:
        proc.kill()
        proc.wait()


def synthesize(text, stop, progress=lambda done, total: None, folder=None):
    """Yield (path, n) for each sentence spoken: a wav file under folder (pause included) and the number n of the
    entry of segments(text) it belongs to.

    stop is a threading.Event; setting it kills the engine. progress(done, total) reports the first-use download
    in bytes; (0, 0) means loading the model, which only the first request after a start has to wait for.
    """
    folder = folder or tempfile.mkdtemp(prefix="negar-tts-")
    if not available():
        raise TTSError(INSTALL_HINT)
    with _lock:  # one request at a time
        if _proc is None or _proc.poll() is not None:
            _start()
        proc, err = _proc, _err
        finished = threading.Event()

        def reaper():
            while not (stop.is_set() or finished.is_set()):
                stop.wait(0.2)
            if stop.is_set() and not finished.is_set():  # a stop after the reading ended must keep the engine
                shutdown()

        threading.Thread(target=reaper, daemon=True).start()
        message, done = None, False
        try:
            proc.stdin.write(json.dumps({"dir": folder, "segs": [text[a:b] for a, b in segments(text)]}) + "\n")
            proc.stdin.flush()
            for line in proc.stdout:
                if not line.startswith("@@"):
                    continue  # stray prints from libraries
                msg = json.loads(line[2:])
                if "p" in msg:
                    progress(*msg["p"])
                elif "wav" in msg:
                    yield msg["wav"], msg.get("seg", 0)
                elif "err" in msg:
                    message = msg["err"]
                elif "done" in msg:
                    done = True
                    break
        except (BrokenPipeError, OSError):
            pass  # the engine died: reported below
        finally:
            finished.set()
            if not done:  # cancelled, crashed or the consumer stopped early: never leave a half-served engine
                shutdown()
        if stop.is_set():
            return
        if message:
            raise TTSError(message)
        if not done:
            proc.wait()
            err.seek(0)
            tail = err.read().decode("utf-8", "replace").strip().splitlines()[-4:]
            raise TTSError(f"The speech engine stopped unexpectedly (exit code {proc.returncode}).\n" + "\n".join(tail))


# ---- child process -------------------------------------------------------------------------------------------


def _say(**msg):
    print("@@" + json.dumps(msg), flush=True)


def _load():
    """Download (first use) and load the model; returns what _speak needs, or None after reporting an error."""
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import GatedRepoError, RepositoryNotFoundError

    last = [-2]

    def progress(done, total):  # called hundreds of times a second: report only when the percent moves
        pct = done * 100 // total if total else -1
        if pct != last[0]:
            last[0] = pct
            _say(p=[done, total])

    try:
        _download(progress, threading.Event())
    except (GatedRepoError, RepositoryNotFoundError):  # 401 until the terms are accepted and a token is set
        return _say(err=GATED_HINT)
    progress(0, 0)  # downloaded (or cached): now loading into memory
    from pocket_tts import TTSModel

    snap = Path(snapshot_download(MODEL_ID, ignore_patterns=SKIP, local_files_only=True))
    sys.path.insert(0, str(snap))  # normalize_fa.py and speak_fa.py come with the weights
    import speak_fa as sf

    # The shipped config points at hf:// URLs; point it at the cached files so loading needs no network or login
    cfg = (snap / "config.yaml").read_text(encoding="utf-8")
    for name in ("model.safetensors", "tokenizer.model"):
        cfg = cfg.replace(f"hf://{MODEL_ID}/{name}", str((snap / name).resolve()))
    with tempfile.TemporaryDirectory(prefix="negar-tts-cfg-") as tmp:
        cfg_path = Path(tmp) / "config.yaml"
        cfg_path.write_text(cfg, encoding="utf-8")
        model = TTSModel.load_model(config=str(cfg_path), temp=0.3, eos_threshold=-2.0)
    state = model.get_state_for_audio_prompt(str(snap / VOICE))
    return model, state, int(model.mimi.sample_rate), model.flow_lm.conditioner.tokenizer.sp, sf


def _speak(engine, folder, segs):
    import numpy as np

    model, state, sr, sp, sf = engine
    n = 0
    for seg_no, seg in enumerate(segs):
        text = sf.normalize(sf.with_end(" ".join(seg.split())))
        if not text.strip():
            continue
        for piece in sf.split_sentences(text, lambda s: len(sp.encode(s))):
            # one sentence per piece, never cut inside it: a cut made the model repeat words
            audio = sf.generate_chunk(model, state, piece, frames_after_eos=0, sample_rate=sr, max_tokens=10_000)
            audio = np.concatenate(
                [sf.clean_start(sf.trim_silence(audio, sr), sr), np.zeros(int(PAUSE_SEC * sr), np.float32)]
            )
            audio = audio * min(4.0, 0.9 / max(float(np.abs(audio).max()), 1e-6))  # model output peaks near 0.25
            path = str(Path(folder) / f"{n}.wav")
            n += 1
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes((audio.clip(-1, 1) * 32767).astype("<i2").tobytes())
            _say(wav=path, seg=seg_no)
    if not n:
        _say(err="The text has no Persian letters: English words and symbols are skipped, write them in Persian.")


def _serve():
    """Load once, then answer one JSON request per stdin line until the app closes the pipe."""
    engine = _load()
    if not engine:
        return
    for line in sys.stdin:
        req = json.loads(line)
        try:
            _speak(engine, req["dir"], req["segs"])
        except Exception as e:  # noqa: BLE001  # a bad request must not take the loaded model down
            _say(err=f"Could not run the TTS model: {e}")
        _say(done=1)


if __name__ == "__main__":
    try:
        _serve()
    except Exception as e:  # noqa: BLE001  # whatever it is, tell the app instead of dying with a traceback
        _say(err=f"Could not run the TTS model: {e}")
