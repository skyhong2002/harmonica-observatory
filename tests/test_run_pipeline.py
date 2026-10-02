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


if __name__ == "__main__":
    unittest.main()
