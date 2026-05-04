from __future__ import annotations

import json
import os
from pathlib import Path

from .exceptions import ConfigError

DEFAULT_SERVER_URL = "http://svc.gofindarc.today:8080/v1"
DEFAULT_CONFIG_DIR = Path.home() / ".finda"


def _resolve_config_dir(config_dir: str | Path | None = None) -> Path:
    if config_dir is None:
        return DEFAULT_CONFIG_DIR
    return Path(config_dir).expanduser()


def _resolve_config_path(config_dir: str | Path | None = None) -> Path:
    return _resolve_config_dir(config_dir) / "config.json"


class Config:
    def __init__(self, api_key: str, server_url: str, agent_id: str | None = None) -> None:
        self.api_key = api_key
        self.server_url = server_url.rstrip("/")
        self.agent_id = agent_id

    @classmethod
    def load(
        cls,
        api_key: str | None = None,
        server_url: str | None = None,
        config_dir: str | Path | None = None,
    ) -> "Config":
        """Load config with priority: param > env > file."""
        file_data = _read_config_file(config_dir=config_dir)
        resolved_key = api_key or os.environ.get("FINDARC_API_KEY") or file_data.get("api_key")
        resolved_url = (
            server_url
            or os.environ.get("FINDARC_SERVER_URL")
            or file_data.get("server_url")
            or DEFAULT_SERVER_URL
        )
        agent_id = file_data.get("agent_id")

        if not resolved_key:
            raise ConfigError(
                "No API key found. Run `finda register` or set FINDARC_API_KEY."
            )

        return cls(
            api_key=resolved_key,
            server_url=resolved_url,
            agent_id=agent_id,
        )

    @staticmethod
    def save(
        agent_id: str,
        api_key: str,
        server_url: str = DEFAULT_SERVER_URL,
        config_dir: str | Path | None = None,
    ) -> None:
        resolved_dir = _resolve_config_dir(config_dir)
        config_path = _resolve_config_path(config_dir)
        resolved_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {"agent_id": agent_id, "api_key": api_key, "server_url": server_url},
                indent=2,
            )
        )
        try:
            config_path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def registration_exists(config_dir: str | Path | None = None) -> bool:
        return _resolve_config_dir(config_dir).exists()


def _read_config_file(config_dir: str | Path | None = None) -> dict:
    config_path = _resolve_config_path(config_dir)
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        raise ConfigError(f"Config file {config_path} is malformed.")
