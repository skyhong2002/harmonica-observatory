import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import llm_backend
import social_feed_watchdog as watchdog
import tag_directory_entries as directory


class CodexBackendTests(unittest.TestCase):
    def test_codex_uses_cli_without_reading_keys(self):
        with mock.patch.dict(os.environ, {'HARMONICA_LLM_PROVIDER': 'codex'}, clear=True), mock.patch.object(watchdog.subprocess, 'run') as run:
            self.assertEqual(watchdog.read_llm_token('unused', 'unused'), ('codex-cli-session', 'codex-cli'))
            run.assert_not_called()

    def test_default_gateway_key_comes_from_env_then_gateway_keychain(self):
        with mock.patch.dict(os.environ, {'HARMONICA_LLM_API_KEY': 'gateway-key'}, clear=True):
            self.assertEqual(watchdog.read_llm_token('', ''), ('gateway-key', 'env:HARMONICA_LLM_API_KEY'))
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(llm_backend.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='kc-key\n')) as run:
            self.assertEqual(llm_backend.read_token(), ('kc-key', 'keychain:harmonica-ai-gateway/harmonica'))
            self.assertEqual(run.call_args.args[0][3], 'harmonica-ai-gateway')

    def test_defaults_are_gateway_aliases_and_allow_operator_overrides(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(llm_backend.provider(), 'gateway')
            self.assertEqual(llm_backend.base_url(), 'http://127.0.0.1:8317/v1')
            self.assertEqual(llm_backend.model_name(), 'sky-fast')
            self.assertEqual(llm_backend.review_model_name(), 'sky-quality')
            self.assertEqual(watchdog.DEFAULT_LLM_MODEL, 'sky-fast')
        with mock.patch.dict(os.environ, {'HARMONICA_LLM_PROVIDER': 'codex'}, clear=True):
            self.assertEqual(llm_backend.model_name(), '')
            self.assertEqual(llm_backend.review_model_name(), '')
        with mock.patch.dict(os.environ, {'HARMONICA_INTAKE_AI_MODEL': 'review-alias'}, clear=True):
            self.assertEqual(llm_backend.review_model_name(), 'review-alias')
        for selected, variable, fallback in (
            ('codex', 'HARMONICA_CODEX_MODEL', ''),
            ('gateway', 'HARMONICA_LLM_MODEL', 'sky-fast'),
            ('openai', 'HARMONICA_LLM_MODEL', 'sky-fast'),
        ):
            for configured, expected in (('', fallback), ('   ', fallback), ('gpt-6-astra', 'gpt-6-astra')):
                with self.subTest(provider=selected, configured=configured), mock.patch.dict(
                    os.environ, {'HARMONICA_LLM_PROVIDER': selected, variable: configured}, clear=True
                ):
                    self.assertEqual(llm_backend.model_name(), expected)

    def test_codex_command_passes_only_a_configured_model_and_reports_it(self):
        for configured, expected in (('', None), ('gpt-6-astra', 'gpt-6-astra')):
            with self.subTest(configured=configured), tempfile.TemporaryDirectory() as directory:
                environment = {'HARMONICA_STATE_DIR': directory, 'HARMONICA_LLM_PROVIDER': 'codex',
                               'HARMONICA_CODEX_MODEL': configured}
                def run(args, **kwargs):
                    self.assertEqual(args.count('--model'), 1 if expected else 0)
                    if expected:
                        self.assertEqual(args[args.index('--model') + 1], expected)
                    self.assertIn('--ignore-user-config', args)
                    self.assertIn('features.shell_tool=false', args)
                    Path(args[args.index('--output-last-message') + 1]).write_text('{"json":"{}"}')
                    return mock.Mock(returncode=0)
                with mock.patch.dict(os.environ, environment, clear=True), \
                     mock.patch.object(llm_backend, 'codex_binary', return_value=sys.executable), \
                     mock.patch.object(llm_backend.subprocess, 'run', side_effect=run):
                    result = json.loads(llm_backend.codex_chat({'model': 'gpt-6-luna', 'messages': []}))
                self.assertEqual(result['model'], expected or 'codex-cli-default')
                usage = json.loads((Path(directory) / 'codex/usage.json').read_text())
                self.assertEqual(usage['limit'], 12)
                self.assertEqual(usage['calls'], 1)

    def test_disabled_never_gets_token(self):
        with mock.patch.dict(os.environ, {'HARMONICA_LLM_PROVIDER': 'disabled', 'OPENAI_API_KEY': 'do-not-use'}, clear=True):
            self.assertEqual(watchdog.read_llm_token('', ''), ('', 'disabled'))

    def test_codex_is_bounded_and_does_not_inherit_api_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {'HARMONICA_STATE_DIR': directory, 'HARMONICA_LLM_PROVIDER': 'codex',
                           'HARMONICA_CODEX_MAX_CALLS_PER_HOUR': '1', 'APIFY_TOKEN': 'secret', 'OPENAI_API_KEY': 'secret'}
            def run(args, **kwargs):
                self.assertNotIn('APIFY_TOKEN', kwargs['env'])
                self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
                self.assertIn('read-only', args)
                self.assertIn('features.shell_tool=false', args)
                Path(args[args.index('--output-last-message') + 1]).write_text(json.dumps({'json': '{"relevant":true}'}))
                return mock.Mock(returncode=0)
            with mock.patch.dict(os.environ, environment), mock.patch.object(llm_backend, 'codex_binary', return_value=sys.executable), mock.patch.object(llm_backend.subprocess, 'run', side_effect=run):
                value = json.loads(llm_backend.codex_chat({'messages': []}))
                self.assertTrue(json.loads(value['choices'][0]['message']['content'])['relevant'])
                with self.assertRaisesRegex(RuntimeError, 'hourly call limit'):
                    llm_backend.codex_chat({'messages': []})

    def test_cli_failure_never_exposes_stderr_or_falls_back(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {'HARMONICA_STATE_DIR': directory, 'HARMONICA_LLM_PROVIDER': 'codex'}), mock.patch.object(llm_backend, 'codex_binary', return_value=sys.executable), mock.patch.object(llm_backend.subprocess, 'run', return_value=mock.Mock(returncode=1, stderr='sensitive value')):
            with self.assertRaises(RuntimeError) as caught:
                llm_backend.codex_chat({'messages': []})
            self.assertNotIn('sensitive value', str(caught.exception))

    def test_provider_is_authoritative_even_with_accidental_api_token(self):
        with mock.patch.dict(os.environ, {'HARMONICA_LLM_PROVIDER': 'codex'}), \
             mock.patch.object(llm_backend, 'codex_chat', return_value='cli-envelope') as cli, \
             mock.patch.object(watchdog.subprocess, 'run') as paid:
            self.assertEqual(watchdog.curl_json('https://api.openai.com/v1/chat/completions', 'accidental-api-key', {}, 10), 'cli-envelope')
            cli.assert_called_once()
            paid.assert_not_called()
        with mock.patch.dict(os.environ, {'HARMONICA_LLM_PROVIDER': 'openai'}), mock.patch.object(watchdog.subprocess, 'run') as paid:
            with self.assertRaises(RuntimeError):
                watchdog.curl_json('https://api.openai.com/v1/chat/completions', 'codex-cli-session', {}, 10)
            paid.assert_not_called()
        with mock.patch.dict(os.environ, {'HARMONICA_LLM_PROVIDER': 'disabled'}), mock.patch.object(watchdog.subprocess, 'run') as paid:
            with self.assertRaises(RuntimeError):
                watchdog.curl_json('https://api.openai.com/v1/chat/completions', 'real-key', {}, 10)
            paid.assert_not_called()

    def test_classifier_environment_preserves_login_location_without_collector_secrets(self):
        values = {'HOME': '/home/test', 'CODEX_HOME': '/home/test/codex', 'PATH': '/bin',
                  'HARMONICA_APIFY_API_TOKEN': 'a', 'APIFY_API_TOKEN': 'b', 'HARMONICA_META_ACCESS_TOKEN': 'c',
                  'INSTAGRAM_COOKIE': 'd', 'CODEX_ACCESS_TOKEN': 'e', 'OPENAI_BASE_URL': 'https://unexpected.example',
                  'COMMUNITY_ENCRYPTION_KEY': 'f'}
        with mock.patch.dict(os.environ, values, clear=True):
            self.assertEqual(llm_backend.inference_environment(), {k: values[k] for k in ('HOME', 'CODEX_HOME', 'PATH')})

    def test_corrupt_usage_ledger_does_not_reset_call_budget(self):
        for content in ('not-json', '[]', '{"calls": -1}', '{"calls": "unexpected"}'):
            with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {'HARMONICA_STATE_DIR': directory, 'HARMONICA_LLM_PROVIDER': 'codex'}), \
                 mock.patch.object(llm_backend, 'codex_binary', return_value=sys.executable), mock.patch.object(llm_backend.subprocess, 'run') as run:
                state = Path(directory) / 'codex'
                state.mkdir()
                (state / 'usage.json').write_text(content)
                with self.assertRaisesRegex(RuntimeError, 'usage ledger'):
                    llm_backend.codex_chat({'messages': []})
                run.assert_not_called()
                self.assertEqual((state / 'usage.json').read_text(), content)

    def test_hourly_limit_is_persisted_as_paused(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {'HARMONICA_STATE_DIR': directory, 'HARMONICA_LLM_PROVIDER': 'codex', 'HARMONICA_CODEX_MAX_CALLS_PER_HOUR': '0'}), \
             mock.patch.object(llm_backend, 'codex_binary', return_value=sys.executable), mock.patch.object(llm_backend.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'hourly call limit'):
                llm_backend.codex_chat({'messages': []})
            run.assert_not_called()
            self.assertEqual(json.loads((Path(directory) / 'codex/usage.json').read_text())['status'], 'paused')

    def test_bad_structured_result_leaves_error_status_not_running(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {'HARMONICA_STATE_DIR': directory, 'HARMONICA_LLM_PROVIDER': 'codex'}), \
             mock.patch.object(llm_backend, 'codex_binary', return_value=sys.executable):
            def run(args, **kwargs):
                self.assertIn('forced_login_method="chatgpt"', args)
                self.assertIn('features.plugins=false', args)
                self.assertIn('features.hooks=false', args)
                self.assertIn('tools.view_image=false', args)
                Path(args[args.index('--output-last-message') + 1]).write_text('[]')
                return mock.Mock(returncode=0)
            with mock.patch.object(llm_backend.subprocess, 'run', side_effect=run):
                with self.assertRaisesRegex(RuntimeError, 'no valid structured result'):
                    llm_backend.codex_chat({'messages': []})
            self.assertEqual(json.loads((Path(directory) / 'codex/usage.json').read_text())['status'], 'error')


