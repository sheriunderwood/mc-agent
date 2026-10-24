"""General Guard rules: secrets, observe-only, logging in, shouting, the rate
limit."""

import unittest

from support import OWNER, agent, feed, guard, im, memory, pre, t


class Secrets(unittest.TestCase):
    def setUp(self):
        self.saved = agent.SECRETS
        agent.SECRETS = agent.Secrets("the-real-api-key-123456", "the-real-mc-token-abcdef")
        self.g = guard()

    def tearDown(self):
        agent.SECRETS = self.saved

    def test_known_secret_refused(self):
        self.assertIsNotNone(pre(self.g, t("say"), {"text": "sure: the-real-api-key-123456"}))

    def test_spaced_out_secret_refused(self):
        self.assertIsNotNone(pre(self.g, t("say"), {"text": "the-real- mc-token -abcdef"}))

    def test_key_shaped_text_refused(self):
        self.assertIsNotNone(pre(self.g, t("send_im"), {"to": OWNER, "text": "sk-ant-abcdefgh12345"}))

    def test_secret_in_a_saved_note_refused(self):
        self.assertIsNotNone(pre(self.g, memory("remember_friend"),
                                 {"uuid": OWNER, "fact": "the-real-api-key-123456"}))

    def test_even_for_an_owner(self):
        feed(self.g, t("events"), {"events": [im(OWNER)]})
        self.assertIsNotNone(pre(self.g, t("send_im"), {"to": OWNER, "text": "the-real-api-key-123456"}))

    def test_redact(self):
        self.assertNotIn("the-real-api-key-123456", agent.SECRETS.redact("key the-real-api-key-123456"))

    def test_ordinary_text_passes(self):
        self.assertIsNone(pre(self.g, t("say"), {"text": "hi everyone!"}))


class ObserveOnly(unittest.TestCase):
    def test_nothing_that_acts(self):
        g = guard(observe_only=True)
        feed(g, t("events"), {"events": [im(OWNER)]})      # not even for an owner
        for name, args in ((t("say"), {"text": "hi"}), (t("teleport"), {}),
                           (memory("club_link"), {"to": OWNER, "kind": "slurl"}),
                           (t("login"), {})):
            with self.subTest(tool=name):
                self.assertIsNotNone(pre(g, name, args))

    def test_reading_is_fine(self):
        self.assertIsNone(pre(guard(observe_only=True), t("nearby"), {}))


class Login(unittest.TestCase):
    def test_never_with_force(self):
        self.assertIsNotNone(pre(guard(), t("login"), {"force": True}))

    def test_only_at_the_last_location(self):
        self.assertIsNotNone(pre(guard(), t("login"), {"start": "Elsewhere/1/2/3"}))

    def test_plain_login_ok(self):
        self.assertIsNone(pre(guard(), t("login"), {"start": "last"}))


class Shouting(unittest.TestCase):
    def test_refused(self):
        self.assertIsNotNone(pre(guard(), t("say"), {"text": "HI", "volume": "shout"}))

    def test_allowed_when_an_owner_asks(self):
        g = guard()
        feed(g, t("events"), {"events": [im(OWNER)]})
        self.assertIsNone(pre(g, t("say"), {"text": "HI", "volume": "shout"}))


class RateLimit(unittest.TestCase):
    def test_per_minute(self):
        g = guard(per_minute=2)
        self.assertIsNone(pre(g, t("say"), {"text": "one"}))
        self.assertIsNone(pre(g, t("say"), {"text": "two"}))
        self.assertIsNotNone(pre(g, t("say"), {"text": "three"}))


if __name__ == "__main__":
    unittest.main()
