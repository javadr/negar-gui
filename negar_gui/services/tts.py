"""Offline Persian text-to-speech with a choice of engines (ENGINES):

* tiny-ava: Tiny Ava (mehdi-hf/tiny-ava, 4.5M parameters, ONNX Runtime, no torch). Tiny (~30 MB), open repo, CPU only.
* cilla-lite: Cilla Lite (mehdi-hf/cilla-lite), same family and files layout as Cilla Mini, 109M parameters.
* cilla: Cilla Mini (mehdi-hf/cilla-mini, pocket-tts based). Small (112 MB), loads fast, runs on the CPU.
* chatterbox: Chatterbox Farsi (mehdi-hf/chatterbox-farsi, a Chatterbox fine-tune). Better voice and zero-shot cloning,
  3 GB, slow to load; wants an NVIDIA GPU (it runs on the CPU, much slower than real time).

Synthesis runs in a child process (python -m negar_gui.services.tts <engine>): importing torch inside the Qt process crashed the
whole app (SIGSEGV in libtriton/LLVM) and a busy worker thread starved the UI. The child talks to the app through
"@@{json}" lines on stdout; a crash there only fails the read-aloud request, and cancelling just kills it.

The packages are optional and imported lazily. Both model repos are gated: each user accepts the terms once and logs
in to Hugging Face. After the first download they run offline.
"""

import fnmatch
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import wave
from pathlib import Path

PAUSE_SEC = 0.15  # between sentences
FROZEN = getattr(sys, "frozen", False)  # PyInstaller build: only Tiny Ava is inside (no torch), sys.executable is Negar
BUNDLE = Path(getattr(sys, "_MEIPASS", ".")) / "tinyava"  # the models of the standalone executable
CILLA = "mehdi-hf/cilla-mini"
CILLA_LITE = "mehdi-hf/cilla-lite"
TINY = "mehdi-hf/tiny-ava"
TINY_G2P = (
    "https://raw.githubusercontent.com/mallahyari/tiny-ava/main/demo/assets/g2p/"  # the G2P models are not on the hub
)
CHATTERBOX = "mehdi-hf/chatterbox-farsi"
CHATTERBOX_BASE = "ResembleAI/chatterbox"
CILLA_SKIP = ["phonon/*", "samples/*", "prompts/voice*.wav", "*.md", ".gitattributes"]  # Mac/browser runtimes, demos
LITE_SKIP = ["samples/*", "prompts/voice2.wav", "*.md", ".gitattributes"]  # demos, the second voice, docs
CHATTERBOX_BASE_FILES = ["ve.pt", "s3gen.pt", "conds.pt", "grapheme_mtl_merged_expanded_v1.json", "Cangjie5_TC.json"]
ENGINES = {
    "tiny-ava": {
        "title": "Tiny (Tiny Ava, CPU, 30 MB)",
        "fa": "ریز (آوای ریزمیزه، پردازنده، ۳۰ مگابایت)",
        "packages": ("onnxruntime", "numpy"),
        "pip": "pip install onnxruntime numpy",
        "page": f"https://huggingface.co/{TINY}",
        "files": {TINY: {"allow_patterns": ["onnx/*"]}},
        "urls": [TINY_G2P + "g2p_encoder.onnx", TINY_G2P + "g2p_decoder.onnx"],
        "license": '(CC BY 4.0: public use must say "Powered by tiny-ava (Mehdi Allahyari / OncillaAI)".)',
        "license_fa": "(CC BY 4.0: در استفادهٔ عمومی باید نوشته شود «Powered by tiny-ava (Mehdi Allahyari / OncillaAI)».)",
    },
    "cilla": {
        "title": "Fast (Cilla Mini, CPU)",
        "fa": "سریع (سیلا مینی، پردازنده)",
        "packages": ("torch", "pocket_tts"),
        "pip": 'pip install --extra-index-url https://download.pytorch.org/whl/cpu torch "pocket-tts>=4.0.1"',
        "page": f"https://huggingface.co/{CILLA}",
        "files": {CILLA: {"ignore_patterns": CILLA_SKIP}},
        "license": "(The model is non-commercial: CC BY-NC 4.0.)",
        "license_fa": "(مدل غیرتجاری است: CC BY-NC 4.0.)",
    },
    "cilla-lite": {
        "title": "Balanced (Cilla Lite, CPU)",
        "fa": "متعادل (سیلا لایت، پردازنده)",
        "packages": ("torch", "pocket_tts"),
        "pip": 'pip install --extra-index-url https://download.pytorch.org/whl/cpu torch "pocket-tts>=4.0.1"',
        "page": f"https://huggingface.co/{CILLA_LITE}",
        "files": {CILLA_LITE: {"ignore_patterns": LITE_SKIP}},
        "license": "(The model is non-commercial: CC BY-NC 4.0.)",
        "license_fa": "(مدل غیرتجاری است: CC BY-NC 4.0.)",
    },
    "chatterbox": {
        "title": "High quality (Chatterbox Farsi, GPU recommended)",
        "fa": "کیفیت بالا (چتربکس فارسی، کارت گرافیک توصیه می‌شود)",
        "packages": ("torch", "chatterbox"),
        "pip": 'pip install chatterbox-tts "setuptools<81"',
        "page": f"https://huggingface.co/{CHATTERBOX}",
        "files": {
            CHATTERBOX: {"allow_patterns": ["t3_fa.safetensors", "voices/female.wav"]},
            CHATTERBOX_BASE: {"allow_patterns": CHATTERBOX_BASE_FILES},
        },
        "license": (
            '(The model is non-commercial; public use must say "Powered by OncillaAI Chatterbox Farsi". '
            "Output carries an inaudible watermark.)"
        ),
        "license_fa": (
            "(مدل غیرتجاری است؛ در استفادهٔ عمومی باید نوشته شود «Powered by OncillaAI Chatterbox Farsi». "
            "خروجی دارای واترمارک نامحسوس است.)"
        ),
    },
}
DEFAULT_ENGINE = "cilla"
if FROZEN:  # the other engines need torch, which the executable does not carry
    ENGINES, DEFAULT_ENGINE = {"tiny-ava": ENGINES["tiny-ava"]}, "tiny-ava"
