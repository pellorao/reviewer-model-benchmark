#!/usr/bin/env python3
"""Build and verify all deployed HTML by exact SHA-256 (footer build date ignored); no credentials or APIs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import Request
from urllib.parse import urlsplit
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
MAX_PAGE_BYTES = 10_000_000


# Cloudflare Pages answers 403 to urllib's default Python-urllib agent.
USER_AGENT = 'check-release/1'


class CheckFailure(ValueError):
    """A fixed, public reason safe to include in telemetry."""


def fetch(url, timeout):
    # Do not consult local proxy credentials; caller supplies only a public URL.
    from urllib.request import build_opener, ProxyHandler
    with build_opener(ProxyHandler({})).open(
            Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': USER_AGENT}), timeout=timeout) as response:
        body = response.read(MAX_PAGE_BYTES + 1)
        if len(body) > MAX_PAGE_BYTES:
            raise CheckFailure('page_too_large')
        return body


# build.py stamps the footer with date.today() (English and Chinese, in the markup and in the
# language table), so a build on another day or in another timezone differs only there.
FOOTER_DATE = re.compile(
    rb'Updated [A-Z][a-z]{2} \d{1,2}, \d{4}'
    + rb'|' + '更新于 \\d{4} 年 \\d{1,2} 月 \\d{1,2} 日'.encode())


def page_digest(body):
    """SHA-256 of a page with the footer's build date blanked; everything else stays exact."""
    return hashlib.sha256(FOOTER_DATE.sub(b'<date>', body)).digest()


def compare_pages(site, base_url, timeout, fetcher=fetch):
    pages = sorted(site.glob('*.html'))
    if not pages or not (site / 'index.html').is_file():
        raise CheckFailure('missing_local_pages')
    for page in pages:
        remote = fetcher(base_url.rstrip('/') + '/' + ('' if page.name == 'index.html' else page.name), timeout)
        if page_digest(remote) != page_digest(page.read_bytes()):
            raise CheckFailure('content_mismatch:' + page.name)


def attempts(stage, commit, log, action, limit, delay, *, sleep=time.sleep):
    for attempt in range(1, limit + 1):
        reason = None
        try:
            action()
        except Exception as error:
            # Never store command output, URLs, local paths or exception payloads.
            reason = (str(error) if isinstance(error, CheckFailure) else
                      'http_status:' + str(error.code) if isinstance(error, HTTPError) else type(error).__name__)
        row = {'commit': commit, 'ts': datetime.now(timezone.utc).isoformat(),
               'stage': stage, 'result': 'success' if reason is None else 'failure',
               'attempt': attempt, 'failure_reason': reason}
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row) + '\n')
        if reason is None:
            return True
        if attempt < limit:
            sleep(delay)
    return False


def build(root, site, python):
    site.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / 'resources', site / 'resources', dirs_exist_ok=True)
    for label, command in (
            ('unit_tests', [str(python), 'test_build.py']),
            ('render', [str(python), 'build.py', 'benchmark-results.json', str(site / 'index.html')])):
        try:
            subprocess.run(command, cwd=root, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=600)
        except subprocess.CalledProcessError as error:
            raise CheckFailure(label + ':exit_' + str(error.returncode)) from error
        except subprocess.TimeoutExpired as error:
            raise CheckFailure(label + ':timeout') from error


def check_release(commit, log, local_build, deploy, limit, delay):
    if not attempts('build', commit, log, local_build, limit, delay):
        return 1
    return 0 if attempts('deploy', commit, log, deploy, limit, delay) else 1


def copy_inputs(root, clean, commit):
    """Copy tracked build and snapshot verification inputs from the requested commit."""
    names = subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', commit], cwd=root, text=True).splitlines()
    for name in names:
        if not (name in ('build.py', 'stats.py', 'test_build.py', 'pricing.json', 'sources.json')
                or re.fullmatch(r'benchmark-results[^/]*\.json', name)
                or re.fullmatch(r'snapshots/arw/[0-9a-f]{64}\.tar\.gz', name)
                or name.startswith('resources/')):
            continue
        target = clean / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('wb') as stream:
            subprocess.run(['git', 'show', commit + ':' + name], cwd=root, stdout=stream, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True, help='Full commit id of the current clean checkout')
    parser.add_argument('--log', required=True, type=Path)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--python', required=True, type=Path,
                        help='Interpreter with the publishing dependency Plotly 6.9.0 installed')
    parser.add_argument('--attempts', type=int, default=3, choices=range(1, 6))
    parser.add_argument('--timeout', type=float, default=15)
    parser.add_argument('--delay', type=float, default=5)
    args = parser.parse_args()
    # Resolving the venv's interpreter symlink would discard its environment.
    args.python = args.python.expanduser().absolute()
    url = urlsplit(args.base_url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        parser.error('base-url must be a public HTTPS URL without credentials, query or fragment')
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit) or not (0 < args.timeout <= 60 and 0 <= args.delay <= 60):
        parser.error('require full commit, timeout (0,60], delay [0,60]')
    def verify_checkout():
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True)
        if head != args.commit or dirty:
            raise CheckFailure('checkout_mismatch')
    # Copy only public build inputs; never traverse private logs or credentials.
    scratch = ROOT / '.tmp' / 'metricfeed'
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(scratch)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        clean = Path(directory)
        site = clean / 'artifacts'
        def local_build():
            verify_checkout()
            copy_inputs(ROOT, clean, args.commit)
            build(clean, site / 'reviewer-model-benchmark', args.python)
        return check_release(args.commit, args.log, local_build,
                             lambda: compare_pages(site / 'reviewer-model-benchmark', args.base_url, args.timeout),
                             args.attempts, args.delay)


if __name__ == '__main__':
    sys.exit(main())
