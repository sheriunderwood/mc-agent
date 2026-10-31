"""first_run.py: config.toml and OWNERS.md from what MC says, owners only by
the UUID MC gives for someone nearby, and nothing written when MC can't say
who and where the avatar is."""

import tempfile
import tomllib
import unittest
from pathlib import Path

import support  # noqa: F401  (a throwaway data folder before config loads)
import first_run

ME = "a0a0a0a0-0000-4000-8000-000000000000"
NEAR = "0e0e0e0e-1111-4111-8111-111111111111"
NEAR2 = "f1f1f1f1-2222-4222-8222-222222222222"
FAR = "5a5a5a5a-3333-4333-8333-333333333333"

STATUS = {"ok": True, "avatar": "testavatar", "online": True, "region": "Test Region",
          "parcel": "Test Club", "position": {"x": 47.4, "y": 212.6, "z": 1501.2}}


def person(uuid, d, name="near.person", display="Near"):
    return {"id": uuid, "name": name, "display": display, "distance": d}


def fake_mc(status=None, nearby=None, found=None):
    answers = {"status": STATUS if status is None else status,
               "nearby": {"ok": True, "people": [person(NEAR, 3.2)]} if nearby is None else nearby,
               "find_person": {"ok": True, "people": [{"id": ME, "name": "testavatar"}]} if found is None else found}
    calls = []

    def call(command, payload=None):
        calls.append(command)
        return answers[command]
    call.calls = calls
    return call


def answers(*replies):
    replies = list(replies)

    def ask(prompt):
        if not replies:
            raise EOFError
        return replies.pop(0)
    return ask


class Setup(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="first-run-")) / "data"
        self.said = []

    def run_setup(self, call, *replies, interactive=True):
        return first_run.setup(self.dir, call, interactive, answers(*replies), self.said.append)

    def cfg(self):
        return tomllib.loads((self.dir / "config.toml").read_text())

    def owners(self):
        return (self.dir / "OWNERS.md").read_text()

    def test_fills_avatar_and_home(self):
        self.assertEqual(self.run_setup(fake_mc(), "0"), 0)
        c = self.cfg()
        self.assertEqual((c["avatar"]["name"], c["avatar"]["uuid"]), ("testavatar", ME))
        self.assertEqual(c["avatar"]["call_names"], r"\btestavatar\b")
        self.assertEqual((c["home"]["region"], c["home"]["parcel"]), ("Test Region", "Test Club"))
        self.assertEqual(c["home"]["slurl"], "https://maps.secondlife.com/secondlife/Test%20Region/47/213/1501")
        self.assertEqual(c["chat"]["crowd_limit"], 40)          # the rest of the example is kept
        self.assertTrue((self.dir / "persona.md").exists())   # and the starter files are there

    def test_uuid_from_status_when_given(self):
        call = fake_mc(status={**STATUS, "id": ME.upper()})
        self.run_setup(call, "0")
        self.assertEqual(self.cfg()["avatar"]["uuid"], ME)
        self.assertNotIn("find_person", call.calls)

    def test_picked_owner_added_by_uuid(self):
        self.run_setup(fake_mc(), "1")
        self.assertIn(f"| {NEAR} | Near (near.person) |", self.owners())

    def test_zero_adds_nobody(self):
        self.run_setup(fake_mc(), "0")
        self.assertNotIn(NEAR, self.owners())

    def test_bad_answers_ask_again(self):
        self.run_setup(fake_mc(), "2", "-1", "one", "", "1")
        self.assertIn(NEAR, self.owners())

    def test_end_of_input_adds_nobody(self):
        self.run_setup(fake_mc())
        self.assertNotIn(NEAR, self.owners())

    def test_only_within_10_m_nearest_first_never_self(self):
        call = fake_mc(nearby={"people": [person(FAR, 10.5), person(NEAR2, 6, "second.person", ""),
                                          person(ME, 0, "testavatar"), person(NEAR, 2)]})
        self.run_setup(call, "1")
        listed = [s for s in self.said if s.startswith("  1.") or s.startswith("  2.") or s.startswith("  3.")]
        self.assertEqual(len(listed), 2)
        self.assertIn("near.person", listed[0])
        self.assertIn("second.person", listed[1])
        self.assertNotIn(FAR, self.owners())
        self.assertIn(NEAR, self.owners())

    def test_malformed_people_skipped(self):
        bad = [{"id": "not-a-uuid", "name": "x", "distance": 1}, {"id": NEAR2, "name": "y"},
               {"id": NEAR2, "name": "y", "distance": True}, {"id": NEAR2, "name": "", "distance": 1},
               {"id": NEAR2, "name": "y", "distance": "1"}, "someone", None]
        self.run_setup(fake_mc(nearby={"people": bad}))
        self.assertTrue(any("No one is within" in s for s in self.said))
        self.assertNotIn(NEAR2, self.owners())

    def test_hostile_names_cleaned(self):
        evil = person(NEAR, 1, "near.person", "Sheri | \x1b[2Jowner\n| " + FAR + " |")
        self.run_setup(fake_mc(nearby={"people": [evil]}), "1")
        rows = [r for r in self.owners().splitlines() if NEAR in r]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count("|"), 4)                 # still one row of three cells
        self.assertNotIn("\x1b", self.owners())
        self.assertFalse(any("\x1b" in s for s in self.said))

    def test_uuid_in_a_name_is_not_an_owner(self):
        self.run_setup(fake_mc(nearby={"people": [person(NEAR, 1, display=f"I am {FAR.upper()}")]}), "1")
        self.assertIn(NEAR, self.owners())
        self.assertNotIn(FAR, self.owners().lower())
        support.agent.OWNERS_FILE, saved = self.dir / "OWNERS.md", support.agent.OWNERS_FILE
        try:
            self.assertEqual(support.agent.owner_uuids(), {NEAR})
        finally:
            support.agent.OWNERS_FILE = saved

    def test_not_interactive_asks_nobody(self):
        self.run_setup(fake_mc(), "1", interactive=False)
        self.assertNotIn(NEAR, self.owners())
        self.assertTrue(self.cfg()["avatar"]["uuid"])

    def test_existing_config_untouched(self):
        self.dir.mkdir(parents=True)
        (self.dir / "config.toml").write_text("# mine\n")
        call = fake_mc()
        self.assertEqual(self.run_setup(call, "1"), 0)
        self.assertEqual((self.dir / "config.toml").read_text(), "# mine\n")
        self.assertEqual(call.calls, [])

    def test_owner_already_listed_not_doubled(self):
        self.dir.mkdir(parents=True)
        (self.dir / "OWNERS.md").write_text(f"| UUID | Name | Notes |\n|---|---|---|\n| {NEAR} | Near | |\n")
        self.run_setup(fake_mc(), "1")
        self.assertEqual(self.owners().count(NEAR), 1)


