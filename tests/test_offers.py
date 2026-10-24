"""Answering offers, menus and permission requests without an owner in the
tick: only the narrow exceptions (an owner's gift, a standing friendship
approval, a friend's dance), decided from fields MC sets."""

import unittest

from support import APPROVED, BLOCKED, FRIEND, OWNER, STRANGER, feed, guard, pre, t


def with_prompt(details: dict, number: int = 7):
    """A Guard that has seen this pending prompt (as after calling `pending`)."""
    g = guard()
    feed(g, t("pending"), {"prompts": [dict(details, id=number)]})
    return g


def answer(g, **args):
    return pre(g, t("answer"), dict({"prompt": 7}, **args))


class OwnerGift(unittest.TestCase):
    def offer(self, **kw):
        return dict({"kind": "offer", "offer": "inventory", "title": "A landmark"}, **kw)

    def test_from_the_owner(self):
        self.assertIsNone(answer(with_prompt(self.offer(from_id=OWNER)), accept=True))

    def test_teleport_from_the_owner(self):
        self.assertIsNone(answer(with_prompt(self.offer(from_id=OWNER, offer="teleport")), accept=True))

    def test_from_a_stranger(self):
        self.assertIsNotNone(answer(with_prompt(self.offer(from_id=STRANGER)), accept=True))

    def test_stranger_with_owner_uuid_in_the_message(self):
        g = with_prompt(self.offer(from_id=STRANGER, message=f"from {OWNER}", title=f"gift {OWNER}"))
        self.assertIsNotNone(answer(g, accept=True))

    def test_stranger_using_the_owner_name(self):
        g = with_prompt(self.offer(from_id=STRANGER, from_name="Owner Person"))
        self.assertIsNotNone(answer(g, accept=True))

    def test_missing_from_id(self):
        self.assertIsNotNone(answer(with_prompt(self.offer()), accept=True))

    def test_unknown_prompt_number(self):
        g = with_prompt(self.offer(from_id=OWNER))
        self.assertIsNotNone(pre(g, t("answer"), {"prompt": 99, "accept": True}))

    def test_friendship_from_the_owner_still_waits(self):
        self.assertIsNotNone(answer(with_prompt(self.offer(from_id=OWNER, offer="friendship")), accept=True))

    def test_group_from_the_owner_still_waits(self):
        self.assertIsNotNone(answer(with_prompt(self.offer(from_id=OWNER, offer="group invite")), accept=True))


class StandingFriendship(unittest.TestCase):
    def offer(self, **kw):
        return dict({"kind": "offer", "offer": "friendship"}, **kw)

    def test_approved_sender(self):
        self.assertIsNone(answer(with_prompt(self.offer(from_id=APPROVED)), accept=True))

    def test_other_sender(self):
        self.assertIsNotNone(answer(with_prompt(self.offer(from_id=STRANGER)), accept=True))

    def test_approved_uuid_in_a_strangers_message(self):
        g = with_prompt(self.offer(from_id=STRANGER, message=f"I'm {APPROVED}"))
        self.assertIsNotNone(answer(g, accept=True))

    def test_only_friendship_offers(self):
        g = with_prompt({"kind": "offer", "offer": "inventory", "from_id": APPROVED})
        self.assertIsNotNone(answer(g, accept=True))


class DanceInvitations(unittest.TestCase):
    def permission(self, owner_name, asks="animate your avatar", **kw):
        return dict({"kind": "permission", "object_name": "Dance HUD", "owner_name": owner_name,
                     "asks": asks}, **kw)

    def test_friend_animation_only(self):
        self.assertIsNone(answer(with_prompt(self.permission("Friend Person")), grant=True))

    def test_stranger(self):
        self.assertIsNotNone(answer(with_prompt(self.permission("Stranger Person")), grant=True))

    def test_blocked(self):
        g = with_prompt(self.permission("Blocked Person"))
        self.assertIsNotNone(answer(g, grant=True))

    def test_more_than_animation(self):
        for asks in ("animate your avatar, take your money", "animate your avatar and attach",
                     "animate your avatar; teleport you", "take controls"):
            with self.subTest(asks=asks):
                self.assertIsNotNone(answer(with_prompt(self.permission("Friend Person", asks=asks)),
                                            grant=True))

    def test_debit(self):
        g = with_prompt(self.permission("Friend Person", asks_debit=True))
        self.assertIsNotNone(answer(g, grant=True))

    def test_refusing_is_always_fine(self):
        self.assertIsNone(answer(with_prompt(self.permission("Stranger Person")), grant=False))

    def menu(self, owner_name, text="Friend Person wants to dance with you", **kw):
        return dict({"kind": "menu", "owner_name": owner_name, "text": text,
                     "buttons": ["Accept", "Decline"]}, **kw)

    def test_friends_dance_menu(self):
        self.assertIsNone(answer(with_prompt(self.menu("Friend Person")), button="Accept"))

    def test_decline_button_always_fine(self):
        self.assertIsNone(answer(with_prompt(self.menu("Stranger Person", text="dance?")), button="Decline"))

    def test_other_buttons_refused(self):
        self.assertIsNotNone(answer(with_prompt(self.menu("Friend Person")), button="Pay 100"))

    def test_menu_that_is_not_about_dancing(self):
        g = with_prompt(self.menu("Friend Person", text="Join my group"))
        self.assertIsNotNone(answer(g, button="Accept"))

    def test_text_naming_a_friend_counts(self):
        # Known, deliberate: a menu whose text names a friend counts as from them
        # (a club's dance ball saying who invited you), though an object writes
        # that text. The worst case is a dance. If this changes, change this test.
        g = with_prompt(self.menu("Stranger Person", text="Friend Person wants to dance with you"))
        self.assertIsNone(answer(g, button="Accept"))


if __name__ == "__main__":
    unittest.main()
