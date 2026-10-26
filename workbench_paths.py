"""Paths and local preferences for the self-contained public workbench."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = ROOT = Path(__file__).resolve().parent


def configured_path(name, default):
    value = Path(os.environ.get(name, str(default))).expanduser()
    # Relative overrides are always relative to this checkout, not a caller's cwd.
    return (value if value.is_absolute() else ROOT / value).resolve()


DATA_DIR = configured_path('MLX_WORKBENCH_DATA_DIR', ROOT / 'data')
MODEL_DIR = configured_path('MLX_WORKBENCH_MODEL_DIR', ROOT / 'models')
OUTPUT_DIR = DATA_DIR / 'output'
LOG_DIR = DATA_DIR / 'logs'
REFERENCES_DIR = DATA_DIR / 'references'
SETTINGS_FILE = DATA_DIR / 'settings.json'


def settings():
    try:
        value = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def tavern_enabled():
    return settings().get('tavern_enabled') is True


def is_local_origin(value):
    """Browser origins used by a local SillyTavern, never arbitrary websites."""
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')
                and not parsed.path and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment
                and parsed.port is not None and 1 <= parsed.port <= 65535)
    except ValueError:
        return False
