"""Read-only inventory and conservative secret-pattern checks before publishing.

Reports relative filenames and pattern names only, never matching secret values.
This is a bounded pattern scan, not a guarantee that content contains no secrets.
No files, Git configuration, or index entries are changed except an explicitly
requested JSON report. Scientific outputs and preserved failed runs are retained.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

ROOT_EXCLUSIONS = {'.git', '.venv', '.pytest_cache', 'build', 'dist', 'tmp'}
ANY_DIRECTORY_EXCLUSIONS = {'.git', '__pycache__', '.pytest_cache'}
TEXT_SUFFIXES = {'.py', '.m', '.md', '.rst', '.json', '.txt', '.log', '.xml', '.toml',
                 '.yaml', '.yml', '.ps1', '.cmd', '.cjs', '.js', '.css', '.html',
                 '.csv', '.inp', '.lock', '.ini', '.cfg'}
PATTERNS = {
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github_classic_token': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
    'github_fine_grained_token': re.compile(r'\bgithub_pat_[A-Za-z0-9_]{50,}\b'),
    'aws_access_key_id': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'google_api_key': re.compile(r'\bAIza[A-Za-z0-9_-]{35}\b'),
    'openai_api_key': re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b'),
    'assigned_password_or_token': re.compile(
        r'''(?im)^\s*(?:password|passwd|api_key|access_token|secret_key)\s*[=:]\s*["'][^"'\s]{8,}["']'''),
}


def project_files(root):
    """Yield ordinary project files; external checkouts are separately pinned."""
    for current, directories, files in os.walk(root, followlinks=False):
        parent = Path(current)
        relative = parent.relative_to(root)
        directories[:] = [name for name in directories
                          if name not in ANY_DIRECTORY_EXCLUSIONS
                          and not name.endswith('.egg-info')
                          and not (relative == Path('.') and name in ROOT_EXCLUSIONS)
                          and not (relative == Path('.') and name == 'upstream')
                          and not (relative == Path('tools') and name == 'vendor')
                          and not (parent/name).is_symlink()]
        for name in files:
            path = parent/name
            if path.is_symlink() or name.endswith(('.pyc', '.pyo')):
                continue
            if relative.parts[:1] == ('outputs',) and name in ('server.lock', 'worker.lock', 'cancel.request', 'gui-server.log'):
                continue
            yield path


def audit(root, report_path=None):
    groups = defaultdict(lambda: {'files': 0, 'bytes': 0})
    findings, large, local_paths, hashes = [], [], [], {}
    text_count = 0
    for path in sorted(project_files(root)):
        if report_path and path.resolve() == report_path.resolve():
            continue
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        group = relative.split('/')[0] if '/' in relative else '(root)'
        groups[group]['files'] += 1
        groups[group]['bytes'] += size
        if size >= 50*1024*1024:
            large.append({'file': relative, 'bytes': size, 'exceeds_100_MiB': size > 100*1024*1024})
        content = path.read_bytes()
        hashes[relative] = hashlib.sha256(content).hexdigest()
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ('.gitignore', '.gitmodules', 'LICENSE'):
            continue
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            continue
        text_count += 1
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append({'file': relative, 'pattern': label})
        if re.search(r'(?i)[A-Z]:[\\/]+Users[\\/]+', text):
            local_paths.append(relative)
    return {
        'schema': 'openstream-publication-audit-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Project source, documentation, tests, tools, results and reference exports; not Git internals or external checkouts.',
        'exclusions': sorted(ROOT_EXCLUSIONS | {'upstream/ (pinned submodule)', 'tools/vendor/ (external inspection checkout)',
                                                  '**/__pycache__/', '**/*.egg-info/', 'GUI runtime locks and server log'}),
        'groups': dict(groups), 'files': sum(g['files'] for g in groups.values()),
        'bytes': sum(g['bytes'] for g in groups.values()), 'text_files_scanned': text_count,
        'credential_pattern_findings': findings, 'files_at_least_50_MiB': large,
        'files_containing_local_user_paths': local_paths,
        'local_path_note': 'Historical environment/provenance records retain original local paths; these are not authentication secrets.',
        'limitations': 'Pattern-only scan; binary scientific arrays and images are inventoried and hashed, not semantically scanned for credentials.',
        'sha256': hashes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, help='Write the filename-only report here')
    args = parser.parse_args()
    report = audit(args.root.resolve(), args.output)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('files', 'bytes', 'text_files_scanned', 'groups',
                                           'credential_pattern_findings', 'files_at_least_50_MiB')}, indent=2))
    print('Files retaining historical local-user paths:', len(report['files_containing_local_user_paths']))
    return 1 if report['credential_pattern_findings'] or any(p['exceeds_100_MiB'] for p in report['files_at_least_50_MiB']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
