"""Token usage tracking from Claude Code conversation transcripts."""

import json
from dataclasses import dataclass
from pathlib import Path

from nagare.log import logger

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read + self.cache_creation

    @property
    def display(self) -> str:
        """Human-readable token summary."""
        total = self.total
        if total == 0:
            return ""
        return f"{_format_tokens(total)} ({_format_tokens(self.output_tokens)} out)"


def _format_tokens(n: int) -> str:
    """Format token count: 1234 -> 1.2k, 1234567 -> 1.2M."""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}k"
    return f"{n / 1_000_000:.1f}M"


def _project_dir_name(path: str) -> str:
    """Convert a project path to Claude's directory name format."""
    return path.replace("/", "-")


def get_session_tokens(project_path: str) -> TokenUsage:
    """Get total token usage for the most recent session of a project.

    Reads the latest transcript JSONL file for the project and sums
    all usage blocks.
    """
    dir_name = _project_dir_name(project_path)
    project_dir = CLAUDE_PROJECTS_DIR / dir_name

    if not project_dir.is_dir():
        return TokenUsage()

    # Find the most recent transcript file
    transcripts = sorted(project_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not transcripts:
        return TokenUsage()

    return _parse_transcript_tokens(transcripts[0])


def get_all_session_tokens(project_paths: list[str]) -> dict[str, TokenUsage]:
    """Batch get token usage for multiple projects."""
    result = {}
    for path in project_paths:
        try:
            result[path] = get_session_tokens(path)
        except Exception:
            result[path] = TokenUsage()
    return result


def _parse_transcript_tokens(transcript_path: Path) -> TokenUsage:
    """Sum usage data from a transcript JSONL file."""
    usage = TokenUsage()
    try:
        with open(transcript_path) as f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                    msg = entry.get("message") or entry
                    u = msg.get("usage")
                    if u:
                        usage.input_tokens += u.get("input_tokens", 0)
                        usage.output_tokens += u.get("output_tokens", 0)
                        usage.cache_read += u.get("cache_read_input_tokens", 0)
                        usage.cache_creation += u.get("cache_creation_input_tokens", 0)
                except (json.JSONDecodeError, AttributeError):
                    continue
    except OSError:
        pass
    return usage
