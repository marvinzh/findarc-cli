import json

from click.testing import CliRunner
import pytest

from findarc.cli.main import cli


class StubClient:
    register_calls: list[tuple[str, str, str | None]] = []
    current_agent_calls = 0
    list_tasks_calls: list[tuple[str | None, int, str | None]] = []

    def __init__(self, config):
        self.config = config

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    @staticmethod
    def register(name: str, server_url: str, description: str | None = None) -> dict:
        StubClient.register_calls.append((name, server_url, description))
        return {"agent_id": "AI-register", "api_key": "KEY-register", "name": name}

    def get_current_agent(self) -> dict:
        StubClient.current_agent_calls += 1
        return {
            "agent_id": "AI-current",
            "name": "Current Agent",
            "role": "requester",
        }

    def become_provider(self, agent_id: str, tags: list[str], models: list[str] | None = None) -> dict:
        return {
            "agent_id": agent_id,
            "role": "provider",
            "tags": tags,
            "models": models or [],
        }

    def retire_provider(self, agent_id: str) -> dict:
        return {"agent_id": agent_id, "role": "requester"}

    def list_tasks(
        self,
        status: str | None = None,
        limit: int = 5,
        cursor: str | None = None,
    ) -> dict:
        StubClient.list_tasks_calls.append((status, limit, cursor))
        return {"tasks": [], "limit": limit, "next_cursor": None}


def test_register_uses_global_server_url_override(monkeypatch):
    from findarc import config as config_module
    from findarc import client as client_module

    runner = CliRunner()
    saved: dict[str, str] = {}
    StubClient.register_calls.clear()

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "registration_exists",
        staticmethod(lambda config_dir=None: False),
    )
    monkeypatch.setattr(
        config_module.Config,
        "save",
        staticmethod(
            lambda agent_id, api_key, server_url, config_dir=None: saved.update(
                {
                    "agent_id": agent_id,
                    "api_key": api_key,
                    "server_url": server_url,
                    "config_dir": config_dir,
                }
            )
        ),
    )

    result = runner.invoke(
        cli,
        ["--server-url", "http://remote/v1", "register", "--name", "agent"],
    )

    assert result.exit_code == 0
    assert StubClient.register_calls == [("agent", "http://remote/v1", None)]
    assert saved == {
        "agent_id": "AI-register",
        "api_key": "KEY-register",
        "server_url": "http://remote/v1",
        "config_dir": None,
    }
    assert "Credentials saved to config.json" in result.stderr


def test_register_uses_custom_config_directory(monkeypatch, tmp_path):
    from findarc import client as client_module

    runner = CliRunner()
    StubClient.register_calls.clear()
    config_dir = tmp_path / "finda-config"

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)

    result = runner.invoke(
        cli,
        ["--config", str(config_dir), "register", "--name", "agent"],
    )

    assert result.exit_code == 0
    assert StubClient.register_calls == [("agent", "http://localhost:8000/v1", None)]
    saved = json.loads((config_dir / "config.json").read_text())
    assert saved == {
        "agent_id": "AI-register",
        "api_key": "KEY-register",
        "server_url": "http://localhost:8000/v1",
    }
    assert "Credentials saved to config.json" in result.stderr


def test_register_fails_when_finda_directory_already_exists(monkeypatch):
    from findarc import config as config_module
    from findarc import client as client_module

    runner = CliRunner()
    StubClient.register_calls.clear()

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "registration_exists",
        staticmethod(lambda config_dir=None: True),
    )

    result = runner.invoke(
        cli,
        ["register", "--name", "agent"],
    )

    assert result.exit_code == 1
    assert StubClient.register_calls == []
    assert json.loads(result.stderr) == {
        "error": "Agent already registered."
    }


def test_register_uses_custom_config_directory_for_duplicate_check(monkeypatch, tmp_path):
    from findarc import client as client_module

    runner = CliRunner()
    StubClient.register_calls.clear()
    config_dir = tmp_path / "finda-config"
    config_dir.mkdir()

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)

    result = runner.invoke(
        cli,
        ["--config", str(config_dir), "register", "--name", "agent"],
    )

    assert result.exit_code == 1
    assert StubClient.register_calls == []
    assert json.loads(result.stderr) == {"error": "Agent already registered."}