_engine = DEFAULT_ENGINE  # the one the app asked for; the child process of another one is replaced on the next request


def hints(name):
    """(install hint, gated hint) in English and Persian for engine name: {english: persian}."""
    e = ENGINES[name]
    install = (
        "Read Aloud is not part of the standalone executable.\nInstall Negar-GUI with pip to use it (see the README)."
        if FROZEN
        else f"Text-to-speech needs optional packages (Python 3.10+):\n{e['pip']}"
    )
    install_fa = (
        "خواندن متن در فایل اجرایی مستقل وجود ندارد.\nNegar-GUI را با pip نصب کنید (به README نگاه کنید)."
        if FROZEN
        else f"تبدیل متن به گفتار به بسته‌های اختیاری نیاز دارد (پایتون ۳.۱۰ به بالا):\n{e['pip']}"
    )
    gated = (
        f"The voice model is gated. Once, in a browser: open {e['page']} and accept the terms. Then create a Read "
        "token at https://huggingface.co/settings/tokens and run:\nhf auth login --token <your token>\n\n"
        + e["license"]
    )
    gated_fa = (
        f"دسترسی به مدل صوتی محدود است. یک بار در مرورگر: {e['page']} را باز کنید و شرایط را بپذیرید. سپس در "
        "https://huggingface.co/settings/tokens یک توکن Read بسازید و اجرا کنید:\nhf auth login --token <your token>"
        "\n\n" + e["license_fa"]
    )
    return {install: install_fa, gated: gated_fa}


def install_hint(name=None):
    return next(iter(hints(name or _engine)))


NO_PERSIAN = "The text has no Persian letters: English words and symbols are skipped, write them in Persian."
NO_PERSIAN_FA = "متن حروف فارسی ندارد: واژه‌ها و نمادهای انگلیسی خوانده نمی‌شوند، آن‌ها را فارسی بنویسید."


def localized(message, persian):
    """The Persian version of one of our messages (any engine's), or the message itself."""
    if not persian:
        return message
    table = {NO_PERSIAN: NO_PERSIAN_FA}
    for name in ENGINES:
        table.update(hints(name))
    return table.get(message, message)


class TTSError(RuntimeError):
    """A problem to show the user as is."""


