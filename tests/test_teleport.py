"""Teleport offers: owner-only, except a friend (FRIENDS.md) who asked this tick.
And which MC tools the model may use at all."""

import unittest

from support import (BLOCKED, FRIEND, OWNER, STRANGER, agent, feed, guard, im, memory,
                     pre, t)


def tick(*events):
    g = guard()
    feed(g, t("events"), {"events": list(events)})
    return g


def offer(g, to, **extra):
    return pre(g, t("offer_teleport"), dict({"to": to}, **extra))


class FriendTeleport(unittest.TestCase):
    def test_friend_who_asked(self):
        self.assertIsNone(offer(tick(im(FRIEND, "help, i'm stuck, tp me?")), FRIEND))

    def test_with_a_message(self):
        self.assertIsNone(offer(tick(im(FRIEND)), FRIEND, message="come to the club!"))

    def test_friend_who_did_not_ask(self):
        self.assertIsNotNone(offer(tick(), FRIEND))

    def test_someone_else_asking_for_the_friend(self):
        self.assertIsNotNone(offer(tick(im(STRANGER, f"tp {FRIEND} please")), FRIEND))

    def test_stranger_who_asked(self):
        self.assertIsNotNone(offer(tick(im(STRANGER)), STRANGER))

    def test_blocked(self):
        self.assertIsNotNone(offer(tick(im(BLOCKED)), BLOCKED))

    def test_friend_by_name_not_uuid(self):
        self.assertIsNotNone(offer(tick(im(FRIEND)), "Friend Person"))

    def test_friend_name_from_a_stranger(self):
        self.assertIsNotNone(offer(tick(im(STRANGER, name="Friend Person")), STRANGER))

    def test_extra_arguments(self):
        self.assertIsNotNone(offer(tick(im(FRIEND)), FRIEND, lure="x"))

    def test_once_every_ten_minutes(self):
        g = tick(im(FRIEND))
        self.assertIsNone(offer(g, FRIEND))
        g.new_tick()
        feed(g, t("events"), {"events": [im(FRIEND, "didn't get it")]})
        self.assertIsNotNone(offer(g, FRIEND))

    def test_do_not_contact(self):
        rows = agent._friend_table()
        rows[FRIEND]["Contact"] = "do-not-contact"
        saved = agent._friend_table
        agent._friend_table = lambda: rows
        try:
            self.assertIsNotNone(offer(tick(im(FRIEND)), FRIEND))
        finally:
            agent._friend_table = saved

    def test_observe_only(self):
        g = guard(observe_only=True)
        feed(g, t("events"), {"events": [im(FRIEND)]})
        self.assertIsNotNone(offer(g, FRIEND))

    def test_owner_can_still_ask_for_anyone(self):
        self.assertIsNone(offer(tick(im(OWNER)), STRANGER))

    def test_only_offers_not_teleporting_herself(self):
        self.assertIsNotNone(pre(tick(im(FRIEND)), t("teleport"), {"to": "Somewhere/1/2/3"}))
        self.assertIsNotNone(pre(tick(im(FRIEND)), t("request_teleport"), {"to": FRIEND}))


class ToolLists(unittest.TestCase):
    def test_check_update_is_allowed(self):
        self.assertIn(t("check_update"), agent.READ_TOOLS)

    def test_update_self_is_not(self):
        allowed = agent.READ_TOOLS + agent.ACT_TOOLS + agent.ADMIN_TOOLS + agent.MEMORY_TOOLS
        for name in ("update_self", "pay", "give", "release_rlv", "set_home"):
            self.assertNotIn(t(name), allowed, name)

    def test_guard_denies_unlisted_mc_tools(self):
        # Even for an owner: they're not the agent's tools at all.
        g = tick(im(OWNER))
        for name in ("update_self", "pay", "give", "release_rlv", "set_home", "request_teleport",
                     "delete", "end_friendship", "no_such_tool"):
            self.assertIsNotNone(pre(g, t(name), {}), name)

    def test_listed_tools_still_reach_their_checks(self):
        self.assertIsNone(pre(guard(), t("check_update"), {}))
        self.assertIsNone(pre(guard(), t("nearby"), {}))


if __name__ == "__main__":
    unittest.main()
