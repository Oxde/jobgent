"""Chat that edits the profile. The model proposes dotted-path edits; we apply them and report back."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from jobgent.llm import LLM
from jobgent.profile.store import ProfileStore

_PROMPT = (Path(__file__).parent / "prompts" / "assistant.md").read_text()
Turn = tuple[str, str]  # (role, text)


class ProfileEdit(BaseModel):
    path: str
    value: str


class AssistantReply(BaseModel):
    reply: str
    edits: list[ProfileEdit] = Field(default_factory=list)
    notes: str | None = None


class ChatResult(BaseModel):
    reply: str
    applied: list[str]
    failed: list[str]


def _render(profile_yaml: str, history: list[Turn], message: str) -> str:
    convo = "\n".join(f"{role}: {text}" for role, text in history[-12:])
    return f"## Profile\n{profile_yaml}\n\n## Conversation so far\n{convo}\n\n## New message\nuser: {message}"


def chat(llm: LLM, model: str, store: ProfileStore, history: list[Turn], message: str) -> ChatResult:
    profile_yaml = yaml.safe_dump(store.load().model_dump(mode="json"), sort_keys=False, allow_unicode=True)
    out = llm.complete_json(
        model=model, system=_PROMPT, user=_render(profile_yaml, history, message), schema=AssistantReply, max_tokens=4096
    )
    applied: list[str] = []
    failed: list[str] = []
    for edit in out.edits:
        try:
            store.update(edit.path, edit.value)
            applied.append(edit.path)
        except (KeyError, ValueError) as e:
            failed.append(f"{edit.path}: {e}")
    if out.notes:
        store.notes_append(out.notes)
    return ChatResult(reply=out.reply, applied=applied, failed=failed)
