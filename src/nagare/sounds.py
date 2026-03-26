"""CESP sound engine — plays sounds from openpeon sound packs.

Supports Linux (PipeWire, PulseAudio, FFmpeg, mpv, SoX, ALSA),
macOS (afplay), and WSL (PowerShell media player).

All playback is async (fire-and-forget) — never blocks the caller.
"""

import json
import os
import platform
import random
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from nagare.log import logger

PACKS_DIR = Path.home() / ".local" / "share" / "nagare" / "packs"
MANIFEST_NAME = "openpeon.json"

# CESP categories nagare uses
CATEGORIES = (
    "session.start",
    "task.acknowledge",
    "task.complete",
    "task.error",
    "input.required",
    "session.end",
)


@dataclass
class SoundPack:
    """A loaded openpeon sound pack."""
    name: str
    display_name: str
    root: Path
    categories: dict[str, list[dict]]  # category → list of {file, label}
    aliases: dict[str, str]  # alias → category


@dataclass
class SoundEngine:
    """Manages pack loading, sound selection, and playback."""
    volume: float = 0.7
    muted: bool = False
    enabled_categories: dict[str, bool] = field(default_factory=dict)
    _packs: dict[str, SoundPack] = field(default_factory=dict)
    _last_played: dict[str, str] = field(default_factory=dict)  # category → last file
    _last_play_time: dict[str, float] = field(default_factory=dict)  # category → timestamp
    _debounce_ms: int = 500
    _player_cmd: list[str] | None = None

    def load_pack(self, name: str) -> SoundPack | None:
        """Load a sound pack by name from the packs directory."""
        if name in self._packs:
            return self._packs[name]

        pack_dir = PACKS_DIR / name
        manifest_path = pack_dir / MANIFEST_NAME
        if not manifest_path.exists():
            logger.warning("sound pack '%s' not found at %s", name, manifest_path)
            return None

        try:
            data = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("failed to load sound pack '%s': %s", name, e)
            return None

        categories: dict[str, list[dict]] = {}
        for cat_name, cat_data in data.get("categories", {}).items():
            sounds = cat_data.get("sounds", [])
            # Resolve file paths relative to pack root
            for sound in sounds:
                file_path = sound.get("file", "")
                if "/" not in file_path:
                    file_path = f"sounds/{file_path}"
                sound["_resolved"] = str(pack_dir / file_path)
            categories[cat_name] = sounds

        pack = SoundPack(
            name=data.get("name", name),
            display_name=data.get("display_name", name),
            root=pack_dir,
            categories=categories,
            aliases=data.get("category_aliases", {}),
        )
        self._packs[name] = pack
        logger.info("loaded sound pack '%s' (%s)", pack.display_name, pack.root)
        return pack

    def play(self, pack_name: str, category: str) -> None:
        """Play a random sound from the given category. Fire-and-forget."""
        if self.muted:
            return

        # Per-category toggle
        if not self.enabled_categories.get(category, True):
            return

        # Debounce
        now = time.time()
        last = self._last_play_time.get(category, 0)
        if (now - last) * 1000 < self._debounce_ms:
            return

        pack = self.load_pack(pack_name)
        if not pack:
            return

        # Resolve category (with alias fallback)
        sounds = pack.categories.get(category)
        if sounds is None:
            alias_target = pack.aliases.get(category)
            if alias_target:
                sounds = pack.categories.get(alias_target)
        if not sounds:
            return  # silently skip

        # Pick random sound with no-repeat
        sound = self._pick_sound(category, sounds)
        if not sound:
            return

        file_path = sound.get("_resolved", "")
        if not file_path or not Path(file_path).exists():
            logger.warning("sound file not found: %s", file_path)
            return

        self._last_play_time[category] = now
        self._last_played[category] = file_path
        self._play_file(file_path)
        logger.debug("playing sound: %s (%s)", sound.get("label", ""), file_path)

    def _pick_sound(self, category: str, sounds: list[dict]) -> dict | None:
        """Pick a random sound, excluding the last played for this category."""
        if not sounds:
            return None
        if len(sounds) == 1:
            return sounds[0]

        last = self._last_played.get(category, "")
        candidates = [s for s in sounds if s.get("_resolved") != last]
        if not candidates:
            candidates = sounds
        return random.choice(candidates)

    def _play_file(self, path: str) -> None:
        """Play an audio file async using the best available player."""
        cmd = self._get_player_cmd(path)
        if not cmd:
            return

        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as e:
            logger.warning("failed to play sound: %s", e)

    def _get_player_cmd(self, path: str) -> list[str] | None:
        """Build the playback command for the current platform."""
        vol = self.volume
        system = platform.system()

        if system == "Darwin":
            return ["afplay", "-v", str(vol), path]

        # Linux (including WSL): try native players first
        if self._player_cmd is not None:
            if self._player_cmd:
                return self._player_cmd + [path]
            return None  # no player found previously

        for player, args_fn in _LINUX_PLAYERS:
            if shutil.which(player):
                self._player_cmd = args_fn(vol)
                logger.info("using audio player: %s", player)
                return self._player_cmd + [path]

        # WSL fallback: use PowerShell if no Linux player available
        if _is_wsl():
            logger.info("using WSL PowerShell audio fallback")
            return _wsl_player_cmd(path, vol)

        logger.warning("no audio player found on this system")
        self._player_cmd = []  # avoid re-scanning
        return None

    def list_installed_packs(self) -> list[dict]:
        """List all installed sound packs."""
        packs = []
        if not PACKS_DIR.exists():
            return packs
        for d in sorted(PACKS_DIR.iterdir()):
            manifest = d / MANIFEST_NAME
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text())
                    cat_count = sum(
                        len(c.get("sounds", []))
                        for c in data.get("categories", {}).values()
                    )
                    packs.append({
                        "name": data.get("name", d.name),
                        "display_name": data.get("display_name", d.name),
                        "categories": list(data.get("categories", {}).keys()),
                        "sound_count": cat_count,
                    })
                except (OSError, json.JSONDecodeError):
                    continue
        return packs


