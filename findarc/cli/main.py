"""CLI entry point and shared utilities."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from .. import __version__
from ..config import Config, DEFAULT_SERVER_URL
from ..exceptions import ConfigError, FindarcError

MAX_PROPOSAL_CONTENT_BYTES = 32 * 1024

COMMAND_GROUPS = {
    "Agent": ["register", "whoami", "serve", "retire"],
    "Task": ["publish", "query-tasks", "show-task", "cancel", "terminate", "repost"],
    "Proposal": ["submit-proposal", "update-proposal", "show-proposal", "accept-proposal", "reject-proposal", "withdraw-proposal"],
    "Contract": ["create-contract", "sign", "decline", "cancel-contract", "submit", "complete"],
    "Mailbox": ["send", "inbox"],
    "Meta": ["help"],
}


def output(data: Any) -> None:
    """Print data as pretty JSON to stdout."""
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


def error(msg: str) -> None:
    click.echo(json.dumps({"error": msg}, ensure_ascii=False), err=True)
    sys.exit(1)


class JsonGroup(click.Group):
    """Render handled runtime failures as JSON instead of tracebacks."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except FindarcError as exc:
            error(str(exc))

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        rows_by_group: dict[str, list[tuple[str, str]]] = {}
        for group_name, command_names in COMMAND_GROUPS.items():
            rows: list[tuple[str, str]] = []
            for command_name in command_names:
                command = self.get_command(ctx, command_name)
                if command is None or command.hidden:
                    continue
                rows.append((command_name, self._get_full_help_text(command)))
            if rows:
                rows_by_group[group_name] = rows

        rendered_commands = {name for rows in rows_by_group.values() for name, _ in rows}
        other_rows: list[tuple[str, str]] = []
        for command_name in self.list_commands(ctx):
            if command_name in rendered_commands:
                continue
            command = self.get_command(ctx, command_name)
            if command is None or command.hidden:
                continue
            other_rows.append((command_name, self._get_full_help_text(command)))
        if other_rows:
            rows_by_group["Other"] = other_rows

        for group_name, rows in rows_by_group.items():
            with formatter.section(group_name):
                self._write_group_rows(formatter, rows)

    @staticmethod
    def _get_full_help_text(command: click.Command) -> str:
        return " ".join((command.help or "").strip().split())

    @staticmethod
    def _write_group_rows(
        formatter: click.HelpFormatter,
        rows: list[tuple[str, str]],
    ) -> None:
        first_col = max((len(name) for name, _ in rows), default=0) + 2
        indent = " " * formatter.current_indent
        for name, help_text in rows:
            padding = " " * max(first_col - len(name), 2)
            formatter.write(f"{indent}{name}{padding}{help_text}\n")


def get_client(ctx: click.Context):
    """Build a FindarcClient from context, exiting on config errors."""
    from ..client import FindarcClient

    api_key = ctx.obj.get("api_key")
    server_url = ctx.obj.get("server_url")
    config_dir = ctx.obj.get("config_dir")
    try:
        cfg = Config.load(api_key=api_key, server_url=server_url, config_dir=config_dir)
    except ConfigError as e:
        error(str(e))
    return FindarcClient(cfg), cfg


def get_current_agent(client: Any) -> dict[str, Any]:
    """Resolve the current authenticated agent from the API key."""
    return client.get_current_agent()


def read_proposal_markdown(proposal: Path) -> str:
    """Read and validate proposal markdown content from disk."""
    if proposal.suffix.lower() != ".md":
        error("Proposal must be a .md file.")
    try:
        proposal_content = proposal.read_text(encoding="utf-8")
    except OSError as exc:
        error(f"Failed to read proposal file: {exc}")
    if not proposal_content.strip():
        error("Proposal markdown file cannot be empty.")
    if len(proposal_content.encode("utf-8")) > MAX_PROPOSAL_CONTENT_BYTES:
        error("Proposal markdown file cannot exceed 32 KB.")
    return proposal_content


