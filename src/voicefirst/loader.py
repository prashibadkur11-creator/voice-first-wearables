"""Load and validate developer YAML configs (the receptionist).

Validates auth.yaml / commands.yaml against the repo schemas at load time --
the same schemas CI enforces -- so a bad config fails fast with a readable
message, not a stack trace deep in the engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from jsonschema import Draft202012Validator

# schema/ lives at the repo root, two levels up from src/voicefirst/config/.
_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schema"


class ConfigError(Exception):
    """Raised when a config file fails schema validation."""


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} is not a YAML mapping")
    return data


def _validate(data: Dict[str, Any], schema_file: str, source: Path) -> None:
    schema = yaml.safe_load(open(_SCHEMA_DIR / schema_file))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        lines = [f"{source} failed validation against {schema_file}:"]
        for e in errors:
            where = "/".join(str(p) for p in e.path) or "(root)"
            lines.append(f"  - at {where}: {e.message}")
        raise ConfigError("\n".join(lines))


def load_auth_config(path: str | Path) -> Dict[str, Any]:
    """Parse + validate an auth.yaml. Returns the config dict."""
    p = Path(path)
    data = _load_yaml(p)
    _validate(data, "auth.schema.yaml", p)
    return data


def load_commands(path: str | Path) -> Dict[str, Any]:
    """Parse + validate a commands.yaml. Returns the config dict."""
    p = Path(path)
    data = _load_yaml(p)
    _validate(data, "commands.schema.yaml", p)
    return data