class ClassifierProvenanceTests(unittest.TestCase):
    def test_classifiers_preserve_actual_response_model(self):
        content = {"is_relevant": True, "confidence": 0.9, "categories": ["posts-videos"],
                   "labels": ["口琴"], "sourceTags": ["口琴"], "summary": "Public artist", "reason": "Public post"}
        envelope = json.dumps({"model": "actual-provider-model", "choices": [{"message": {"content": json.dumps(content)}}]})
        with mock.patch.dict(os.environ, {"HARMONICA_LLM_PROVIDER": "codex"}), mock.patch.object(watchdog, "curl_json", return_value=envelope):
            post = watchdog.classify_with_llm({"text": "harmonica"}, [], token="codex-cli-session", base_url="unused", model="old-api-model", timeout=5)
            entry = directory.classify_entry({"name": "Public artist"}, token="codex-cli-session", base_url="unused", model="old-api-model", timeout=5)
        for result in (post, entry):
            self.assertEqual(result["llm_model"], "actual-provider-model")
            self.assertEqual(result["llm_provider"], "codex")

    def test_codex_failure_never_multiplies_calls_for_http_fallbacks(self):
        settings = {"HARMONICA_LLM_PROVIDER": "codex", "HARMONICA_LLM_RETRIES": "3",
                    "HARMONICA_LLM_FALLBACK_MODELS": "another-model,third-model"}
        with mock.patch.dict(os.environ, settings), mock.patch.object(watchdog.time, "sleep") as sleep:
            for module, function, invoke in (
                (watchdog, "classify_with_llm", lambda stats: watchdog.cached_llm_classification({"text": "new"}, [], cache={}, token="session", base_url="unused", model="old-model", timeout=1, stats=stats)),
                (directory, "classify_entry", lambda stats: directory.cached_classify({"name": "new"}, cache={}, token="session", base_url="unused", model="old-model", timeout=1, refresh=False, stats=stats)),
            ):
                stats = {}
                with mock.patch.object(module, function, side_effect=RuntimeError("hourly limit")) as classify:
                    with self.assertRaises(RuntimeError):
                        invoke(stats)
                    classify.assert_called_once()
                self.assertEqual(stats.get("fallback_uses", 0), 0)
            sleep.assert_not_called()

    def test_explicit_api_mode_keeps_retry_and_fallback(self):
        with mock.patch.dict(os.environ, {"HARMONICA_LLM_PROVIDER": "openai", "HARMONICA_LLM_RETRIES": "2", "HARMONICA_LLM_FALLBACK_MODELS": "backup"}), \
             mock.patch.object(watchdog, "classify_with_llm", side_effect=[RuntimeError("unavailable"), RuntimeError("unavailable"), {"llm_model": "backup-resolved"}]) as classify, \
             mock.patch.object(watchdog.time, "sleep"):
            stats = {}
            result = watchdog.cached_llm_classification({"text": "new"}, [], cache={}, token="key", base_url="unused", model="primary", timeout=1, stats=stats)
        self.assertEqual([call.kwargs["model"] for call in classify.call_args_list], ["primary", "primary", "backup"])
        self.assertEqual(result["llm_model"], "backup-resolved")
        self.assertEqual(stats["fallback_uses"], 1)

    def test_existing_cache_keeps_original_provenance(self):
        post = {"text": "old public post"}
        original = {"llm_model": "historic-api-model", "llm_provider": "openai"}
        cache = {"items": {watchdog.post_fingerprint(post): original}}
        with mock.patch.dict(os.environ, {"HARMONICA_LLM_PROVIDER": "codex"}), mock.patch.object(watchdog, "classify_with_llm") as classify:
            result = watchdog.cached_llm_classification(post, [], cache=cache, token="session", base_url="unused", model="codex-default", timeout=1, stats={})
        self.assertEqual(result, original)
        classify.assert_not_called()

    def test_runtime_describes_configured_provider_without_api_url_for_cli(self):
        with mock.patch.dict(os.environ, {"HARMONICA_LLM_PROVIDER": "codex", "HARMONICA_CODEX_MODEL": "chosen-cli-model"}):
            self.assertEqual(llm_backend.runtime_metadata("old-model", "https://api.openai.com/v1"),
                             {"provider": "codex", "model": "chosen-cli-model", "base_url": "codex-cli"})
        with mock.patch.dict(os.environ, {"HARMONICA_LLM_PROVIDER": "disabled"}):
            self.assertEqual(llm_backend.runtime_metadata("old-model", "unused"), {"provider": "disabled", "model": "", "base_url": ""})


