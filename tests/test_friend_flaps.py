"""A friend whose online status keeps flipping: after FLAP_CHANGES changes in
FLAP_WINDOW_S their notices stop waking the model and are taken out of its
events, and the program reports it once an hour. Others are untouched."""

import json
import unittest
from unittest import mock

from support import FRIEND, OWNER, agent, guard, t

MIN = 60


def friend(seq, online=True, who=FRIEND, name="Flaky Friend"):
    return {"seq": seq, "type": "friend", "id": who, "name": name, "online": online}


class Flaps(unittest.TestCase):
    def setUp(self):
        self.flaps = agent.FriendFlaps()
        self.reports = []
        patcher = mock.patch.object(agent, "report", self.reports.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def feed(self, seqs, start=0.0, step=2 * MIN, **kw):
        return [self.flaps.note(friend(s, online=s % 2 == 0, **kw), now=start + i * step)
                for i, s in enumerate(seqs)]

    def test_first_changes_go_through_then_quiet(self):
        quiet = self.feed(range(1, 8))
        self.assertEqual(quiet, [False] * agent.FLAP_CHANGES + [True] * (7 - agent.FLAP_CHANGES))

    def test_reported_once_an_hour(self):
        self.feed(range(1, 20))                   # 19 changes over 36 minutes
        self.assertEqual(len(self.reports), 1)
        self.assertIn("Flaky Friend", self.reports[0])
        self.feed(range(20, 30), start=70 * MIN)  # still flickering an hour later
        self.assertEqual(len(self.reports), 2)

    def test_slow_changes_never_quiet(self):
        self.assertEqual(self.feed(range(1, 10), step=20 * MIN), [False] * 9)
        self.assertEqual(self.reports, [])

    def test_same_event_counted_once(self):
        ev = friend(5)
        for _ in range(10):                       # the stream and events both see it
            self.assertFalse(self.flaps.note(ev, now=0))
        self.assertEqual(self.flaps.changes[FRIEND.lower()], [0])

    def test_quiet_event_stays_quiet_when_seen_again(self):
        self.feed(range(1, 7))
        self.assertTrue(self.flaps.note(friend(6, online=True), now=99 * MIN))

    def test_other_friends_unaffected(self):
        self.feed(range(1, 10))
        self.assertFalse(self.flaps.note(friend(100, who=OWNER, name="Owner"), now=5 * MIN))

    def test_not_friend_events_or_no_id(self):
        self.assertFalse(self.flaps.note({"seq": 1, "type": "chat", "id": FRIEND}))
        for i in range(10):
            self.assertFalse(self.flaps.note({"seq": 10 + i, "type": "friend"}, now=i))

    def test_restart_forgets_event_numbers(self):
        self.feed(range(1, 7))
        self.flaps.restarted()
        self.assertEqual(self.flaps.quiet_seqs, set())

    def test_name_is_trimmed(self):
        self.feed(range(1, 7), name="Long   " + "x" * 200)
        self.assertLess(len(self.reports[0]), 300)


class HiddenFromEvents(unittest.TestCase):
    def test_events_result_drops_flickers_keeps_the_rest(self):
        flaps = agent.FriendFlaps()
        with mock.patch.object(agent, "FLAPS", flaps), mock.patch.object(agent, "report"):
            for i, s in enumerate(range(1, 7)):
                flaps.note(friend(s), now=i * MIN)
            evs = [friend(5), friend(6), friend(50, who=OWNER, name="Owner"),
                   {"seq": 51, "type": "chat", "conversation_kind": "im", "text": "hi", "from_id": OWNER}]
            g = guard()
            out, _ = g.crowd_filtered({"tool_name": t("events"), "tool_input": {},
                                       "tool_response": [{"type": "text", "text": json.dumps({"events": evs})}]})
        result = json.loads(out["hookSpecificOutput"]["updatedMCPToolOutput"][0]["text"])
        self.assertEqual([e["seq"] for e in result["events"]], [50, 51])
        self.assertIn("2 online/offline notices", result["friend_flicker_hidden"])


if __name__ == "__main__":
    unittest.main()
