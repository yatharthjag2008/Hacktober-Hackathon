from support import HarnessTest, reply, tool_call

DESIGN = "# Box\n\nPitch: a box on screen.\n"
MAIN_GD = 'extends Node2D\n\nfunc _ready() -> void:\n\tprint("box ready")\n'


class BuildNewGame(HarnessTest):
    def test_create_write_check_finish(self):
        r = self.run_harness([
            tool_call("create_game", name="box", title="Box", design=DESIGN),
            tool_call("write_file", path="main.gd", content=MAIN_GD),
            tool_call("run_game"),
            tool_call("finish", summary="A box. No controls."),
        ], ["make a box game"], "--no-grill")

        game = self.out_dir / "box"
        self.assertTrue((game / "project.godot").exists())
        self.assertEqual((game / "design.md").read_text(), DESIGN)
        self.assertEqual((game / "main.gd").read_text(), MAIN_GD)

        results = r.events("tool_result")
        self.assertEqual([e["tool"] for e in results], ["create_game", "write_file", "run_game", "finish"])
        self.assertTrue(results[2]["result"].startswith("CLEAN"), results[2]["result"])
        self.assertEqual(results[3]["result"], "DONE")
        self.assertEqual([e["content"] for e in r.events("user")], ["make a box game"])
        self.assertEqual(len(r.events("model")), 4)
        self.assertEqual(len(r.requests), 4)  # finish ends the turn; EOF ends the Session
        self.assertIn("FINISHED", r.stdout)
