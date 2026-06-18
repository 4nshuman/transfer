import json
import tempfile
import unittest
from pathlib import Path

from clean_copilot_surface_data import delete_targets, find_targets as find_surface_targets
from clean_run_data import clean_targets, find_targets
from load_agent import find_agent_files, load_agents
from agent_tools.cli.collect_sessions import collect_cli_sessions
from agent_tools.discovery.discover_sources import discover_sources
from agent_tools.sdk.collect_jsonl import collect_sdk_jsonl
from agent_tools.schema import FIELDS
from agent_tools.vscode.collect_chat_sessions import collect_vscode_chat_sessions, find_vscode_chat_debug_files
from agent_tools.vscode.collect_logs import collect_vscode_logs, find_vscode_log_files
from agent_tools.write_output import write_jsonl

FIXTURES = Path(__file__).parent / "fixtures"


class CopilotObservabilityTests(unittest.TestCase):
    def test_sdk_jsonl_usage_row(self):
        rows = collect_sdk_jsonl(FIXTURES / "sdk_events.jsonl")

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(set(row), set(FIELDS))
        self.assertEqual(row["source"], "sdk_jsonl")
        self.assertEqual(row["run_id"], "api-call-1")
        self.assertEqual(row["session_id"], "sdk-session-1")
        self.assertEqual(row["session_label"], "SDK fixture session")
        self.assertEqual(row["agent_name"], "review_agent")
        self.assertEqual(row["model"], "gpt-5.2-codex")
        self.assertEqual(row["input_tokens"], 120)
        self.assertEqual(row["output_tokens"], 45)
        self.assertEqual(row["total_tokens"], 165)
        self.assertEqual(row["cached_tokens"], 15)
        self.assertEqual(row["duration_ms"], 1500)
        self.assertEqual(row["workspace"], "/workspace/app")
        self.assertEqual(row["user"], "octocat")
        self.assertEqual(row["field_confidence"], "high")

        tool_calls = json.loads(row["tool_calls"])
        self.assertEqual(tool_calls[0]["id"], "tool-1")
        self.assertEqual(tool_calls[0]["name"], "shell")
        self.assertEqual(tool_calls[0]["status"], "success")

    def test_cli_session_row(self):
        rows = collect_cli_sessions(FIXTURES)

        cli_rows = [row for row in rows if row["session_id"] == "cli-session-1"]
        self.assertEqual(len(cli_rows), 1)
        row = cli_rows[0]
        self.assertEqual(set(row), set(FIELDS))
        self.assertEqual(row["source"], "cli_session")
        self.assertEqual(row["session_label"], "CLI fixture session")
        self.assertEqual(row["model"], "gpt-5.2-codex")
        self.assertEqual(row["input_tokens"], 30)
        self.assertEqual(row["output_tokens"], 12)
        self.assertEqual(row["total_tokens"], 42)
        self.assertEqual(row["cached_tokens"], 4)
        self.assertEqual(row["workspace"], "/workspace/app")
        self.assertEqual(row["user"], "octocat")
        self.assertEqual(row["field_confidence"], "medium")

        tool_calls = json.loads(row["tool_calls"])
        self.assertEqual(tool_calls[0]["id"], "cli-tool-1")
        self.assertEqual(tool_calls[0]["name"], "read_file")

    def test_cli_session_state_labels_from_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            session_dir = root / "cli-session-from-dir"
            session_dir.mkdir()
            (session_dir / "vscode.metadata.json").write_text(
                json.dumps({"customTitle": "Sidecar session title"}),
                encoding="utf-8",
            )
            (session_dir / "events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session.start",
                                "id": "event-start-id",
                                "timestamp": "2026-06-18T10:00:00Z",
                                "data": {"sessionId": "cli-session-from-dir"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "user.message",
                                "id": "event-user-id",
                                "timestamp": "2026-06-18T10:00:01Z",
                                "data": {"content": "Show me this session"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            rows = collect_cli_sessions(root)

        user_rows = [row for row in rows if row["raw_source_ref"].endswith("events.jsonl:2")]
        self.assertEqual(len(user_rows), 1)
        self.assertEqual(user_rows[0]["session_id"], "cli-session-from-dir")
        self.assertEqual(user_rows[0]["session_label"], "Sidecar session title")

    def test_discover_sources_with_explicit_paths(self):
        sdk_path = FIXTURES / "sdk_events.jsonl"
        sources = discover_sources(
            cli_state_dir=FIXTURES,
            cli_store_db=FIXTURES / "missing.db",
            sdk_jsonl=sdk_path,
        )

        by_source = {source["source"]: source for source in sources}
        self.assertTrue(by_source["cli_session_state"]["available"])
        self.assertTrue(by_source["sdk_jsonl"]["available"])
        self.assertFalse(by_source["cli_session_store"]["available"])

    def test_vscode_log_collection(self):
        rows = collect_vscode_logs(FIXTURES / "vscode_logs")

        self.assertEqual(len(rows), 2)
        error_row = rows[0]
        request_row = rows[1]

        self.assertEqual(set(error_row), set(FIELDS))
        self.assertEqual(error_row["source"], "vscode_logs")
        self.assertEqual(error_row["timestamp"], "2026-06-18T14:43:56.937")
        self.assertEqual(error_row["agent_name"], "CopilotCLISession")
        self.assertIn("unauthorized", error_row["error_status"])
        self.assertEqual(error_row["field_confidence"], "low")

        self.assertEqual(request_row["run_id"], "35eb72b9-81ab-4472-96bc-89ef0ed15ac7")
        self.assertEqual(request_row["model"], "gpt-4.1")
        self.assertEqual(request_row["error_status"], "")

    def test_vscode_log_include_info(self):
        rows = collect_vscode_logs(FIXTURES / "vscode_logs", include_info=True)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["user"], "octocat")

    def test_find_vscode_log_files(self):
        files = find_vscode_log_files(FIXTURES / "vscode_logs")

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "GitHub Copilot Chat.log")

    def test_vscode_chat_debug_collection(self):
        rows = collect_vscode_chat_sessions(FIXTURES / "vscode_workspace_storage")

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(set(row), set(FIELDS))
        self.assertEqual(row["source"], "vscode_chat_debug")
        self.assertEqual(row["run_id"], "response-1")
        self.assertEqual(row["session_id"], "debug-session-1")
        self.assertEqual(row["session_label"], "Chatbot introduction")
        self.assertEqual(row["timestamp"], "2026-06-18T09:16:08.269000Z")
        self.assertEqual(row["agent_name"], "panel/editAgent")
        self.assertEqual(row["model"], "gpt-5.3-codex")
        self.assertEqual(row["input_tokens"], 15905)
        self.assertEqual(row["output_tokens"], 206)
        self.assertEqual(row["total_tokens"], 16111)
        self.assertEqual(row["cached_tokens"], 13824)
        self.assertEqual(row["duration_ms"], 6722)
        self.assertEqual(row["workspace"], "/Users/octocat/project")
        self.assertEqual(row["field_confidence"], "high")

        tool_calls = json.loads(row["tool_calls"])
        self.assertEqual(tool_calls[0]["id"], "tool-span-1")
        self.assertEqual(tool_calls[0]["name"], "manage_todo_list")

    def test_find_vscode_chat_debug_files(self):
        files = find_vscode_chat_debug_files(FIXTURES / "vscode_workspace_storage")

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "main.jsonl")

    def test_write_jsonl_uses_normalized_fields(self):
        rows = collect_sdk_jsonl(FIXTURES / "sdk_events.jsonl")

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "observations.jsonl"
            write_jsonl(rows, output)
            written = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(written), 1)
        self.assertEqual(set(written[0]), set(FIELDS))
        self.assertEqual(written[0]["session_id"], "sdk-session-1")

    def test_load_agents_copies_agent_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_dir = root / "agents"
            target_dir = root / "copilot_agents"
            source_dir.mkdir()
            agent_file = source_dir / "example.agent.md"
            agent_file.write_text("---\nname: Example\n---\n", encoding="utf-8")

            actions = load_agents(source_dir, target_dir)

            self.assertEqual(actions[0]["status"], "created")
            self.assertEqual((target_dir / "example.agent.md").read_text(encoding="utf-8"), agent_file.read_text(encoding="utf-8"))

    def test_load_agents_reports_unchanged_and_updated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_dir = root / "agents"
            target_dir = root / "copilot_agents"
            source_dir.mkdir()
            target_dir.mkdir()
            source = source_dir / "example.agent.md"
            target = target_dir / "example.agent.md"
            source.write_text("one", encoding="utf-8")
            target.write_text("one", encoding="utf-8")

            unchanged = load_agents(source_dir, target_dir)
            self.assertEqual(unchanged[0]["status"], "unchanged")

            source.write_text("two", encoding="utf-8")
            updated = load_agents(source_dir, target_dir)
            self.assertEqual(updated[0]["status"], "updated")
            self.assertEqual(target.read_text(encoding="utf-8"), "two")

    def test_load_agents_dry_run_does_not_create_target(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_dir = root / "agents"
            target_dir = root / "copilot_agents"
            source_dir.mkdir()
            (source_dir / "example.agent.md").write_text("agent", encoding="utf-8")

            actions = load_agents(source_dir, target_dir, dry_run=True)

            self.assertEqual(actions[0]["status"], "created")
            self.assertFalse(target_dir.exists())

    def test_find_agent_files_only_returns_agent_markdown(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_dir = Path(tmp_dir)
            agent = source_dir / "example.agent.md"
            agent.write_text("agent", encoding="utf-8")
            (source_dir / "notes.md").write_text("notes", encoding="utf-8")

            self.assertEqual(find_agent_files(source_dir), [agent])

    def test_clean_run_data_only_targets_generated_outputs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            generated = root / "session_rundown.jsonl"
            generated.write_text("data", encoding="utf-8")
            observations = root / "vscode-observations.jsonl"
            observations.write_text("data", encoding="utf-8")
            keep = root / "README.md"
            keep.write_text("keep", encoding="utf-8")
            cache = root / "agent_tools" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "module.pyc").write_text("cache", encoding="utf-8")

            targets = find_targets(root)
            target_names = {path.name for path in targets}
            self.assertEqual(target_names, {"session_rundown.jsonl", "vscode-observations.jsonl", "__pycache__"})

            preview = clean_targets(targets, apply=False)
            self.assertTrue(generated.exists())
            self.assertEqual({action["status"] for action in preview}, {"would_delete"})

            deleted = clean_targets(targets, apply=True)
            self.assertFalse(generated.exists())
            self.assertFalse(observations.exists())
            self.assertFalse(cache.exists())
            self.assertTrue(keep.exists())
            self.assertEqual({action["status"] for action in deleted}, {"deleted"})

    def test_clean_copilot_surface_data_targets_raw_logs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            home = Path(tmp_dir)
            cli_session = home / ".copilot" / "session-state" / "session-1"
            cli_session.mkdir(parents=True)
            keep_agent = home / ".copilot" / "agents" / "agent.agent.md"
            keep_agent.parent.mkdir(parents=True)
            keep_agent.write_text("agent", encoding="utf-8")
            cache = home / ".copilot" / "vscode.session.metadata.cache.json"
            cache.write_text("{}", encoding="utf-8")

            code_logs = home / "Library" / "Application Support" / "Code" / "logs" / "run" / "window1"
            copilot_log_dir = code_logs / "exthost" / "GitHub.copilot-chat"
            copilot_log_dir.mkdir(parents=True)
            (copilot_log_dir / "GitHub Copilot Chat.log").write_text("log", encoding="utf-8")
            agent_log = code_logs / "output" / "agentSessionsOutput.log"
            agent_log.parent.mkdir()
            agent_log.write_text("log", encoding="utf-8")

            chat_dir = home / "Library" / "Application Support" / "Code" / "User" / "workspaceStorage" / "abc" / "GitHub.copilot-chat"
            debug_logs = chat_dir / "debug-logs"
            transcripts = chat_dir / "transcripts"
            debug_logs.mkdir(parents=True)
            transcripts.mkdir()
            keep_index = chat_dir / "workspace-chunks.db"
            keep_index.write_text("db", encoding="utf-8")

            targets = find_surface_targets(home)
            target_paths = {Path(target["path"]) for target in targets}
            self.assertIn(cli_session.resolve(), target_paths)
            self.assertIn(cache.resolve(), target_paths)
            self.assertIn(copilot_log_dir.resolve(), target_paths)
            self.assertIn(agent_log.resolve(), target_paths)
            self.assertIn(debug_logs.resolve(), target_paths)
            self.assertIn(transcripts.resolve(), target_paths)
            self.assertNotIn(keep_agent.resolve(), target_paths)
            self.assertNotIn(keep_index.resolve(), target_paths)

            preview = delete_targets(targets, home.resolve(), apply=False)
            self.assertEqual({action["status"] for action in preview}, {"would_delete"})

            delete_targets(targets, home.resolve(), apply=True)
            self.assertFalse(cli_session.exists())
            self.assertFalse(cache.exists())
            self.assertFalse(copilot_log_dir.exists())
            self.assertFalse(agent_log.exists())
            self.assertFalse(debug_logs.exists())
            self.assertFalse(transcripts.exists())
            self.assertTrue(keep_agent.exists())
            self.assertTrue(keep_index.exists())

    def test_code_files_stay_under_350_lines(self):
        root = FIXTURES.parents[1]
        code_files = [
            root / "copilot_observability.py",
            root / "clean_copilot_surface_data.py",
            root / "clean_run_data.py",
            root / "load_agent.py",
            *sorted((root / "agent_tools").rglob("*.py")),
        ]

        too_large = {}
        for path in code_files:
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if line_count > 350:
                too_large[str(path.relative_to(root))] = line_count

        self.assertEqual(too_large, {})


if __name__ == "__main__":
    unittest.main()