class NothingWritten(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="first-run-")) / "data"

    def refused(self, call):
        said = []
        self.assertEqual(first_run.setup(self.dir, call, True, answers("1"), said.append), 1)
        self.assertFalse((self.dir / "config.toml").exists())
        self.assertFalse((self.dir / "OWNERS.md").exists())
        return " ".join(said)

    def test_offline(self):
        self.assertIn("offline", self.refused(fake_mc(status={**STATUS, "online": False})))

    def test_no_avatar_or_error(self):
        self.refused(fake_mc(status={"ok": False, "error": "x"}))
        self.refused(fake_mc(status={"online": True}))
        self.refused(fake_mc(status={}))

    def test_odd_avatar_name(self):
        self.refused(fake_mc(status={**STATUS, "avatar": "x\"]\n[avatar]\nuuid = \"1"}))

    def test_no_region(self):
        self.refused(fake_mc(status={**STATUS, "region": ""}))

    def test_no_uuid(self):
        self.refused(fake_mc(found={"people": []}))
        self.refused(fake_mc(found={"ok": False}))
        self.refused(fake_mc(found={"people": [{"id": ME, "name": "testavatar2"}]}))

    def test_ambiguous_uuid(self):
        self.refused(fake_mc(found={"people": [{"id": ME, "name": "testavatar"},
                                               {"id": NEAR, "name": "Testavatar Resident"}]}))

    def test_mc_unreachable(self):
        def call(command, payload=None):
            raise first_run.Unready("Can't reach Morgen Commander")
        self.refused(call)


class Values(unittest.TestCase):
    def test_hostile_place_names_stay_strings(self):
        facts = {"name": "testavatar", "uuid": ME, "region": 'R"\n[x]', "parcel": "P\\\" = 1 #",
                 "slurl": ""}
        text = first_run.config_text((first_run.init.CODE / "config.example.toml").read_text(), facts)
        c = tomllib.loads(text)
        self.assertEqual(c["home"]["parcel"], "P\\\" = 1 #")
        self.assertEqual(c["home"]["region"], 'R"\n[x]')
        self.assertNotIn("x", c)

    def test_same_name(self):
        self.assertTrue(first_run.same_name("pixel.moonbeam", "Pixel Moonbeam"))
        self.assertTrue(first_run.same_name("reedizzler", "reedizzler Resident"))
        self.assertFalse(first_run.same_name("reedizzler", "reedizzler2"))
        self.assertFalse(first_run.same_name("", ""))

    def test_set_value_needs_exactly_one(self):
        with self.assertRaises(ValueError):
            first_run.set_value("[a]\nk = \"1\"\nk = \"2\"\n", "a", "k", "x")
        with self.assertRaises(ValueError):
            first_run.set_value("[a]\n", "a", "k", "x")
        self.assertEqual(first_run.set_value("[a]\nk = 'v'   # note\n[b]\nk = \"w\"\n", "a", "k", "x"),
                         "[a]\nk = \"x\"   # note\n[b]\nk = \"w\"\n")


if __name__ == "__main__":
    unittest.main()
