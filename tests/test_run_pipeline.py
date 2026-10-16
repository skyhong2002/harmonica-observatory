import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_pipeline  # noqa: E402


class GoogleWorkspacePythonTests(unittest.TestCase):
    def test_configured_runtime_wins(self):
        with mock.patch.dict(
            os.environ, {"HARMONICA_GOOGLE_WORKSPACE_PYTHON": "/custom/python"}
        ):
            self.assertEqual(run_pipeline.google_workspace_python(), "/custom/python")

    def test_existing_stable_runtime_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "python"
            runtime.touch()
            with (
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(run_pipeline, "DEFAULT_GOOGLE_WORKSPACE_PYTHON", runtime),
            ):
                self.assertEqual(run_pipeline.google_workspace_python(), str(runtime))


class StoryBackupPipelineTests(unittest.TestCase):
    def commands(self, enabled, extra=()):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"HARMONICA_ISV_ENABLED": enabled}), mock.patch.object(run_pipeline, "load_dotenv"), mock.patch.object(run_pipeline, "run") as run, mock.patch.object(sys, "argv", ["run_pipeline", "--no-lock", "--runtime-status", str(Path(directory) / "runtime.json"), *extra]):
            self.assertEqual(run_pipeline.main(), 0)
            return [call.args[0] for call in run.call_args_list]

    def test_opt_in_backup_follows_primary_publisher_before_profiles(self):
        commands = self.commands("1")
        paths = [c[1] for c in commands]
        i = paths.index("scripts/insta_stories_viewer.py")
        self.assertEqual(paths[i - 1], "scripts/publish_story_cache.py")
        self.assertEqual(commands[i][2:], ["--scheduled", "--pipeline-lock-held"])
        self.assertIn("profile", commands[i + 1])

    def test_disabled_and_skipped_watch_or_instagram_never_run_backup(self):
        for enabled, extra in [("0", ()), ("1", ("--skip-instagram",)), ("1", ("--skip-watch",))]:
            self.assertNotIn("scripts/insta_stories_viewer.py", [c[1] for c in self.commands(enabled, extra)])


class PublicDataRebuildTests(unittest.TestCase):
    def steps(self, backfill_writes):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox.jsonl"
            candidates = root / "candidates.jsonl"
            candidates.write_text('{"source_id": "a"}\n', encoding="utf-8")
            runtime = root / "runtime.json"

            def fake_run(args, *, optional=False, step="", status_hook=None):
                if args[1] == "scripts/backfill_public_source_pages.py" and backfill_writes:
                    with candidates.open("a", encoding="utf-8") as handle:
                        handle.write('{"source_id": "b"}\n')

            with (
                mock.patch.object(run_pipeline, "load_dotenv"),
                mock.patch.object(run_pipeline, "BACKFILL_OUTPUTS", (inbox, candidates)),
                mock.patch.object(run_pipeline, "run", side_effect=fake_run) as run,
                mock.patch.object(sys, "argv", ["run_pipeline", "--no-lock", "--skip-watch", "--skip-calendar-sync", "--runtime-status", str(runtime)]),
            ):
                self.assertEqual(run_pipeline.main(), 0)
            steps = [call.kwargs.get("step") for call in run.call_args_list]
            runtime_steps = {step["name"]: step["status"] for step in json.loads(runtime.read_text())["steps"]}
            return steps, runtime_steps

    def test_second_build_is_skipped_when_backfill_adds_nothing(self):
        steps, runtime_steps = self.steps(backfill_writes=False)
        self.assertEqual(steps.count("build public data"), 1)
        self.assertNotIn("rebuild public data", steps)
        self.assertEqual(runtime_steps["rebuild public data"], "skipped")

    def test_second_build_runs_after_backfill_adds_rows(self):
        steps, _ = self.steps(backfill_writes=True)
        self.assertEqual(
            steps[steps.index("build public data"):steps.index("build public data") + 3],
            ["build public data", "backfill source pages", "rebuild public data"],
        )


class LockAndStatusTests(unittest.TestCase):
    def test_second_acquirer_is_refused_while_first_holds_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "run_pipeline.lock"
            self.assertTrue(run_pipeline.acquire_lock(lock, stale_after_minutes=240))
            self.assertFalse(run_pipeline.acquire_lock(lock, stale_after_minutes=240))
            self.assertEqual(run_pipeline.load_lock(lock)["pid"], os.getpid())
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["run_pipeline.lock"])
            run_pipeline.release_lock(lock)
            self.assertFalse(lock.exists())

    def test_fresh_empty_lock_file_is_treated_as_held_not_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "run_pipeline.lock"
            lock.touch()
            self.assertFalse(run_pipeline.acquire_lock(lock, stale_after_minutes=240))
            self.assertTrue(lock.exists())

    def test_lock_of_dead_process_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "run_pipeline.lock"
            lock.write_text('{"pid": 999999999, "started_at": "2026-01-01T00:00:00+00:00"}\n')
            self.assertTrue(run_pipeline.acquire_lock(lock, stale_after_minutes=240))
            self.assertEqual(run_pipeline.load_lock(lock)["pid"], os.getpid())

    def test_atomic_json_temp_name_is_private_to_the_process(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pipeline-runtime.json"
            run_pipeline.write_json_atomic(target, {"a": 1})
            with mock.patch.object(run_pipeline.os, "getpid", return_value=424242):
                run_pipeline.write_json_atomic(target, {"a": 2})
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["pipeline-runtime.json"])
            self.assertIn('"a": 2', target.read_text())

    def test_failed_status_is_published_before_lock_release(self):
        order = []
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime.json"
            lock = Path(directory) / "lock"

            def failing_run(*args, **kwargs):
                raise RuntimeError("boom")

            def release(path):
                order.append(("release", runtime.exists() and '"failed"' in runtime.read_text()))

            with mock.patch.object(run_pipeline, "load_dotenv"), mock.patch.object(run_pipeline, "run", failing_run), mock.patch.object(run_pipeline, "release_lock", release), mock.patch.object(sys, "argv", ["run_pipeline", "--runtime-status", str(runtime), "--lock-file", str(lock)]):
                with self.assertRaises(RuntimeError):
                    run_pipeline.main()
        self.assertEqual(order, [("release", True)])


if __name__ == "__main__":
    unittest.main()
