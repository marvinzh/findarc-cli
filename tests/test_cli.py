import json

from click.testing import CliRunner

from findarc.cli.main import cli


class StubClient:
    register_calls: list[tuple[str, str, str | None]] = []
    current_agent_calls = 0

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
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        config_module.Config,
        "save",
        staticmethod(lambda agent_id, api_key, server_url: saved.update(
            {"agent_id": agent_id, "api_key": api_key, "server_url": server_url}
        )),
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
    }
    assert "Credentials saved to ~/.finda/config.json" in result.stderr


def test_register_fails_when_finda_directory_already_exists(monkeypatch):
    from findarc import config as config_module
    from findarc import client as client_module

    runner = CliRunner()
    StubClient.register_calls.clear()

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "registration_exists",
        staticmethod(lambda: True),
    )

    result = runner.invoke(
        cli,
        ["register", "--name", "agent"],
    )

    assert result.exit_code == 1
    assert StubClient.register_calls == []
    assert json.loads(result.stderr) == {
        "error": "Agent already registered. Remove ~/.finda to register again."
    }


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
            lambda cls, api_key=None, server_url=None: config_module.Config(
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


def test_serve_and_retire_resolve_current_agent_with_env_overrides(monkeypatch):
    from findarc import client as client_module
    from findarc import config as config_module

    runner = CliRunner()

    monkeypatch.setattr(client_module, "FindarcClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "load",
        classmethod(
            lambda cls, api_key=None, server_url=None: config_module.Config(
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
            lambda cls, api_key=None, server_url=None: config_module.Config(
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
