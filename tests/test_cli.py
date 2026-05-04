import json
import sys
from pathlib import Path

from click.testing import CliRunner
import httpx
import pytest

from finda.cli.main import cli, main


class StubClient:
    register_calls: list[tuple[str, str, str | None]] = []
    current_agent_calls = 0
    get_status_calls: list[int] = []
    list_tasks_calls: list[tuple[str | None, int, str | None]] = []
    submit_proposal_calls: list[tuple[str, str]] = []
    update_proposal_calls: list[tuple[str, str]] = []
    get_proposal_calls: list[str] = []
    get_contract_calls: list[str] = []
    list_submissions_calls: list[str] = []
    download_artifact_calls: list[tuple[str, Path | None]] = []
    get_inbox_calls: list[tuple[bool, str | None, int | None, str | None]] = []
    withdraw_proposal_calls: list[tuple[str, str | None]] = []
    create_contract_calls: list[tuple[str, str, str, float | None]] = []

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

    def get_status(self, limit: int = 5) -> dict:
        StubClient.get_status_calls.append(limit)
        return {
            "generated_at": "2026-05-04T00:00:00Z",
            "limit": limit,
            "agent": {
                "agent_id": "AI-current",
                "name": "Current Agent",
                "role": "requester",
                "availability": "available",
                "tags": [],
                "models": [],
            },
            "tasks": {
                "as_requester": {"total": 1, "counts": [{"status": "open", "count": 1}], "items": []},
                "as_provider": {"total": 0, "counts": [], "items": []},
            },
            "proposals": {"total": 0, "counts": [], "items": []},
            "contracts": {
                "as_requester": {"total": 0, "counts": [], "items": []},
                "as_provider": {"total": 0, "counts": [], "items": []},
            },
            "mailbox": {"unread_count": 0},
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

    def submit_proposal(self, task_id: str, content: str) -> dict:
        StubClient.submit_proposal_calls.append((task_id, content))
        return {"task_id": task_id, "content": content}

    def update_proposal(self, task_id: str, content: str) -> dict:
        StubClient.update_proposal_calls.append((task_id, content))
        return {"task_id": task_id, "content": content}

    def get_proposal(self, proposal_id: str) -> dict:
        StubClient.get_proposal_calls.append(proposal_id)
        return {"proposal_id": proposal_id, "content": "# Proposal\n\nDetailed plan."}

    def get_contract(self, contract_id: str) -> dict:
        StubClient.get_contract_calls.append(contract_id)
        return {"contract_id": contract_id, "status": "pending_signature"}

    def list_submissions(self, contract_id: str) -> dict:
        StubClient.list_submissions_calls.append(contract_id)
        return {
            "submissions": [
                {
                    "submission_id": "SUB-20260504120000000000ABCD",
                    "contract_id": contract_id,
                    "task_id": "TK-1",
                    "submitted_by": "AI-provider",
                    "content": "Final delivery package",
                    "artifact_filename": "delivery.zip",
                    "created_at": "2026-05-04T12:00:00Z",
                }
            ]
        }

    def download_artifact(self, submission_id: str, output_path: Path | None = None) -> dict:
        StubClient.download_artifact_calls.append((submission_id, output_path))
        return {
            "submission_id": submission_id,
            "artifact_filename": "delivery.zip",
            "saved_to": str(output_path or Path("delivery.zip")),
        }

    def get_inbox(self, *, unread=False, task_id=None, limit=None, cursor=None) -> dict:
        StubClient.get_inbox_calls.append((unread, task_id, limit, cursor))
        return {
            "total": 1,
            "next_cursor": None,
            "messages": [
                {
                    "message_id": "MSG-1",
                    "type": "contract",
                    "task_id": "TK-1",
                    "proposal_id": None,
                    "contract_id": "CT-1",
                    "sender_agent_id": None,
                    "content": "Contract ready",
                    "read": False,
                    "created_at": "2026-05-04T12:00:00Z",
                }
            ],
        }

    def reject_proposal(self, proposal_id: str, reason: str | None = None) -> dict:
        return {"proposal_id": proposal_id, "status": "rejected", "reason": reason}

    def withdraw_proposal(self, proposal_id: str, reason: str | None = None) -> dict:
        StubClient.withdraw_proposal_calls.append((proposal_id, reason))
        return {"proposal_id": proposal_id, "status": "rejected", "reason": reason}

    def create_contract(
        self,
        task_id: str,
        delivery_standard: str,
        deadline: str,
        contract_type: str = "loose",
        price: float | None = None,
    ) -> dict:
        StubClient.create_contract_calls.append((task_id, delivery_standard, deadline, price))
        return {
            "task_id": task_id,
            "contract_type": contract_type,
            "delivery_standard": delivery_standard,
            "deadline": deadline,
            "price": price,
        }

    def submit_delivery(self, contract_id: str, content: str, artifact_zip: Path) -> dict:
        return {
            "contract_id": contract_id,
            "content": content,
            "artifact_filename": artifact_zip.name,
        }


def test_register_uses_global_server_url_override(monkeypatch):
    from finda import config as config_module
    from finda import client as client_module

    runner = CliRunner()
    saved: dict[str, str] = {}
    StubClient.register_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
    from finda import client as client_module

    runner = CliRunner()
    StubClient.register_calls.clear()
    config_dir = tmp_path / "finda-config"

    monkeypatch.setattr(client_module, "FindaClient", StubClient)

    result = runner.invoke(
        cli,
        ["--config", str(config_dir), "register", "--name", "agent"],
    )

    assert result.exit_code == 0
    assert StubClient.register_calls == [("agent", "http://svc.gofinda.today:8080/v1", None)]
    saved = json.loads((config_dir / "config.json").read_text())
    assert saved == {
        "agent_id": "AI-register",
        "api_key": "KEY-register",
        "server_url": "http://svc.gofinda.today:8080/v1",
    }
    assert "Credentials saved to config.json" in result.stderr


def test_register_fails_when_finda_directory_already_exists(monkeypatch):
    from finda import config as config_module
    from finda import client as client_module

    runner = CliRunner()
    StubClient.register_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
    assert result.stderr == "Error: Agent already registered.\n"


def test_register_uses_custom_config_directory_for_duplicate_check(monkeypatch, tmp_path):
    from finda import client as client_module

    runner = CliRunner()
    StubClient.register_calls.clear()
    config_dir = tmp_path / "finda-config"
    config_dir.mkdir()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)

    result = runner.invoke(
        cli,
        ["--config", str(config_dir), "register", "--name", "agent"],
    )

    assert result.exit_code == 1
    assert StubClient.register_calls == []
    assert result.stderr == "Error: Agent already registered.\n"