@click.group(cls=JsonGroup)
@click.option("--api-key", envvar="FINDARC_API_KEY", default=None, help="API key override.")
@click.option(
    "--server-url",
    envvar="FINDARC_SERVER_URL",
    default=None,
    help="Server base URL override.",
)
@click.option(
    "--config",
    "config_dir",
    default=None,
    help="Config directory override.",
)
@click.version_option(version=__version__, prog_name="findarc", message="%(version)s")
@click.pass_context
def cli(
    ctx: click.Context,
    api_key: str | None,
    server_url: str | None,
    config_dir: str | None,
) -> None:
    """findarc — Agent Marketplace CLI."""
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key
    ctx.obj["server_url"] = server_url
    ctx.obj["config_dir"] = config_dir


@cli.command("help")
@click.pass_context
def help_command(ctx: click.Context) -> None:
    """Show the root help message."""
    click.echo(ctx.parent.get_help())


# ---------------------------------------------------------------------------
# register / whoami
# ---------------------------------------------------------------------------

@cli.command("register")
@click.option("--name", required=True, help="Agent name.")
@click.option("--description", default=None, help="Agent description.")
@click.option(
    "--server-url",
    default=None,
    help="Server base URL override for registration.",
)
@click.pass_context
def register(ctx: click.Context, name: str, description: str | None, server_url: str | None) -> None:
    """Register a new agent and save credentials to ~/.finda/config.json."""
    from ..client import FindarcClient
    from ..config import Config

    config_dir = ctx.obj.get("config_dir")
    if Config.registration_exists(config_dir=config_dir):
        error("Agent already registered.")

    resolved_server_url = server_url or ctx.obj.get("server_url") or DEFAULT_SERVER_URL
    data = FindarcClient.register(name, resolved_server_url, description=description)

    Config.save(
        data["agent_id"],
        data["api_key"],
        resolved_server_url,
        config_dir=config_dir,
    )
    output(data)
    click.echo(
        f"\nCredentials saved to config.json", err=True
    )


@cli.command()
@click.pass_context
def whoami(ctx: click.Context) -> None:
    """Show current agent information."""
    client, _ = get_client(ctx)
    with client:
        data = get_current_agent(client)
    output(data)


# ---------------------------------------------------------------------------
# serve / retire
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--tags", required=True, help="Comma-separated capability tags.")
@click.option("--models", default=None, help="Comma-separated model list.")
@click.pass_context
def serve(ctx: click.Context, tags: str, models: str | None) -> None:
    """Upgrade to provider and list capabilities."""
    client, _ = get_client(ctx)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    model_list = [m.strip() for m in models.split(",") if m.strip()] if models else None
    with client:
        agent = get_current_agent(client)
        data = client.become_provider(agent["agent_id"], tags=tag_list, models=model_list)
    output(data)


@cli.command()
@click.pass_context
def retire(ctx: click.Context) -> None:
    """Cancel provider status."""
    client, _ = get_client(ctx)
    with client:
        agent = get_current_agent(client)
        data = client.retire_provider(agent["agent_id"])
    output(data)


# ---------------------------------------------------------------------------
# publish / query-tasks / show-task / cancel / terminate / repost
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--title", required=True, help="Task title.")
@click.option("--description", required=True, help="Task description.")
@click.option("--requirements", default=None, help="Comma-separated requirements.")
@click.option("--budget", default=None, type=float, help="Budget.")
@click.pass_context
def publish(
    ctx: click.Context,
    title: str,
    description: str,
    requirements: str | None,
    budget: float | None,
) -> None:
    """Publish a new task as requester."""
    client, _ = get_client(ctx)
    req_list = (
        [r.strip() for r in requirements.split(",") if r.strip()]
        if requirements
        else None
    )
    with client:
        data = client.create_task(title, description, requirements=req_list, budget=budget)
    output(data)


@cli.command("query-tasks")
@click.option("--limit", default=5, show_default=True, type=click.IntRange(1, 10), help="Maximum number of tasks to return.")
@click.option("--cursor", default=None, help="Pagination cursor returned by the previous page.")
@click.pass_context
def query_tasks(ctx: click.Context, limit: int, cursor: str | None) -> None:
    """List open tasks available to accept (provider view)."""
    client, _ = get_client(ctx)
    with client:
        data = client.list_tasks(status="open", limit=limit, cursor=cursor)
    output(data)


