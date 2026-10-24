"""Filling in the HUD scripts' settings: only checked values, and no script at
all when one is missing or unsafe."""

import asyncio
import re
import unittest
from unittest import mock

from support import AVATAR, OWNER, agent, config

DANCE = agent._repo_script("dance_hud").read_text()
WEARING = agent._repo_script("wearing").read_text()


def fill(text=DANCE + WEARING):
    return agent.fill_script(text)


class FillScript(unittest.TestCase):
    def test_fills_everything(self):
        for name, text in (("dance_hud", DANCE), ("wearing", WEARING)):
            with self.subTest(script=name):
                out, why = fill(text)
                self.assertIsNotNone(out, why)
                self.assertFalse(re.search(r"@@[A-Z_]+@@", out))
        out, _ = fill(DANCE)
        self.assertIn(f'key AVATAR = "{AVATAR}";', out)
        self.assertIn(f'list OWNERS = ["{OWNER}"];', out)
        self.assertIn("list COMMANDERS = [];", out)
        self.assertIn("integer CMD_CHANNEL = 34336;", out)
        out, _ = fill(WEARING)
        self.assertIn('string HOME_REGION = "Testregion";', out)

    def refused(self, **patch):
        with mock.patch.multiple(config, **patch):
            out, why = fill()
        self.assertIsNone(out)
        return why

    def test_no_avatar_uuid(self):
        self.refused(AVATAR_UUID="")

    def test_lsl_injection_through_settings(self):
        self.refused(AVATAR_UUID='x"; llDie(); //')
        self.refused(HOME_PARCEL='Club"; llDie(); string x = "')
        self.refused(HOME_REGION="Test\\region")
        self.refused(HOME_REGION="Test\nregion")

    def test_empty_parcel(self):
        self.refused(HOME_PARCEL="")

    def huds(self, **values):
        real = config.get
        return lambda section, key: values.get(key, real(section, key)) if section == "huds" else real(section, key)

    def test_bad_channels(self):
        for channel in (0, "34336; llDie()", None):
            with self.subTest(channel=channel):
                self.refused(get=self.huds(dance_channel=channel))

    def test_bad_commander(self):
        self.refused(get=self.huds(extra_commanders=['x", llDie(), "']))

    def test_no_owners(self):
        with mock.patch.object(agent, "owner_uuids", lambda: set()):
            out, _ = fill()
        self.assertIsNone(out)

    def test_unknown_placeholder(self):
        out, why = fill('key X = "@@SOMETHING_NEW@@";')
        self.assertIsNone(out)
        self.assertIn("SOMETHING_NEW", why)


class TidyScripts(unittest.TestCase):
    """tidy_scripts: old versions and extra copies of the repo's scripts go to
    the Trash, by id; the newest copy and everything else stay."""

    V = agent.script_version(agent._repo_script("dance_hud"))

    def entry(self, name, id, created="2026-10-24T15:00:00+00:00", type="script"):
        e = {"name": name, "id": id, "type": type}
        if created:
            e["created"] = created
        return e

    def ids(self, entries):
        go, notes = agent.scripts_to_tidy(entries)
        return sorted(e["id"] for e, _ in go), notes

    def test_extra_copy_of_current_version(self):
        cur = f"dance_hud-v{self.V}"
        go, _ = self.ids([self.entry(cur, "old", "2026-10-18T10:00:00+00:00"),
                          self.entry(cur, "new", "2026-10-24T15:58:00+00:00")])
        self.assertEqual(go, ["old"])

    def test_three_copies_keep_the_newest(self):
        cur = f"dance_hud-v{self.V}"
        go, _ = self.ids([self.entry(cur, "a", "2026-10-01T00:00:00+00:00"),
                          self.entry(cur, "c", "2026-10-24T00:00:00+00:00"),
                          self.entry(cur, "b", "2026-10-10T00:00:00+00:00")])
        self.assertEqual(go, ["a", "b"])

    def test_old_versions_and_unversioned(self):
        go, _ = self.ids([self.entry("dance_hud-v1.0.0", "v1"), self.entry("dance_hud", "plain"),
                          self.entry(f"dance_hud-v{self.V}", "current")])
        self.assertEqual(go, ["plain", "v1"])

    def test_same_named_old_copies_each_by_their_own_id(self):
        go, _ = self.ids([self.entry("dance_hud-v1.0.0", "x1"), self.entry("dance_hud-v1.0.0", "x2")])
        self.assertEqual(go, ["x1", "x2"])

    def test_no_dates_left_alone(self):
        cur = f"dance_hud-v{self.V}"
        go, notes = self.ids([self.entry(cur, "a", None), self.entry(cur, "b")])
        self.assertEqual(go, [])
        self.assertTrue(notes and "left alone" in notes[0])

    def test_no_id_left_alone(self):
        go, notes = self.ids([{"name": "dance_hud-v1.0.0", "type": "script"}])
        self.assertEqual(go, [])
        self.assertTrue(notes)

    def test_other_scripts_never_touched(self):
        go, _ = self.ids([self.entry("My own script", "m1", "2026-10-01T00:00:00+00:00"),
                          self.entry("My own script", "m2", "2026-10-24T00:00:00+00:00"),
                          self.entry("dance_hud_extra-v1.0.0", "lookalike"),
                          self.entry(f"dance_hud-v{self.V}", "notecard", type="notecard"),
                          self.entry(f"dance_hud-v{self.V}", "notecard2", type="notecard")])
        self.assertEqual(go, [])

    def test_tool_deletes_by_id(self):
        cur = f"dance_hud-v{self.V}"
        listing = {"ok": True, "entries": [self.entry(cur, "old-id", "2026-10-18T10:00:00+00:00"),
                                           self.entry(cur, "new-id", "2026-10-24T15:58:00+00:00"),
                                           self.entry("My own script", "mine")]}
        calls = []

        async def fake(token, port, command, payload):
            calls.append((command, payload))
            return listing if command == "list_folder" else {"ok": True}
        with mock.patch.object(agent, "mc_call", fake), mock.patch.dict(agent.MC_CONN, {"token": "x", "port": 1}):
            dry = asyncio.run(agent.tidy_scripts.handler({"dry_run": True}))["content"][0]["text"]
            self.assertFalse([c for c in calls if c[0] == "delete"], "dry run deletes nothing")
            self.assertIn("extra copy", dry)
            asyncio.run(agent.tidy_scripts.handler({}))
        self.assertEqual([p["item"] for c, p in calls if c == "delete"], ["old-id"])


if __name__ == "__main__":
    unittest.main()