def test_register_duplicate_uses_json_error_when_requested(monkeypatch):
    from finda import config as config_module
    from finda import client as client_module

    runner = CliRunner()
    StubClient.register_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
    monkeypatch.setattr(
        config_module.Config,
        "registration_exists",
        staticmethod(lambda config_dir=None: True),
    )

    result = runner.invoke(
        cli,
        ["--json", "register", "--name", "agent"],
    )

    assert result.exit_code == 1
    assert StubClient.register_calls == []
    assert json.loads(result.stderr) == {"error": "Agent already registered."}


def test_whoami_uses_authenticated_agent_not_local_agent_id(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.current_agent_calls = 0

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--json", "--api-key", "KEY", "--server-url", "http://server/v1", "whoami"],
    )

    assert result.exit_code == 0
    assert StubClient.current_agent_calls == 1
    assert json.loads(result.output) == {
        "agent_id": "AI-current",
        "name": "Current Agent",
        "role": "requester",
    }


def test_whoami_loads_config_from_custom_directory(monkeypatch, tmp_path):
    from finda import client as client_module

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

    monkeypatch.setattr(client_module, "FindaClient", StubClient)

    result = runner.invoke(
        cli,
        ["--json", "--config", str(config_dir), "whoami"],
    )

    assert result.exit_code == 0
    assert StubClient.current_agent_calls == 1
    assert json.loads(result.output) == {
        "agent_id": "AI-current",
        "name": "Current Agent",
        "role": "requester",
    }


def test_whoami_pretty_prints_by_default(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.current_agent_calls = 0

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--api-key", "KEY", "--server-url", "http://server/v1", "whoami"],
    )

    assert result.exit_code == 0
    assert result.output == "agent_id: AI-current\nname: Current Agent\nrole: requester\n"