class ChatRequestCompatibilityTests(unittest.TestCase):
    def test_sampling_parameters_are_omitted_by_default_for_any_model(self):
        for model in ('sky-fast', 'sky-quality', 'operator-model'):
            for effort in (None, 'low', 'none'):
                with self.subTest(model=model, effort=effort), mock.patch.dict(os.environ, {}, clear=True):
                    body = {'model': model, 'messages': [], 'temperature': 0, 'top_p': 1,
                            'logprobs': False, 'top_logprobs': 2, 'max_completion_tokens': 500,
                            'response_format': {'type': 'json_object'}}
                    if effort is not None:
                        body['reasoning_effort'] = effort
                    original = json.loads(json.dumps(body))
                    prepared = llm_backend.compatible_chat_body(body)
                    self.assertEqual(body, original)
                    self.assertEqual(prepared.get('reasoning_effort'), effort)
                    self.assertEqual(prepared['response_format'], body['response_format'])
                    self.assertEqual(prepared['max_completion_tokens'], 500)
                    for key in ('temperature', 'top_p', 'top_logprobs', 'logprobs'):
                        self.assertNotIn(key, prepared)

    def test_operator_can_declare_sampling_support(self):
        body = {'model': 'sky-fast', 'messages': [], 'temperature': 0, 'top_p': 1, 'logprobs': False}
        with mock.patch.dict(os.environ, {'HARMONICA_LLM_SEND_SAMPLING': '1'}):
            self.assertEqual(llm_backend.compatible_chat_body(body), body)


