#!/usr/bin/env python3
"""OpenGames Harness: a conversational CLI that designs, builds and iterates on Godot games with any model.

Usage:
    python3 harness.py                          # start a conversation
    python3 harness.py "a 3D marble maze"       # start with a first message
    python3 harness.py --open pong              # continue working on a game in out/pong
    python3 harness.py --out-dir /tmp/games     # keep games and traces somewhere else

No dependencies beyond the Python standard library.
"""
import argparse
import base64
import http.client
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
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "template"
DEFAULT_OUT = ROOT / "out"
DEFAULT_GODOT = ROOT / "tools" / "godot"
INPUT_SIM = ROOT / "input_sim.gd"
CAPTURE = ROOT / "capture.gd"
MAX_TOOL_OUTPUT = 4000
KEEP_RECENT = 6  # messages at the end of the history that are never compacted

# --- terminal -------------------------------------------------------------

C = {"dim": "\033[2m", "bold": "\033[1m", "cyan": "\033[36m", "yellow": "\033[33m",
     "green": "\033[32m", "red": "\033[31m", "magenta": "\033[35m", "blue": "\033[34m",
     "reset": "\033[0m"}


def say(color, label, text=""):
    print(f"{C[color]}{C['bold']}{label}{C['reset']} {text}", flush=True)


def ask(prompt):
    try:
        return input(f"\n{C['bold']}{prompt}{C['reset']}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "/quit"


class Trace:
    """Appends every event of a Session to <out>/.sessions/<timestamp>.jsonl."""

    def __init__(self, out):
        sessions = out / ".sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        self.file = sessions / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".jsonl")

    def log(self, event, **data):
        with self.file.open("a") as f:
            f.write(json.dumps({"t": round(time.time(), 3), "event": event, **data}) + "\n")


# --- prompt ---------------------------------------------------------------

SYSTEM_PROMPT = """You are OpenGames, a game designer and developer agent in a terminal conversation with a
Player-Creator. Together you make small, complete games in Godot 4 (GDScript): any genre, 2D or 3D.
The Player-Creator may not know Godot. Talk plainly and briefly.

When you reply without calling a tool, your reply is shown to the Player-Creator and you wait for their answer.

## New games
{grill_rule}

Design Interview format: ask 2-4 numbered questions per round about decisions you can't sensibly
assume (genre and 2D/3D, core loop, controls, win/lose, scoring, look). Give a recommended answer
for each, worded so "yes" accepts it:

Q1 - <title>: <question>
  Recommended: <answer>

A Design Proposal is Markdown with: Title, Pitch (one sentence), 2D or 3D, Core Loop, Controls,
Win/Lose, Scoring and HUD, Look, Out of Scope. Keep scope buildable in an hour: no imported assets
(visuals are simple shapes), no audio, no networking.

Once the design is settled, call create_game with a short name and the design, then build it.

## Existing games
Use list_games / open_game when the Player-Creator refers to an existing game. Anything they ask
for after a game exists is a Change Request: a new feature, a change, or a bug they found while
playing. Read the files you need before editing them.

## How to build or change a game
1. Write files with write_file (always COMPLETE contents). Split into several .gd files if it helps.
2. Call run_game to do a Run Check. It launches the game headless for ~30s of game time while
   simulating random key presses, mouse clicks and mouse movement, and returns errors.
3. If there are errors, read them carefully, fix the files, and run_game again.
4. After a CLEAN Run Check you may receive screenshots of the running game (a Visual Check).
   Compare them with design.md: a black or empty screen, a camera that misses the action,
   unreadable HUD or missing elements are bugs. Fix them and run_game again.
5. Keep design.md current: when features or controls change, update it.
6. Call finish with a short summary of what you did and the controls. Do not stop before finish
   while the game has unchecked edits.

A new game's project contains project.godot (main scene res://main.tscn, window 1152x648,
Compatibility renderer), main.tscn (root node Main with script res://main.gd), main.gd (placeholder;
replace it) and design.md. project.godot and main.tscn are managed by the harness and can't be
edited: main.gd may extend Node, Node2D, Node3D or Control and the root node type follows it
automatically. Put all game code in main.gd and other .gd files you create.

## Rules for reliable games
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

Current state: {state}
"""

GRILL_ON = ("Before building a new game, run a Design Interview (1-3 rounds), then show a Design Proposal "
            "and ask the Player-Creator to accept it. Only call create_game after they accept. If they say "
            "\"just build it\" or similar, skip straight to create_game using your recommendations.")
GRILL_OFF = ("Design Interview is off: turn the Player-Creator's description into a Design Proposal yourself, "
             "using sensible defaults, and call create_game straight away.")

TOOLS = [
    {"type": "function", "function": {
        "name": "create_game",
        "description": "Create a new game project from the template and open it. Its design.md is set to `design`.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Short folder name, e.g. marble-maze"},
            "title": {"type": "string", "description": "Display title of the game"},
            "design": {"type": "string", "description": "The accepted Design Proposal (Markdown)"}},
            "required": ["name", "title", "design"]}}},
    {"type": "function", "function": {
        "name": "open_game",
        "description": "Open an existing game so you can change it. Returns its files and design.md.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "list_games",
        "description": "List the games that exist.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a file in the open game with complete contents.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path relative to the project root, e.g. main.gd"},
            "content": {"type": "string", "description": "Full file contents"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file from the open game.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List all files in the open game.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "run_game",
        "description": "Run Check: launch the open game headless for ~30s of game time while random keys, "
                       "clicks and mouse movement are simulated, and return errors and output.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "play_game",
        "description": "Launch the open game in a window for the Player-Creator to play.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Declare the current build or Change Request done. Only allowed after a CLEAN "
                       "Run Check with no later edits.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string", "description": "What you did, and the game's controls"}},
            "required": ["summary"]}}},
]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}

