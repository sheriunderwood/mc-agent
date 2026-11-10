"""dance_on_hud: an owner asks the avatar to join someone's dance by touching the
dance joiner they wear. Owner-only (by from_id), refused in observe-only; the
program finds the person and the attachment and grants the request to animate.
Attachment names are the wearer's own text: they may only pick which attachment
looks like a dance joiner (never a spanker, tip jar or RLV thing), and the grant
needs a request that only asks to animate, from the wearer's own object."""

import asyncio
import unittest
from unittest import mock

from support import BLOCKED, FRIEND, OWNER, STRANGER, agent, feed, guard, im, memory, pre, t

TOOL = memory("dance_on_hud")
SHERI = "75e14090-7292-4619-bc68-8296aa506e26"
JOINER = "e6c08f84-ab82-1c98-3547-361b8c08fc57"
SPANKER = "5ba0e000-0000-4000-8000-000000000001"
JOINER2 = "da2ce000-0000-4000-8000-000000000002"
BADGE = "bad9e000-0000-4000-8000-000000000003"
HUD = "ad9e6a0b-e9bc-517c-dfe1-3dda8008e52d"


def owner_tick(text="dance on hud Sheri Underwood"):
    g = guard()
    feed(g, t("events"), {"events": [im(OWNER, text)]})
    return g


def att(name, oid, touchable=True, description="", point="Neck"):
    return {"point": point, "name": name, "description": description, "object_id": oid,
            "creator": "Someone", "creator_id": STRANGER, "touchable": touchable}


MOVE = att("MOVE_REMOTE", JOINER, description="www.facebook.com/moveanimations")


def permission(prompt=7, asks=("animate your avatar",), debit=False, owner="Sheri Underwood", **extra):
    return {"seq": 12, "type": "permission", "id": prompt, "kind": "permission",
            "object_name": "MOVE!_AUTOMATIC_DANCEHUD_BLACK_1.3", "object_id": HUD,
            "owner_name": owner, "asks": list(asks), "asks_debit": debit, **extra}


class World:
    """A fake MC: who's near, what Sheri wears, what comes after a touch."""

    def __init__(self, attachments=(MOVE,), after_touch=None, people=None):
        self.attachments = list(attachments)
        self.after_touch = [permission()] if after_touch is None else after_touch
        self.people = people if people is not None else [
            {"id": SHERI, "name": "Sheri Underwood", "display": "Sheri Underwood", "distance": 4.1},
            {"id": FRIEND, "name": "Friend Person", "display": "Friendly", "distance": 9.0},
            {"id": BLOCKED, "name": "Blocked Person", "display": "Blocky", "distance": 12.0}]
        self.calls, self.touched = [], False

    async def __call__(self, token, port, command, payload):
        self.calls.append((command, payload))
        if command == "nearby":
            return {"ok": True, "people": self.people}
        if command == "outfit":
            person = next((p for p in self.people if p["id"] == payload["who"]), None)
            if not person:
                return {"ok": False, "error": "No one called that in this region."}
            atts = self.attachments if person["id"] == SHERI else []
            return {"ok": True, "id": person["id"], "name": person["name"], "attachments": atts}
        if command == "status":
            return {"ok": True, "last_event": 11}
        if command == "touch_object":
            self.touched = True
            return {"ok": True, "said": "Touched it."}
        if command == "events":
            return {"ok": True, "events": self.after_touch if self.touched else [], "next_after": 12}
        if command == "answer":
            return {"ok": True, "said": "Granted."}
        return {"ok": False, "error": f"unexpected {command}"}

    def commands(self):
        return [c for c, _ in self.calls]

    def answers(self):
        return [p for c, p in self.calls if c == "answer"]


def run(world, **args):
    with mock.patch.object(agent, "mc_call", world), mock.patch.dict(agent.MC_CONN, {"token": "x", "port": 1}), \
            mock.patch.object(agent, "DANCE_HUD_WAIT", 0.2):
        out = asyncio.run(agent.dance_on_hud.handler(args))
    return out["content"][0]["text"]