def _capture_curl(sent, stdout='{}'):
    def run(args, **kwargs):
        data_line = next(line for line in kwargs['input'].splitlines() if line.startswith('data-binary = "@'))
        url_line = next(line for line in kwargs['input'].splitlines() if line.startswith('url = '))
        sent.append((url_line[len('url = "'):-1], json.loads(Path(data_line[len('data-binary = "@'):-1]).read_text())))
        return mock.Mock(returncode=0, stdout=stdout)
    return run


class GatewayHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name)

    def env(self, **values):
        return mock.patch.dict(os.environ, {'HARMONICA_STATE_DIR': str(self.state), **values}, clear=True)

    def test_default_provider_posts_alias_to_gateway_without_sampling(self):
        body = {'model': 'sky-fast', 'messages': [{'role': 'user', 'content': 'Classify harmonica'}],
                'temperature': 0, 'reasoning_effort': 'low', 'response_format': {'type': 'json_object'}}
        sent = []
        with self.env(), mock.patch.object(llm_backend.subprocess, 'run', side_effect=_capture_curl(sent)), \
             mock.patch.object(llm_backend, 'codex_chat') as cli:
            self.assertEqual(watchdog.curl_json(watchdog.llm_endpoint(llm_backend.base_url()), 'test-key', body, 10), '{}')
            cli.assert_not_called()
        url, payload = sent[0]
        self.assertEqual(url, 'http://127.0.0.1:8317/v1/chat/completions')
        self.assertEqual(payload['model'], 'sky-fast')
        self.assertNotIn('temperature', payload)
        self.assertEqual(payload['reasoning_effort'], 'low')
        self.assertEqual(body['temperature'], 0)
        usage = json.loads((self.state / 'llm/usage.json').read_text())
        self.assertEqual((usage['calls'], usage['limit'], usage['status']), (1, 120, 'ok'))

    def test_http_calls_share_an_hourly_budget(self):
        sent = []
        with self.env(HARMONICA_LLM_MAX_CALLS_PER_HOUR='1'), \
             mock.patch.object(llm_backend.subprocess, 'run', side_effect=_capture_curl(sent)):
            llm_backend.chat({'model': 'sky-fast', 'messages': []}, token='k', timeout=5)
            with self.assertRaisesRegex(RuntimeError, 'hourly call limit'):
                llm_backend.chat({'model': 'sky-fast', 'messages': []}, token='k', timeout=5)
        self.assertEqual(len(sent), 1)
        self.assertEqual(json.loads((self.state / 'llm/usage.json').read_text())['status'], 'paused')

    def test_http_slot_is_exclusive_across_processes(self):
        import fcntl
        (self.state / 'llm').mkdir(mode=0o700)
        with (self.state / 'llm/inference.lock').open('a+') as holder:
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
            with self.env(HARMONICA_LLM_LOCK_WAIT='0'), mock.patch.object(llm_backend.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'busy'):
                    llm_backend.chat({'model': 'sky-fast', 'messages': []}, token='k', timeout=5)
                run.assert_not_called()

    def test_http_failure_is_recorded_and_not_hidden(self):
        with self.env(), mock.patch.object(llm_backend.subprocess, 'run', return_value=mock.Mock(returncode=22, stdout='denied', stderr='')):
            with self.assertRaisesRegex(RuntimeError, 'curl exited 22'):
                llm_backend.chat({'model': 'sky-fast', 'messages': []}, token='k', timeout=5)
        self.assertEqual(json.loads((self.state / 'llm/usage.json').read_text())['status'], 'error')

    def test_classifiers_record_requested_alias_and_resolved_model(self):
        content = {"is_relevant": True, "confidence": 0.9, "categories": ["posts-videos"],
                   "labels": ["口琴"], "sourceTags": ["口琴"], "summary": "Public artist", "reason": "Public post"}
        envelope = json.dumps({"model": "resolved-upstream", "choices": [{"message": {"content": json.dumps(content)}}]})
        with self.env(), mock.patch.object(llm_backend.subprocess, 'run', side_effect=_capture_curl([], envelope)):
            post = watchdog.classify_with_llm({"text": "harmonica"}, [], token="k", base_url=llm_backend.base_url(), model="sky-fast", timeout=5)
            entry = directory.classify_entry({"name": "Public artist"}, token="k", base_url=llm_backend.base_url(), model="sky-fast", timeout=5)
        for result in (post, entry):
            self.assertEqual(result["llm_model"], "resolved-upstream")
            self.assertEqual(result["llm_requested_model"], "sky-fast")
            self.assertEqual(result["llm_provider"], "gateway")


if __name__ == '__main__':
    unittest.main()