# --- projects -------------------------------------------------------------

ERROR_PATTERN = re.compile(r"^\s*(SCRIPT ERROR|USER SCRIPT ERROR|ERROR|USER ERROR|Error):")
# Files the harness owns: editing them is how models corrupt projects.
PROTECTED = {"project.godot", "main.tscn"}
# Engine shutdown noise, not caused by the game's logic.
NOISE_PATTERN = re.compile(r"leaked at exit|in use at exit|still in use at exit|Pages in use exist at exit")


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "game"


def list_game_names(out):
    return sorted(p.parent.name for p in out.glob("*/project.godot")) if out.exists() else []


class Project:
    def __init__(self, path: Path, cfg):
        self.path = path.resolve()
        self.name = path.name
        self.cfg = cfg
        self.dirty = False                # edits that have not passed a Run Check yet
        self.clean_since_last_edit = False
        self.pending_shots: list[Path] = []

    def _inside(self, p: Path) -> bool:
        return p == self.path or self.path in p.parents

    def _resolve(self, rel: str) -> Path:
        """Map a model-given path into the game folder. "/x" means the game's x, like "res://x",
        unless it already points inside the game folder. ".." may never leave the folder."""
        p = Path(rel.removeprefix("res://"))
        if p.is_absolute() and not self._inside(p.resolve()):
            p = p.relative_to(p.anchor)
        p = (self.path / p).resolve()
        if not self._inside(p):
            raise ValueError(f"path escapes project: {rel}")
        return p

    def write_file(self, path, content):
        p = self._resolve(path)
        if str(p.relative_to(self.path)) in PROTECTED:
            return (f"Error: {path} is managed by the harness and can't be edited. The root node in main.tscn "
                    "automatically matches whatever main.gd extends (Node, Node2D, Node3D, Control...).")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        if p.suffix != ".md":  # docs can't break the game, so they don't need a new Run Check
            self.dirty, self.clean_since_last_edit = True, False
        return f"Wrote {path} ({len(content.splitlines())} lines)."

    def read_file(self, path):
        return self._resolve(path).read_text()

    def list_files(self):
        files = [str(f.relative_to(self.path)) for f in sorted(self.path.rglob("*"))
                 if f.is_file() and not f.name.endswith(".uid")
                 and not any(part.startswith(".") for part in f.relative_to(self.path).parts)]
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
            r = subprocess.run([self.cfg.godot, "--path", str(self.path), *args],
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

    def sync_root(self):
        """Make main.tscn's root node type match the class main.gd extends."""
        script, scene = self.path / "main.gd", self.path / "main.tscn"
        m = re.search(r"^extends\s+([A-Za-z0-9_]+)", script.read_text(), re.M) if script.exists() else None
        if m and scene.exists():
            scene.write_text(re.sub(r'(\[node name="Main" type=")[^"]+', rf"\g<1>{m.group(1)}", scene.read_text()))

    def run_game(self):
        self.sync_root()
        # Import first so scripts and scenes are registered, then run a fixed number of
        # 60 fps frames (fast in headless, but simulated time advances normally).
        subprocess.run([self.cfg.godot, "--headless", "--path", str(self.path), "--import"],
                       capture_output=True, text=True, timeout=120)
        out = self._launch([INPUT_SIM], ["--headless", "--fixed-fps", "60", "--quit-after", str(self.cfg.frames)], 90)
        # Runtime errors in _process repeat every frame; keep each distinct line once.
        lines = list(dict.fromkeys(l for l in out.splitlines()
                                   if l.strip() and not l.startswith("Godot Engine v")
                                   and not NOISE_PATTERN.search(l)))
        errors = [l for l in lines if ERROR_PATTERN.search(l)]
        if errors or "TIMEOUT" in out:
            self.clean_since_last_edit = False
            return "ERRORS FOUND:\n" + "\n".join(lines)
        self.dirty, self.clean_since_last_edit = False, True
        if self.cfg.visual:
            self.pending_shots = self.capture()
        return "CLEAN: game ran without errors.\nOutput:\n" + "\n".join(lines[-30:])

    def capture(self):
        """Visual Check: render the game for real and screenshot it at fixed frames."""
        shot_dir = Path(tempfile.mkdtemp(prefix="opengames-shots-"))
        self._launch([INPUT_SIM, CAPTURE], ["--fixed-fps", "60"], 60, env={"HARNESS_SHOT_DIR": str(shot_dir)})
        return sorted(shot_dir.glob("shot_*.png"))

    def play_game(self):
        self.sync_root()
        subprocess.Popen([self.cfg.godot, "--path", str(self.path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Launched the game in a window."

    def finish(self, summary):
        if not self.clean_since_last_edit:
            return "REJECTED: run_game must report CLEAN after your last edit before you can finish."
        return "DONE"


def create_project(cfg, name, title, design):
    game_dir = cfg.out / slugify(name)
    if game_dir.exists():
        raise ValueError(f"a game named {game_dir.name} already exists; pick another name or open_game it")
    shutil.copytree(TEMPLATE, game_dir)
    (game_dir / "design.md").write_text(design.strip() + "\n")
    pg = game_dir / "project.godot"
    pg.write_text(pg.read_text().replace('config/name="Generated Game"',
                                         f'config/name="{title[:60].replace(chr(34), "")}"'))
    return Project(game_dir, cfg)


# --- model client ---------------------------------------------------------

def chat(cfg, messages, tools):
    payload = {"model": cfg.model, "messages": messages, "tools": tools}
    req = urllib.request.Request(cfg.base_url.rstrip("/") + "/chat/completions",
                                 data=json.dumps(payload).encode(), headers={
                                     "Content-Type": "application/json",
                                     "Authorization": f"Bearer {cfg.api_key}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["choices"][0]["message"]


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


# --- session --------------------------------------------------------------

HELP = """Just talk: describe a new game, ask for changes, or report bugs you found while playing.
  /games          list games            /open <name>   switch to a game
  /play           play the open game    /files         list the open game's files
  /grill on|off   Design Interview      /model <name>  switch model
  /new            fresh conversation    /help          this help
  /quit           exit"""


class Session:
    """One continuous conversation between the Player-Creator and the agent."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.project: Project | None = None
        self.trace = Trace(cfg.out)
        self.messages = [{"role": "system", "content": ""}]
        self.trace.log("session", model=cfg.model, base_url=cfg.base_url)

    # -- state shown to the model --

    def _system(self):
        state = (f'game "{self.project.name}" is open.' if self.project
                 else "no game is open. Existing games: " + (", ".join(list_game_names(self.cfg.out)) or "none") + ".")
        return SYSTEM_PROMPT.format(grill_rule=GRILL_ON if self.cfg.grill else GRILL_OFF, state=state)

    def prompt(self):
        return f"{self.project.name} › " if self.project else "› "

    # -- tools that manage games; the rest go to the open Project --

    def create_game(self, name, title, design):
        self.project = create_project(self.cfg, name, title, design)
        say("magenta", "CREATED", str(self.project.path))
        return f"Created and opened {self.project.name}. Now build it."

    def open_game(self, name):
        path = self.cfg.out / slugify(name)
        if not (path / "project.godot").exists():
            return f"Error: no game named {name}. Games: {', '.join(list_game_names(self.cfg.out)) or 'none'}"
        self.project = Project(path, self.cfg)
        design = path / "design.md"
        say("magenta", "OPENED", str(self.project.path))
        return (f"Opened {self.project.name}.\nFiles:\n{self.project.list_files()}\n\ndesign.md:\n"
                + (design.read_text() if design.exists() else "(none yet; write one)"))

    def list_games(self):
        return "\n".join(list_game_names(self.cfg.out)) or "No games yet."

    def call_tool(self, fn, fargs):
        if fn in ("create_game", "open_game", "list_games"):
            return getattr(self, fn)(**fargs)
        if self.project is None:
            return "Error: no game is open. Use create_game or open_game first."
        return getattr(self.project, fn)(**fargs)

    # -- the agent turn --

    def turn(self, user_text):
        """Handle one Player-Creator message: run the agent until it replies or finishes."""
        self.trace.log("user", content=user_text)
        self.messages.append({"role": "user", "content": user_text})
        nudged = False
        for step in range(1, self.cfg.max_steps + 1):
            self.messages[0]["content"] = self._system()
            compact(self.messages)
            print(f"{C['dim']}  thinking…{C['reset']}", end="\r", flush=True)
            try:
                msg = chat(self.cfg, self.messages, TOOLS)
            except (OSError, http.client.HTTPException) as e:  # HTTP errors, timeouts, refused or dropped connections
                detail = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else str(e)
                say("red", "MODEL ERROR", detail)
                self.trace.log("model_error", detail=detail)
                return
            print(" " * 20, end="\r")
            self.messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
            self.trace.log("model", content=msg.get("content"), tool_calls=msg.get("tool_calls"))
            calls = msg.get("tool_calls") or []
            if not calls:
                if self.project and self.project.dirty and not nudged:
                    # The model stopped mid-build; push it to check and finish before handing back.
                    nudged = True
                    if msg.get("content"):
                        say("cyan", "MODEL", msg["content"].strip())
                    self.messages.append({"role": "user", "content": "You have edits that have not passed a "
                                          "Run Check. Call run_game, fix any errors, then finish."})
                    continue
                print(f"\n{(msg.get('content') or '').strip()}")
                return
            if msg.get("content"):
                say("cyan", "MODEL", msg["content"].strip())
            for call in calls:
                if self._run_call(call):
                    return
            if self.project and self.project.pending_shots:
                self._visual_check()
        say("red", "STOPPED", f"hit {self.cfg.max_steps} steps; say \"continue\" to keep going")

    def _run_call(self, call):
        """Execute one tool call. Returns True when the model finished its task."""
        fn = call["function"]["name"]
        try:
            fargs = json.loads(call["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            fargs = None
        shown = {k: (f"<{len(v.splitlines())} lines>" if k in ("content", "design") else v)
                 for k, v in (fargs or {}).items()}
        say("yellow", "TOOL", f"{fn}({json.dumps(shown)})")
        if fargs is None:
            result = "Error: arguments were not valid JSON."
        elif fn not in TOOL_NAMES:
            result = f"Error: unknown tool {fn}."
        else:
            try:
                result = self.call_tool(fn, fargs)
            except TypeError as e:
                result = f"Error: bad arguments for {fn}: {e}. Check the tool's required parameters."
            except Exception as e:
                result = f"Error: {e}"
        self.trace.log("tool_result", tool=fn, result=result)
        if fn == "run_game":
            say("green" if result.startswith("CLEAN") else "red", "RUN CHECK", result.splitlines()[0])
            for l in result.splitlines()[1:12]:
                print(f"  {C['dim']}{l}{C['reset']}")
        elif result.startswith(("Error", "REJECTED")):
            say("red", "RESULT", result)
        self.messages.append({"role": "tool", "tool_call_id": call.get("id", fn),
                              "content": result[:MAX_TOOL_OUTPUT]})
        if fn == "finish" and result == "DONE":
            say("green", "FINISHED", fargs["summary"])
            print(f"{C['dim']}Type /play to play it, or ask for changes.{C['reset']}")
            return True
        return False

    def _visual_check(self):
        shots, self.project.pending_shots = self.project.pending_shots, []
        say("blue", "VISUAL CHECK", f"sending {len(shots)} screenshot(s) to the model")
        self.trace.log("visual_check", screenshots=[str(s) for s in shots])
        self.messages.append({"role": "user", "content": [
            {"type": "text", "text": "Visual Check: screenshots of the running game after 1s and 4s "
             "with simulated input. Compare them with design.md. If something looks wrong, fix it and "
             "run_game again. If it looks right, call finish."},
            *({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(s.read_bytes()).decode()}} for s in shots)]})

    # -- slash commands --

    def command(self, line):
        """Handle a /command. Returns False when the session should end."""
        self.trace.log("command", line=line)
        cmd, _, arg = line.partition(" ")
        arg = arg.strip()
        if cmd == "/quit":
            return False
        elif cmd == "/help":
            print(HELP)
        elif cmd == "/games":
            print(self.list_games())
        elif cmd == "/open":
            if not arg:
                print("Usage: /open <name>")
            else:
                result = self.open_game(arg)
                if result.startswith("Error"):
                    say("red", "ERROR", result)
                else:
                    # Tell the model what happened so the conversation stays coherent.
                    self.messages.append({"role": "user", "content": f"[I opened a game]\n{result}"})
                    self.messages.append({"role": "assistant", "content": f"{self.project.name} is open."})
        elif cmd in ("/play", "/files"):
            if not self.project:
                print("No game is open. Use /open <name> or describe a new game.")
            elif cmd == "/play":
                self.project.play_game()
            else:
                print(self.project.list_files())
        elif cmd == "/grill":
            if arg in ("on", "off"):
                self.cfg.grill = arg == "on"
            print(f"Design Interview is {'on' if self.cfg.grill else 'off'}.")
        elif cmd == "/model":
            if arg:
                self.cfg.model = arg
            print(f"Model: {self.cfg.model}")
        elif cmd == "/new":
            self.project = None
            self.messages = [{"role": "system", "content": ""}]
            print("Started a fresh conversation.")
        else:
            print(f"Unknown command {cmd}. /help lists commands.")
        return True

    def run(self, first_message=None):
        print(f"{C['bold']}{C['magenta']}OpenGames{C['reset']}  "
              f"{C['dim']}model {self.cfg.model} · Design Interview {'on' if self.cfg.grill else 'off'}"
              f" · {len(list_game_names(self.cfg.out))} game(s) in {self.cfg.out}{C['reset']}")
        print(f"{C['dim']}{HELP}{C['reset']}")
        if not first_message:
            print("\nWhat game do you want to make?")
        while True:
            line = first_message or ask(self.prompt())
            first_message = None
            if not line:
                continue
            if line.startswith("/"):
                if not self.command(line):
                    print(f"{C['dim']}Session saved to {self.trace.file}{C['reset']}")
                    return
                continue
            self.turn(line)


def main():
    ap = argparse.ArgumentParser(description="OpenGames: a conversational CLI that designs, builds and "
                                             "iterates on Godot games with any model.")
    ap.add_argument("message", nargs="?", help="Optional first message, e.g. \"a 3D marble maze\"")
    ap.add_argument("--open", metavar="NAME", help="Start with an existing game from the output directory open")
    ap.add_argument("--model", default=os.environ.get("HARNESS_MODEL", "gemma4:31b-cloud"))
    ap.add_argument("--base-url", default=os.environ.get("HARNESS_BASE_URL", "http://localhost:11434/v1"))
    ap.add_argument("--api-key", default=os.environ.get("HARNESS_API_KEY", "ollama"))
    ap.add_argument("--godot", default=os.environ.get("GODOT", str(DEFAULT_GODOT)))
    ap.add_argument("--max-steps", type=int, default=40, help="Max agent steps per message")
    ap.add_argument("--frames", type=int, default=1800, help="Frames (at 60 fps) to run during a Run Check")
    ap.add_argument("--no-grill", dest="grill", action="store_false", help="Skip the Design Interview")
    ap.add_argument("--no-visual", dest="visual", action="store_false",
                    help="Skip the Visual Check (needs a display and a vision-capable model)")
    ap.add_argument("--out-dir", dest="out", type=Path, default=os.environ.get("HARNESS_OUT_DIR", DEFAULT_OUT),
                    help="Where games and Session traces are written (default: out/)")
    cfg = ap.parse_args()
    cfg.out = cfg.out.resolve()

    session = Session(cfg)
    if cfg.open:
        session.command(f"/open {cfg.open}")
    session.run(cfg.message)


if __name__ == "__main__":
    main()
