import os
from unittest.mock import patch
from nagare.config import (
    load_config,
    save_notification_config,
    NagareConfig,
    NotificationEventConfig,
    NotificationConfig,
)


def test_default_config():
    with patch.dict(os.environ, {}, clear=True):
        with patch("nagare.config.CONFIG_PATH", "/nonexistent/config.toml"):
            cfg = load_config()
    assert cfg.notification_duration == 3000
    assert cfg.picker_width == "80%"
    assert cfg.picker_height == "80%"
    assert cfg.theme == "tokyonight"


def test_default_notification_config():
    with patch("nagare.config.CONFIG_PATH", "/nonexistent/config.toml"):
        cfg = load_config()
    n = cfg.notifications
    assert n.enabled is True
    # needs_input defaults
    assert n.needs_input.toast is True
    assert n.needs_input.bell is True
    assert n.needs_input.os_notify is True
    assert n.needs_input.popup is False
    assert n.needs_input.popup_timeout == 10
    assert n.needs_input.min_working_seconds == 0
    # task_complete defaults
    assert n.task_complete.toast is True
    assert n.task_complete.bell is False
    assert n.task_complete.os_notify is False
    assert n.task_complete.popup is False
    assert n.task_complete.popup_timeout == 10
    assert n.task_complete.min_working_seconds == 30
    # no per-session overrides
    assert n.sessions == {}


def test_load_from_toml(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
enabled = true
duration = 5000

[notifications.needs_input]
toast = false
bell = false
popup = true
popup_timeout = 15

[notifications.task_complete]
toast = false
min_working_seconds = 60

[picker]
popup_width = "90%"
popup_height = "70%"
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notification_duration == 5000
    assert cfg.picker_width == "90%"
    assert cfg.picker_height == "70%"
    # needs_input overrides
    assert cfg.notifications.needs_input.toast is False
    assert cfg.notifications.needs_input.bell is False
    assert cfg.notifications.needs_input.popup is True
    assert cfg.notifications.needs_input.popup_timeout == 15
    # needs_input defaults preserved for unset fields
    assert cfg.notifications.needs_input.os_notify is True
    assert cfg.notifications.needs_input.min_working_seconds == 0
    # task_complete overrides
    assert cfg.notifications.task_complete.toast is False
    assert cfg.notifications.task_complete.min_working_seconds == 60
    # task_complete defaults preserved
    assert cfg.notifications.task_complete.bell is False
    assert cfg.notifications.task_complete.popup is False
    assert cfg.notifications.task_complete.popup_timeout == 10


def test_partial_config(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
duration = 4000
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notification_duration == 4000
    # notifications object should still have all defaults
    assert cfg.notifications.enabled is True
    assert cfg.notifications.needs_input.toast is True
    assert cfg.notifications.task_complete.min_working_seconds == 30


def test_per_session_overrides(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
enabled = true

[notifications.sessions.playground]
enabled = false

[notifications.sessions.production-backend]
popup = true
os_notify = true
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert "playground" in cfg.notifications.sessions
    assert cfg.notifications.sessions["playground"]["enabled"] is False
    assert "production-backend" in cfg.notifications.sessions
    assert cfg.notifications.sessions["production-backend"]["popup"] is True
    assert cfg.notifications.sessions["production-backend"]["os_notify"] is True


def test_notifications_disabled(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
enabled = false
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notifications.enabled is False


def test_full_config(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
enabled = true

[notifications.needs_input]
toast = true
bell = false
os_notify = true
popup = true
popup_timeout = 15
min_working_seconds = 5

[notifications.task_complete]
toast = false
bell = true
os_notify = true
popup = true
popup_timeout = 20
min_working_seconds = 120

[notifications.sessions.playground]
enabled = false

[notifications.sessions.production-backend]
popup = true
os_notify = true

[picker]
popup_width = "70%"
popup_height = "60%"

[appearance]
theme = "catppuccin"
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notifications.enabled is True
    assert cfg.notifications.needs_input == NotificationEventConfig(
        toast=True, bell=False, os_notify=True, popup=True,
        popup_timeout=15, min_working_seconds=5,
    )
    assert cfg.notifications.task_complete == NotificationEventConfig(
        toast=False, bell=True, os_notify=True, popup=True,
        popup_timeout=20, min_working_seconds=120,
    )
    assert cfg.notifications.sessions["playground"] == {"enabled": False}
    assert cfg.notifications.sessions["production-backend"] == {
        "popup": True, "os_notify": True,
    }
    assert cfg.picker_width == "70%"
    assert cfg.picker_height == "60%"
    assert cfg.theme == "catppuccin"


def test_empty_notifications_section(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notifications.enabled is True
    assert cfg.notifications.needs_input.toast is True
    assert cfg.notifications.sessions == {}


def test_save_notification_config_roundtrip(tmp_path):
    """Save config then load it — values should match."""
    config_file = tmp_path / "config.toml"
    # Start with an existing appearance section
    config_file.write_text('[appearance]\ntheme = "nord"\n')

    nc = NotificationConfig(
        enabled=False,
        needs_input=NotificationEventConfig(
            toast=False, bell=True, os_notify=False,
            popup=True, popup_timeout=15, min_working_seconds=0,
        ),
        task_complete=NotificationEventConfig(
            toast=True, bell=False, os_notify=True,
            popup=False, popup_timeout=20, min_working_seconds=60,
        ),
        sessions={"playground": {"enabled": False}},
    )

    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        save_notification_config(nc)
        cfg = load_config()

    assert cfg.notifications.enabled is False
    assert cfg.notifications.needs_input.toast is False
    assert cfg.notifications.needs_input.bell is True
    assert cfg.notifications.needs_input.popup is True
    assert cfg.notifications.needs_input.popup_timeout == 15
    assert cfg.notifications.task_complete.toast is True
    assert cfg.notifications.task_complete.os_notify is True
    assert cfg.notifications.task_complete.min_working_seconds == 60
    assert cfg.notifications.sessions["playground"]["enabled"] is False
    # Appearance section preserved
    assert cfg.theme == "nord"


def test_save_notification_config_creates_file(tmp_path):
    """Save config when no file exists."""
    config_file = tmp_path / "config.toml"
    nc = NotificationConfig()

    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        save_notification_config(nc)
        cfg = load_config()

    assert cfg.notifications.enabled is True
    assert cfg.notifications.needs_input.toast is True
