"""Session behavior through the CLI seam: gates, nudges, slash commands, errors, limits, compaction."""
from unittest import mock

import socket

import support
from support import DESIGN, DROP, MAIN_GD, HarnessTest, box_game, reply, tool_call


def last_message(request):
    return request["messages"][-1]


class DesignInterview(HarnessTest):
    def test_no_game_folder_until_the_proposal_is_accepted(self):
        out_dir = self.out_dir
        folders_at_request = []

        class Recording(list):
            def append(self, body):
                folders_at_request.append(sorted(p.name for p in out_dir.iterdir() if not p.name.startswith(".")))
                super().append(body)

        class SnapshotFake(support.FakeModel):
            def __init__(self, script):
                super().__init__(script)
                self.requests = Recording()

        with mock.patch.object(support, "FakeModel", SnapshotFake):
            r = self.run_harness([
                reply("Q1 - Look: 2D?\n  Recommended: 2D"),
                reply("Design Proposal:\n" + DESIGN + "\nAccept?"),
                *box_game(reply("Created.")),
            ], ["make a box game", "yes", "yes"])

        self.assertIn("run a Design Interview", r.requests[0]["messages"][0]["content"])
        self.assertEqual([last_message(q)["content"] for q in r.requests[:3]],
                         ["make a box game", "yes", "yes"])
        self.assertEqual(folders_at_request, [[], [], [], ["box"]])  # nothing exists until the proposal is accepted
        self.assertTrue((self.out_dir / "box" / "project.godot").exists())


class FinishGate(HarnessTest):
    def test_finish_needs_a_clean_check_after_the_last_game_edit_but_not_after_a_doc_edit(self):
        r = self.run_harness(box_game(
            tool_call("write_file", path="main.gd", content=MAIN_GD),
            tool_call("finish", summary="too early"),
            tool_call("run_game"),
            tool_call("write_file", path="design.md", content=DESIGN + "\nControls: none.\n"),
            tool_call("finish", summary="A box."),
        ), ["make a box game"], "--no-grill")

        results = [(e["tool"], e["result"]) for e in r.events("tool_result")]
        self.assertEqual(results[2][0], "finish")
        self.assertTrue(results[2][1].startswith("REJECTED"), results[2][1])
        self.assertTrue(results[3][1].startswith("CLEAN"), results[3][1])
        self.assertEqual(results[5], ("finish", "DONE"))
        self.assertEqual(len(r.requests), 6)
        self.assertIn("FINISHED", r.stdout)


class UncheckedEditNudge(HarnessTest):
    def test_a_text_reply_with_unchecked_edits_gets_exactly_one_nudge(self):
        r = self.run_harness(box_game(
            tool_call("write_file", path="main.gd", content=MAIN_GD),
            reply("All done!"),
            reply("Still not checked, sorry."),
            reply("Never sent."),
        ), ["make a box game"], "--no-grill")

        self.assertEqual(len(r.requests), 4)  # one nudge, then control went back to stdin (EOF)
        nudge = last_message(r.requests[3])
        self.assertEqual(nudge["role"], "user")
        self.assertIn("Run Check", nudge["content"])
        self.assertIn("Still not checked, sorry.", r.stdout)


class SlashCommands(HarnessTest):
    def make_game(self, name, *files):
        game = self.out_dir / name
        game.mkdir()
        for f in ("project.godot", *files):
            (game / f).write_text("")

    def test_games_lists_existing_games(self):
        self.make_game("pong")
        self.make_game("snake")
        r = self.run_harness([], ["/games", "/quit"])
        self.assertIn("pong\nsnake", r.stdout)
        self.assertEqual(r.requests, [])
        self.assertEqual([e["line"] for e in r.events("command")], ["/games", "/quit"])

    def test_open_switches_game_and_tells_the_model(self):
        self.make_game("pong", "main.gd", "design.md")
        r = self.run_harness([reply("ok")], ["/open pong", "/files", "make the ball faster"])
        self.assertIn("OPENED", r.stdout)
        self.assertIn("main.gd", r.stdout.split("OPENED", 1)[1])
        messages = r.requests[0]["messages"]
        self.assertIn('game "pong" is open', messages[0]["content"])
        self.assertTrue(messages[1]["content"].startswith("[I opened a game]"), messages[1])
        self.assertEqual(messages[-1]["content"], "make the ball faster")

    def test_files_lists_the_open_games_files(self):
        self.make_game("pong", "main.gd", "paddle.gd")
        r = self.run_harness([], ["/files"], "--open", "pong")
        self.assertIn("main.gd\npaddle.gd\nproject.godot", r.stdout)

    def test_grill_toggles_the_design_interview_for_the_next_request(self):
        r = self.run_harness([reply("a"), reply("b")], ["hi", "/grill off", "hello"])
        self.assertIn("run a Design Interview", r.requests[0]["messages"][0]["content"])
        self.assertIn("Design Interview is off", r.requests[1]["messages"][0]["content"])
        self.assertIn("Design Interview is off.", r.stdout)

    def test_model_switches_the_model_used_by_the_next_request(self):
        r = self.run_harness([reply("a"), reply("b")], ["hi", "/model other-model", "hello"], "--model", "first-model")
        self.assertEqual([q["model"] for q in r.requests], ["first-model", "other-model"])

    def test_new_starts_a_fresh_history(self):
        r = self.run_harness([reply("a"), reply("b")], ["remember the word banana", "/new", "hello"])
        second = r.requests[1]["messages"]
        self.assertEqual([m["role"] for m in second], ["system", "user"])
        self.assertEqual(second[1]["content"], "hello")
        self.assertNotIn("banana", str(second))

    def test_quit_ends_the_session_and_is_traced(self):
        r = self.run_harness([reply("a")], ["/quit", "never read"])
        self.assertEqual(r.requests, [])
        self.assertEqual(r.returncode, 0)
        self.assertIn("Session saved to", r.stdout)
        self.assertEqual([e["line"] for e in r.events("command")], ["/quit"])


