import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import HARNESS, FakeModel


def quit_session(harness, env):
    """Start a Session and /quit straight away, without --out-dir. Needs no model calls or Godot."""
    with FakeModel([]) as fake:
        env = {**{k: v for k, v in os.environ.items() if k != "HARNESS_OUT_DIR"}, **env}
        subprocess.run([sys.executable, str(harness), "--base-url", fake.url, "--no-visual"],
                       input="/quit\n", capture_output=True, text=True, timeout=60, env=env, check=True)


def trace_lines(out):
    return [json.loads(l) for f in (out / ".sessions").glob("*.jsonl") for l in f.read_text().splitlines()]


class OutputDirectory(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="opengames-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_env_var_sets_output_directory(self):
        out = self.tmp / "games"
        quit_session(HARNESS, {"HARNESS_OUT_DIR": str(out)})
        self.assertEqual([e["event"] for e in trace_lines(out)], ["session"])

    def test_defaults_to_out_next_to_harness(self):
        harness = self.tmp / "harness.py"  # a copy, so the real out/ is never touched
        shutil.copy(HARNESS, harness)
        quit_session(harness, {})
        self.assertEqual([e["event"] for e in trace_lines(self.tmp / "out")], ["session"])
