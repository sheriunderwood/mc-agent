"""Who the agent may message, and club links."""

import asyncio
import unittest

from support import (BLOCKED, FRIEND, OWNER, SLURL, STRANGER, agent, config, feed, guard, im,
                     memory, pre, t)


def tick(*events, region=()):
    """A Guard for a tick in which these people wrote and these are nearby."""
    g = guard()
    feed(g, t("events"), {"events": list(events)})
    feed(g, t("nearby"), {"people": [{"id": u} for u in region]})
    return g


def send(g, to, text="hello"):
    return pre(g, t("send_im"), {"to": to, "text": text})


class Replying(unittest.TestCase):
    def test_friend_anywhere(self):
        self.assertIsNone(send(tick(im(FRIEND)), FRIEND))

    def test_stranger_in_the_region(self):
        self.assertIsNone(send(tick(im(STRANGER), region=[STRANGER]), STRANGER))

    def test_stranger_elsewhere(self):
        self.assertIsNotNone(send(tick(im(STRANGER)), STRANGER))

    def test_blocked_never(self):
        self.assertIsNotNone(send(tick(im(BLOCKED), region=[BLOCKED]), BLOCKED))

    def test_stranger_pasting_the_club_link_by_hand(self):
        # Strangers elsewhere get club links only through club_link.
        self.assertIsNotNone(send(tick(im(STRANGER)), STRANGER, f"here {SLURL}"))


class StartingConversations(unittest.TestCase):
    def test_someone_in_the_region(self):
        self.assertIsNone(send(tick(region=[STRANGER]), STRANGER))

    def test_someone_elsewhere(self):
        self.assertIsNotNone(send(tick(), FRIEND))

    def test_the_owner_anywhere(self):
        self.assertIsNone(send(tick(), OWNER))

    def test_when_the_owner_asks(self):
        self.assertIsNone(send(tick(im(OWNER)), FRIEND))

    def test_blocked_even_when_the_owner_asks(self):
        self.assertIsNotNone(send(tick(im(OWNER)), BLOCKED))


class ClubLink(unittest.TestCase):
    def link(self, g, to, kind="slurl"):
        return pre(g, memory("club_link"), {"to": to, "kind": kind})

    def test_anyone_who_asked(self):
        self.assertIsNone(self.link(tick(im(STRANGER)), STRANGER))

    def test_not_unasked(self):
        self.assertIsNotNone(self.link(tick(), STRANGER))

    def test_not_blocked(self):
        self.assertIsNotNone(self.link(tick(im(BLOCKED)), BLOCKED))

    def test_uuid_only(self):
        self.assertIsNotNone(self.link(tick(im(STRANGER)), "Stranger Person"))

    def test_known_kinds_only(self):
        self.assertIsNotNone(self.link(tick(im(STRANGER)), STRANGER, kind="teleport"))

    def test_once_an_hour_per_kind(self):
        g = tick(im(STRANGER))
        self.assertIsNone(self.link(g, STRANGER))
        self.assertIsNotNone(self.link(g, STRANGER))
        self.assertIsNone(self.link(g, STRANGER, kind="landmark"))

    def test_hourly_cap(self):
        g = guard()
        for i in range(agent.Guard.CLUB_LINK_PER_HOUR):
            u = f"{i:08x}-6666-4666-8666-666666666666"
            g.spoke.add(u)
            self.assertIsNone(self.link(g, u))
        g.spoke.add(STRANGER)
        self.assertIsNotNone(self.link(g, STRANGER))

    def test_sends_only_the_configured_link(self):
        calls = []

        async def fake_mc(token, port, command, payload):
            calls.append((command, payload))
            return {"ok": True, "found": []}
        saved = agent.mc_call, dict(agent.MC_CONN)
        agent.mc_call = fake_mc
        agent.MC_CONN.update(token="x", port=1)
        try:
            asyncio.run(agent.club_link.handler({"to": STRANGER, "kind": "slurl"}))
            asyncio.run(agent.club_link.handler({"to": STRANGER, "kind": "landmark"}))   # none: the SLURL
        finally:
            agent.mc_call = saved[0]
            agent.MC_CONN.clear()
            agent.MC_CONN.update(saved[1])
        ims = [p for c, p in calls if c == "send_im"]
        self.assertEqual(len(ims), 2)
        for p in ims:
            self.assertEqual(p["to"], STRANGER)
            self.assertEqual(p["text"], f"here's the {config.HOME_PARCEL} 🖤 {SLURL}")
        self.assertFalse([c for c, _ in calls if c == "give"], "no landmark to give")


if __name__ == "__main__":
    unittest.main()
