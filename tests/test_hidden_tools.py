"""MC tools the model may not use are hidden from it (they cost prompt tokens),
the list comes only from MC's own tools/list, and a bad or missing list hides
nothing: the Guard refuses those tools either way."""

import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import agent, guard, pre, t

MC_NAMES = ["status", "events", "say", "send_im", "answer", "login", "delete", "pay", "give", "block"]


def args(**kw) -> argparse.Namespace:
    base = dict(model="claude-opus-5-5", effort="medium", chat_backend="anthropic",
                chat_model="claude-haiku-5-5", chat_effort="medium", ollama_model=None,
                observe_only=False, max_turns=25)
    return argparse.Namespace(**{**base, **kw})


def options(**kw):
    with mock.patch.dict(os.environ, {"MC_API_TOKEN": "test-token"}):
        return agent.build_options(args(**kw), guard(), "chat")


def fake_mc(output: str) -> str:
    """A stand-in for `MorgenCommander --mcp` that prints `output` and exits."""
    d = Path(tempfile.mkdtemp(prefix="fake-mc-"))
    (d / "out.txt").write_text(output)
    script = d / "mc"
    script.write_text(f"#!{sys.executable}\nimport sys\nsys.stdin.read()\n"
                      f"sys.stdout.write(open({str(d / 'out.txt')!r}).read())\n")
    script.chmod(0o755)
    return str(script)


def tools_list(*names, id=2) -> str:
    import json
    return json.dumps({"jsonrpc": "2.0", "id": id, "result": {"tools": [{"name": n} for n in names]}}) + "\n"


class Hidden(unittest.TestCase):
    def setUp(self):
        self.saved = list(agent.MC_OFFERED)
        agent.MC_OFFERED[:] = MC_NAMES

    def tearDown(self):
        agent.MC_OFFERED[:] = self.saved

    def test_unallowed_tools_hidden(self):
        hidden = options().disallowed_tools
        for name in ("delete", "pay", "give", "block"):
            self.assertIn(t(name), hidden)

    def test_allowed_tools_stay_visible(self):
        o = options()
        for name in ("status", "events", "say", "send_im", "answer", "login"):
            self.assertNotIn(t(name), o.disallowed_tools)
            self.assertIn(t(name), o.allowed_tools)

    def test_observe_only_hides_acting_tools(self):
        hidden = options(observe_only=True).disallowed_tools
        for name in ("say", "send_im", "answer", "login"):
            self.assertIn(t(name), hidden)
        self.assertNotIn(t("events"), hidden)

    def test_own_tools_never_hidden(self):
        self.assertFalse([n for n in options().disallowed_tools if not n.startswith(f"mcp__{agent.SERVER}__")])

    def test_unknown_list_hides_nothing_and_guard_still_refuses(self):
        agent.MC_OFFERED[:] = []
        self.assertEqual(options().disallowed_tools, agent.BLOCKED_TOOLS)
        self.assertIsNotNone(pre(guard(), t("delete"), {"id": "x"}))
        self.assertIsNotNone(pre(guard(), t("pay"), {"to": "x", "amount": 10}))

    def test_hidden_tool_called_anyway_is_refused(self):
        self.assertIsNotNone(pre(guard(), t("give"), {"to": "x", "item": "y"}))


class Listing(unittest.TestCase):
    def listed(self, output: str):
        with mock.patch.object(agent, "MC_COMMAND", fake_mc(output)):
            return agent.list_mc_tools("test-token", timeout=10)

    def test_reads_tools_list(self):
        out = tools_list("status", "say")
        self.assertEqual(self.listed('{"jsonrpc":"2.0","id":1,"result":{}}\n' + out), ["status", "say"])

    def test_odd_names_dropped(self):
        self.assertEqual(self.listed(tools_list("say", "say; rm -rf", "../x", "", "events")), ["say", "events"])

    def test_non_string_and_non_dict_entries_dropped(self):
        out = '{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":5},"say",{"name":"status"},null]}}\n'
        self.assertEqual(self.listed(out), ["status"])

    def test_garbage_or_error_gives_none(self):
        self.assertIsNone(self.listed("not json\n[1,2]\n"))
        self.assertIsNone(self.listed('{"jsonrpc":"2.0","id":2,"error":{"code":-1}}\n'))
        self.assertIsNone(self.listed('{"jsonrpc":"2.0","id":2,"result":{"tools":"say"}}\n'))
        self.assertIsNone(self.listed(""))

    def test_answer_to_another_id_ignored(self):
        self.assertIsNone(self.listed(tools_list("say", id=3)))

    def test_missing_mc_gives_none(self):
        with mock.patch.object(agent, "MC_COMMAND", "/nonexistent/MorgenCommander"):
            self.assertIsNone(agent.list_mc_tools("test-token"))

    def test_refresh_keeps_last_good_list(self):
        saved = list(agent.MC_OFFERED)
        try:
            agent.MC_OFFERED[:] = ["status", "say"]
            with mock.patch.object(agent, "list_mc_tools", return_value=None):
                agent.refresh_mc_tools("test-token")
            self.assertEqual(agent.MC_OFFERED, ["status", "say"])
            with mock.patch.object(agent, "list_mc_tools", return_value=["status", "say", "pay"]):
                agent.refresh_mc_tools("test-token")
            self.assertEqual(agent.MC_OFFERED, ["status", "say", "pay"])
        finally:
            agent.MC_OFFERED[:] = saved


if __name__ == "__main__":
    unittest.main()
