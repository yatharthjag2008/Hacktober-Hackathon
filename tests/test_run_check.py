"""Run Check and game-project behavior, through the CLI seam (ticket 02)."""
import shutil

from support import ROOT, HarnessTest, reply, tool_call

TEMPLATE = ROOT / "template"

DESIGN = "# Box\n\nPitch: a box on screen.\n"


def build(*steps, name="box"):
    """Script: create a game, then the given steps."""
    return [tool_call("create_game", name=name, title="Box", design=DESIGN), *steps]


def run_results(r):
    return [e["result"] for e in r.events("tool_result") if e["tool"] == "run_game"]


class RunCheckFeedback(HarnessTest):
    def assert_error_fed_back(self, r, needle):
        results = run_results(r)
        self.assertTrue(results, r.stdout)
        self.assertTrue(results[0].startswith("ERRORS FOUND"), results[0])
        self.assertIn(needle, results[0])
        # Requests: first message, after create_game, after write_file, after run_game.
        fed_back = [m for m in r.requests[3]["messages"] if m["role"] == "tool"][-1]["content"]
        self.assertTrue(fed_back.startswith("ERRORS FOUND"), fed_back)
        self.assertIn(needle, fed_back)

    def test_parse_error_goes_back_to_the_model(self):
        r = self.run_harness(build(
            tool_call("write_file", path="main.gd", content="extends Node2D\n\nfunc _ready(:\n\tpass\n"),
            tool_call("run_game"),
            reply("I'll fix it."),
        ), ["make a box game"], "--no-grill")
        self.assert_error_fed_back(r, "Parse Error")

    def test_error_only_reached_by_a_key_press_goes_back_to_the_model(self):
        script = ("extends Node2D\n\nvar target: Node = null\n\n"
                  "func _unhandled_input(event: InputEvent) -> void:\n"
                  "\tif event is InputEventKey and event.pressed:\n"
                  "\t\ttarget.queue_free()\n")
        r = self.run_harness(build(
            tool_call("write_file", path="main.gd", content=script),
            tool_call("run_game"),
            reply("I'll fix it."),
        ), ["make a box game"], "--no-grill")
        self.assert_error_fed_back(r, "queue_free")


class RunCheckVerdict(HarnessTest):
    def existing_game(self, name, *, drop=()):
        """Put a copy of the game template in the out dir, minus the files in `drop`."""
        shutil.copytree(TEMPLATE, self.out_dir / name)
        for f in drop:
            (self.out_dir / name / f).unlink()

    def check_existing(self, name):
        r = self.run_harness([tool_call("run_game"), reply("ok")], ["check it"], "--no-grill", "--open", name)
        results = run_results(r)
        self.assertTrue(results, r.stdout)
        return results[0]

    def test_game_without_a_main_scene_fails(self):
        self.existing_game("nomain", drop=["main.tscn"])
        result = self.check_existing("nomain")
        self.assertTrue(result.startswith("ERRORS FOUND"), result)

    def test_game_with_no_main_scene_configured_fails(self):
        self.existing_game("unset")
        pg = self.out_dir / "unset" / "project.godot"
        pg.write_text(pg.read_text().replace('run/main_scene="res://main.tscn"\n', ""))
        result = self.check_existing("unset")
        self.assertTrue(result.startswith("ERRORS FOUND"), result)

    def test_engine_shutdown_noise_alone_passes(self):
        # Leaking a texture makes Godot print "ERROR: ... were leaked at exit." on shutdown.
        self.existing_game("leaky")
        (self.out_dir / "leaky" / "main.gd").write_text(
            "extends Node\n\nfunc _ready() -> void:\n"
            "\tvar holder := Object.new()\n"
            '\tholder.set_meta("res", ImageTexture.create_from_image(Image.create(4, 4, false, Image.FORMAT_RGBA8)))\n'
            '\tholder.set_meta("node", Node.new())\n')
        result = self.check_existing("leaky")
        self.assertTrue(result.startswith("CLEAN"), result)