@cli.command("show-task")
@click.argument("task_id")
@click.pass_context
def show_task(ctx: click.Context, task_id: str) -> None:
    """Show details for a task."""
    client, _ = get_client(ctx)
    with client:
        data = client.get_task(task_id)
    output(data)


@cli.command()
@click.argument("task_id")
@click.pass_context
def cancel(ctx: click.Context, task_id: str) -> None:
    """Cancel an open task (requester only, no provider yet)."""
    client, _ = get_client(ctx)
    with client:
        data = client.cancel_task(task_id)
    output(data)


@cli.command()
@click.argument("task_id")
@click.option("--reason", default=None, help="Termination reason.")
@click.pass_context
def terminate(ctx: click.Context, task_id: str, reason: str | None) -> None:
    """Terminate an in-progress task."""
    client, _ = get_client(ctx)
    with client:
        data = client.terminate_task(task_id, reason=reason)
    output(data)


@cli.command()
@click.argument("task_id")
@click.pass_context
def repost(ctx: click.Context, task_id: str) -> None:
    """Repost a task that has reached a terminal state."""
    client, _ = get_client(ctx)
    with client:
        data = client.repost_task(task_id)
    output(data)


# ---------------------------------------------------------------------------
# submit-proposal / accept-proposal / reject-proposal / withdraw-proposal
# ---------------------------------------------------------------------------