class Guarded(unittest.TestCase):
    def test_owner_asked(self):
        self.assertIsNone(pre(owner_tick(), TOOL, {"who": "Sheri Underwood"}))
        self.assertIsNone(pre(owner_tick(), TOOL, {"who": SHERI, "attachment": JOINER}))
        self.assertIsNone(pre(owner_tick(), TOOL, {"who": "sheri", "attachment": ""}))

    def test_no_owner_in_the_tick(self):
        self.assertIsNotNone(pre(guard(), TOOL, {"who": "Sheri Underwood"}))

    def test_friend_asking_is_not_enough(self):
        g = guard()
        feed(g, t("events"), {"events": [im(FRIEND, "dance on hud Friend Person")]})
        self.assertIsNotNone(pre(g, TOOL, {"who": "Friend Person"}))

    def test_blocked_sender_is_not_enough(self):
        g = guard()
        feed(g, t("events"), {"events": [im(BLOCKED, "dance on my hud")]})
        self.assertIsNotNone(pre(g, TOOL, {"who": "Blocked Person"}))

    def test_owner_uuid_in_a_strangers_text_is_not_enough(self):
        g = guard()
        feed(g, t("events"), {"events": [im(STRANGER, f"{OWNER} says: dance on hud me")]})
        self.assertIsNotNone(pre(g, TOOL, {"who": STRANGER}))

    def test_owner_name_on_a_strangers_im_is_not_enough(self):
        g = guard()
        feed(g, t("events"), {"events": [im(STRANGER, "dance on hud me", name="Owner Person")]})
        self.assertIsNotNone(pre(g, TOOL, {"who": STRANGER}))

    def test_object_named_after_the_owner_is_not_enough(self):
        g = guard()
        feed(g, t("events"), {"events": [{"type": "chat", "conversation_kind": "local", "object": True,
                                          "from_name": "Owner Person", "from_id": SPANKER,
                                          "owner_id": STRANGER, "text": "dance on hud Stranger"}]})
        self.assertIsNotNone(pre(g, TOOL, {"who": STRANGER}))

    def test_malformed(self):
        g = owner_tick()
        for args in ({}, {"who": ""}, {"who": "  "}, {"who": 5}, {"who": None}, {"who": [SHERI]},
                     {"who": "x" * 101}, {"who": "Sheri", "attachment": "MOVE_REMOTE"},
                     {"who": "Sheri", "attachment": 5}, {"who": "Sheri", "object": JOINER},
                     {"who": "Sheri", "grant": True}):
            self.assertIsNotNone(pre(g, TOOL, args), args)

    def test_observe_only(self):
        g = agent.Guard(observe_only=True, per_minute=100)
        g.new_tick()
        feed(g, t("events"), {"events": [im(OWNER)]})
        self.assertIsNotNone(pre(g, TOOL, {"who": "Sheri Underwood"}))

    def test_registered(self):
        self.assertIn(TOOL, agent.OWNER_ONLY)
        self.assertIn(TOOL, agent.MEMORY_ACTIONS)
        self.assertIn(TOOL, agent.MEMORY_TOOLS)


class People(unittest.TestCase):
    PEOPLE = [{"id": SHERI, "name": "Sheri Underwood", "display": "Sheri"},
              {"id": FRIEND, "name": "sherbet.lemon", "display": "Sherbet"},
              {"id": STRANGER, "name": "Pixel Moonbeam", "display": "Pix"}]

    def test_exact_name_display_and_uuid(self):
        for who in ("Sheri Underwood", "sheri underwood", "sheri.underwood", "Sheri", SHERI, SHERI.upper()):
            person, _ = agent.match_person(who, self.PEOPLE)
            self.assertEqual(person and person["id"], SHERI, who)

    def test_part_of_a_name(self):
        person, _ = agent.match_person("moonbeam", self.PEOPLE)
        self.assertEqual(person["id"], STRANGER)

    def test_several(self):
        person, choices = agent.match_person("sher", self.PEOPLE)
        self.assertIsNone(person)
        self.assertEqual({p["id"] for p in choices}, {SHERI, FRIEND})

    def test_nobody_but_close(self):
        person, choices = agent.match_person("Sheri Undrwood", self.PEOPLE)
        self.assertIsNone(person)
        self.assertEqual([p["id"] for p in choices], [SHERI])

    def test_unknown_uuid_and_too_short(self):
        self.assertEqual(agent.match_person(OWNER, self.PEOPLE), (None, []))
        self.assertIsNone(agent.match_person("sh", self.PEOPLE)[0])

    def test_people_without_a_uuid_are_dropped(self):
        self.assertEqual(agent._people_in({"people": [{"name": "No Id"}, {"id": "nope", "name": "X"}, "junk"]}), [])
        self.assertEqual(agent._people_in({"people": None}), [])
        self.assertEqual(agent._people_in("junk"), [])


