import asyncio
from types import SimpleNamespace

import pytest

from src.activities import subagent


def test_missing_api_key_fails_clearly(monkeypatch):
    """No live Anthropic call in CI -- this only exercises the
    configuration-guard path (same "keep CI fast, no live dependencies"
    approach as every other test in this repo). Stubs get_settings()
    directly rather than deleting the env var, since a local .env file
    (used for local dev) can otherwise still supply a real key via
    pydantic-settings' env_file fallback."""
    monkeypatch.setattr(
        subagent, "get_settings",
        lambda: SimpleNamespace(anthropic_api_key=None, default_model="claude-haiku-4-5-20251001",
                                draft_delay_seconds=0),
    )

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        asyncio.run(subagent.draft_email_activity("a@example.com", "Hello", "say hi"))