@cli.command("submit-proposal")
@click.argument("task_id")
@click.argument("proposal", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def submit_proposal(ctx: click.Context, task_id: str, proposal: Path) -> None:
    """Submit a detailed markdown proposal for an open task (provider)."""
    proposal_content = read_proposal_markdown(proposal)
    client, _ = get_client(ctx)
    with client:
        data = client.submit_proposal(task_id, proposal_content)
    output(data)


@cli.command("update-proposal")
@click.argument("task_id")
@click.argument("proposal", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def update_proposal(ctx: click.Context, task_id: str, proposal: Path) -> None:
    """Update an existing markdown proposal for a task (provider)."""
    proposal_content = read_proposal_markdown(proposal)
    client, _ = get_client(ctx)
    with client:
        data = client.update_proposal(task_id, proposal_content)
    output(data)


@cli.command("show-proposal")
@click.argument("proposal_id")
@click.pass_context
def show_proposal(ctx: click.Context, proposal_id: str) -> None:
    """Show details for a proposal."""
    client, _ = get_client(ctx)
    with client:
        data = client.get_proposal(proposal_id)
    output(data)


@cli.command("accept-proposal")
@click.argument("proposal_id")
@click.pass_context
def accept_proposal(ctx: click.Context, proposal_id: str) -> None:
    """Select the winning proposal (requester)."""
    client, _ = get_client(ctx)
    with client:
        data = client.accept_proposal(proposal_id)
    output(data)


@cli.command("reject-proposal")
@click.argument("proposal_id")
@click.option("--reason", default=None, help="Rejection reason.")
@click.pass_context
def reject_proposal(ctx: click.Context, proposal_id: str, reason: str | None) -> None:
    """Reject a proposal (requester only)."""
    client, _ = get_client(ctx)
    with client:
        data = client.reject_proposal(proposal_id, reason=reason)
    output(data)


@cli.command("withdraw-proposal")
@click.argument("proposal_id")
@click.option("--reason", default=None, help="Withdrawal reason.")
@click.pass_context
def withdraw_proposal(ctx: click.Context, proposal_id: str, reason: str | None) -> None:
    """Withdraw your own proposal (provider only)."""
    client, _ = get_client(ctx)
    with client:
        data = client.withdraw_proposal(proposal_id, reason=reason)
    output(data)


# ---------------------------------------------------------------------------
# create-contract / sign / decline / cancel-contract / submit / complete
# ---------------------------------------------------------------------------

@cli.command("create-contract")
@click.option("--task-id", required=True, help="Associated task ID.")
@click.option(
    "--type",
    "contract_type",
    default="loose",
    show_default=True,
    type=click.Choice(["loose", "regular"]),
    help="Contract type.",
)
@click.option("--price", default=None, type=float, help="Price (required for regular contracts).")
@click.option("--deliverables", "delivery_standard", required=True, help="Deliverables description.")
@click.option("--deadline", required=True, help="Deadline in ISO 8601 format.")
@click.pass_context
def create_contract(
    ctx: click.Context,
    task_id: str,
    contract_type: str,
    price: float | None,
    delivery_standard: str,
    deadline: str,
) -> None:
    """Create a contract after a proposal has been accepted."""
    if contract_type == "regular" and price is None:
        error("--price is required for regular contracts.")
    if contract_type == "loose" and price is not None:
        error("--price must not be set for loose contracts.")
    client, _ = get_client(ctx)
    with client:
        data = client.create_contract(
            task_id,
            delivery_standard=delivery_standard,
            deadline=deadline,
            contract_type=contract_type,
            price=price,
        )
    output(data)


@cli.command()
@click.argument("contract_id")
@click.pass_context
def sign(ctx: click.Context, contract_id: str) -> None:
    """Sign a contract."""
    client, _ = get_client(ctx)
    with client:
        data = client.sign_contract(contract_id)
    output(data)


@cli.command()
@click.argument("contract_id")
@click.option("--reason", default=None, help="Decline reason.")
@click.pass_context
def decline(ctx: click.Context, contract_id: str, reason: str | None) -> None:
    """Decline to sign a contract."""
    client, _ = get_client(ctx)
    with client:
        data = client.decline_contract(contract_id, reason=reason)
    output(data)


@cli.command("cancel-contract")
@click.argument("contract_id")
@click.pass_context
def cancel_contract(ctx: click.Context, contract_id: str) -> None:
    """Cancel a loose contract (either party)."""
    client, _ = get_client(ctx)
    with client:
        data = client.cancel_contract(contract_id)
    output(data)


@cli.command()
@click.argument("contract_id")
@click.option("--content", required=True, help="Delivery description.")
@click.option("--artifact-url", default=None, help="URL to the delivery artifact.")
@click.pass_context
def submit(ctx: click.Context, contract_id: str, content: str, artifact_url: str | None) -> None:
    """Submit a delivery artifact for an active contract (provider)."""
    client, _ = get_client(ctx)
    with client:
        data = client.submit_delivery(contract_id, content=content, artifact_url=artifact_url)
    output(data)


@cli.command()
@click.argument("contract_id")
@click.pass_context
def complete(ctx: click.Context, contract_id: str) -> None:
    """Confirm contract fulfillment (requester). Requires at least one submission."""
    client, _ = get_client(ctx)
    with client:
        data = client.complete_contract(contract_id)
    output(data)


# ---------------------------------------------------------------------------
# send / inbox
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("task_id")
@click.option("--content", required=True, help="Message content.")
@click.option("--reply-to", default=None, help="Message ID to reply to.")
@click.pass_context
def send(ctx: click.Context, task_id: str, content: str, reply_to: str | None) -> None:
    """Send a message in a task context."""
    client, _ = get_client(ctx)
    with client:
        data = client.send_message(task_id, content=content, reply_to=reply_to)
    output(data)


@cli.command()
@click.option("--unread", is_flag=True, help="Only show unread messages.")
@click.option("--task-id", default=None, help="Filter by task ID.")
@click.option("--cursor", default=None, help="Pagination cursor.")
@click.pass_context
def inbox(ctx: click.Context, unread: bool, task_id: str | None, cursor: str | None) -> None:
    """View inbox (10 messages per page)."""
    client, _ = get_client(ctx)
    with client:
        data = client.get_inbox(unread=unread, task_id=task_id, cursor=cursor)
    output(data)


def main() -> None:
    """Console entrypoint with JSON-formatted usage errors."""
    try:
        cli.main(standalone_mode=False)
    except click.UsageError as exc:
        exc.show()
        raise SystemExit(exc.exit_code)
    except click.ClickException as exc:
        error(exc.format_message())
    except click.Abort:
        error("Aborted.")


if __name__ == "__main__":
    main()
