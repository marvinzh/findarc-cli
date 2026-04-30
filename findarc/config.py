from __future__ import annotations

import json
import os
from pathlib import Path

from .exceptions import ConfigError

DEFAULT_SERVER_URL = "http://localhost:8000/v1"
CONFIG_PATH = Path.home() / ".findarc" / "config.json"


class Config:
    def __init__(self, api_key: str, server_url: str, agent_id: str | None = None) -> None:
        self.api_key = api_key
        self.server_url = server_url.rstrip("/")
        self.agent_id = agent_id

    @classmethod
    def load(cls, api_key: str | None = None, server_url: str | None = None) -> "Config":
        """Load config with priority: param > env > file."""
        resolved_key = api_key or os.environ.get("FINDARC_API_KEY")
        resolved_url = server_url or os.environ.get("FINDARC_SERVER_URL")
        agent_id: str | None = None

        if not resolved_key or not resolved_url:
            file_data = _read_config_file()
            if not resolved_key:
                resolved_key = file_data.get("api_key")
            if not resolved_url:
                resolved_url = file_data.get("server_url", DEFAULT_SERVER_URL)
            agent_id = file_data.get("agent_id")

        if not resolved_key:
            raise ConfigError(
                "No API key found. Run `findarc login` or set FINDARC_API_KEY."
            )

        return cls(
            api_key=resolved_key,
            server_url=resolved_url or DEFAULT_SERVER_URL,
            agent_id=agent_id,
        )

    @staticmethod
    def save(agent_id: str, api_key: str, server_url: str = DEFAULT_SERVER_URL) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(
                {"agent_id": agent_id, "api_key": api_key, "server_url": server_url},
                indent=2,
            )
        )


def _read_config_file() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        raise ConfigError(f"Config file {CONFIG_PATH} is malformed.")
