"""~/.config/mcsl-agent (the old name) moves to ~/.config/mc-agent once, with
a symlink left at the old name for services installed before; nothing is lost
or overwritten, and a failed move keeps the old folder in use."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (a throwaway data folder before config loads)
import config


class MoveOldSecretsDir(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="config-home-"))
        self.new, self.old = self.home / "mc-agent", self.home / "mcsl-agent"

    def move(self):
        return config.move_old_secrets_dir(self.new, self.old)

    def secrets(self, folder: Path, text: str = "MC_API_TOKEN=abc\n") -> None:
        folder.mkdir()
        (folder / "secrets.env").write_text(text)
        (folder / "secrets.env").chmod(0o600)

    def test_moves_and_leaves_a_link(self):
        self.secrets(self.old)
        self.assertEqual(self.move(), self.new)
        self.assertEqual((self.new / "secrets.env").read_text(), "MC_API_TOKEN=abc\n")
        self.assertEqual(oct((self.new / "secrets.env").stat().st_mode & 0o777), "0o600")
        self.assertTrue(self.old.is_symlink())
        self.assertEqual(os.readlink(self.old), "mc-agent")
        self.assertEqual((self.old / "secrets.env").read_text(), "MC_API_TOKEN=abc\n")   # old units still read it

    def test_second_run_changes_nothing(self):
        self.secrets(self.old)
        self.move()
        self.assertEqual(self.move(), self.new)
        self.assertTrue(self.old.is_symlink())

    def test_new_folder_wins_old_left_alone(self):
        self.secrets(self.new, "MC_API_TOKEN=new\n")
        self.secrets(self.old, "MC_API_TOKEN=old\n")
        self.assertEqual(self.move(), self.new)
        self.assertEqual((self.new / "secrets.env").read_text(), "MC_API_TOKEN=new\n")
        self.assertEqual((self.old / "secrets.env").read_text(), "MC_API_TOKEN=old\n")
        self.assertFalse(self.old.is_symlink())

    def test_neither_gives_the_new_place(self):
        self.assertEqual(self.move(), self.new)
        self.assertFalse(self.new.exists() or self.old.exists())

    def test_old_name_is_a_file_not_moved(self):
        self.old.write_text("not a folder")
        self.assertEqual(self.move(), self.new)
        self.assertTrue(self.old.is_file())
        self.assertFalse(self.new.exists())

    def test_dangling_old_link_ignored(self):
        self.old.symlink_to("nowhere")
        self.assertEqual(self.move(), self.new)

    def test_failed_move_keeps_old_in_use(self):
        self.secrets(self.old)
        with mock.patch.object(Path, "rename", side_effect=PermissionError):
            self.assertEqual(self.move(), self.old)
        self.assertTrue((self.old / "secrets.env").is_file())
        self.assertFalse(self.new.exists())

    def test_link_failure_still_uses_new(self):
        self.secrets(self.old)
        with mock.patch.object(Path, "symlink_to", side_effect=OSError):
            self.assertEqual(self.move(), self.new)
        self.assertTrue((self.new / "secrets.env").is_file())

    def test_secret_read_from_the_moved_file(self):
        self.secrets(self.old, "export MC_API_TOKEN='tok123'\n")
        moved = self.move() / "secrets.env"
        with mock.patch.object(config, "SECRETS_FILE", moved), mock.patch.dict(os.environ, {"MC_API_TOKEN": ""}):
            self.assertEqual(config.secret("MC_API_TOKEN"), "tok123")


if __name__ == "__main__":
    unittest.main()