class ProtectedFiles(HarnessTest):
    def test_writes_to_engine_config_and_main_scene_are_refused(self):
        r = self.run_harness(build(
            tool_call("write_file", path="project.godot", content="broken"),
            tool_call("write_file", path="res://main.tscn", content="broken"),
            tool_call("write_file", path="./main.tscn", content="broken"),
            reply("ok"),
        ), ["make a box game"], "--no-grill")
        game = self.out_dir / "box"
        results = [e["result"] for e in r.events("tool_result") if e["tool"] == "write_file"]
        self.assertEqual(len(results), 3)
        for result in results:
            self.assertTrue(result.startswith("Error"), result)
        self.assertEqual((game / "main.tscn").read_text(), (TEMPLATE / "main.tscn").read_text())
        self.assertIn('config/name="Box"', (game / "project.godot").read_text())

    def test_main_script_of_any_root_type_runs_clean(self):
        for root in ("Node2D", "Node3D", "Control"):
            with self.subTest(root=root):
                script = f'extends {root}\n\nfunc _ready() -> void:\n\tprint("ready as ", get_class())\n'
                r = self.run_harness(build(
                    tool_call("write_file", path="main.gd", content=script),
                    tool_call("run_game"),
                    reply("ok"),
                ), ["make a game"], "--no-grill", out_dir=self.out_dir / root)
                results = run_results(r)
                self.assertTrue(results, r.stdout)
                self.assertTrue(results[0].startswith("CLEAN"), results[0])
                self.assertIn(f"ready as {root}", results[0])


class PathConfinement(HarnessTest):
    def test_reading_or_writing_outside_the_game_folder_is_refused(self):
        outside = self.out_dir / "secret.txt"
        outside.write_text("secret")
        r = self.run_harness(build(
            tool_call("write_file", path="../escaped.gd", content="x"),
            tool_call("write_file", path=str(self.out_dir / "abs.gd"), content="x"),
            tool_call("read_file", path="../secret.txt"),
            tool_call("read_file", path="res://../secret.txt"),
            reply("ok"),
        ), ["make a box game"], "--no-grill")
        results = [e["result"] for e in r.events("tool_result") if e["tool"] in ("write_file", "read_file")]
        self.assertEqual(len(results), 4)
        for result in results:
            self.assertTrue(result.startswith("Error"), result)
            self.assertNotIn("secret", result.replace("secret.txt", ""))
        self.assertFalse((self.out_dir / "escaped.gd").exists())
        self.assertFalse((self.out_dir / "abs.gd").exists())
        self.assertEqual(list((self.out_dir / "box").rglob("abs.gd")), [])

    def test_absolute_path_inside_the_game_folder_is_allowed(self):
        target = self.out_dir / "box" / "player.gd"
        r = self.run_harness(build(
            tool_call("write_file", path=str(target), content="extends Node\n"),
            tool_call("read_file", path=str(target)),
            reply("ok"),
        ), ["make a box game"], "--no-grill")
        results = [e["result"] for e in r.events("tool_result")][1:]
        self.assertTrue(results[0].startswith("Wrote"), results[0])
        self.assertEqual(results[1], "extends Node\n")
        self.assertEqual(target.read_text(), "extends Node\n")


class Cleanup(HarnessTest):
    def test_check_leaves_no_injected_scripts_and_config_unchanged(self):
        r = self.run_harness(build(
            tool_call("write_file", path="main.gd", content='extends Node2D\n\nfunc _ready() -> void:\n\tprint("hi")\n'),
            reply("about to check"),
        ), ["make a box game"], "--no-grill")
        game = self.out_dir / "box"
        before_config = (game / "project.godot").read_bytes()
        before_files = sorted(p.relative_to(game) for p in game.rglob("*") if ".godot" not in p.parts)

        self.run_harness([tool_call("run_game"), reply("ok")], ["check it"], "--no-grill", "--open", "box")

        self.assertEqual((game / "project.godot").read_bytes(), before_config)
        after = sorted(p.relative_to(game) for p in game.rglob("*") if ".godot" not in p.parts)
        leftovers = [p for p in after if p.name.startswith(("input_sim", "capture"))]
        self.assertEqual(leftovers, [])
        new = [str(p) for p in set(after) - set(before_files) if not p.name.endswith(".uid")]
        self.assertEqual(new, [], "unexpected new files")