class Cancelled(Exception):
    pass


def _wanted(name, kw):
    allow, ignore = kw.get("allow_patterns") or ["*"], kw.get("ignore_patterns") or []
    return any(fnmatch.fnmatch(name, p) for p in allow) and not any(fnmatch.fnmatch(name, p) for p in ignore)


def _cached(name):
    """True when every file of the engine is already in the hub cache (no network needed)."""
    from huggingface_hub import snapshot_download

    for repo, kw in ENGINES[name]["files"].items():
        snapshot_download(repo, local_files_only=True, **kw)
    for url in ENGINES[name].get("urls", []):
        if not _url_path(url).exists():
            raise FileNotFoundError(url)


def _url_path(url):
    from huggingface_hub.constants import HF_HOME

    return Path(HF_HOME) / "negar-tts" / url.rsplit("/", 1)[1]


def _download(name, progress, stop):
    """Fetch the engine's files into the hub cache, reporting progress(done_bytes, total_bytes). No-op when cached."""
    from huggingface_hub import HfApi, snapshot_download
    from tqdm.auto import tqdm

    files = ENGINES[name]["files"]
    try:
        _cached(name)
        return
    except Exception:  # noqa: BLE001, S110  # any failure here just means: download
        pass
    api = HfApi()
    total = sum(
        f.size or 0
        for repo, kw in files.items()
        for f in api.model_info(repo, files_metadata=True).siblings
        if _wanted(f.rfilename, kw)
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

    for repo, kw in files.items():
        snapshot_download(repo, tqdm_class=Bar, **kw)
    for url in ENGINES[name].get("urls", []):
        path = _url_path(url)
        if not path.exists():
            if stop.is_set():
                raise Cancelled
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")  # never leave a truncated model that _cached would accept
            urllib.request.urlretrieve(url, tmp)  # noqa: S310  # fixed https URL above
            tmp.replace(path)


def available(name=None):
    name = name or _engine
    if FROZEN:
        return name == "tiny-ava"  # models and onnxruntime are inside the executable
    return sys.version_info >= (3, 10) and all(importlib.util.find_spec(p) for p in ENGINES[name]["packages"])


def engine():
    return _engine


def set_engine(name):
    """Choose the engine for the next request; the running one (if another) is stopped."""
    global _engine
    if name in ENGINES and name != _engine:
        _engine = name
        shutdown()


_CMD = (
    [sys.executable, "--tts-worker"]  # main.py hands this over to worker()
    if FROZEN
    else [sys.executable, "-m", "negar_gui.services.tts"]
)  # the engine name is appended  # tests replace this with a fake worker
_proc = None  # the engine stays loaded between requests: loading torch and the model takes seconds
_err = None
_lock = threading.Lock()


def _start():
    global _proc, _err
    _err = tempfile.TemporaryFile()  # noqa: SIM115  # stderr of the child, read on failure
    _proc = subprocess.Popen(
        [*_CMD, _engine],
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
            FROZEN or _cached(_engine)
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
        raise TTSError(install_hint())
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


def _load(name):
    """Download (first use) and load the engine; returns (speak, sample_rate), or None after reporting an error.

    speak(text) yields the audio (float32 numpy) of each sentence of one segment.
    """
    if FROZEN:  # nothing to download: the models are in the executable
        return _load_tiny()
    from huggingface_hub.errors import GatedRepoError, RepositoryNotFoundError

    last = [-2]

    def progress(done, total):  # called hundreds of times a second: report only when the percent moves
        pct = done * 100 // total if total else -1
        if pct != last[0]:
            last[0] = pct
            _say(p=[done, total])

    try:
        _download(name, progress, threading.Event())
    except (GatedRepoError, RepositoryNotFoundError):  # 401 until the terms are accepted and a token is set
        return _say(err=list(hints(name))[1])
    progress(0, 0)  # downloaded (or cached): now loading into memory
    loaders = {"chatterbox": _load_chatterbox, "tiny-ava": _load_tiny}
    return loaders[name]() if name in loaders else _load_cilla(name)


def _snap(repo):
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo, local_files_only=True, **_repo_kw(repo)))


def _repo_kw(repo):
    return next(kw for e in ENGINES.values() for r, kw in e["files"].items() if r == repo)


