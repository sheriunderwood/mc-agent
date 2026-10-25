"""[log] mirror: each log line also goes to a console or file, redacted like the
log file, and a mirror that can't be written never stops the agent."""

import unittest
from unittest import mock

from support import DATA, REAL_LOG, agent

SECRET = "sk-ant-test-0123456789abcdefghij"


class LogMirror(unittest.TestCase):
    def setUp(self):
        self.mirror = DATA / "mirror.txt"
        self.addCleanup(self.mirror.unlink, missing_ok=True)

    def log(self, line, mirror):
        with mock.patch.object(agent, "LOG_MIRROR", mirror), \
                mock.patch.object(agent, "SECRETS", agent.Secrets(SECRET)), mock.patch("builtins.print"):
            REAL_LOG(line)

    def test_line_goes_to_the_mirror(self):
        self.log("hello from the test", str(self.mirror))
        self.assertRegex(self.mirror.read_text(), r"^\d\d:\d\d:\d\d hello from the test\n$")

    def test_secret_is_redacted(self):
        self.log(f"key is {SECRET}", str(self.mirror))
        self.assertNotIn(SECRET, self.mirror.read_text())

    def test_unwritable_mirror_is_ignored(self):
        self.log("still fine", str(DATA / "no-such-folder" / "tty"))

    def test_no_mirror_by_default(self):
        self.assertEqual(agent.LOG_MIRROR, "")


if __name__ == "__main__":
    unittest.main()