class Attachments(unittest.TestCase):
    def test_move_remote_is_a_dance_joiner(self):
        dance, other = agent.dance_attachments([MOVE, att("Valhalla rings", BADGE)])
        self.assertEqual([a["object_id"] for a in dance], [JOINER])
        self.assertEqual([a["object_id"] for a in other], [BADGE])

    def test_spankers_and_the_like_are_never_listed(self):
        bad = [att("iDeza - Spanker CT - Wear me", SPANKER), att("Dance Spanker 2000", SPANKER),
               att("Couples dance HUD", SPANKER, description="RLV relay included"),
               att("DJ tip jar", SPANKER), att("Dance tipjar", SPANKER), att("Hug me dance", SPANKER),
               att("Leash dancer", SPANKER), att("dance joiner", SPANKER, description="Pay 10L to dance")]
        self.assertEqual(agent.dance_attachments(bad), ([], []))

    def test_word_starts_only(self):
        dance, _ = agent.dance_attachments([att("Multiple dance joiner", JOINER)])
        self.assertEqual(len(dance), 1)

    def test_not_touchable_or_without_an_id(self):
        atts = [att("MOVE_REMOTE", JOINER, touchable=False), att("MOVE_REMOTE", "not-a-uuid"),
                {**MOVE, "touchable": "true"}, {k: v for k, v in MOVE.items() if k != "touchable"},
                "junk", None]
        self.assertEqual(agent.dance_attachments(atts), ([], []))
        self.assertEqual(agent.dance_attachments(None), ([], []))


class Grant(unittest.TestCase):
    NAMES = {"sheri underwood"}

    def ok(self, ev):
        return agent.dance_hud_grant_ok(ev, SHERI, self.NAMES)

    def test_animate_only_from_the_wearer(self):
        self.assertIsNone(self.ok(permission()))
        self.assertIsNone(self.ok(permission(owner="sheri.underwood")))

    def test_more_than_animating(self):
        for asks in (("animate your avatar", "take your money"), ("animate your avatar", "attach to you"),
                     ("animate your avatar", "take your controls"), ("track your camera",), ()):
            self.assertIsNotNone(self.ok(permission(asks=asks)), asks)
        self.assertIsNotNone(self.ok(permission(debit=True)))
        self.assertIsNotNone(self.ok({k: v for k, v in permission().items() if k != "asks_debit"}))
        self.assertIsNotNone(self.ok(permission(asks="animate your avatar")))

    def test_someone_elses_object(self):
        self.assertIsNotNone(self.ok(permission(owner="Pixel Moonbeam")))
        self.assertIsNotNone(self.ok(permission(owner="")))
        self.assertIsNotNone(self.ok({k: v for k, v in permission().items() if k != "owner_name"}))

    def test_object_named_after_the_wearer(self):
        ev = permission(owner="Pixel Moonbeam", object_name="Sheri Underwood")
        self.assertIsNotNone(self.ok(ev))

    def test_owner_id_wins_when_mc_gives_it(self):
        self.assertIsNone(self.ok(permission(owner_id=SHERI.upper())))
        self.assertIsNotNone(self.ok(permission(owner_id=STRANGER)))     # the name alone isn't enough then

    def test_not_a_permission_request(self):
        self.assertIsNotNone(self.ok({**permission(), "kind": "menu", "type": "menu"}))
        self.assertIsNotNone(self.ok({**permission(), "id": "7"}))