def test_whoami_uses_authenticated_agent_not_local_agent_id(monkeypatch):
    from findarc import client as client_module
    from findarc import config as config_module

    runner = CliRunner()
    StubClient.current_agent_calls = 0

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "load",
        classmethod(
            lambda cls, api_key=None, server_url=None, config_dir=None: config_module.Config(
                api_key=api_key or "KEY",
                server_url=server_url or "http://server/v1",
                agent_id="AI-stale-local",
            )
        ),
    )

    result = runner.invoke(
        cli,
        ["--api-key", "KEY", "--server-url", "http://server/v1", "whoami"],
    )

    assert result.exit_code == 0
    assert StubClient.current_agent_calls == 1
    assert json.loads(result.output) == {
        "agent_id": "AI-current",
        "name": "Current Agent",
        "role": "requester",
    }


def test_whoami_loads_config_from_custom_directory(monkeypatch, tmp_path):
    from findarc import client as client_module

    runner = CliRunner()
    StubClient.current_agent_calls = 0
    config_dir = tmp_path / "finda-config"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "agent_id": "AI-local",
                "api_key": "KEY",
                "server_url": "http://server/v1",
            }
        )
    )

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)

    result = runner.invoke(
        cli,
        ["--config", str(config_dir), "whoami"],
    )

    assert result.exit_code == 0
    assert StubClient.current_agent_calls == 1
    assert json.loads(result.output) == {
        "agent_id": "AI-current",
        "name": "Current Agent",
        "role": "requester",
    }


def test_serve_and_retire_resolve_current_agent_with_env_overrides(monkeypatch):
    from findarc import client as client_module
    from findarc import config as config_module

    runner = CliRunner()

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "load",
        classmethod(
            lambda cls, api_key=None, server_url=None, config_dir=None: config_module.Config(
                api_key=api_key or "ENVKEY",
                server_url=server_url or "http://env/v1",
                agent_id=None,
            )
        ),
    )

    serve_result = runner.invoke(
        cli,
        ["serve", "--tags", "python,fastapi", "--models", "gpt-4.1"],
        env={"FINDARC_API_KEY": "ENVKEY", "FINDARC_SERVER_URL": "http://env/v1"},
    )
    retire_result = runner.invoke(
        cli,
        ["retire"],
        env={"FINDARC_API_KEY": "ENVKEY", "FINDARC_SERVER_URL": "http://env/v1"},
    )

    assert serve_result.exit_code == 0
    assert json.loads(serve_result.output) == {
        "agent_id": "AI-current",
        "role": "provider",
        "tags": ["python", "fastapi"],
        "models": ["gpt-4.1"],
    }
    assert retire_result.exit_code == 0
    assert json.loads(retire_result.output) == {
        "agent_id": "AI-current",
        "role": "requester",
    }


def test_query_tasks_uses_default_limit_of_five(monkeypatch):
    from findarc import client as client_module
    from findarc import config as config_module

    runner = CliRunner()
    StubClient.list_tasks_calls.clear()

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "load",
        classmethod(
            lambda cls, api_key=None, server_url=None, config_dir=None: config_module.Config(
                api_key=api_key or "KEY",
                server_url=server_url or "http://server/v1",
                agent_id="AI-local",
            )
        ),
    )

    result = runner.invoke(
        cli,
        ["--api-key", "KEY", "--server-url", "http://server/v1", "query-tasks"],
    )

    assert result.exit_code == 0
    assert StubClient.list_tasks_calls == [("open", 5, None)]
    assert json.loads(result.output) == {"tasks": [], "limit": 5, "next_cursor": None}


def test_query_tasks_accepts_custom_limit(monkeypatch):
    from findarc import client as client_module
    from findarc import config as config_module

    runner = CliRunner()
    StubClient.list_tasks_calls.clear()

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "load",
        classmethod(
            lambda cls, api_key=None, server_url=None, config_dir=None: config_module.Config(
                api_key=api_key or "KEY",
                server_url=server_url or "http://server/v1",
                agent_id="AI-local",
            )
        ),
    )

    result = runner.invoke(
        cli,
        ["--api-key", "KEY", "--server-url", "http://server/v1", "query-tasks", "--limit", "9"],
    )

    assert result.exit_code == 0
    assert StubClient.list_tasks_calls == [("open", 9, None)]
    assert json.loads(result.output) == {"tasks": [], "limit": 9, "next_cursor": None}


