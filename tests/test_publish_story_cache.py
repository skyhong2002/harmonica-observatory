import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import publish_story_cache as publisher
import run_pipeline


class PublishStoryCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = dt.datetime(2026, 9, 23, tzinfo=dt.timezone.utc)
        self.source = {'id': 'ig_story_test', 'username': 'test', 'enabled': True, 'provider': 'apify_stories', 'type': 'rsshub_instagram_story'}
        self.post = {'key': 'ig_story_test:123', 'source_id': self.source['id'], 'story': True,
                     'posted_at': '2026-09-22T00:00:00Z', 'story_expires_at': '2026-09-23T00:00:00Z', 'include_without_keywords': True,
                     'image_url': '/assets/feed-images/story.webp'}
        self.write('data/feeds/social_sources.json', {'sources': [self.source]})
        self.write('state/instagram_public.json', {'sources': {self.source['id']: {'posts': [self.post]}}})
        self.write('site/api/latest.json', {'updates': []})
        self.write('state/social_seen.json', {'seen': {'unrelated': 'keep', self.post['key']: 'baseline'}, 'initialized_at': 'original', 'custom': {'keep': True}})
        self.calls = []

    def write(self, path, value):
        publisher.write_json_atomic(self.root / path, value)

    def fake_runner(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual(kwargs['env']['HARMONICA_LLM_PROVIDER'], 'disabled')
        if command[1].endswith('social_feed_watchdog.py'):
            self.assertIn('--no-llm-tags', command)
            self.assertIn('--emit-initial', command)
            ids = [command[i + 1] for i, arg in enumerate(command) if arg == '--source-id']
            self.assertEqual(ids, [self.source['id']])
            seen_path = Path(command[command.index('--seen') + 1])
            seen = publisher.read_json(seen_path)
            if self.post['key'] not in seen['seen']:
                path = self.root / 'data/feeds/social_candidates.jsonl'
                with path.open('a') as stream:
                    stream.write(json.dumps(self.post) + '\n')
                seen['seen'][self.post['key']] = 'published'
            publisher.write_json_atomic(seen_path, seen)
        else:
            self.assertEqual(Path(command[1]).name, 'generate_rss_feeds.py')
            self.assertIn('--offline', command)
            rows = [json.loads(line) for line in (self.root / 'data/feeds/social_candidates.jsonl').read_text().splitlines()]
            self.write('site/api/latest.json', {'updates': rows})
        return subprocess.CompletedProcess(command, 0)

    def test_missing_candidate_previously_marked_seen_is_repaired_without_touching_other_state(self):
        result = publisher.publish_cached_stories(self.root, now=self.now, runner=self.fake_runner)
        self.assertEqual(result, {'status': 'published', 'sources': 1, 'pendingStories': 1, 'publishedStories': 1})
        seen = publisher.read_json(self.root / 'state/social_seen.json')
        self.assertEqual(seen['seen']['unrelated'], 'keep')
        self.assertEqual(seen['initialized_at'], 'original')
        self.assertEqual(seen['custom'], {'keep': True})
        self.assertEqual(seen['seen'][self.post['key']], 'published')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(publisher.publish_cached_stories(self.root, now=self.now, runner=self.fake_runner)['status'], 'unchanged')
        self.assertEqual(len(self.calls), 2)

    def test_existing_candidate_is_published_without_replaying_it(self):
        path = self.root / 'data/feeds/social_candidates.jsonl'
        path.write_text(json.dumps(self.post) + '\n')
        publisher.publish_cached_stories(self.root, now=self.now, runner=self.fake_runner)
        self.assertEqual(len(path.read_text().splitlines()), 1)
        self.assertEqual(publisher.read_json(self.root / 'state/social_seen.json')['seen'][self.post['key']], 'baseline')

    def test_no_pending_stories_runs_no_commands_and_ignores_disabled_other_providers_expired_and_naive_dates(self):
        self.write('data/feeds/social_sources.json', {'sources': [self.source,
            {**self.source, 'id': 'disabled', 'enabled': False}, {**self.source, 'id': 'profile', 'provider': 'instagram_public'}]})
        self.write('state/instagram_public.json', {'sources': {
            self.source['id']: {'posts': [{**self.post, 'posted_at': '2000-01-01T00:00:00Z'}, {**self.post, 'key': 'naive', 'posted_at': '2099-01-01'}]},
            'disabled': {'posts': [self.post]}, 'profile': {'posts': [self.post]}}})
        result = publisher.publish_cached_stories(self.root, now=self.now, runner=self.fake_runner)
        self.assertEqual(result['status'], 'unchanged')
        self.assertEqual(self.calls, [])

    def test_watchdog_failure_cannot_replace_the_original_seen_state_or_run_rss(self):
        before = (self.root / 'state/social_seen.json').read_text()
        runner = mock.Mock(side_effect=subprocess.CalledProcessError(1, ['watchdog']))
        with self.assertRaises(subprocess.CalledProcessError):
            publisher.publish_cached_stories(self.root, now=self.now, runner=runner)
        self.assertEqual((self.root / 'state/social_seen.json').read_text(), before)
        self.assertEqual(runner.call_count, 1)

    def test_standalone_uses_native_lock_and_pipeline_mode_reuses_existing_lock(self):
        with mock.patch.object(publisher, 'PROJECT_ROOT', self.root), mock.patch.object(publisher, 'acquire_lock', return_value=False) as acquire, mock.patch.object(publisher, 'publish_cached_stories') as publish:
            self.assertEqual(publisher.main([]), 0)
            acquire.assert_called_once(); publish.assert_not_called()
        with mock.patch.object(publisher, 'PROJECT_ROOT', self.root), mock.patch.object(publisher, 'acquire_lock') as acquire, mock.patch.object(publisher, 'release_lock') as release, mock.patch.object(publisher, 'publish_cached_stories', return_value={'status': 'unchanged'}):
            self.assertEqual(publisher.main(['--pipeline-lock-held']), 0)
            acquire.assert_not_called(); release.assert_not_called()

    def test_pipeline_publishes_before_a_later_collector_failure_under_the_same_lock(self):
        calls = []
        lock = self.root / 'state/run_pipeline.lock'
        def run(command, **kwargs):
            name = Path(command[1]).name; calls.append(name)
            self.assertTrue(lock.exists())
            if name == 'publish_story_cache.py':
                self.assertIn('--pipeline-lock-held', command)
                publisher.publish_cached_stories(self.root, now=self.now, runner=self.fake_runner)
            if name == 'youtube_ytdlp_fetcher.py':
                self.assertEqual(publisher.read_json(self.root / 'site/api/latest.json')['updates'][0]['key'], self.post['key'])
                raise subprocess.CalledProcessError(1, command)
        argv = ['run_pipeline.py', '--skip-source-build', '--skip-calendar-sync', '--lock-file', str(lock), '--runtime-status', str(self.root / 'runtime.json')]
        with mock.patch.object(run_pipeline, 'PROJECT_ROOT', self.root), mock.patch.object(run_pipeline, 'run', side_effect=run), mock.patch.object(sys, 'argv', argv):
            with self.assertRaises(subprocess.CalledProcessError):
                run_pipeline.main()
        self.assertEqual(calls, ['instagram_public_fetcher.py', 'publish_story_cache.py', 'instagram_public_fetcher.py', 'youtube_ytdlp_fetcher.py'])
        self.assertFalse(lock.exists())
        self.assertEqual(publisher.read_json(self.root / 'site/api/latest.json')['updates'][0]['key'], self.post['key'])

    def test_corrupt_existing_seen_state_fails_closed_before_any_command_or_overwrite(self):
        for invalid in ['{broken', '{"seen": []}', '{"seen": null}', '[]']:
            with self.subTest(invalid=invalid):
                path = self.root / 'state/social_seen.json'
                path.write_text(invalid)
                runner = mock.Mock()
                with self.assertRaises(ValueError):
                    publisher.publish_cached_stories(self.root, now=self.now, runner=runner)
                runner.assert_not_called()
                self.assertEqual(path.read_text(), invalid)

    def test_profile_fetch_failure_happens_after_stories_are_already_public(self):
        phases = []
        lock = self.root / 'state/run_pipeline.lock'
        def run(command, **kwargs):
            name = Path(command[1]).name
            if name == 'instagram_public_fetcher.py':
                phase = command[command.index('--kind') + 1]
                phases.append(phase)
                self.assertIn('--pipeline-lock-held', command)
                if phase == 'profile':
                    self.assertEqual(publisher.read_json(self.root / 'site/api/latest.json')['updates'][0]['key'], self.post['key'])
                    raise subprocess.CalledProcessError(1, command)
            elif name == 'publish_story_cache.py':
                phases.append('publish')
                publisher.publish_cached_stories(self.root, now=self.now, runner=self.fake_runner)
        argv = ['run_pipeline.py', '--skip-source-build', '--skip-calendar-sync', '--lock-file', str(lock), '--runtime-status', str(self.root / 'runtime.json')]
        with mock.patch.object(run_pipeline, 'PROJECT_ROOT', self.root), mock.patch.object(run_pipeline, 'run', side_effect=run), mock.patch.object(sys, 'argv', argv):
            with self.assertRaises(subprocess.CalledProcessError):
                run_pipeline.main()
        self.assertEqual(phases, ['story', 'publish', 'profile'])
        self.assertFalse(lock.exists())


if __name__ == '__main__':
    unittest.main()