class ModelErrors(HarnessTest):
    def test_http_500_is_reported_and_the_session_keeps_going(self):
        r = self.run_harness([500, reply("Back online.")], ["first", "second"])
        self.assertIn("MODEL ERROR", r.stdout)
        self.assertIn("scripted 500", r.stdout)
        self.assertEqual(len(r.events("model_error")), 1)
        self.assertIn("scripted 500", r.events("model_error")[0]["detail"])
        self.assertEqual(len(r.requests), 2)
        self.assertEqual(last_message(r.requests[1])["content"], "second")
        self.assertIn("Back online.", r.stdout)

    def test_a_dropped_connection_is_reported_and_the_session_keeps_going(self):
        r = self.run_harness([DROP, reply("Back online.")], ["first", "second"])
        self.assertIn("MODEL ERROR", r.stdout)
        self.assertEqual(len(r.events("model_error")), 1, r.stdout)
        self.assertEqual(len(r.requests), 2)
        self.assertEqual(last_message(r.requests[1])["content"], "second")
        self.assertIn("Back online.", r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_an_unreachable_model_is_reported_and_the_session_keeps_going(self):
        with socket.socket() as s:  # a port nothing listens on
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        r = self.run_harness([], ["first", "second"], "--base-url", f"http://127.0.0.1:{port}/v1")
        self.assertIn("MODEL ERROR", r.stdout)
        self.assertEqual([e["content"] for e in r.events("user")], ["first", "second"])
        self.assertEqual(len(r.events("model_error")), 2, r.stdout)
        self.assertEqual(r.returncode, 0)


class StepLimit(HarnessTest):
    def test_a_model_that_never_finishes_stops_at_max_steps(self):
        r = self.run_harness([tool_call("list_games")] * 10, ["make a game"], "--max-steps", "3")
        self.assertEqual(len(r.requests), 3)
        self.assertIn("STOPPED", r.stdout)
        self.assertIn("hit 3 steps", r.stdout)
        self.assertEqual(r.returncode, 0)


class HistoryCompaction(HarnessTest):
    def test_old_write_file_contents_drop_out_of_later_requests(self):
        marker = "UNIQUE_MARKER_42"
        content = MAIN_GD + f"# {marker}\n"
        r = self.run_harness(box_game(
            tool_call("write_file", path="main.gd", content=content),
            *[tool_call("list_files") for _ in range(6)],
            reply("Waiting."),
        ), ["make a box game"], "--no-grill")

        self.assertEqual((self.out_dir / "box" / "main.gd").read_text(), content)
        self.assertIn(marker, str(r.requests[2]))  # sent right after it was written
        self.assertNotIn(marker, str(r.requests[-1]))
        self.assertIn("<omitted", str(r.requests[-1]))

    def test_long_old_file_reads_are_truncated_in_later_requests(self):
        marker = "UNIQUE_MARKER_43"
        notes = "# Notes\n\n" + "filler line\n" * 200 + marker + "\n"  # well past the truncation point
        r = self.run_harness(box_game(
            tool_call("write_file", path="notes.md", content=notes),
            tool_call("read_file", path="notes.md"),
            *[tool_call("list_files") for _ in range(6)],
            reply("Waiting."),
        ), ["make a box game"], "--no-grill")

        self.assertEqual(r.results("read_file"), [notes])
        read_result = [m for m in r.requests[3]["messages"] if m["role"] == "tool"][-1]["content"]
        self.assertEqual(read_result, notes)  # sent in full right after it was read
        self.assertNotIn(marker, str(r.requests[-1]))
        self.assertIn("<omitted: read earlier", str(r.requests[-1]))
