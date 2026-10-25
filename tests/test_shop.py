"""The shop's region check: only a clear answer from the map API counts. An
answer it doesn't recognise ("Invalid Capability ID.", an error page) is
"unknown", and never overwrites a real result."""

import sys
import unittest
from unittest import mock

import support  # noqa: F401  (sets up the throwaway data folder)

sys.path.insert(0, str(support.CODE / "tools"))
import shop_lookup  # noqa: E402

ROW = ("| Store | [store #1](https://marketplace.secondlife.com/stores/1) | "
       "[Somewhere/1/2/3](https://maps.secondlife.com/secondlife/Somewhere/1/2/3) | "
       "{region} | — | — | someone |")


def answering(body):
    return mock.patch.object(shop_lookup, "fetch", return_value=body)


class RegionExists(unittest.TestCase):
    def test_coordinates_mean_up(self):
        with answering("var coords = {'x' : 1000, 'y' : 1000 };"):
            self.assertIs(shop_lookup.region_exists("Somewhere"), True)

    def test_error_means_gone(self):
        with answering("var coords = {'error' : true };"):
            self.assertIs(shop_lookup.region_exists("Somewhere"), False)

    def test_invalid_capability_is_unknown(self):
        with answering("Invalid Capability ID.\n"):
            self.assertIsNone(shop_lookup.region_exists("Somewhere"))

    def test_empty_or_html_is_unknown(self):
        for body in ("", "<html><body>502 Bad Gateway</body></html>"):
            with answering(body):
                self.assertIsNone(shop_lookup.region_exists("Somewhere"))

    def test_unreachable_is_unknown(self):
        with mock.patch.object(shop_lookup, "fetch",
                               side_effect=shop_lookup.urllib.error.URLError("down")):
            self.assertIsNone(shop_lookup.region_exists("Somewhere"))


class VerifyAll(unittest.TestCase):
    def setUp(self):
        shop_lookup.SHOP.mkdir(exist_ok=True)
        self.path = shop_lookup.SHOP / "testing.md"
        self.addCleanup(self.path.unlink, missing_ok=True)

    def run_with(self, region_cell, body):
        self.path.write_text(shop_lookup.HEADER + ROW.format(region=region_cell) + "\n")
        with answering(body), mock.patch.object(shop_lookup.time, "sleep"), \
                mock.patch("builtins.print"):
            shop_lookup.verify_all()
        return self.path.read_text()

    def test_unknown_keeps_earlier_result(self):
        text = self.run_with("✓ region up 2026-10-20", "Invalid Capability ID.\n")
        self.assertIn("✓ region up 2026-10-20", text)
        self.assertNotIn("✗", text)

    def test_unknown_fills_an_empty_cell(self):
        self.assertIn("? map API not answering", self.run_with("—", "Invalid Capability ID.\n"))

    def test_clear_answer_replaces(self):
        text = self.run_with("✓ region up 2026-10-20", "var coords = {'error' : true };")
        self.assertIn("✗ region gone", text)


if __name__ == "__main__":
    unittest.main()
