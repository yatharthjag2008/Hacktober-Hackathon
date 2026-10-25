"""Test seam: run the Harness CLI as a subprocess against a scripted fake model server.

Standard library only. Typical use:

    class MyTest(HarnessTest):
        def test_x(self):
            r = self.run_harness([tool_call("list_games"), reply("hi")], ["make a game"])
            r.stdout, r.requests, r.out_dir, r.trace
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness.py"
GODOT = os.environ.get("GODOT", str(ROOT / "tools" / "godot"))
TEMPLATE = ROOT / "template"
HAVE_GODOT = os.path.isfile(GODOT) and os.access(GODOT, os.X_OK)
requires_godot = unittest.skipUnless(HAVE_GODOT, f"Godot binary not found at {GODOT}; set GODOT=/path/to/godot")
TIMEOUT = 300  # seconds one Harness run may take

# --- the box game: a minimal game most tests build ---------------------------

DESIGN = "# Box\n\nPitch: a red box on screen.\n"
MAIN_GD = ('extends Node2D\n\nfunc _ready() -> void:\n\tprint("box ready")\n\n'
           "func _draw() -> void:\n\tdraw_rect(Rect2(100, 100, 200, 200), Color.RED)\n")

# --- scripted assistant messages -------------------------------------------

_ids = iter(range(1, 1_000_000))


def reply(text):
    """A text-only assistant message."""
    return {"role": "assistant", "content": text}


def call(fn, /, **args):
    """One tool call, for use inside calls()."""
    return {"id": f"call_{next(_ids)}", "type": "function",
            "function": {"name": fn, "arguments": json.dumps(args)}}


def calls(*tool_calls, content=None):
    """An assistant message making several tool calls at once."""
    return {"role": "assistant", "content": content, "tool_calls": list(tool_calls)}


def tool_call(fn, /, **args):
    """An assistant message making a single tool call."""
    return calls(call(fn, **args))


def box_game(*steps, name="box"):
    """Script: create the box game (design.md = DESIGN, main.gd still the template's), then `steps`."""
    return [tool_call("create_game", name=name, title="Box", design=DESIGN), *steps]


# --- fake model server -------------------------------------------------------

DROP = "drop"

class FakeModel:
    """OpenAI-compatible chat-completions server that replays `script` and records request bodies.

    Each script item is an assistant message dict, an int to answer with that HTTP status, or DROP to
    close the connection without answering.
    Once the script runs out it replies "(script exhausted)" so the Harness never hangs.
    """

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                item = fake.script.pop(0) if fake.script else reply("(script exhausted)")
                if item == DROP:
                    self.close_connection = True
                    return
                if isinstance(item, int):
                    data, status = json.dumps({"error": f"scripted {item}"}).encode(), item
                else:
                    data, status = json.dumps({"choices": [{"message": item}]}).encode(), 200
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


# --- running the Harness ------------------------------------------------------

class Result:
    def __init__(self, stdout, requests, out_dir, returncode):
        self.stdout, self.requests, self.out_dir, self.returncode = stdout, requests, Path(out_dir), returncode

    @property
    def trace(self):
        """All trace events from out_dir/.sessions/*.jsonl, oldest file first."""
        return [json.loads(l) for f in sorted((self.out_dir / ".sessions").glob("*.jsonl"))
                for l in f.read_text().splitlines() if l.strip()]

    def events(self, kind):
        return [e for e in self.trace if e["event"] == kind]

    def results(self, tool):
        """The results of every call to `tool`, in order."""
        return [e["result"] for e in self.events("tool_result") if e["tool"] == tool]


def run_harness(script, lines=(), *args, out_dir, visual=False, frames=120):
    """Run harness.py with piped stdin `lines` (EOF ends the Session) against a FakeModel(script).

    `args` are extra CLI arguments (e.g. "--open", "pong"). Returns a Result.
    """
    with FakeModel(script) as fake:
        cmd = [sys.executable, str(HARNESS), "--base-url", fake.url, "--out-dir", str(out_dir),
               "--godot", GODOT, "--frames", str(frames), *([] if visual else ["--no-visual"]), *args]
        p = subprocess.run(cmd, input="".join(l + "\n" for l in lines), capture_output=True, text=True,
                           timeout=TIMEOUT, cwd=ROOT)
    return Result(p.stdout + p.stderr, fake.requests, out_dir, p.returncode)


@requires_godot
class HarnessTest(unittest.TestCase):
    """Base class: gives each test a fresh temp out dir at self.out_dir."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="opengames-test-")
        self.addCleanup(tmp.cleanup)
        self.out_dir = Path(tmp.name)

    def run_harness(self, script, lines=(), *args, **kw):
        kw.setdefault("out_dir", self.out_dir)
        return run_harness(script, lines, *args, **kw)
