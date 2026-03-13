import os
from unittest.mock import patch
from nagare.config import load_config, NagareConfig


def test_default_config():
    with patch.dict(os.environ, {}, clear=True):
        with patch("nagare.config.CONFIG_PATH", "/nonexistent/config.toml"):
            cfg = load_config()
    assert cfg.notification_backend == "tmux"
    assert cfg.notification_duration == 2000
    assert cfg.poll_interval == 3
    assert cfg.picker_width == "80%"
    assert cfg.picker_height == "80%"


def test_load_from_toml(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
backend = "notify-send"
duration = 3000
poll_interval = 5

[picker]
popup_width = "90%"
popup_height = "70%"
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notification_backend == "notify-send"
    assert cfg.notification_duration == 3000
    assert cfg.poll_interval == 5
    assert cfg.picker_width == "90%"
    assert cfg.picker_height == "70%"


def test_partial_config(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
duration = 4000
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notification_backend == "tmux"
    assert cfg.notification_duration == 4000
    assert cfg.poll_interval == 3
