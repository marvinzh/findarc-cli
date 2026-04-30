"""Data models for the findarc SDK (TypedDict-based for easy JSON serialization)."""
from __future__ import annotations

from typing import Any


# Reuse plain dict / TypedDict style — keep it lightweight.
# All models are just type aliases over dict so SDK responses are directly
# JSON-serialisable without extra conversion.

AgentResponse = dict[str, Any]
TaskResponse = dict[str, Any]
ProposalResponse = dict[str, Any]
ContractResponse = dict[str, Any]
MessageResponse = dict[str, Any]
MailboxResponse = dict[str, Any]
SubmissionResponse = dict[str, Any]