def _load_cilla(name):
    from pocket_tts import TTSModel

    repo, voice = (CILLA, "prompts/parisa.wav") if name == "cilla" else (CILLA_LITE, "prompts/voice1.wav")
    snap = _snap(repo)
    sys.path.insert(0, str(snap))  # normalize_fa.py and speak_fa.py come with the weights
    import speak_fa as sf

    # The shipped config points at hf:// URLs; point it at the cached files so loading needs no network or login
    cfg = (snap / "config.yaml").read_text(encoding="utf-8")
    for f in ("model.safetensors", "tokenizer.model"):
        cfg = cfg.replace(f"hf://{repo}/{f}", str((snap / f).resolve()))
    with tempfile.TemporaryDirectory(prefix="negar-tts-cfg-") as tmp:
        cfg_path = Path(tmp) / "config.yaml"
        cfg_path.write_text(cfg, encoding="utf-8")
        model = TTSModel.load_model(config=str(cfg_path), temp=0.3, eos_threshold=-2.0)
    state = model.get_state_for_audio_prompt(str(snap / voice))  # a 3-10 s clip ending at a pause
    sr, sp = int(model.mimi.sample_rate), model.flow_lm.conditioner.tokenizer.sp

    def speak(seg):
        text = sf.normalize(sf.with_end(" ".join(seg.split())))
        if not text.strip():
            return
        for piece in sf.split_sentences(text, lambda s: len(sp.encode(s))):
            # one sentence per piece, never cut inside it: a cut made the model repeat words
            audio = sf.generate_chunk(model, state, piece, frames_after_eos=0, sample_rate=sr, max_tokens=10_000)
            yield sf.clean_start(sf.trim_silence(audio, sr), sr)

    return speak, sr


TINY_IPA = {
    "a": "a",
    "A": "ɑ",
    "e": "e",
    "o": "o",
    "i": "i",
    "u": "u",
    "p": "p",
    "b": "b",
    "t": "t",
    "d": "d",
    "k": "k",
    "g": "ɡ",
    "q": "q",
    "?": "ʔ",
    "f": "f",
    "v": "v",
    "s": "s",
    "z": "z",
    "S": "ʃ",
    "Z": "ʒ",
    "x": "x",
    "h": "h",
    "C": "tʃ",
    "j": "dʒ",
    "m": "m",
    "n": "n",
    "l": "l",
    "r": "r",
    "y": "j",
}  # from the tiny-ava README
TINY_VOWELS = {"a", "e", "o", "i", "u", "ɑ"}


def _load_tiny():
    import numpy as np
    import onnxruntime as ort

    snap = BUNDLE if FROZEN else _snap(TINY) / "onnx"
    g2p = [
        ort.InferenceSession(str(BUNDLE / u.rsplit("/", 1)[1] if FROZEN else _url_path(u)))
        for u in ENGINES["tiny-ava"]["urls"]
    ]
    model = ort.InferenceSession(str(snap / "tiny-ava-parisa.onnx"))
    symbols = json.loads((snap / "tiny-ava-parisa.json").read_text(encoding="utf-8"))["symbols"]
    sym2id, phones = {s: i for i, s in enumerate(symbols)}, set(symbols[17:])

    def phonemes(text):
        enc, dec = g2p
        ids = np.array([[b + 3 for b in text.encode("utf-8")] + [1]], dtype=np.int64)
        attn = np.ones_like(ids)
        (hidden,) = enc.run(None, {"input_ids": ids, "attention_mask": attn})
        out = [0]
        for _ in range(256):
            (logits,) = dec.run(
                None,
                {
                    "decoder_input_ids": np.array([out], dtype=np.int64),
                    "encoder_hidden_states": hidden,
                    "encoder_attention_mask": attn,
                },
            )
            nxt = int(logits[0, -1].argmax())
            if nxt == 1:
                break
            out.append(nxt)
        return bytes(i - 3 for i in out[1:] if 3 <= i <= 258).decode("utf-8", errors="ignore").strip()

    def speak(seg):
        text = " ".join(seg.split())
        if not re.search(r"[\u0600-\u06FF]", text):
            return
        syms, stress = ["<bos>"], [0]
        for word in phonemes(text).split():
            if syms[-1] in phones:
                syms.append("<sp>")
                stress.append(0)
            stem, ez = (
                (word[:-3], "ye") if word.endswith("-ye") else (word[:-2], "e") if word.endswith("-e") else (word, "")
            )
            stem = stem.replace("-", "")
            if len(stem) >= 2 and stem[0] == "?" and stem[1] in "aAeoiu":
                stem = stem[1:]
            phs = [[TINY_IPA[c], 0] for c in stem if c in TINY_IPA]
            for ph in reversed(phs):  # stress the last vowel
                if ph[0] in TINY_VOWELS:
                    ph[1] = 1
                    break
            phs += [[TINY_IPA[c], 2 if TINY_IPA[c] in TINY_VOWELS else 0] for c in ez if c in TINY_IPA]
            syms += [p for p, _ in phs]
            stress += [lvl for _, lvl in phs]
        syms += [".", "<eos>"]
        stress += [0, 0]
        audio, _ = model.run(
            None,
            {
                "tokens": np.array([[sym2id[s] for s in syms]], dtype=np.int64),
                "stress": np.array([stress], dtype=np.int64),
                "voice": np.array([0], dtype=np.int64),
                "speed": np.array([1.0], dtype=np.float32),
                "pitch_shift": np.array([0.0], dtype=np.float32),
                "pitch_range": np.array([1.05], dtype=np.float32),
            },
        )
        yield audio[0]

    return speak, 24000


