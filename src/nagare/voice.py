"""Voice notification engine — speaks contextual messages via TTS.

Auto-detects the best available TTS engine:
  macOS: say (built-in)
  piper-tts: neural, offline, good quality
  edge-tts: neural, online, excellent quality
  espeak-ng: robotic, offline, universal fallback
  WSL PowerShell SAPI: zero-install fallback on WSL

All speech is async (fire-and-forget) — never blocks the caller.
"""

import platform
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from nagare.log import logger

# Default templates for each CESP category
DEFAULT_TEMPLATES: dict[str, str] = {
    "session.start": "{session} is online",
    "task.acknowledge": "{session} is working on it",
    "task.complete": "{session} finished",
    "task.error": "{session} hit an error",
    "input.required": "{session} needs your attention",
    "session.end": "{session} signed off",
}


@dataclass
class VoiceEngine:
    """Manages TTS engine detection and speech."""
    engine: str = "auto"  # auto, say, piper, edge-tts, espeak
    voice: str = ""  # engine-specific voice name
    speed: int = 160  # words per minute (where supported)
    volume: float = 0.8
    templates: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TEMPLATES))
    _detected_engine: str | None = None
    _last_speak_time: float = 0
    _debounce_ms: int = 2000  # longer debounce than sounds — speech overlaps badly
    _piper_model: str = ""  # resolved path to piper model

    def speak(self, category: str, session: str, **kwargs) -> None:
        """Speak a templated message for the given category. Fire-and-forget."""
        # Debounce
        now = time.time()
        if (now - self._last_speak_time) * 1000 < self._debounce_ms:
            return
        self._last_speak_time = now

        template = self.templates.get(category)
        if not template:
            return

        text = template.format(session=session, category=category, **kwargs)
        engine = self._resolve_engine()
        if not engine:
            return

        logger.debug("voice speak: engine=%s text=%s", engine, text)
        self._speak_with_engine(engine, text)

    def _resolve_engine(self) -> str | None:
        """Detect or return the configured TTS engine."""
        if self._detected_engine is not None:
            return self._detected_engine or None

        if self.engine != "auto":
            self._detected_engine = self.engine
            return self.engine

        # Auto-detect best available
        system = platform.system()

        if system == "Darwin" and shutil.which("say"):
            self._detected_engine = "say"
        elif shutil.which("piper") and self._find_piper_model():
            self._detected_engine = "piper"
        elif _has_edge_tts():
            self._detected_engine = "edge-tts"
        elif shutil.which("espeak-ng"):
            self._detected_engine = "espeak"
        elif shutil.which("espeak"):
            self._detected_engine = "espeak"
        elif _is_wsl():
            self._detected_engine = "wsl-sapi"
        else:
            logger.warning("no TTS engine found")
            self._detected_engine = ""
            return None

        logger.info("voice engine: %s", self._detected_engine)
        return self._detected_engine

    def _find_piper_model(self) -> bool:
        """Find a piper model in standard locations."""
        if self._piper_model:
            return True

        # Check common model locations
        search_paths = [
            Path.home() / ".local" / "share" / "piper-voices",
            Path.home() / ".local" / "share" / "nagare" / "piper-voices",
            Path("/usr/share/piper-voices"),
        ]
        for base in search_paths:
            if not base.exists():
                continue
            for model in base.rglob("*.onnx"):
                self._piper_model = str(model)
                logger.info("piper model found: %s", self._piper_model)
                return True
        return False

    def _speak_with_engine(self, engine: str, text: str) -> None:
        """Dispatch speech to the appropriate engine."""
        try:
            if engine == "say":
                self._speak_say(text)
            elif engine == "piper":
                self._speak_piper(text)
            elif engine == "edge-tts":
                self._speak_edge_tts(text)
            elif engine == "espeak":
                self._speak_espeak(text)
            elif engine == "wsl-sapi":
                self._speak_wsl_sapi(text)
        except Exception:
            logger.exception("voice speak failed (engine=%s)", engine)

    def _speak_say(self, text: str) -> None:
        """macOS say command."""
        cmd = ["say"]
        if self.voice:
            cmd += ["-v", self.voice]
        cmd += ["-r", str(self.speed), text]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    def _speak_piper(self, text: str) -> None:
        """Piper neural TTS — pipe text to piper, output to temp wav, play it."""
        if not self._piper_model:
            return
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name

        # piper reads from stdin, writes wav to file
        cmd = f'echo {_shell_escape(text)} | piper --model {_shell_escape(self._piper_model)} --output_file {tmp} && '
        cmd += _get_play_cmd(tmp, self.volume)
        cmd += f' ; rm -f {tmp}'

        subprocess.Popen(["sh", "-c", cmd], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    def _speak_edge_tts(self, text: str) -> None:
        """Microsoft Edge TTS — generates mp3, then plays it."""
        import sys
        voice = self.voice or "en-US-GuyNeural"
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp = f.name

        python = sys.executable
        cmd = f'{_shell_escape(python)} -m edge_tts --text {_shell_escape(text)} --voice {_shell_escape(voice)} --write-media {tmp} && '
        cmd += _get_play_cmd(tmp, self.volume)
        cmd += f' ; rm -f {tmp}'

        subprocess.Popen(["sh", "-c", cmd], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    def _speak_espeak(self, text: str) -> None:
        """espeak-ng or espeak."""
        binary = "espeak-ng" if shutil.which("espeak-ng") else "espeak"
        cmd = [binary]
        if self.voice:
            cmd += ["-v", self.voice]
        cmd += ["-s", str(self.speed), "-a", str(int(self.volume * 200)), text]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    def _speak_wsl_sapi(self, text: str) -> None:
        """Windows SAPI via PowerShell from WSL."""
        escaped = text.replace("'", "''")
        ps_script = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Volume = {int(self.volume * 100)}; "
            f"$s.Rate = {max(-5, min(5, (self.speed - 160) // 30))}; "
            f"$s.Speak('{escaped}')"
        )
        powershell = shutil.which("powershell.exe") or "powershell.exe"
        subprocess.Popen(
            [powershell, "-NoProfile", "-Command", ps_script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def _has_edge_tts() -> bool:
    """Check if edge-tts is importable."""
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _shell_escape(s: str) -> str:
    """Escape a string for shell use."""
    return "'" + s.replace("'", "'\\''") + "'"


def _get_play_cmd(path: str, volume: float) -> str:
    """Return a shell command to play an audio file."""
    if platform.system() == "Darwin":
        return f"afplay -v {volume} {path}"
    for player, cmd_fn in [
        ("paplay", lambda: f"paplay --volume={int(volume * 65536)} {path}"),
        ("ffplay", lambda: f"ffplay -nodisp -autoexit -volume {int(volume * 100)} {path}"),
        ("mpv", lambda: f"mpv --no-terminal --volume={int(volume * 100)} {path}"),
        ("play", lambda: f"play -v {volume} {path}"),
        ("aplay", lambda: f"aplay -q {path}"),
    ]:
        if shutil.which(player):
            return cmd_fn()
    return f"cat {path} > /dev/null"  # fallback: silent


# Singleton
_voice: VoiceEngine | None = None


def get_voice_engine() -> VoiceEngine:
    global _voice
    if _voice is None:
        _voice = VoiceEngine()
    return _voice


def speak(category: str, session: str, volume: float = 0.8, **kwargs) -> None:
    """Convenience function: speak a notification message."""
    engine = get_voice_engine()
    engine.volume = volume
    engine.speak(category, session, **kwargs)
