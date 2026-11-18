#!/usr/bin/env python3
"""
Comprehensive test suite for Chat Clip Finder (both Node.js and Python implementations)
"""

import unittest
import json
import subprocess
import tempfile
import os
from pathlib import Path

from chat_clips import format_hms, calculate_median


class TestChatClipFinder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_dir = Path(__file__).resolve().parent
        cls.demo_json = cls.repo_dir / "demo_chat.json"
        if not cls.demo_json.exists():
            from generate_demo_chat import generate_demo_chat
            generate_demo_chat(str(cls.demo_json))

    def test_format_hms(self):
        self.assertEqual(format_hms(0), "0:00:00")
        self.assertEqual(format_hms(59), "0:00:59")
        self.assertEqual(format_hms(60), "0:01:00")
        self.assertEqual(format_hms(3665), "1:01:05")
        self.assertEqual(format_hms(7200), "2:00:00")

    def test_calculate_median(self):
        self.assertEqual(calculate_median([]), 0)
        self.assertEqual(calculate_median([5]), 5)
        self.assertEqual(calculate_median([1, 10, 2]), 2)
        self.assertEqual(calculate_median([1, 2, 3, 4]), 3)

    def test_spike_detection_logic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            test_chat = tmp_path / "test_chat.json"

            # 600 seconds total (10 mins)
            # Baseline: 1 msg every 10s (indices 0..59)
            # Big spike at 300s (index 30): 50 msgs
            comments = [{"content_offset_seconds": float(t)} for t in range(0, 600, 10)]
            for _ in range(50):
                comments.append({"content_offset_seconds": 300.0 + (_ * 0.1)})
            comments.sort(key=lambda c: c["content_offset_seconds"])

            with open(test_chat, "w", encoding="utf-8") as f:
                json.dump({"comments": comments}, f)

            out_dir = tmp_path / "out"
            res = subprocess.run(
                ["python3", str(self.repo_dir / "chat_clips.py"), str(test_chat), "--out", str(out_dir), "--dry-run"],
                capture_output=True,
                text=True
            )
            self.assertEqual(res.returncode, 0, f"Python CLI failed: {res.stderr}")

            moments_file = out_dir / "moments.json"
            self.assertTrue(moments_file.exists())

            with open(moments_file, "r") as f:
                data = json.load(f)

            self.assertGreaterEqual(len(data), 1)
            top_moment = data[0]
            self.assertEqual(top_moment["t"], 300)
            self.assertEqual(top_moment["timestamp"], "0:05:00")
            self.assertEqual(top_moment["start"], 280)  # 300 - 20 (before)
            self.assertEqual(top_moment["end"], 310)    # 300 + 10 (after)

    def test_node_and_python_parity_on_demo_chat(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            out_py = tmp_path / "clips_py"
            out_node = tmp_path / "clips_node"

            # Run Python implementation
            res_py = subprocess.run(
                ["python3", str(self.repo_dir / "chat_clips.py"), str(self.demo_json), "--out", str(out_py), "--dry-run"],
                capture_output=True,
                text=True
            )
            self.assertEqual(res_py.returncode, 0, f"Python run failed: {res_py.stderr}")

            # Run Node implementation
            res_node = subprocess.run(
                ["node", str(self.repo_dir / "chat-clips.mjs"), str(self.demo_json), "--out", str(out_node), "--dry-run"],
                capture_output=True,
                text=True
            )
            self.assertEqual(res_node.returncode, 0, f"Node run failed: {res_node.stderr}")

            with open(out_py / "moments.json") as f:
                data_py = json.load(f)

            with open(out_node / "moments.json") as f:
                data_node = json.load(f)

            self.assertEqual(len(data_py), len(data_node))
            for p, n in zip(data_py, data_node):
                self.assertEqual(p["t"], n["t"], "Peak timestamps do not match")
                self.assertEqual(p["start"], n["start"], "Clip start times do not match")
                self.assertEqual(p["end"], n["end"], "Clip end times do not match")
                self.assertEqual(p["clipStart"], n["clipStart"])
                self.assertEqual(p["clipEnd"], n["clipEnd"])

    def test_custom_cli_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            out_dir = tmp_path / "custom_out"

            res = subprocess.run(
                [
                    "python3", str(self.repo_dir / "chat_clips.py"),
                    str(self.demo_json),
                    "--out", str(out_dir),
                    "--top", "3",
                    "--before", "15",
                    "--after", "15",
                    "--gap", "120",
                    "--dry-run"
                ],
                capture_output=True,
                text=True
            )
            self.assertEqual(res.returncode, 0)
            with open(out_dir / "moments.json") as f:
                data = json.load(f)

            self.assertEqual(len(data), 3)
            for item in data:
                self.assertEqual(item["duration"], 30)
                self.assertEqual(item["end"] - item["start"], 30)

    def test_caption_helper_help(self):
        res = subprocess.run(
            ["python3", str(self.repo_dir / "caption_helper.py"), "--help"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Caption Helper", res.stdout)

    def test_reaction_classifier_emoji_and_gta6(self):
        from ccf.chat import classify
        self.assertGreater(classify("💀💀", "gta6")[0], 0)        # emoji-only messages count now
        self.assertGreater(classify("😭", "gta6")[0], 0)
        self.assertEqual(classify("well done", "gta6")[0], 0)      # 'l' inside words is not an L
        self.assertEqual(classify("WASTED", "gta6")[1], "game")
        self.assertLess(classify("W", "gta6")[0], classify("KEKW", "gta6")[0])  # single letters weigh less

    def test_youtube_live_chat_loader(self):
        from ccf.chat import load_chat
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "x.live_chat.json"
            line = {"replayChatItemAction": {"videoOffsetTimeMsec": "12500", "actions": [{"addChatItemAction": {
                "item": {"liveChatTextMessageRenderer": {"message": {"runs": [{"text": "NO WAY "},
                {"emoji": {"emojiId": "💀"}}]}, "authorName": {"simpleText": "a"}}}}}]}}
            p.write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
            msgs, length = load_chat(p)
            self.assertEqual(len(msgs), 1)
            self.assertAlmostEqual(msgs[0]["t"], 12.5)
            self.assertIn("💀", msgs[0]["text"])

    def test_source_kinds(self):
        from ccf.sources import kind_of
        self.assertEqual(kind_of("https://www.youtube.com/watch?v=abc"), "youtube")
        self.assertEqual(kind_of("https://youtu.be/abc"), "youtube")
        self.assertEqual(kind_of("https://www.twitch.tv/videos/1234567890"), "twitch")

    def test_titles_are_unique_per_clip(self):
        from ccf import titles
        a = titles.make(1, "laugh", "", "kai", "gta6")
        b = titles.make(2, "shock", "", "kai", "gta6")
        self.assertNotEqual(a["title"], b["title"])
        self.assertIn("GTA6", a["tags"])
        self.assertEqual(a["credit"], "@kai")

    def test_ass_builder(self):
        from ccf.captions import build_ass
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "c.ass"
            words = [{"w": "no", "s": 0.0, "e": 0.3}, {"w": "way", "s": 0.3, "e": 0.7}, {"w": "bro", "s": 0.8, "e": 1.1}]
            build_ass(out, words, 5.0, hook="WAIT FOR IT", credit="@kai")
            txt = out.read_text(encoding="utf-8")
            self.assertIn("NO WAY BRO", txt.replace("{\\c&H0000E5FF&\\fscx112\\fscy112}", "").replace("{\\c&H00FFFFFF&\\fscx100\\fscy100}", ""))
            self.assertIn("WAIT FOR IT", txt)
            self.assertIn("@kai", txt)


    def test_discover_keeps_only_gta6_gameplay(self):
        from ccf.discover import is_gta6_gameplay as g
        self.assertTrue(g("🔴 GTA 6 LIVE - FIRST TIME PLAYING"))
        self.assertTrue(g("GTA 6 Gameplay Walkthrough Part 1"))
        self.assertFalse(g("GTA 6 Just Got a MASSIVE Last Minute Info Dump..."))
        self.assertFalse(g("GTA San Andreas Live Stream | GTA 6 soon"))
        self.assertFalse(g("GTA 5 Funny Moments"))
        self.assertFalse(g("LIVE: Playing Fortnite + Talking about GTA 6"))


if __name__ == "__main__":
    unittest.main()