def _load_chatterbox():
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    mine, base = _snap(CHATTERBOX), _snap(CHATTERBOX_BASE)
    with tempfile.TemporaryDirectory(prefix="negar-tts-ckpt-") as tmp:
        # from_local wants one folder with fixed file names: link the cached files together (copy where links fail)
        links = {n: base / n for n in CHATTERBOX_BASE_FILES}
        links["t3_mtl23ls_v2.safetensors"] = mine / "t3_fa.safetensors"
        for name, src in links.items():
            try:
                (Path(tmp) / name).symlink_to(src.resolve())
            except OSError:
                shutil.copy(src, Path(tmp) / name)
        model = ChatterboxMultilingualTTS.from_local(tmp, "cuda" if torch.cuda.is_available() else "cpu")
    voice = str(mine / "voices/female.wav")

    def speak(seg):
        text = " ".join(seg.split())
        if not re.search(r"[\u0600-\u06FF]", text):
            return
        for _ in range(3):  # now and then the model stops almost at once: take such a cut-off take again
            wav = model.generate(text, language_id="ar", audio_prompt_path=voice)  # Persian uses Arabic's token
            if wav.shape[-1] / model.sr >= len(text) / 40:  # Persian speech runs at ~12-15 characters a second
                break
        yield wav.squeeze().cpu().numpy()

    return speak, int(model.sr)


def _speak(engine, folder, segs):
    import numpy as np

    speak, sr = engine
    n = 0
    for seg_no, seg in enumerate(segs):
        for audio in speak(seg):
            audio = np.concatenate([audio.astype(np.float32), np.zeros(int(PAUSE_SEC * sr), np.float32)])
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
        _say(err=NO_PERSIAN)


def _serve(name):
    """Load once, then answer one JSON request per stdin line until the app closes the pipe."""
    engine = _load(name)
    if not engine:
        return
    for line in sys.stdin:
        req = json.loads(line)
        try:
            _speak(engine, req["dir"], req["segs"])
        except Exception as e:  # noqa: BLE001  # a bad request must not take the loaded model down
            _say(err=f"Could not run the TTS model: {e}")
        _say(done=1)


def worker(name):
    """Entry of the child process in the standalone executable (see main.py)."""
    if sys.stdin is None or sys.stdout is None:  # a windowed exe may start without console handles
        sys.stdin = open(0, encoding="utf-8", closefd=False)  # noqa: SIM115
        sys.stdout = open(1, "w", encoding="utf-8", closefd=False)  # noqa: SIM115
    _serve(name)


if __name__ == "__main__":
    try:
        _serve(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ENGINE)
    except Exception as e:  # noqa: BLE001  # whatever it is, tell the app instead of dying with a traceback
        _say(err=f"Could not run the TTS model: {e}")