def test_serve_and_retire_resolve_current_agent_with_env_overrides(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--json", "serve", "--tags", "python,fastapi", "--models", "gpt-4.1"],
        env={"FINDA_API_KEY": "ENVKEY", "FINDA_SERVER_URL": "http://env/v1"},
    )
    retire_result = runner.invoke(
        cli,
        ["--json", "retire"],
        env={"FINDA_API_KEY": "ENVKEY", "FINDA_SERVER_URL": "http://env/v1"},
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
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.list_tasks_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--json", "--api-key", "KEY", "--server-url", "http://server/v1", "query-tasks"],
    )

    assert result.exit_code == 0
    assert StubClient.list_tasks_calls == [("open", 5, None)]
    assert json.loads(result.output) == {"tasks": [], "limit": 5, "next_cursor": None}


def test_query_tasks_pretty_prints_by_default(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.list_tasks_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
    assert result.output == "tasks:\n  []\nlimit: 5\nnext_cursor: null\n"


def test_query_tasks_accepts_custom_limit(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.list_tasks_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--json", "--api-key", "KEY", "--server-url", "http://server/v1", "query-tasks", "--limit", "9"],
    )

    assert result.exit_code == 0
    assert StubClient.list_tasks_calls == [("open", 9, None)]
    assert json.loads(result.output) == {"tasks": [], "limit": 9, "next_cursor": None}


def test_query_tasks_accepts_cursor(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.list_tasks_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
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
    from finda.client import FindaClient
    from finda.config import Config

    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
    try:
        with pytest.raises(ValueError, match="Task list limit cannot exceed 10"):
            client.list_tasks(limit=11)
    finally:
        client.close()


def test_sdk_iter_tasks_follows_next_cursor(monkeypatch):
    from finda.client import FindaClient
    from finda.config import Config

    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
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


def test_sdk_get_status_rejects_limit_over_ten():
    from finda.client import FindaClient
    from finda.config import Config

    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
    try:
        with pytest.raises(ValueError, match="Status list limit cannot exceed 10"):
            client.get_status(limit=11)
    finally:
        client.close()


def test_sdk_get_status_passes_limit(monkeypatch):
    from finda.client import FindaClient
    from finda.config import Config

    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"ok": True}

    monkeypatch.setattr(client, "_request", fake_request)

    try:
        result = client.get_status(limit=3)
    finally:
        client.close()

    assert result == {"ok": True}
    assert calls == [("GET", "/agents/me/status", {"params": {"limit": 3}})]


def test_sdk_submit_proposal_sends_markdown_content(monkeypatch):
    from finda.client import FindaClient
    from finda.config import Config

    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"ok": True}

    monkeypatch.setattr(client, "_request", fake_request)

    try:
        result = client.submit_proposal("TK-1", "# Proposal\n\nDetailed plan.")
    finally:
        client.close()

    assert result == {"ok": True}
    assert calls == [
        (
            "POST",
            "/tasks/TK-1/proposals",
            {"json": {"content": "# Proposal\n\nDetailed plan."}},
        )
    ]


def test_sdk_update_proposal_sends_markdown_content(monkeypatch):
    from finda.client import FindaClient
    from finda.config import Config

    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"ok": True}

    monkeypatch.setattr(client, "_request", fake_request)

    try:
        result = client.update_proposal("TK-1", "# Proposal\n\nDetailed update.")
    finally:
        client.close()

    assert result == {"ok": True}
    assert calls == [
        (
            "PUT",
            "/tasks/TK-1/proposals",
            {"json": {"content": "# Proposal\n\nDetailed update."}},
        )
    ]


def test_submit_proposal_reads_markdown_file(monkeypatch, tmp_path):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.submit_proposal_calls.clear()
    proposal_path = tmp_path / "proposal.md"
    proposal_path.write_text("# Proposal\n\nDetailed plan.", encoding="utf-8")

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "submit-proposal",
            "TK-1",
            str(proposal_path),
        ],
    )

    assert result.exit_code == 0
    assert StubClient.submit_proposal_calls == [("TK-1", "# Proposal\n\nDetailed plan.")]
    assert json.loads(result.output) == {
        "task_id": "TK-1",
        "content": "# Proposal\n\nDetailed plan.",
    }


def test_update_proposal_reads_markdown_file(monkeypatch, tmp_path):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.update_proposal_calls.clear()
    proposal_path = tmp_path / "proposal.md"
    proposal_path.write_text("# Proposal\n\nDetailed update.", encoding="utf-8")

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "update-proposal",
            "TK-1",
            str(proposal_path),
        ],
    )

    assert result.exit_code == 0
    assert StubClient.update_proposal_calls == [("TK-1", "# Proposal\n\nDetailed update.")]
    assert json.loads(result.output) == {
        "task_id": "TK-1",
        "content": "# Proposal\n\nDetailed update.",
    }


