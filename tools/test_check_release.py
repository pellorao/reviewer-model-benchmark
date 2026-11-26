"""Offline release checks; no requests reach a network."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

if __package__:
    from . import check_release as release
else:
    import check_release as release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'index.html').write_bytes(b'<html>benchmark</html>')
        self.log = self.root / 'events.jsonl'

    def test_compare_exact_content_and_missing_pages(self):
        calls = []
        def fetch(url, timeout):
            calls.append((url, timeout))
            return b'<html>benchmark</html>'
        release.compare_pages(self.root, 'https://example.org/bench/', 4, fetch)
        self.assertEqual(calls, [('https://example.org/bench/', 4)])
        with self.assertRaisesRegex(release.CheckFailure, 'content_mismatch:index.html'):
            release.compare_pages(self.root, 'https://example.org', 4, lambda *_: b'old')
        (self.root / 'index.html').unlink()
        with self.assertRaisesRegex(release.CheckFailure, 'missing_local_pages'):
            release.compare_pages(self.root, 'https://example.org', 4, fetch)

    def test_compare_checks_the_v1_page_below_the_site_root(self):
        (self.root / 'v1').mkdir()
        (self.root / 'v1' / 'index.html').write_bytes(b'<html>v1</html>')
        pages = {'https://example.org/bench/': b'<html>benchmark</html>',
                 'https://example.org/bench/v1/': b'<html>v1</html>'}
        seen = []
        def fetch(url, timeout):
            seen.append(url)
            return pages[url]
        release.compare_pages(self.root, 'https://example.org/bench/', 4, fetch)
        self.assertEqual(sorted(seen), sorted(pages))
        pages['https://example.org/bench/v1/'] = b'old'
        with self.assertRaisesRegex(release.CheckFailure, 'content_mismatch:v1/index.html'):
            release.compare_pages(self.root, 'https://example.org/bench/', 4, fetch)

    def test_compare_ignores_only_the_footer_date(self):
        def page(en_date, zh_date, body='data'):
            return ('<footer><span class="footer-updated" data-i18n="footer_updated">Updated %s</span></footer>'
                    '<script>{"en": {"footer_updated": "Updated %s"}, "zh": {"footer_updated": "更新于 %s"}}'
                    '</script><p>%s</p>' % (en_date, en_date, zh_date, body)).encode()
        (self.root / 'index.html').write_bytes(page('Nov 18, 2026', '2026 年 11 月 18 日'))
        # A build one day (or one timezone) later differs only in the date and must still match.
        release.compare_pages(self.root, 'https://example.org', 4,
                              lambda *_: page('Nov 17, 2026', '2026 年 11 月 17 日'))
        with self.assertRaisesRegex(release.CheckFailure, 'content_mismatch:index.html'):
            release.compare_pages(self.root, 'https://example.org', 4,
                                  lambda *_: page('Nov 17, 2026', '2026 年 11 月 17 日', 'other'))

    def test_fetch_sets_user_agent_and_bounds_response(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.read.return_value = b'page'
        with patch('urllib.request.build_opener', return_value=opener), patch.object(release, 'MAX_PAGE_BYTES', 4):
            self.assertEqual(release.fetch('https://example.org', 3), b'page')
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_header('User-agent'), release.USER_AGENT)
            response.read.assert_called_with(5)
            response.read.return_value = b'large'
            with self.assertRaisesRegex(release.CheckFailure, 'page_too_large'):
                release.fetch('https://example.org', 3)

    def test_retry_logs_final_success_and_safe_failure(self):
        calls, delays = [], []
        def action():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('private path must not be logged')
        self.assertTrue(release.attempts('deploy', 'a'*40, self.log, action, 3, 2, sleep=delays.append))
        rows = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual([r['attempt'] for r in rows], [1, 2])
        self.assertEqual([r['result'] for r in rows], ['failure', 'success'])
        self.assertEqual(rows[0]['failure_reason'], 'RuntimeError')
        self.assertIsNone(rows[1]['failure_reason'])
        self.assertEqual(delays, [2])
        from datetime import datetime
        self.assertIsNotNone(datetime.fromisoformat(rows[0]['ts']).tzinfo)
        self.assertEqual(set(rows[0]), {'commit', 'ts', 'stage', 'result', 'attempt', 'failure_reason'})

    def test_build_failure_never_checks_deployment(self):
        def fail():
            raise release.CheckFailure('unit_tests:exit_1')
        result = release.check_release('a'*40, self.log, fail,
                                       lambda: self.fail('deploy ran'), 2, 0)
        self.assertEqual(result, 1)
        self.assertEqual([json.loads(r)['stage'] for r in self.log.read_text().splitlines()], ['build', 'build'])

    def test_deploy_mismatch_retries_after_successful_build(self):
        bodies = iter([b'old deployment', b'<html>benchmark</html>'])
        result = release.check_release('a'*40, self.log, lambda: None,
            lambda: release.compare_pages(self.root, 'https://example.org', 4,
                                          lambda *_: next(bodies)), 2, 0)
        self.assertEqual(result, 0)
        rows = [json.loads(r) for r in self.log.read_text().splitlines()]
        self.assertEqual([(r['stage'], r['result'], r['attempt']) for r in rows],
                         [('build', 'success', 1), ('deploy', 'failure', 1), ('deploy', 'success', 2)])
        self.assertEqual(rows[1]['failure_reason'], 'content_mismatch:index.html')

    def test_main_rejects_dirty_or_wrong_checkout_before_fetch(self):
        for head, dirty in [('a'*40, ' M build.py'), ('b'*40, '')]:
            with self.subTest(head=head, dirty=dirty), patch.object(release, 'ROOT', self.root), \
                    patch.object(release.sys, 'argv', ['check_release.py', '--commit', 'a'*40,
                        '--log', str(self.log), '--base-url', 'https://example.org',
                        '--python', '/caller/python', '--attempts', '1']), \
                    patch.object(release.subprocess, 'check_output', side_effect=[head, dirty]), \
                    patch.object(release, 'fetch', side_effect=AssertionError('network requested')), \
                    patch.dict(release.os.environ):
                self.assertEqual(release.main(), 1)
        self.assertEqual([json.loads(r)['failure_reason'] for r in self.log.read_text().splitlines()],
                         ['checkout_mismatch', 'checkout_mismatch'])

    def test_main_preserves_virtualenv_interpreter_path(self):
        python = self.root / 'venv/bin/python'
        python.parent.mkdir(parents=True)
        python.symlink_to(release.sys.executable)
        with patch.object(release, 'ROOT', self.root), \
                patch.object(release.sys, 'argv', ['check_release.py', '--commit', 'a'*40,
                    '--log', str(self.log), '--base-url', 'https://example.org', '--python', str(python)]), \
                patch.object(release.subprocess, 'check_output', side_effect=['a'*40, '']), \
                patch.object(release, 'copy_inputs'), patch.object(release, 'build') as build, \
                patch.object(release, 'compare_pages'), patch.dict(release.os.environ):
            self.assertEqual(release.main(), 0)
        self.assertEqual(build.call_args.args[2], python)

    def test_build_uses_supplied_interpreter_and_stops_on_test_failure(self):
        (self.root / 'resources').mkdir()
        (self.root / 'resources/site.css').write_text('body{}')
        with patch.object(release.subprocess, 'run') as run:
            release.build(self.root, self.root / 'site', Path('/caller/python'))
        commands = [c.args[0] for c in run.call_args_list]
        self.assertEqual(commands[0], ['/caller/python', 'test_build.py'])
        self.assertEqual(commands[1][:3], ['/caller/python', 'build.py', 'benchmark-results.json'])
        self.assertTrue((self.root / 'site/resources/site.css').is_file())
        with patch.object(release.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'test')) as run:
            with self.assertRaisesRegex(release.CheckFailure, 'unit_tests:exit_1'):
                release.build(self.root, self.root / 'site', Path('/caller/python'))
        self.assertEqual(run.call_count, 1)

    def test_failing_unit_tests_print_only_test_ids(self):
        (self.root / 'resources').mkdir()
        stderr = ('ERROR: test_x (__main__.V2Tests.test_x)\nTraceback...\nSECRET body\n'
                  'FAIL: test_y (__main__.SourcesTests.test_y)\nERROR: setUpClass (__main__.V2Tests)\n')
        error = subprocess.CalledProcessError(1, 'test', stderr=stderr)
        with patch.object(release.subprocess, 'run', side_effect=error), \
                patch('sys.stderr', new_callable=io.StringIO) as out:
            with self.assertRaisesRegex(release.CheckFailure, 'unit_tests:exit_1'):
                release.build(self.root, self.root / 'site', Path('/caller/python'))
        self.assertEqual(out.getvalue().splitlines(), [
            'failed test: ERROR: test_x (__main__.V2Tests.test_x)',
            'failed test: FAIL: test_y (__main__.SourcesTests.test_y)',
            'failed test: ERROR: setUpClass (__main__.V2Tests)'])

    def test_clean_copy_carries_every_input_the_unit_tests_read(self):
        # Regression: v2 snapshots and pricing-v2.json were missing from the copy (unit_tests:exit_1).
        sources = json.loads((Path(release.ROOT) / 'sources.json').read_text(encoding='utf-8'))
        wanted = sorted({item['file'] for item in sources['snapshots']}
                        | {'pricing-v2.json', 'snapshots/v2/export.json', 'snapshots/v2/supplement.json'})
        def git_show(command, *, cwd, stdout, check):
            stdout.write(b'x')
        clean = self.root / 'clean'
        with patch.object(release.subprocess, 'check_output', return_value='\n'.join(wanted)), \
                patch.object(release.subprocess, 'run', side_effect=git_show):
            release.copy_inputs(self.root, clean, 'a' * 40)
        self.assertEqual(sorted(str(p.relative_to(clean)) for p in clean.rglob('*') if p.is_file()), wanted)

    def test_export_reads_commit_blobs_and_excludes_private_files(self):
        bundle = 'snapshots/arw/' + 'b' * 64 + '.tar.gz'
        copied = ['bench/v3/leakcheck.py', 'benchmark-results-phase4.json', 'build.py', 'resources/site.css', bundle]
        names = '\n'.join(copied + ['.env', 'private.log', 'snapshots/arw/private.tar.gz',
                                     'bench/v3/bank.py', 'bench/v3/tests/test_leakcheck.py'])
        def git_show(command, *, cwd, stdout, check):
            self.assertEqual(command[:2], ['git', 'show'])
            self.assertEqual(cwd, self.root)
            self.assertTrue(check)
            stdout.write(command[2].encode())
        clean = self.root / 'clean'
        commit = 'a' * 40
        with patch.object(release.subprocess, 'check_output', return_value=names), \
                patch.object(release.subprocess, 'run', side_effect=git_show):
            release.copy_inputs(self.root, clean, commit)
        self.assertEqual(sorted(str(p.relative_to(clean)) for p in clean.rglob('*') if p.is_file()),
                         copied)
        self.assertEqual((clean / bundle).read_text(), f'{commit}:{bundle}')


if __name__ == '__main__':
    unittest.main()