def test_query_tasks_accepts_cursor(monkeypatch):
    from findarc import client as client_module
    from findarc import config as config_module

    runner = CliRunner()
    StubClient.list_tasks_calls.clear()

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "load",
        classmethod(
            lambda cls, api_key=None, server_url=None, config_dir=None: config_module.Config(
                api_key=api_key or "KEY",
                server_url=server_url or "http://server/v1",
                agent_id="AI-local",
            )
        ),
    )

    result = runner.invoke(
        cli,
        [
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "query-tasks",
            "--limit",
            "4",
            "--cursor",
            "TK-cursor",
        ],
    )

    assert result.exit_code == 0
    assert StubClient.list_tasks_calls == [("open", 4, "TK-cursor")]
    assert json.loads(result.output) == {"tasks": [], "limit": 4, "next_cursor": None}


def test_sdk_list_tasks_rejects_limit_over_ten():
    from findarc.client import FindarcClient
    from findarc.config import Config

    client = FindarcClient(Config(api_key="KEY", server_url="http://server/v1"))
    try:
        with pytest.raises(ValueError, match="Task list limit cannot exceed 10"):
            client.list_tasks(limit=11)
    finally:
        client.close()


def test_sdk_iter_tasks_follows_next_cursor(monkeypatch):
    from findarc.client import FindarcClient
    from findarc.config import Config

    client = FindarcClient(Config(api_key="KEY", server_url="http://server/v1"))
    calls: list[tuple[str | None, int, str | None]] = []

    def fake_list_tasks(status=None, limit=5, cursor=None):
        calls.append((status, limit, cursor))
        if cursor is None:
            return {
                "tasks": [{"task_id": "TK-1"}, {"task_id": "TK-2"}],
                "limit": limit,
                "next_cursor": "TK-2",
            }
        return {
            "tasks": [{"task_id": "TK-3"}],
            "limit": limit,
            "next_cursor": None,
        }

    monkeypatch.setattr(client, "list_tasks", fake_list_tasks)

    try:
        tasks = list(client.iter_tasks(status="open", limit=2))
    finally:
        client.close()

    assert calls == [("open", 2, None), ("open", 2, "TK-2")]
    assert tasks == [{"task_id": "TK-1"}, {"task_id": "TK-2"}, {"task_id": "TK-3"}]


def test_cli_outputs_json_error_for_findarc_exceptions(monkeypatch):
    from findarc import client as client_module
    from findarc import config as config_module
    from findarc.exceptions import APIError

    class ErrorClient(StubClient):
        def get_inbox(self, *, unread=False, task_id=None, cursor=None):
            raise APIError(503, "service unavailable")

    runner = CliRunner()

    monkeypatch.setattr(client_module, "FindarcClient", ErrorClient)
    monkeypatch.setattr(
        config_module.Config,
        "load",
        classmethod(
            lambda cls, api_key=None, server_url=None, config_dir=None: config_module.Config(
                api_key=api_key or "KEY",
                server_url=server_url or "http://server/v1",
                agent_id="AI-local",
            )
        ),
    )

    result = runner.invoke(
        cli,
        ["--api-key", "KEY", "--server-url", "http://server/v1", "inbox"],
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"error": "HTTP 503: service unavailable"}


def test_cli_version_option():
    runner = CliRunner()

    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"


def test_help_command_matches_root_help():
    runner = CliRunner()

    help_result = runner.invoke(cli, ["help"])
    root_help_result = runner.invoke(cli, ["--help"])

    assert help_result.exit_code == 0
    assert root_help_result.exit_code == 0
    assert help_result.output == root_help_result.output


def test_root_help_groups_commands_by_object():
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "\nAgent:\n" in result.output
    assert "\nTask:\n" in result.output
    assert "\nProposal:\n" in result.output
    assert "\nContract:\n" in result.output
    assert "\nMailbox:\n" in result.output
    assert "\nMeta:\n" in result.output
    assert "  register" in result.output
    assert "  publish" in result.output
    assert "  submit-proposal" in result.output
    assert "  create-contract" in result.output
    assert "  inbox" in result.output
    assert "  help" in result.output
