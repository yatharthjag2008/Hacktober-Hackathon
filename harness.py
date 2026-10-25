#!/usr/bin/env python3
"""OpenGames Harness: drives any OpenAI-compatible model to design, build and iterate on Godot games.

Usage:
    python3 harness.py new "a pong game" [--grill] [--name pong]
    python3 harness.py edit pong
    python3 harness.py play pong

No dependencies beyond the Python standard library.
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "template"
OUT = ROOT / "out"
DEFAULT_GODOT = ROOT / "tools" / "godot"
INPUT_SIM = ROOT / "input_sim.gd"
CAPTURE = ROOT / "capture.gd"
HARNESS_DIR = ".harness"
MAX_TOOL_OUTPUT = 4000
KEEP_RECENT = 6  # messages at the end of the history that are never compacted

# --- terminal trace -------------------------------------------------------

C = {"dim": "\033[2m", "bold": "\033[1m", "cyan": "\033[36m", "yellow": "\033[33m",
     "green": "\033[32m", "red": "\033[31m", "magenta": "\033[35m", "blue": "\033[34m",
     "reset": "\033[0m"}


def say(color, label, text=""):
    print(f"{C[color]}{C['bold']}{label}{C['reset']} {text}", flush=True)


def ask(prompt="› "):
    try:
        return input(f"{C['bold']}{prompt}{C['reset']}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "/quit"


class Trace:
    """Appends every event of a session to <project>/.harness/trace.jsonl."""

    def __init__(self, project_path: Path):
        d = project_path / HARNESS_DIR
        d.mkdir(exist_ok=True)
        (d / ".gdignore").touch()  # keep Godot from importing harness files
        self.file = d / "trace.jsonl"

    def log(self, event, **data):
        with self.file.open("a") as f:
            f.write(json.dumps({"t": round(time.time(), 3), "event": event, **data}) + "\n")


# --- prompts --------------------------------------------------------------

DESIGN_PROMPT = """You are a game designer interviewing a Player-Creator about a small game they want built
in Godot 4. They may not know Godot. Your job is to reach a shared understanding of the design,
then write a Design Proposal.

Interview in rounds. Each round, ask the 2-4 most important open questions whose answers you
can't sensibly assume (genre and 2D/3D, core loop, controls, win/lose, scoring, look and feel,
scope). Number each question and give your recommended answer, worded so "yes" accepts it:

Q1 - <title>: <question>
  Recommended: <answer>

Keep scope small enough for one person to build in an hour: no imported assets (visuals are
built from simple shapes), no audio, no networking.

When the important decisions are settled (usually after 1-3 rounds), or when the Player-Creator
asks for it, write the Design Proposal inside <proposal></proposal> tags as Markdown with these
sections: Title, Pitch (one sentence), 2D or 3D, Core Loop, Controls, Win/Lose, Scoring and HUD,
Look, Out of Scope. If they ask for changes to a proposal, write a revised one in the same tags.
"""

BUILD_PROMPT = """You are a game developer agent that builds and maintains small, complete games in
Godot 4 (GDScript). Any genre is allowed: 2D or 3D, action, puzzle, platformer, shooter, racing...