def test_show_proposal_fetches_proposal_by_id(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.get_proposal_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "show-proposal",
            "PP-1",
        ],
    )

    assert result.exit_code == 0
    assert StubClient.get_proposal_calls == ["PP-1"]
    assert json.loads(result.output) == {
        "proposal_id": "PP-1",
        "content": "# Proposal\n\nDetailed plan.",
    }


def test_withdraw_proposal_calls_client(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.withdraw_proposal_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "withdraw-proposal",
            "PP-1",
            "--reason",
            "No longer available",
        ],
    )

    assert result.exit_code == 0
    assert StubClient.withdraw_proposal_calls == [("PP-1", "No longer available")]
    assert json.loads(result.output) == {
        "proposal_id": "PP-1",
        "status": "rejected",
        "reason": "No longer available",
    }


def test_submit_proposal_requires_markdown_file(monkeypatch, tmp_path):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    proposal_path = tmp_path / "proposal.txt"
    proposal_path.write_text("Detailed plan.", encoding="utf-8")

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "submit-proposal",
            "TK-1",
            str(proposal_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {"error": "Proposal must be a .md file."}


def test_submit_proposal_rejects_empty_markdown_file(monkeypatch, tmp_path):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    proposal_path = tmp_path / "proposal.md"
    proposal_path.write_text(" \n", encoding="utf-8")

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "submit-proposal",
            "TK-1",
            str(proposal_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {"error": "Proposal markdown file cannot be empty."}


def test_submit_proposal_rejects_markdown_file_over_32kb(monkeypatch, tmp_path):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    proposal_path = tmp_path / "proposal.md"
    proposal_path.write_text("a" * (32 * 1024 + 1), encoding="utf-8")

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "submit-proposal",
            "TK-1",
            str(proposal_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {"error": "Proposal markdown file cannot exceed 32 KB."}


def test_cli_outputs_json_error_for_finda_exceptions(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module
    from finda.exceptions import APIError

    class ErrorClient(StubClient):
        def get_inbox(self, *, unread=False, task_id=None, limit=None, cursor=None):
            raise APIError(503, "service unavailable")

    runner = CliRunner()

    monkeypatch.setattr(client_module, "FindaClient", ErrorClient)
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
        ["--json", "--api-key", "KEY", "--server-url", "http://server/v1", "inbox"],
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"error": "HTTP 503: service unavailable"}


def test_inbox_uses_default_count_of_ten(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.get_inbox_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--json", "--api-key", "KEY", "--server-url", "http://server/v1", "inbox"],
    )

    assert result.exit_code == 0
    assert StubClient.get_inbox_calls == [(False, None, 10, None)]
    assert json.loads(result.output)["total"] == 1


def test_inbox_accepts_custom_count(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.get_inbox_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "inbox",
            "--count",
            "3",
        ],
    )

    assert result.exit_code == 0
    assert StubClient.get_inbox_calls == [(False, None, 3, None)]
    assert json.loads(result.output)["total"] == 1


def test_sdk_get_inbox_sends_limit_param(monkeypatch):
    from finda.client import FindaClient
    from finda.config import Config

    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
    captured: dict[str, object] = {}

    def fake_request(method: str, path: str, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = kwargs.get("params")
        return {"total": 0, "next_cursor": None, "messages": []}

    try:
        client._request = fake_request  # type: ignore[method-assign]
        result = client.get_inbox(limit=4)
    finally:
        client.close()

    assert captured == {
        "method": "GET",
        "path": "/mailbox",
        "params": {"limit": "4"},
    }
    assert result == {"total": 0, "next_cursor": None, "messages": []}


def test_cli_version_option():
    runner = CliRunner()

    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"


def test_status_command_fetches_current_status(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.get_status_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--json", "--api-key", "KEY", "--server-url", "http://server/v1", "status", "--limit", "3"],
    )

    assert result.exit_code == 0
    assert StubClient.get_status_calls == [3]
    assert json.loads(result.output)["limit"] == 3


def test_show_contract_fetches_contract_by_id(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.get_contract_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--json", "--api-key", "KEY", "--server-url", "http://server/v1", "show-contract", "CT-1"],
    )

    assert result.exit_code == 0
    assert StubClient.get_contract_calls == ["CT-1"]
    assert json.loads(result.output) == {"contract_id": "CT-1", "status": "pending_signature"}


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
    assert "\nOthers:\n" in result.output
    assert "  register" in result.output
    assert "  status" in result.output
    assert "  publish" in result.output
    assert "  show-task" in result.output
    assert "  submit-proposal" in result.output
    assert "  update-proposal" in result.output
    assert "  show-proposal" in result.output
    assert "  withdraw-proposal" in result.output
    assert "  create-contract" in result.output
    assert "  show-contract" in result.output
    assert "  inbox" in result.output
    assert "  help" in result.output


def test_root_help_shows_full_command_descriptions():
    runner = CliRunner()

    result = runner.invoke(cli, ["--config", "~/.finda", "help"])

    assert result.exit_code == 0
    assert "Register a new agent and save credentials to ~/.finda/config.json." in result.output
    assert "Show current agent status across tasks, proposals, contracts, and mailbox." in result.output
    assert "List open tasks available to accept (provider view)." in result.output
    assert "Cancel an open task (requester only, no provider yet)." in result.output
    assert "Submit a detailed markdown proposal for an open task (provider)." in result.output
    assert "Update an existing markdown proposal for a task (provider)." in result.output
    assert "Show details for a proposal." in result.output
    assert "Reject a proposal (requester only)." in result.output
    assert "Withdraw your own proposal (provider only)." in result.output
    assert "Create a contract after a proposal has been accepted." in result.output
    assert "Show details for a contract." in result.output
    assert "Submit a delivery artifact for an active contract (provider)." in result.output


def test_submit_help_uses_message_and_zip_artifact_option():
    runner = CliRunner()

    result = runner.invoke(cli, ["submit", "--help"])

    assert result.exit_code == 0
    assert "--message TEXT" in result.output
    assert "--artifact-zip FILE" in result.output
    assert "--content" not in result.output
    assert "--artifact-zip-url" not in result.output
    assert "delivery.zip" in result.output


def test_download_artifact_help_uses_saved_to_option():
    runner = CliRunner()

    result = runner.invoke(cli, ["download-artifact", "--help"])

    assert result.exit_code == 0
    assert "--saved-to FILE" in result.output
    assert "--output" not in result.output
    assert "downloads/delivery.zip" in result.output


def test_sdk_submit_delivery_rejects_non_zip_file(tmp_path):
    from finda.client import FindaClient
    from finda.config import Config

    artifact_path = tmp_path / "delivery.txt"
    artifact_path.write_text("not a zip", encoding="utf-8")
    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
    try:
        with pytest.raises(ValueError, match="Artifact file must be a .zip file"):
            client.submit_delivery("CT-1", content="Done", artifact_zip=artifact_path)
    finally:
        client.close()


def test_sdk_submit_delivery_rejects_zip_over_size_limit(tmp_path):
    from finda.client import FindaClient
    from finda.config import Config

    artifact_path = tmp_path / "delivery.zip"
    artifact_path.write_bytes(b"x" * ((32 * 1024 * 1024) + 1))
    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
    try:
        with pytest.raises(ValueError, match="Artifact zip file cannot exceed 32 MB\\."):
            client.submit_delivery("CT-1", content="Done", artifact_zip=artifact_path)
    finally:
        client.close()


def test_sdk_download_artifact_saves_response_content(tmp_path):
    from finda.client import FindaClient
    from finda.config import Config

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/contracts/submissions/SUB-1/artifact"
        return httpx.Response(
            200,
            headers={"content-disposition": 'attachment; filename="delivery.zip"'},
            content=b"zip-bytes",
        )

    client = FindaClient(Config(api_key="KEY", server_url="http://server/v1"))
    client._http = httpx.Client(
        base_url="http://server/v1",
        headers={"Authorization": "Bearer KEY"},
        transport=httpx.MockTransport(handler),
    )
    target = tmp_path / "downloads" / "delivery.zip"
    try:
        result = client.download_artifact("SUB-1", output_path=target)
    finally:
        client.close()

    assert target.read_bytes() == b"zip-bytes"
    assert result == {
        "submission_id": "SUB-1",
        "artifact_filename": "delivery.zip",
        "saved_to": str(target),
    }


def test_submit_uploads_zip_artifact(monkeypatch, tmp_path):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    artifact_path = tmp_path / "delivery.zip"
    artifact_path.write_bytes(b"zip-bytes")

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "submit",
            "CT-1",
            "--message",
            "Final delivery package",
            "--artifact-zip",
            str(artifact_path),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "contract_id": "CT-1",
        "content": "Final delivery package",
        "artifact_filename": "delivery.zip",
    }


def test_show_submissions_lists_contract_submissions(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.list_submissions_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--json", "--api-key", "KEY", "--server-url", "http://server/v1", "show-submissions", "CT-1"],
    )

    assert result.exit_code == 0
    assert StubClient.list_submissions_calls == ["CT-1"]
    assert json.loads(result.output)["submissions"][0]["artifact_filename"] == "delivery.zip"


def test_download_artifact_uses_default_filename(monkeypatch):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.download_artifact_calls.clear()

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
        ["--json", "--api-key", "KEY", "--server-url", "http://server/v1", "download-artifact", "SUB-1"],
    )

    assert result.exit_code == 0
    assert StubClient.download_artifact_calls == [("SUB-1", None)]
    assert json.loads(result.output) == {
        "submission_id": "SUB-1",
        "artifact_filename": "delivery.zip",
        "saved_to": "delivery.zip",
    }


def test_download_artifact_accepts_output_path(monkeypatch, tmp_path):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.download_artifact_calls.clear()
    output_path = tmp_path / "artifact.zip"

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "download-artifact",
            "SUB-1",
            "--saved-to",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert StubClient.download_artifact_calls == [("SUB-1", output_path)]
    assert json.loads(result.output) == {
        "submission_id": "SUB-1",
        "artifact_filename": "delivery.zip",
        "saved_to": str(output_path),
    }


def test_submit_rejects_zip_over_size_limit(monkeypatch, tmp_path):
    from finda import config as config_module

    runner = CliRunner()
    artifact_path = tmp_path / "delivery.zip"
    artifact_path.write_bytes(b"x" * ((32 * 1024 * 1024) + 1))

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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "submit",
            "CT-1",
            "--message",
            "Final delivery package",
            "--artifact-zip",
            str(artifact_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {"error": "Artifact zip file cannot exceed 32 MB."}


def test_create_contract_help_uses_deliverables_option():
    runner = CliRunner()

    result = runner.invoke(cli, ["create-contract", "--help"])

    assert result.exit_code == 0
    assert "--deliverables FILE" in result.output
    assert "--delivery-standard" not in result.output
    assert "deliverables.md" in result.output
    assert "2026-05-20T18:00:00+08:00" in result.output


def test_create_contract_reads_deliverables_markdown_file(monkeypatch, tmp_path):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    StubClient.create_contract_calls.clear()
    deliverables_path = tmp_path / "deliverables.md"
    deliverables_path.write_text("# Deliverables\n\nShip the API and tests.", encoding="utf-8")

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "create-contract",
            "--task-id",
            "TK-1",
            "--deliverables",
            str(deliverables_path),
            "--deadline",
            "2026-05-20T18:00:00+08:00",
        ],
    )

    assert result.exit_code == 0
    assert StubClient.create_contract_calls == [
        ("TK-1", "# Deliverables\n\nShip the API and tests.", "2026-05-20T18:00:00+08:00", None)
    ]
    assert json.loads(result.output) == {
        "task_id": "TK-1",
        "contract_type": "loose",
        "delivery_standard": "# Deliverables\n\nShip the API and tests.",
        "deadline": "2026-05-20T18:00:00+08:00",
        "price": None,
    }


def test_create_contract_requires_markdown_deliverables_file(monkeypatch, tmp_path):
    from finda import client as client_module
    from finda import config as config_module

    runner = CliRunner()
    deliverables_path = tmp_path / "deliverables.txt"
    deliverables_path.write_text("Ship the API and tests.", encoding="utf-8")

    monkeypatch.setattr(client_module, "FindaClient", StubClient)
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
            "--json",
            "--api-key",
            "KEY",
            "--server-url",
            "http://server/v1",
            "create-contract",
            "--task-id",
            "TK-1",
            "--deliverables",
            str(deliverables_path),
            "--deadline",
            "2026-05-20T18:00:00+08:00",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr) == {"error": "Deliverables must be a .md file."}


def test_main_shows_usage_body_without_json_for_missing_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["finda"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    assert captured.err.startswith("Usage: finda [OPTIONS] COMMAND [ARGS]...")
    assert '{"error":' not in captured.err
