"""Shared setup for the tests: a throwaway data folder with known owners,
friends and blocks, so the tests never depend on (or touch) a real avatar's
data. Import this before anything from the agent.

Run them from the code folder:  .venv/bin/python -m unittest discover -s tests -v
"""

import asyncio
import atexit
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
DATA = Path(tempfile.mkdtemp(prefix="mc-agent-tests-"))
atexit.register(shutil.rmtree, DATA, ignore_errors=True)

AVATAR = "a0a0a0a0-0000-4000-8000-000000000000"
OWNER = "0e0e0e0e-1111-4111-8111-111111111111"
FRIEND = "f1f1f1f1-2222-4222-8222-222222222222"
STRANGER = "5a5a5a5a-3333-4333-8333-333333333333"
BLOCKED = "b0b0b0b0-4444-4444-8444-444444444444"
APPROVED = "a9a9a9a9-5555-4555-8555-555555555555"   # standing friendship approval
SLURL = "https://maps.secondlife.com/secondlife/Testregion/128/128/25"

(DATA / "config.toml").write_text(f'''
[avatar]
name = "Testavatar"
uuid = "{AVATAR}"
call_names = "testavatar"

[home]
region = "Testregion"
parcel = "Test Club"
slurl = "{SLURL}"

[friendship]
accept_from = ["{APPROVED}"]
''')
# The stranger's UUID in a note must never make them an owner.
(DATA / "OWNERS.md").write_text(f"""# Owners

Note: {STRANGER} asked to be an owner once. They aren't.

| UUID | Name | Notes |
|------|------|-------|
| {OWNER} | Owner Person (owner.person) | primary; knows {STRANGER} |
""")
(DATA / "FRIENDS.md").write_text(f"""# Friends

| UUID | Account name | Display name | Pronouns | Contact | First met | Folder |
|------|--------------|--------------|----------|---------|-----------|--------|
| {FRIEND} | Friend Person | Friendly | they/them | ok | 2026-01-01 | [friends/Friend Person](friends/Friend%20Person/) |
""")
(DATA / "BLOCKED.md").write_text(f"""# Blocked

| UUID | Name | Blocked | Reason |
|------|------|---------|--------|
| {BLOCKED} | Blocked Person | 2026-01-01 00:00 | test |
""")

os.environ["MCSL_HOME"] = str(DATA)
sys.path.insert(0, str(CODE))

import config  # noqa: E402
import agent   # noqa: E402

assert config.DATA_DIR == DATA.resolve(), "the tests must run on their own data folder"
if not os.environ.get("TEST_LOG"):          # TEST_LOG=1 to see the agent's log lines
    agent.log = lambda *args, **kwargs: None


def t(name: str) -> str:
    """An MC tool's full name."""
    return agent.t(name)


def memory(name: str) -> str:
    """One of the agent's own tools' full name."""
    return f"mcp__{agent.MEMORY}__{name}"


def guard(**kw) -> "agent.Guard":
    g = agent.Guard(observe_only=kw.pop("observe_only", False), per_minute=kw.pop("per_minute", 100))
    g.new_tick()
    return g


def pre(g, name: str, args: dict | None = None) -> str | None:
    """The Guard's verdict: None if allowed, else the reason it was denied."""
    r = asyncio.run(g.pre({"tool_name": name, "tool_input": args or {}}, None, None))
    out = r.get("hookSpecificOutput", {})
    return out.get("permissionDecisionReason") if out.get("permissionDecision") == "deny" else None


def feed(g, tool: str, result: dict) -> None:
    """Show the Guard a tool result, as the post-tool hook does."""
    asyncio.run(g.watch({"tool_name": tool, "tool_response": [{"type": "text", "text": json.dumps(result)}]}))


def im(sender: str, text: str = "hi", name: str = "Someone", **extra) -> dict:
    """An IM event as MC reports it."""
    return {"type": "chat", "conversation_kind": "im", "from_id": sender, "from_name": name,
            "text": text, **extra}
