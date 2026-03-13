# tests/test_cli.py
from nagare.setup import generate_tmux_config


def test_generate_tmux_config():
    config = generate_tmux_config()
    assert "nagare pick" in config
    assert "nagare notifs" in config
    assert "display-popup" in config
    assert "bind" in config
