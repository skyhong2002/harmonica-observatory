import plistlib
import shlex
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLIST_PATH = ROOT / "deploy" / "tw.observe.harmonica.social-fast.plist"


class SocialFastPlistTests(unittest.TestCase):
    def test_social_refresh_updates_local_snapshot(self):
        with PLIST_PATH.open("rb") as handle:
            plist = plistlib.load(handle)

        arguments = plist["ProgramArguments"]
        self.assertEqual(arguments[:2], ["/bin/zsh", "-lc"])
        self.assertIn("scripts/run_pipeline.py", arguments[2])
        self.assertNotIn("--publish-pages", arguments[2])
        self.assertIn(".venv/bin/python", arguments[2])
        self.assertEqual(plist["StartInterval"], 1800)

    def test_uses_pipeline_native_lock_without_an_unrecoverable_outer_directory(self):
        plist = plistlib.loads(PLIST_PATH.read_bytes())
        command = plist['ProgramArguments'][2]
        arguments = shlex.split(command)
        self.assertNotIn('social-fast.lock', command)
        self.assertNotIn('mkdir', arguments)
        self.assertNotIn('--no-lock', arguments)
        self.assertIn('exec', arguments)
        self.assertEqual(arguments[arguments.index('scripts/run_pipeline.py') + 1:],
                         ['--skip-youtube', '--skip-facebook', '--skip-llm-tags', '--max-post-age-days', '2'])

    def test_loading_scheduler_does_not_trigger_an_extra_paid_crawl(self):
        plist = plistlib.loads(PLIST_PATH.read_bytes())
        self.assertIs(plist['RunAtLoad'], False)
        self.assertFalse(plist.get('KeepAlive'))
        self.assertEqual(plist['EnvironmentVariables']['HARMONICA_LLM_PROVIDER'], 'gateway')
        self.assertEqual(plist['StartInterval'], 1800)

    def test_inference_jobs_use_gateway_aliases_not_concrete_models(self):
        for name in ("pipeline", "social-fast", "submission-intake"):
            with self.subTest(job=name):
                plist = plistlib.loads((ROOT / "deploy" / f"tw.observe.harmonica.{name}.plist").read_bytes())
                environment = plist["EnvironmentVariables"]
                self.assertEqual(environment["HARMONICA_LLM_PROVIDER"], "gateway")
                for key in ("HARMONICA_CODEX_MODEL", "HARMONICA_LLM_MODEL", "HARMONICA_INTAKE_AI_MODEL"):
                    self.assertNotIn(key, environment)


if __name__ == "__main__":
    unittest.main()
