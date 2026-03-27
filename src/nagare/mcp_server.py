"""nagare MCP server — inter-agent messaging for Claude Code sessions."""

import json
import os
import time
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from nagare.log import logger
from nagare.models import SessionStatus
from nagare.registry import SessionRegistry
from nagare.tmux import run_tmux
from nagare.tmux.scanner import scan_sessions

MESSAGES_DIR = Path.home() / ".local" / "share" / "nagare" / "messages"

mcp = FastMCP("nagare")


def _get_my_session_name() -> str:
    """Resolve the current session name by matching cwd against the registry."""
    cwd = os.getcwd()
    registry = SessionRegistry()
    session = registry.find_by_path(cwd)
    if session:
        return session.name
    # Fallback: check running sessions
    for s in scan_sessions():
        if s.path == cwd:
            return s.name
    return ""


def _get_inbox_dir(session_name: str) -> Path:
    return MESSAGES_DIR / session_name


def _write_message(msg: dict) -> Path:
    inbox = _get_inbox_dir(msg["to_session"])
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / f"msg_{msg['id']}.json"
    path.write_text(json.dumps(msg, indent=2))
    return path


def _read_message(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


@mcp.tool()
def list_agents() -> str:
    """List all available agent sessions with their current status.

    Returns a list of sessions you can message. Each entry shows the session
    name, project path, agent type (claude/opencode), and current status
    (idle/working/waiting_input/dead). You can only send messages to sessions
    that are IDLE.
    """
    my_name = _get_my_session_name()
    sessions = scan_sessions()
    if not sessions:
        return "No agent sessions found."

    lines = []
    for s in sessions:
        if s.name == my_name:
            continue
        status = s.status.value
        lines.append(f"- {s.name} ({s.agent_type.value}) [{status}] — {s.path}")

    if not lines:
        return "No other agent sessions found."
    return "Available agents:\n" + "\n".join(lines)


def _deliver_message(
    my_name: str, target: str, message: str, *, expects_reply: bool = False,
) -> tuple[str | None, Path | None]:
    """Validate target, create message, send-keys nudge. Returns (error, msg_path)."""
    sessions = scan_sessions()
    target_session = None
    for s in sessions:
        if s.name == target:
            target_session = s
            break

    if not target_session:
        return f"Error: Session '{target}' not found. Use list_agents() to see available sessions.", None

    if target_session.status != SessionStatus.IDLE:
        return (
            f"Error: '{target}' is busy (status: {target_session.status.value}). "
            f"Try again later when the agent is idle."
        ), None

    msg_id = uuid.uuid4().hex[:12]
    msg = {
        "id": msg_id,
        "from_session": my_name,
        "to_session": target,
        "content": message,
        "expects_reply": expects_reply,
        "status": "pending",
        "response": None,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "responded_at": None,
    }
    msg_path = _write_message(msg)
    logger.info("message %s: %s -> %s (expects_reply=%s)", msg_id, my_name, target, expects_reply)

    pane_target = f"{target_session.name}:{target_session.window_index}.{target_session.pane_index}"
    if expects_reply:
        nudge = (
            f"You have a message from '{my_name}' that requires a reply. "
            f"Call check_messages() to read it, then reply() to respond."
        )
    else:
        nudge = (
            f"FYI from '{my_name}': {message[:200]} "
            f"— This is informational only. No reply needed. Continue your current work."
        )
    run_tmux("send-keys", "-t", pane_target, nudge, "Enter")

    msg["status"] = "delivered"
    msg_path.write_text(json.dumps(msg, indent=2))

    return None, msg_path


@mcp.tool()
def send_message(target: str, message: str) -> str:
    """Send a message to another agent and return immediately (fire-and-forget).

    The target agent must be IDLE. They will be nudged to check their messages.
    Use check_messages() later to see if they responded.

    Args:
        target: Name of the target session (from list_agents)
        message: Your message for the other agent
    """
    my_name = _get_my_session_name()
    if not my_name:
        return "Error: Could not determine current session name."

    error, _ = _deliver_message(my_name, target, message, expects_reply=False)
    if error:
        return error

    return f"Message sent to '{target}'. Use check_messages() later to see their response."


@mcp.tool()
def send_message_and_wait(target: str, message: str, timeout: int = 120) -> str:
    """Send a message to another agent and wait for their response.

    The target agent must be IDLE (at the prompt, not working). If they are
    busy, this will return an error — try again later.

    Args:
        target: Name of the target session (from list_agents)
        message: Your question or request for the other agent
        timeout: Max seconds to wait for response (default 120)
    """
    my_name = _get_my_session_name()
    if not my_name:
        return "Error: Could not determine current session name."

    error, msg_path = _deliver_message(my_name, target, message, expects_reply=True)
    if error:
        return error

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        current = _read_message(msg_path)
        if current and current.get("status") == "completed":
            logger.info("message %s: got response", current["id"])
            return current["response"]

    logger.warning("message timed out after %ds for '%s'", timeout, target)
    return (
        f"Error: Timed out after {timeout}s waiting for response from '{target}'. "
        f"Use check_messages() later to see if they responded."
    )


@mcp.tool()
def check_messages() -> str:
    """Check for pending messages and late responses.

    Returns:
    - Pending messages sent TO you (use reply() to respond)
    - Completed responses to messages you SENT (in case ask_agent timed out)
    """
    my_name = _get_my_session_name()
    if not my_name:
        return "Error: Could not determine current session name."

    incoming = []
    responses = []

    # Check inbox for messages sent TO me
    inbox = _get_inbox_dir(my_name)
    if inbox.exists():
        for f in sorted(inbox.glob("msg_*.json")):
            msg = _read_message(f)
            if msg and msg.get("status") in ("pending", "delivered"):
                incoming.append(msg)

    # Check all inboxes for completed responses to messages I SENT
    if MESSAGES_DIR.exists():
        for session_dir in MESSAGES_DIR.iterdir():
            if not session_dir.is_dir() or session_dir.name == my_name:
                continue
            for f in sorted(session_dir.glob("msg_*.json")):
                msg = _read_message(f)
                if (msg and msg.get("from_session") == my_name
                        and msg.get("status") == "completed"):
                    responses.append(msg)

    if not incoming and not responses:
        return "No messages."

    lines = []

    if incoming:
        lines.append("=== Pending messages for you ===\n")
        for msg in incoming:
            lines.append(
                f"Message ID: {msg['id']}\n"
                f"From: {msg['from_session']}\n"
                f"Sent: {msg['created_at']}\n"
                f"Content: {msg['content']}"
            )

    if responses:
        lines.append("=== Responses to your messages ===\n")
        for msg in responses:
            lines.append(
                f"To: {msg['to_session']}\n"
                f"Your message: {msg['content'][:100]}{'...' if len(msg['content']) > 100 else ''}\n"
                f"Response: {msg['response']}\n"
                f"Responded at: {msg['responded_at']}"
            )

    return "\n---\n".join(lines)


@mcp.tool()
def reply(message_id: str, content: str) -> str:
    """Reply to a pending message from another agent.

    Args:
        message_id: The message ID from check_messages()
        content: Your response to send back to the requesting agent
    """
    my_name = _get_my_session_name()
    if not my_name:
        return "Error: Could not determine current session name."

    inbox = _get_inbox_dir(my_name)
    msg_path = inbox / f"msg_{message_id}.json"

    if not msg_path.exists():
        return f"Error: Message '{message_id}' not found."

    msg = _read_message(msg_path)
    if not msg:
        return f"Error: Could not read message '{message_id}'."

    if msg.get("status") == "completed":
        return f"Message '{message_id}' was already replied to."

    msg["response"] = content
    msg["status"] = "completed"
    msg["responded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    msg_path.write_text(json.dumps(msg, indent=2))

    logger.info("message %s: replied by %s", message_id, my_name)
    return f"Reply sent to '{msg['from_session']}'."


if __name__ == "__main__":
    mcp.run()