def _is_wsl() -> bool:
    """Detect WSL environment."""
    try:
        release = Path("/proc/version").read_text().lower()
        return "microsoft" in release or "wsl" in release
    except OSError:
        return False


def _wsl_player_cmd(path: str, volume: float) -> list[str] | None:
    """Build a playback command for WSL using PowerShell."""
    # Convert WSL path to Windows path
    try:
        result = subprocess.run(
            ["wslpath", "-w", path],
            capture_output=True, text=True, timeout=2,
        )
        win_path = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None

    if not win_path:
        return None

    ps_script = (
        f'$p = New-Object System.Windows.Media.MediaPlayer; '
        f'$p.Open([Uri]::new("{win_path}")); '
        f'$p.Volume = {volume}; '
        f'$p.Play(); '
        f'Start-Sleep -Seconds 5'
    )
    powershell = shutil.which("powershell.exe") or "powershell.exe"
    return [powershell, "-NoProfile", "-Command", ps_script]


# Linux audio players in preference order
# Each entry: (binary_name, function(volume) → [args_without_file])
_LINUX_PLAYERS: list[tuple[str, callable]] = [
    ("pw-play", lambda v: ["pw-play", f"--volume={v}"]),
    ("paplay", lambda v: ["paplay", f"--volume={int(v * 65536)}"]),
    ("ffplay", lambda v: ["ffplay", "-nodisp", "-autoexit", "-volume", str(int(v * 100))]),
    ("mpv", lambda v: ["mpv", "--no-terminal", f"--volume={int(v * 100)}"]),
    ("play", lambda v: ["play", "-v", str(v)]),
    ("aplay", lambda v: ["aplay", "-q"]),
]


# Singleton engine
_engine: SoundEngine | None = None


def get_engine() -> SoundEngine:
    """Get or create the global sound engine."""
    global _engine
    if _engine is None:
        _engine = SoundEngine()
    return _engine


def play_sound(pack_name: str, category: str, volume: float = 0.7, **overrides) -> None:
    """Convenience function: play a sound from the given pack and category."""
    engine = get_engine()
    engine.volume = volume
    for k, v in overrides.items():
        if hasattr(engine, k):
            setattr(engine, k, v)
    engine.play(pack_name, category)
