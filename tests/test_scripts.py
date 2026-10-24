"""Filling in the HUD scripts' settings: only checked values, and no script at
all when one is missing or unsafe."""

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


if __name__ == "__main__":
    unittest.main()
