#!/usr/bin/env python3
"""Unit tests for the game-identity check (ccf/gamecheck.py)."""

import unittest

from ccf.gamecheck import classify


class TestClassify(unittest.TestCase):

    def test_rejects_mislabeled_twitch_vod(self):
        # The real failure: a Naraka stream filed under the GTA 6 category.
        meta = "title: Naraka Bladepoint ranked\ngenre: Grand Theft Auto VI\ncomment: chapters"
        ok, reason = classify(meta, "")
        self.assertFalse(ok)
        self.assertIn("Naraka", reason)

    def test_chapter_names_are_evidence(self):
        meta = "genre: Grand Theft Auto VI\nNARAKA: BLADEPOINT\nJust Chatting"
        ok, _ = classify(meta, "")
        self.assertFalse(ok)

    def test_accepts_metadata_that_names_the_game(self):
        ok, reason = classify("title: GTA 6 gameplay part 3 - no commentary", "")
        self.assertTrue(ok)
        self.assertIn("metadata", reason)

    def test_accepts_on_screen_marker(self):
        ok, reason = classify("title: some stream", "LEONIDA\nWEAR")
        self.assertTrue(ok)
        self.assertIn("on screen", reason)

    def test_metadata_alone_is_enough_when_screen_has_no_marker(self):
        ok, _ = classify("title: GTA 6 gameplay", "press X to crouch")
        self.assertTrue(ok)

    def test_older_gta_is_not_gta_6(self):
        ok, reason = classify("GTA 5 online heist", "")
        self.assertFalse(ok)
        self.assertIn("older GTA", reason)

    def test_grand_theft_auto_vi_is_not_read_as_gta_v(self):
        ok, _ = classify("Grand Theft Auto VI - free roam", "")
        self.assertTrue(ok)

    def test_no_evidence_fails_closed(self):
        ok, reason = classify("", "")
        self.assertFalse(ok)
        self.assertIn("could not confirm", reason)

    def test_require_screen_text_without_ocr_rejects(self):
        ok, reason = classify("title: GTA 6 gameplay", "", ocr_available=False,
                              require_screen_text=True)
        self.assertFalse(ok)
        self.assertIn("unavailable", reason)

    def test_vice_city_counts_as_gta_6(self):
        ok, _ = classify("Vice City beach at night", "")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
