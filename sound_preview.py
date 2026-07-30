"""
Sound preview helpers for the GUI: play/stop background-music files and render
short narrator-voice samples with Kokoro.

Playback is dependency-free:
- Windows: winsound (stdlib) plays WAV asynchronously; other formats are first
  decoded to a temp WAV with the bundled imageio ffmpeg.
- macOS: afplay (ships with the OS).
- Linux: ffplay when available, else paplay/aplay on a decoded WAV, else the
  desktop's default audio app via xdg-open.

Only one preview plays at a time; starting a new one stops the previous one.
"""

import os
import shutil
import subprocess
import sys
import threading

import soundfile as sf

from paths import resource_path, user_data_root, app_dir

PREVIEW_DIR = os.path.join(user_data_root(), "preview")

VOICE_SAMPLE_TEXT = (
    "This is how your videos will sound. "
    "Pick the voice that fits your channel best."
)

_lock = threading.Lock()
_current_proc = None
_kokoro = None


def _ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _subprocess_kwargs():
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _spawn(args):
    global _current_proc
    _current_proc = subprocess.Popen(args, **_subprocess_kwargs())


def _to_wav(path):
    """Decode any audio file to a temp WAV with the bundled ffmpeg."""
    if path.lower().endswith(".wav"):
        return path
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    wav_path = os.path.join(PREVIEW_DIR, "preview_decoded.wav")
    subprocess.run(
        [_ffmpeg_exe(), "-y", "-i", path, "-acodec", "pcm_s16le", "-ar", "44100", wav_path],
        check=True, **_subprocess_kwargs()
    )
    return wav_path


def play(path):
    """Play an audio file without blocking. Stops any preview already playing."""
    stop()
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Audio file not found: {path}")

    with _lock:
        if os.name == "nt":
            import winsound
            winsound.PlaySound(_to_wav(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif sys.platform == "darwin":
            _spawn(["afplay", path])
        else:
            if shutil.which("ffplay"):
                _spawn(["ffplay", "-nodisp", "-autoexit", "-v", "quiet", path])
            elif shutil.which("paplay"):
                _spawn(["paplay", _to_wav(path)])
            elif shutil.which("aplay"):
                _spawn(["aplay", "-q", _to_wav(path)])
            else:
                # Last resort: hand the file to the desktop's default player
                _spawn(["xdg-open", path])


def stop():
    """Stop whatever preview is currently playing (no-op when idle)."""
    global _current_proc
    with _lock:
        if os.name == "nt":
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        if _current_proc is not None and _current_proc.poll() is None:
            try:
                _current_proc.terminate()
            except Exception:
                pass
        _current_proc = None


def _kokoro_model_paths():
    """Find the Kokoro model: bundled copy first, then the downloaded one."""
    downloaded = os.path.join(app_dir(), "models")
    candidates = [
        (resource_path("models", "kokoro-v0_19.int8.onnx"), resource_path("models", "voices.bin")),
        (os.path.join(downloaded, "kokoro-v0_19.int8.onnx"), os.path.join(downloaded, "voices.bin")),
        (os.path.join(downloaded, "kokoro-v0_19.int8.onnx"), os.path.join(downloaded, "voices.json")),
    ]
    for onnx, voices in candidates:
        if os.path.exists(onnx) and os.path.exists(voices):
            return onnx, voices
    raise FileNotFoundError(
        "Kokoro voice model not found. Generate one video first so the model "
        "downloads, then try the preview again."
    )


def render_voice_sample(voice_id, text=VOICE_SAMPLE_TEXT):
    """Render (and cache) a short WAV sample for a Kokoro voice; returns its path."""
    global _kokoro
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    out_path = os.path.join(PREVIEW_DIR, f"voice_{voice_id}.wav")
    if os.path.exists(out_path):
        return out_path

    if _kokoro is None:
        from kokoro_onnx import Kokoro  # ImportError surfaces to the caller
        onnx_path, voices_path = _kokoro_model_paths()
        _kokoro = Kokoro(onnx_path, voices_path)

    samples, sample_rate = _kokoro.create(text, voice=voice_id, speed=1.0, lang="en-us")
    sf.write(out_path, samples, sample_rate)
    return out_path