You work in a Godot 4 project directory. A new project contains:
- project.godot  (main scene is res://main.tscn; window 1152x648; Compatibility renderer)
- main.tscn      (a plain Node named Main with script res://main.gd)
- main.gd        (placeholder script that extends Node; replace it)
- design.md      (the Design Proposal or Game Brief: the source of truth for what the game is)

How to work on every task (a new game, a change, a new feature, or a bug report):
1. Read the files you need, plan briefly, then write files with write_file
   (always COMPLETE file contents). Split into several .gd files if it helps.
2. Call run_game to do a Run Check. It launches the game headless for ~30s of game time while
   simulating random key presses, mouse clicks and mouse movement, and returns errors.
3. If there are errors, read them carefully, fix the files, and run_game again.
4. After a CLEAN Run Check you may receive screenshots of the running game (a Visual Check).
   Compare them with design.md: a black or empty screen, a camera that misses the action,
   unreadable HUD or missing elements are bugs. Fix them and run_game again; otherwise finish.
5. Keep design.md current: when you add or change features or controls, update it.
6. Call finish with a short summary of what you did and the controls.

Rules for reliable games:
- Build the game in code from main.gd (create nodes in _ready with add_child).
  Avoid hand-writing .tscn files; if you must, use format=3 exactly.
- No imported assets (no images, models or sounds). Build visuals from primitives:
  2D: ColorRect, Polygon2D, Line2D, Label, or custom _draw().
  3D: MeshInstance3D with BoxMesh/SphereMesh/CylinderMesh/CapsuleMesh/PlaneMesh/PrismMesh and a
  StandardMaterial3D (albedo_color), or CSGBox3D/CSGSphere3D with use_collision = true.
- 3D scenes must include a Camera3D (current = true), a DirectionalLight3D, and a WorldEnvironment
  with an Environment (background_mode = Environment.BG_SKY with a ProceduralSkyMaterial, or BG_COLOR).
  Make sure the camera actually looks at the action (look_at after the node is in the tree).
  For physics use CharacterBody3D/RigidBody3D/StaticBody3D/Area3D with CollisionShape3D shapes.
- UI and HUD: put Labels/Controls under a CanvasLayer so they draw on top in both 2D and 3D.
- Use Godot 4 syntax only: @export, @onready, await (not yield), CharacterBody2D/3D (not Kinematic*),
  move_and_slide() takes no arguments, velocity is a built-in property, Vector2/Vector3,
  true/false (not True/False), String formatting with "%d" % x or str(x).
  Signals: button.pressed.connect(_on_pressed).
- Input: use Input.is_key_pressed(KEY_W) / KEY_UP etc., Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT),
  _unhandled_input(event) with InputEventMouseMotion.relative for mouse look, or built-in ui_* actions.
  Do not invent custom input actions.
- Use static typing where easy; indent with tabs. Always guard against null nodes.
- Keep the scope small but fully playable: a goal, a score or win/lose state, and restart (R).
"""

TOOLS = [
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a file in the project with complete contents.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path relative to the project root, e.g. main.gd"},
            "content": {"type": "string", "description": "Full file contents"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file from the project.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List all files in the project.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "run_game",
        "description": "Run Check: launch the game headless for ~30s of game time while random keys, "
                       "clicks and mouse movement are simulated, and return errors and output.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Declare the task done. Only allowed after a CLEAN Run Check with no later edits.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string", "description": "What you did, and the game's controls"}},
            "required": ["summary"]}}},
]

# --- project and tools ----------------------------------------------------

ERROR_PATTERN = re.compile(r"^\s*(SCRIPT ERROR|USER SCRIPT ERROR|ERROR|USER ERROR):")
# Engine shutdown noise, not caused by the game's logic.
NOISE_PATTERN = re.compile(r"leaked at exit|in use at exit|still in use at exit|Pages in use exist at exit")


class Project:
    def __init__(self, path: Path, godot: str, frames: int, visual: bool):
        self.path = path
        self.godot = godot
        self.frames = frames
        self.visual = visual
        self.clean_since_last_edit = False
        self.pending_shots: list[Path] = []

    def _resolve(self, rel: str) -> Path:
        p = (self.path / rel.lstrip("/").removeprefix("res://")).resolve()
        if self.path not in p.parents and p != self.path:
            raise ValueError(f"path escapes project: {rel}")
        if HARNESS_DIR in p.relative_to(self.path).parts:
            raise ValueError(f"{HARNESS_DIR}/ is reserved for the harness")
        return p

    def write_file(self, path, content):
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        self.clean_since_last_edit = False
        return f"Wrote {path} ({len(content.splitlines())} lines)."

    def read_file(self, path):
        return self._resolve(path).read_text()

    def list_files(self):
        files = [str(f.relative_to(self.path)) for f in sorted(self.path.rglob("*"))
                 if f.is_file() and not f.name.endswith(".uid")
                 and not {".godot", HARNESS_DIR} & set(f.relative_to(self.path).parts)]
        return "\n".join(files)

    def _launch(self, autoloads, args, timeout, env=None):
        """Run Godot with harness scripts injected as autoloads for this run only."""
        pg = self.path / "project.godot"
        original = pg.read_text()
        entries = "".join(f'Harness{src.stem.title().replace("_", "")}="*res://{src.name}"\n' for src in autoloads)
        for src in autoloads:
            shutil.copy(src, self.path / src.name)
        pg.write_text(original.replace("[autoload]\n", f"[autoload]\n\n{entries}", 1)
                      if "[autoload]" in original else original + f"\n[autoload]\n\n{entries}")
        try:
            r = subprocess.run([self.godot, "--path", str(self.path), *args],
                               capture_output=True, text=True, timeout=timeout,
                               env={**os.environ, **(env or {})})
            return r.stdout + r.stderr
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or "") + (e.stderr or "") if isinstance(e.stdout, str) else ""
            return out + f"\nTIMEOUT: game did not exit within {timeout}s (infinite loop in _ready/_process?)."
        finally:
            pg.write_text(original)
            for src in autoloads:
                (self.path / src.name).unlink(missing_ok=True)
                (self.path / (src.name + ".uid")).unlink(missing_ok=True)

    def run_game(self):
        # Import first so scripts and scenes are registered, then run a fixed number of
        # 60 fps frames (fast in headless, but simulated time advances normally).
        subprocess.run([self.godot, "--headless", "--path", str(self.path), "--import"],
                       capture_output=True, text=True, timeout=120)
        out = self._launch([INPUT_SIM], ["--headless", "--fixed-fps", "60", "--quit-after", str(self.frames)], 90)
        # Runtime errors in _process repeat every frame; keep each distinct line once.
        lines = list(dict.fromkeys(l for l in out.splitlines()
                                   if l.strip() and not l.startswith("Godot Engine v")
                                   and not NOISE_PATTERN.search(l)))
        errors = [l for l in lines if ERROR_PATTERN.search(l)]
        if errors or "TIMEOUT" in out:
            self.clean_since_last_edit = False
            return "ERRORS FOUND:\n" + "\n".join(lines)
        self.clean_since_last_edit = True
        if self.visual:
            self.pending_shots = self.capture()
        return "CLEAN: game ran without errors.\nOutput:\n" + "\n".join(lines[-30:])

    def capture(self):
        """Visual Check: render the game for real and screenshot it at fixed frames."""
        shot_dir = Path(tempfile.mkdtemp(prefix="opengames-shots-"))
        self._launch([INPUT_SIM, CAPTURE], ["--fixed-fps", "60"], 60, env={"HARNESS_SHOT_DIR": str(shot_dir)})
        return sorted(shot_dir.glob("shot_*.png"))

    def finish(self, summary):
        if not self.clean_since_last_edit:
            return "REJECTED: run_game must report CLEAN after your last edit before you can finish."
        return "DONE"

    def play(self):
        subprocess.Popen([self.godot, "--path", str(self.path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --- model client ---------------------------------------------------------

def chat(cfg, messages, tools=None):
    payload = {"model": cfg.model, "messages": messages}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(cfg.base_url.rstrip("/") + "/chat/completions",
                                 data=json.dumps(payload).encode(), headers={
                                     "Content-Type": "application/json",
                                     "Authorization": f"Bearer {cfg.api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.load(r)["choices"][0]["message"]
    except urllib.error.HTTPError as e:
        sys.exit(f"Model API error {e.code}: {e.read().decode()[:500]}")


def compact(messages):
    """Shrink old history: drop file bodies the model already wrote, old screenshots and old reads.

    The model can always read_file to see current contents, so nothing is lost.
    """
    cutoff = len(messages) - KEEP_RECENT
    for i, m in enumerate(messages[:max(cutoff, 0)]):
        if m["role"] == "assistant":
            for call in m.get("tool_calls") or []:
                fn = call["function"]
                if fn["name"] == "write_file" and '"content"' in (fn.get("arguments") or ""):
                    try:
                        a = json.loads(fn["arguments"])
                    except json.JSONDecodeError:
                        continue
                    if not a.get("content", "").startswith("<omitted"):
                        a["content"] = "<omitted: written earlier; use read_file for current contents>"
                        fn["arguments"] = json.dumps(a)
        elif m["role"] == "user" and isinstance(m["content"], list):
            messages[i] = {"role": "user", "content": "[Visual Check screenshots omitted]"}
        elif m["role"] == "tool" and len(m["content"]) > 1500 and not m["content"].startswith(("ERRORS", "CLEAN")):
            m["content"] = m["content"][:300] + "\n<omitted: read earlier; use read_file again if needed>"


# --- agent loop -----------------------------------------------------------

def run_agent(cfg, project, messages, trace):
    """Run tool-calling steps until the model finishes cleanly. Returns True on success."""
    for step in range(1, cfg.max_steps + 1):
        print(f"{C['dim']}── step {step} ──{C['reset']}")
        compact(messages)
        msg = chat(cfg, messages, TOOLS)
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
        trace.log("model", content=msg.get("content"), tool_calls=msg.get("tool_calls"))
        if msg.get("content"):
            say("cyan", "MODEL", msg["content"].strip())
        calls = msg.get("tool_calls") or []
        if not calls:
            messages.append({"role": "user", "content": "Continue by calling a tool. "
                             "Use run_game to check the game, then finish when it is CLEAN."})
            continue
        for call in calls:
            fn = call["function"]["name"]
            try:
                fargs = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                fargs = None
            shown = {k: (f"<{len(v.splitlines())} lines>" if k == "content" else v)
                     for k, v in (fargs or {}).items()}
            say("yellow", "TOOL", f"{fn}({json.dumps(shown)})")
            if fargs is None:
                result = "Error: arguments were not valid JSON."
            elif fn not in {t["function"]["name"] for t in TOOLS}:
                result = f"Error: unknown tool {fn}."
            else:
                try:
                    result = getattr(project, fn)(**fargs)
                except TypeError as e:
                    result = f"Error: bad arguments for {fn}: {e}. Check the tool's required parameters."
                except Exception as e:
                    result = f"Error: {e}"
            trace.log("tool_result", tool=fn, result=result)
            if fn == "run_game":
                say("green" if result.startswith("CLEAN") else "red", "RUN CHECK", result.splitlines()[0])
                for l in result.splitlines()[1:12]:
                    print(f"  {C['dim']}{l}{C['reset']}")
            elif result.startswith(("Error", "REJECTED")):
                say("red", "RESULT", result)
            messages.append({"role": "tool", "tool_call_id": call.get("id", fn),
                             "content": result[:MAX_TOOL_OUTPUT]})
            if fn == "finish" and result == "DONE":
                say("green", "FINISHED", fargs["summary"])
                return True
        if project.pending_shots:
            shots, project.pending_shots = project.pending_shots, []
            say("blue", "VISUAL CHECK", f"sending {len(shots)} screenshot(s) to the model")
            trace.log("visual_check", screenshots=[str(s) for s in shots])
            messages.append({"role": "user", "content": [
                {"type": "text", "text": "Visual Check: screenshots of the running game after 1s and 4s "
                 "with simulated input. Compare them with design.md. If something looks wrong, fix it and "
                 "run_game again. If it looks right, call finish."},
                *({"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(s.read_bytes()).decode()}} for s in shots)]})
    say("red", "STOPPED", f"hit max steps ({cfg.max_steps}) without a clean finish")
    return False


# --- design interview -----------------------------------------------------

def design_interview(cfg, brief, trace):
    """Grill the Player-Creator about the design until they accept a Design Proposal."""
    say("magenta", "DESIGN", "Answer the questions (\"yes\" accepts the recommendations). "
        "Type /propose to skip to a proposal, /quit to abort.")
    messages = [{"role": "system", "content": DESIGN_PROMPT},
                {"role": "user", "content": f"Game Brief: {brief}"}]
    while True:
        msg = chat(cfg, messages)
        content = msg.get("content") or ""
        messages.append({"role": "assistant", "content": content})
        trace.log("design_model", content=content)
        proposal = re.search(r"<proposal>(.*?)</proposal>", content, re.S)
        if proposal:
            print(f"\n{proposal.group(1).strip()}\n")
            reply = ask("Accept this design? [y = build it / or type changes] › ")
            while reply.startswith("/") and reply != "/quit":
                reply = ask("Type y to build it, describe changes, or /quit › ")
            trace.log("design_user", content=reply)
            if reply == "/quit":
                return None
            if reply.lower() in ("y", "yes", "ok", "accept"):
                return proposal.group(1).strip()
            messages.append({"role": "user", "content": f"Revise the proposal: {reply}"})
            continue
        say("cyan", "DESIGNER", content.strip())
        reply = ask()
        trace.log("design_user", content=reply)
        if reply == "/quit":
            return None
        if reply == "/propose":
            reply = "Write the Design Proposal now, using your recommendations for anything still open."
        messages.append({"role": "user", "content": reply})


# --- sessions -------------------------------------------------------------

HELP = """Type a Change Request: a new feature, a change, or a bug you found while playing.
  /play   launch the game in a window
  /files  list project files
  /help   show this help
  /quit   exit (run `python3 harness.py edit <name>` to continue later)"""


def iterate(cfg, project, messages, trace, name):
    """Interactive loop: each Change Request is built, Run Checked and finished like a new game."""
    say("magenta", "ITERATE", "The game is ready. " + HELP.splitlines()[0])
    print(f"{C['dim']}{HELP}{C['reset']}")
    while True:
        req = ask()
        if not req:
            continue
        if req == "/quit":
            print(f"Continue later with: python3 harness.py edit {name}")
            return
        if req == "/play":
            project.play()
            continue
        if req == "/files":
            print(project.list_files())
            continue
        if req == "/help":
            print(HELP)
            continue
        trace.log("change_request", content=req)
        messages.append({"role": "user", "content":
                         f"Change Request from the Player-Creator: {req}\n"
                         "It may be a new feature, a change, or a bug they found while playing. "
                         "Make it, keep design.md current, Run Check, then finish."})
        project.clean_since_last_edit = False
        run_agent(cfg, project, messages, trace)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "game"


def cmd_new(cfg):
    out = OUT / (cfg.name or slugify(cfg.brief))
    if out.exists():
        if ask(f"{out} exists. Overwrite? [y/N] › ").lower() not in ("y", "yes"):
            return
        shutil.rmtree(out)
    shutil.copytree(TEMPLATE, out)
    trace = Trace(out)
    trace.log("session", mode="new", model=cfg.model, brief=cfg.brief, grill=cfg.grill)
    say("magenta", "HARNESS", f"model={cfg.model} base_url={cfg.base_url}")
    say("magenta", "PROJECT", str(out))
    say("magenta", "BRIEF", cfg.brief)

    design = cfg.brief
    if cfg.grill:
        design = design_interview(cfg, cfg.brief, trace)
        if design is None:
            say("red", "ABORTED", "no design accepted")
            return
        trace.log("design_accepted", proposal=design)
    (out / "design.md").write_text(design + "\n")
    title = re.search(r"^#+\s*(?:Title:?\s*)?(.+)$", design, re.M)
    pg = out / "project.godot"
    pg.write_text(pg.read_text().replace('config/name="Generated Game"',
                                         f'config/name="{(title.group(1) if title else cfg.brief)[:60].replace(chr(34), "")}"'))

    project = Project(out.resolve(), cfg.godot, cfg.frames, cfg.visual)
    messages = [{"role": "system", "content": BUILD_PROMPT},
                {"role": "user", "content": f"Build this game. design.md contains:\n\n{design}"}]
    run_agent(cfg, project, messages, trace)
    if cfg.interactive:
        iterate(cfg, project, messages, trace, out.name)


def open_existing(cfg):
    out = OUT / cfg.name
    if not (out / "project.godot").exists():
        sys.exit(f"No game at {out}")
    return out, Project(out.resolve(), cfg.godot, cfg.frames, cfg.visual)


def cmd_edit(cfg):
    out, project = open_existing(cfg)
    trace = Trace(out)
    trace.log("session", mode="edit", model=cfg.model)
    say("magenta", "HARNESS", f"model={cfg.model} base_url={cfg.base_url}")
    say("magenta", "PROJECT", str(out))
    design = (out / "design.md").read_text() if (out / "design.md").exists() else "(no design.md yet)"
    messages = [{"role": "system", "content": BUILD_PROMPT},
                {"role": "user", "content": f"You are continuing work on an existing game.\n\n"
                 f"Files:\n{project.list_files()}\n\ndesign.md:\n{design}\n\n"
                 "Wait for Change Requests; read files before editing them."},
                {"role": "assistant", "content": "Understood. Ready for Change Requests."}]
    iterate(cfg, project, messages, trace, out.name)


def cmd_play(cfg):
    _, project = open_existing(cfg)
    project.play()


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default=os.environ.get("HARNESS_MODEL", "gemma4:31b-cloud"))
    common.add_argument("--base-url", default=os.environ.get("HARNESS_BASE_URL", "http://localhost:11434/v1"))
    common.add_argument("--api-key", default=os.environ.get("HARNESS_API_KEY", "ollama"))
    common.add_argument("--godot", default=os.environ.get("GODOT", str(DEFAULT_GODOT)))
    common.add_argument("--max-steps", type=int, default=40, help="Max agent steps per task")
    common.add_argument("--frames", type=int, default=1800, help="Frames (at 60 fps) to run during a Run Check")
    common.add_argument("--no-visual", dest="visual", action="store_false",
                        help="Skip the Visual Check (needs a display and a vision-capable model)")

    ap = argparse.ArgumentParser(description="OpenGames: design, build and iterate on Godot games with any model.")
    sub = ap.add_subparsers(dest="command", required=True)
    p_new = sub.add_parser("new", parents=[common], help="Create a new game from a Game Brief")
    p_new.add_argument("brief", help="Game Brief: plain-language description of the game")
    p_new.add_argument("--name", help="Output folder name under out/ (default: from brief)")
    p_new.add_argument("--grill", action="store_true", help="Interview me about the design before building")
    p_new.add_argument("--no-interactive", dest="interactive", action="store_false",
                       help="Exit after the build instead of taking Change Requests")
    p_new.set_defaults(func=cmd_new)
    p_edit = sub.add_parser("edit", parents=[common], help="Iterate on an existing game with Change Requests")
    p_edit.add_argument("name", help="Folder name under out/")
    p_edit.set_defaults(func=cmd_edit)
    p_play = sub.add_parser("play", parents=[common], help="Launch a game in a window")
    p_play.add_argument("name", help="Folder name under out/")
    p_play.set_defaults(func=cmd_play)

    cfg = ap.parse_args()
    cfg.func(cfg)


if __name__ == "__main__":
    main()
