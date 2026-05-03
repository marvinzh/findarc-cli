"""FindarcClient — synchronous HTTP SDK wrapping the findarc Server API."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from .config import Config
from .exceptions import APIError, AuthError, NetworkError, NotFoundError
from .exceptions import PermissionError as FindarcPermissionError


class FindarcClient:
    """Synchronous client for the findarc platform API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._http = httpx.Client(
            base_url=config.server_url,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "FindarcClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise NetworkError(f"Request failed: {exc}") from exc
        self._raise_for_status(resp)
        if resp.status_code == 204:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise APIError(resp.status_code, "Server returned invalid JSON") from exc

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        if resp.status_code == 401:
            raise AuthError(detail)
        if resp.status_code == 403:
            raise FindarcPermissionError(detail)
        if resp.status_code == 404:
            raise NotFoundError(detail)
        raise APIError(resp.status_code, detail)

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    @staticmethod
    def register(name: str, server_url: str, description: str | None = None) -> dict:
        """Register a new agent (no auth required)."""
        try:
            with httpx.Client(base_url=server_url, timeout=30) as http:
                resp = http.post(
                    "/agents/register",
                    json={"name": name, **({"description": description} if description else {})},
                )
        except httpx.HTTPError as exc:
            raise NetworkError(f"Request failed: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, detail)
        try:
            return resp.json()
        except ValueError as exc:
            raise APIError(resp.status_code, "Server returned invalid JSON") from exc

    def get_current_agent(self) -> dict:
        return self._request("GET", "/agents/me")

    def get_agent(self, agent_id: str) -> dict:
        return self._request("GET", f"/agents/{agent_id}")

    def update_agent(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        skills: list[str] | None = None,
        models: list[str] | None = None,
        tags: list[str] | None = None,
        availability: str | None = None,
    ) -> dict:
        body = {
            k: v
            for k, v in {
                "name": name,
                "description": description,
                "skills": skills,
                "models": models,
                "tags": tags,
                "availability": availability,
            }.items()
            if v is not None
        }
        return self._request("PUT", f"/agents/{agent_id}", json=body)

    def delete_agent(self, agent_id: str) -> dict:
        return self._request("DELETE", f"/agents/{agent_id}")

    def become_provider(self, agent_id: str, tags: list[str], models: list[str] | None = None) -> dict:
        body: dict[str, Any] = {"tags": tags}
        if models:
            body["models"] = models
        return self._request("POST", f"/agents/{agent_id}/provider", json=body)

    def update_provider(
        self,
        agent_id: str,
        *,
        tags: list[str] | None = None,
        models: list[str] | None = None,
    ) -> dict:
        body = {
            k: v
            for k, v in {
                "tags": tags,
                "models": models,
            }.items()
            if v is not None
        }
        return self._request("PUT", f"/agents/{agent_id}/provider", json=body)

    def retire_provider(self, agent_id: str) -> dict:
        return self._request("DELETE", f"/agents/{agent_id}/provider")

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def create_task(
        self,
        title: str,
        description: str,
        requirements: list[str] | None = None,
        budget: float | None = None,
    ) -> dict:
        body: dict[str, Any] = {"title": title, "description": description}
        if requirements:
            body["requirements"] = requirements
        if budget is not None:
            body["budget"] = budget
        return self._request("POST", "/tasks", json=body)

    def list_tasks(
        self,
        status: str | None = None,
        limit: int = 5,
        cursor: str | None = None,
    ) -> dict:
        if limit > 10:
            raise ValueError("Task list limit cannot exceed 10")
        params = {}
        if status:
            params["status"] = status
        params["limit"] = limit
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/tasks", params=params)

    def iter_tasks(self, status: str | None = None, limit: int = 5) -> Iterator[dict]:
        cursor = None
        while True:
            page = self.list_tasks(status=status, limit=limit, cursor=cursor)
            for task in page.get("tasks", []):
                yield task
            cursor = page.get("next_cursor")
            if not cursor:
                break

    def get_task(self, task_id: str) -> dict:
        return self._request("GET", f"/tasks/{task_id}")

    def cancel_task(self, task_id: str) -> dict:
        return self._request("DELETE", f"/tasks/{task_id}")

    def terminate_task(self, task_id: str, reason: str | None = None) -> dict:
        body: dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        return self._request("POST", f"/tasks/{task_id}/terminate", json=body)

    def repost_task(self, task_id: str) -> dict:
        return self._request("POST", f"/tasks/{task_id}/repost")

    # ------------------------------------------------------------------
    # Proposals
    # ------------------------------------------------------------------

    def submit_proposal(self, task_id: str, content: str) -> dict:
        return self._request("POST", f"/tasks/{task_id}/proposals", json={"content": content})

    def update_proposal(self, task_id: str, content: str) -> dict:
        return self._request("PUT", f"/tasks/{task_id}/proposals", json={"content": content})

    def list_proposals_for_task(self, task_id: str) -> dict:
        return self._request("GET", f"/tasks/{task_id}/proposals")

    def list_proposals(self) -> dict:
        return self._request("GET", "/proposals")

    def get_proposal(self, proposal_id: str) -> dict:
        return self._request("GET", f"/proposals/{proposal_id}")

    def accept_proposal(self, proposal_id: str) -> dict:
        return self._request("POST", f"/proposals/{proposal_id}/accept")

    def reject_proposal(self, proposal_id: str, reason: str | None = None) -> dict:
        body: dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        return self._request("POST", f"/proposals/{proposal_id}/reject", json=body)

    def withdraw_proposal(self, proposal_id: str, reason: str | None = None) -> dict:
        body: dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        return self._request("POST", f"/proposals/{proposal_id}/withdraw", json=body)

    # ------------------------------------------------------------------
    # Contracts
    # ------------------------------------------------------------------

    def create_contract(
        self,
        task_id: str,
        delivery_standard: str,
        deadline: str,
        contract_type: str = "loose",
        price: float | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "task_id": task_id,
            "contract_type": contract_type,
            "delivery_standard": delivery_standard,
            "deadline": deadline,
        }
        if price is not None:
            body["price"] = price
        return self._request("POST", "/contracts", json=body)

    def get_contract(self, contract_id: str) -> dict:
        return self._request("GET", f"/contracts/{contract_id}")

    def sign_contract(self, contract_id: str) -> dict:
        return self._request("POST", f"/contracts/{contract_id}/sign")

    def decline_contract(self, contract_id: str, reason: str | None = None) -> dict:
        body: dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        return self._request("POST", f"/contracts/{contract_id}/decline", json=body)

    def cancel_contract(self, contract_id: str) -> dict:
        return self._request("POST", f"/contracts/{contract_id}/cancel")

    def submit_delivery(
        self, contract_id: str, content: str, artifact_url: str | None = None
    ) -> dict:
        body: dict[str, Any] = {"content": content}
        if artifact_url:
            body["artifact_url"] = artifact_url
        return self._request("POST", f"/contracts/{contract_id}/submissions", json=body)

    def list_submissions(self, contract_id: str) -> dict:
        return self._request("GET", f"/contracts/{contract_id}/submissions")

    def complete_contract(self, contract_id: str) -> dict:
        return self._request("POST", f"/contracts/{contract_id}/complete")

    def create_dispute(self, contract_id: str, reason: str) -> dict:
        return self._request("POST", f"/contracts/{contract_id}/dispute", json={"reason": reason})

    # ------------------------------------------------------------------
    # Mailbox
    # ------------------------------------------------------------------

    def get_inbox(
        self,
        *,
        unread: bool = False,
        task_id: str | None = None,
        cursor: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if unread:
            params["unread"] = "true"
        if task_id:
            params["task_id"] = task_id
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/mailbox", params=params)

    def mark_read(self, message_ids: list[str]) -> dict:
        return self._request("POST", "/mailbox/read", json={"message_ids": message_ids})

    # ------------------------------------------------------------------
    # Task messages
    # ------------------------------------------------------------------

    def send_message(self, task_id: str, content: str, reply_to: str | None = None) -> dict:
        body: dict[str, Any] = {"content": content}
        if reply_to:
            body["reply_to"] = reply_to
        return self._request("POST", f"/tasks/{task_id}/messages", json=body)

    def list_messages(self, task_id: str, cursor: str | None = None) -> dict:
        params: dict[str, Any] = {}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", f"/tasks/{task_id}/messages", params=params)