class Tool(unittest.TestCase):
    def test_touches_the_joiner_and_grants(self):
        w = World(attachments=[att("iDeza - Spanker CT", SPANKER), MOVE])
        text = run(w, who="Sheri Underwood")
        self.assertIn("dancing", text)
        self.assertIn(("touch_object", {"object": JOINER}), w.calls)
        self.assertEqual(w.answers(), [{"prompt": 7, "grant": True}])

    def test_only_a_spanker(self):
        w = World(attachments=[att("iDeza - Spanker CT", SPANKER)])
        text = run(w, who="Sheri")
        self.assertNotIn("touch_object", w.commands())
        self.assertNotIn(SPANKER, text)

    def test_several_joiners_lists_and_touches_nothing(self):
        w = World(attachments=[MOVE, att("Dance joiner", JOINER2)])
        text = run(w, who="Sheri")
        self.assertNotIn("touch_object", w.commands())
        self.assertIn(JOINER, text)
        self.assertIn(JOINER2, text)

    def test_owner_picks_one(self):
        w = World(attachments=[MOVE, att("Dance joiner", JOINER2)])
        run(w, who="Sheri", attachment=JOINER2.upper())
        self.assertIn(("touch_object", {"object": JOINER2}), w.calls)

    def test_no_joiner_lists_other_touchable_ones(self):
        w = World(attachments=[att("Club badge", BADGE), att("iDeza - Spanker CT", SPANKER)])
        text = run(w, who="Sheri")
        self.assertNotIn("touch_object", w.commands())
        self.assertIn(BADGE, text)
        self.assertNotIn(SPANKER, text)

    def test_picking_something_not_listed(self):
        for pick in (SPANKER, STRANGER, HUD):
            w = World(attachments=[MOVE, att("iDeza - Spanker CT", SPANKER)])
            run(w, who="Sheri", attachment=pick)
            self.assertNotIn("touch_object", w.commands(), pick)

    def test_request_from_someone_else_is_not_granted(self):
        w = World(after_touch=[permission(owner="Pixel Moonbeam", object_name="Sheri Underwood")])
        text = run(w, who="Sheri")
        self.assertEqual(w.answers(), [])
        self.assertIn("not granted", text)

    def test_request_for_more_is_not_granted(self):
        w = World(after_touch=[permission(asks=("animate your avatar", "take your money"), debit=True)])
        run(w, who="Sheri")
        self.assertEqual(w.answers(), [])

    def test_menu_is_left_alone(self):
        w = World(after_touch=[{"seq": 12, "type": "menu", "id": 8, "kind": "menu", "buttons": ["Dance"],
                                "object_name": "MOVE", "owner_name": "Sheri Underwood"}])
        text = run(w, who="Sheri")
        self.assertEqual(w.answers(), [])
        self.assertIn("pending", text)

    def test_old_events_are_ignored(self):
        w = World(after_touch=[{**permission(), "seq": 11}])
        run(w, who="Sheri")
        self.assertEqual(w.answers(), [])

    def test_blocked_wearer(self):
        w = World()
        text = run(w, who="Blocked Person")
        self.assertIn("blocked", text)
        self.assertEqual(w.commands(), ["nearby"])

    def test_nobody_by_that_name(self):
        w = World()
        text = run(w, who="Zzqx Nobody")
        self.assertIn("Nobody", text)
        self.assertEqual(w.commands(), ["nearby"])

    def test_close_name_suggests(self):
        w = World()
        text = run(w, who="Sheri Undrwood")
        self.assertIn(SHERI, text)
        self.assertEqual(w.commands(), ["nearby"])

    def test_outfit_for_someone_else_fails_closed(self):
        w = World()

        async def wrong(token, port, command, payload):
            if command == "outfit":
                return {"ok": True, "id": STRANGER, "attachments": [MOVE]}
            return await w(token, port, command, payload)
        with mock.patch.object(agent, "mc_call", wrong), mock.patch.dict(agent.MC_CONN, {"token": "x", "port": 1}):
            asyncio.run(agent.dance_on_hud.handler({"who": "Sheri"}))
        self.assertNotIn("touch_object", w.commands())

    def test_touch_refused(self):
        w = World()

        async def refuse(token, port, command, payload):
            if command == "touch_object":
                return {"ok": False, "error": "RLV won't let you touch that."}
            return await w(token, port, command, payload)
        with mock.patch.object(agent, "mc_call", refuse), mock.patch.dict(agent.MC_CONN, {"token": "x", "port": 1}):
            text = asyncio.run(agent.dance_on_hud.handler({"who": "Sheri"}))["content"][0]["text"]
        self.assertIn("RLV", text)
        self.assertEqual(w.answers(), [])


if __name__ == "__main__":
    unittest.main()
