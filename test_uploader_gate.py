#!/usr/bin/env python3
"""Candle Gate wiring in youtube_uploader.py (no network)."""
import json
import tempfile
import unittest
from pathlib import Path

import youtube_uploader as yu


class FakeGate:
    def __init__(self, evals):
        self.evals = list(evals)

    def evaluate_live_channel(self, client):
        return {"candle_evaluation": self.evals.pop(0)}


class TestUploaderGate(unittest.TestCase):
    def test_force_skips_gate(self):
        ok, msg = yu.check_candle_gate(force=True)
        self.assertTrue(ok)

    def test_blocked_by_spacing(self):
        gate = FakeGate([{"can_upload": False, "active_layer": "Layer 0", "recommendation": "wait"}])
        ok, msg = yu.check_candle_gate(client=object(), gate=gate)
        self.assertFalse(ok)
        self.assertIn("Layer 0", msg)

    def test_inline_spacing_wait_then_upload(self):
        slept = []
        gate = FakeGate([{"can_upload": False, "requires_spacing_sleep": True, "spacing_sleep_seconds": 600}])
        ok, _ = yu.check_candle_gate(client=object(), gate=gate, sleep_fn=slept.append)
        self.assertTrue(ok)
        self.assertEqual(slept, [600])

    def test_near_threshold_timer_rechecks(self):
        slept = []
        gate = FakeGate([{"can_upload": False, "requires_timer": True, "timer_seconds": 3600},
                         {"can_upload": True, "active_layer": "All Layers Cleared", "recommendation": "go"}])
        ok, _ = yu.check_candle_gate(client=object(), gate=gate, sleep_fn=slept.append)
        self.assertTrue(ok)
        self.assertEqual(sum(slept), 3600)

    def test_record_upload_feeds_preflight(self):
        from preflight_gate import decide
        with tempfile.TemporaryDirectory() as d:
            yu.HISTORY_FILE = Path(d) / "upload_history.json"
            yu.record_upload("abc123", "t", "clip.mp4", "public", mode="viceprint", layout="viceprint")
            saved = json.loads(yu.HISTORY_FILE.read_text())
            self.assertEqual(saved[0]["status"], "uploaded")
            self.assertEqual(saved[0]["mode"], "viceprint")
            self.assertEqual(saved[0]["layout"], "viceprint")
            res = decide(history_path=yu.HISTORY_FILE)
            self.assertFalse(res["proceed"])  # just uploaded -> next run is skipped

    def test_local_layer0_enforced_when_youtube_api_unreachable(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            yu.HISTORY_FILE = Path(d) / "upload_history.json"
            yu.record_upload("recent99", "t", "clip.mp4", "public", mode="stream", layout="stack")
            with patch.object(yu, "youtube_client", side_effect=RuntimeError("token expired")):
                ok, msg = yu.check_candle_gate(force=False, auto_timer=False)
                self.assertFalse(ok)
                self.assertIn("Layer 0", msg)


if __name__ == "__main__":
    unittest.main()
