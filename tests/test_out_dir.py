import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import HARNESS, FakeModel, Result


def quit_session(out, *args, harness=HARNESS, env=()):
    """Start a Session and /quit straight away; `out` is where its trace is expected. Needs no model or Godot.

    Unlike run_harness this can omit --out-dir and set HARNESS_OUT_DIR, which is what these tests vary.
    """
    with FakeModel([]) as fake:
        env = {**{k: v for k, v in os.environ.items() if k != "HARNESS_OUT_DIR"}, **dict(env)}
        p = subprocess.run([sys.executable, str(harness), "--base-url", fake.url, "--no-visual", *args],
                           input="/quit\n", capture_output=True, text=True, timeout=60, env=env, check=True)
    return Result(p.stdout + p.stderr, fake.requests, out, p.returncode)


class OutputDirectory(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="opengames-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def assert_quit_traced(self, r):
        self.assertEqual([e["event"] for e in r.trace], ["session", "command"])

    def test_env_var_sets_output_directory(self):
        out = self.tmp / "games"
        self.assert_quit_traced(quit_session(out, env={"HARNESS_OUT_DIR": str(out)}))

    def test_out_dir_flag_takes_precedence_over_env_var(self):
        from_env, from_flag = self.tmp / "from-env", self.tmp / "from-flag"
        self.assert_quit_traced(quit_session(from_flag, "--out-dir", str(from_flag),
                                             env={"HARNESS_OUT_DIR": str(from_env)}))
        self.assertFalse(from_env.exists())

    def test_defaults_to_out_next_to_harness(self):
        harness = self.tmp / "harness.py"  # a copy, so the real out/ is never touched
        shutil.copy(HARNESS, harness)
        self.assert_quit_traced(quit_session(self.tmp / "out", harness=harness))
