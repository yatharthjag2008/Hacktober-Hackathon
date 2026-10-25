import base64
import os
import subprocess
import sys
import unittest
from pathlib import Path

from support import MAIN_GD, HarnessTest, box_game, tool_call

HAVE_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
requires_display = unittest.skipUnless(
    HAVE_DISPLAY, "Visual Check needs a display: set DISPLAY or WAYLAND_DISPLAY (or run with a virtual one)")

PNG_PREFIX = "data:image/png;base64,"


def image_urls(request):
    """The image part URLs in all messages of one recorded model request."""
    return [part["image_url"]["url"]
            for m in request["messages"] if isinstance(m.get("content"), list)
            for part in m["content"] if part.get("type") == "image_url"]


def checked_box_game(*steps):
    """Script: create the box game, write its main.gd, Run Check it, then `steps`."""
    return box_game(tool_call("write_file", path="main.gd", content=MAIN_GD), tool_call("run_game"), *steps)


@requires_display
class VisualCheckOn(HarnessTest):
    def test_clean_run_check_sends_screenshots_to_the_model(self):
        r = self.run_harness(checked_box_game(tool_call("finish", summary="A red box.")),
                             ["make a box game"], "--no-grill", visual=True)

        # Request index 3 is the one sent after run_game's result.
        self.assertEqual(image_urls(r.requests[2]), [])
        shots = image_urls(r.requests[3])
        self.assertEqual(len(shots), 2, r.stdout)  # about 1 s and 4 s in
        for url in shots:
            self.assertTrue(url.startswith(PNG_PREFIX), url[:60])
            self.assertTrue(base64.b64decode(url[len(PNG_PREFIX):]).startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(len(r.events("visual_check")), 1)
        self.assertIn("FINISHED", r.stdout)

    def test_old_screenshots_are_compacted_out_of_later_requests(self):
        # Four more tool steps push the screenshot message out of the recent window.
        r = self.run_harness(checked_box_game(*[tool_call("list_files")] * 4, tool_call("finish", summary="A red box.")),
                             ["make a box game"], "--no-grill", visual=True)

        self.assertEqual(len(r.requests), 8, r.stdout)
        self.assertEqual(len(image_urls(r.requests[3])), 2, r.stdout)
        last = r.requests[-1]
        self.assertEqual(image_urls(last), [])
        self.assertIn({"role": "user", "content": "[Visual Check screenshots omitted]"}, last["messages"])


class VisualCheckOff(HarnessTest):
    def test_no_visual_never_sends_images(self):
        r = self.run_harness(checked_box_game(tool_call("finish", summary="A red box.")),
                             ["make a box game"], "--no-grill", visual=False)

        self.assertEqual(len(r.requests), 4)
        self.assertEqual([image_urls(q) for q in r.requests], [[], [], [], []])
        self.assertEqual(r.events("visual_check"), [])
        self.assertIn("FINISHED", r.stdout)


class NoDisplay(unittest.TestCase):
    def test_visual_tests_skip_with_a_clear_reason_without_a_display(self):
        env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        p = subprocess.run([sys.executable, "-m", "unittest", "-v", "test_visual_check.VisualCheckOn"],
                           cwd=Path(__file__).parent, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("skipped=2", p.stderr)
        self.assertIn("needs a display", p.stderr)
