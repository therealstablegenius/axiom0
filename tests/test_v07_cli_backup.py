"""v0.7: CLI end-to-end — reviewers, anchors, backup/restore, audit export + independent verifier."""
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from axiom0.cli import execute

VERIFIER = Path(__file__).resolve().parents[1] / 'tools' / 'axiom0_audit_verify.py'


def run(capsys, *argv, ok=True):
    try:
        execute(['--json', *argv])
        code = 0
    except SystemExit as e:
        code = e.code
    out = capsys.readouterr().out.strip().splitlines()
    assert (code == 0) == ok, out
    return json.loads(out[-1]) if out else None


def test_full_operator_cycle(tmp_path, capsys, monkeypatch):
    d = str(tmp_path / 'data')
    monkeypatch.delenv('AXIOM0_LOCAL_ACTOR', raising=False)
    run(capsys, '--data-dir', d, 'init', '--admin', 'howard')
    run(capsys, '--data-dir', d, 'ingest', 'examples/SIMULATED_charter.md')
    key = run(capsys, '--data-dir', d, 'reviewer-add', 'Daliah West')['key']
    assert key.startswith('axr_')
    assert run(capsys, '--data-dir', d, 'reviewer-list')[0]['active'] is True
    run(capsys, '--data-dir', d, '--actor', 'someone_else', 'reviewer-add', 'Mallory', ok=False)  # admin only

    flags = run(capsys, '--data-dir', d, 'warn', 'examples/SIMULATED_service_requests.csv')
    assert flags and flags[0]['rule'] == 'SPIKE-v2'

    receipt_file = run(capsys, '--data-dir', d, 'anchor', '--out', str(tmp_path / 'anchors'))['file']
    assert run(capsys, '--data-dir', d, 'anchor-verify', str(tmp_path / 'anchors'))['ok'] is True

    backup = run(capsys, '--data-dir', d, 'backup', str(tmp_path / 'backups'))
    archive = Path(backup['archive'])
    if os.name == 'posix':
        assert archive.stat().st_mode & 0o077 == 0                     # owner-only: holds the private key

    restored = str(tmp_path / 'restored')
    out = run(capsys, '--data-dir', restored, 'restore', str(archive))
    assert out['ledger_events_at_backup'] == backup['ledger_events']
    assert run(capsys, '--data-dir', restored, 'anchor-verify', receipt_file)['ok'] is True
    run(capsys, '--data-dir', restored, 'restore', str(archive), ok=False)  # refuses a non-empty target

    export = tmp_path / 'audit.jsonl'
    run(capsys, '--data-dir', d, 'export-audit', str(export))
    good = subprocess.run([sys.executable, '-I', str(VERIFIER), str(export), receipt_file],
                          capture_output=True, text=True)
    assert good.returncode == 0 and 'RESULT: PASS' in good.stdout

    # Tamper with one historical event in the export: the independent verifier must fail.
    lines = export.read_text().splitlines()
    ev = json.loads(lines[2]); ev['payload']['actor'] = 'someone else'; lines[2] = json.dumps(ev)
    bad_export = tmp_path / 'tampered.jsonl'
    bad_export.write_text('\n'.join(lines) + '\n')
    bad = subprocess.run([sys.executable, '-I', str(VERIFIER), str(bad_export)], capture_output=True, text=True)
    assert bad.returncode == 1 and 'hash chain broken' in bad.stdout


def test_restore_rejects_altered_archive(tmp_path, capsys):
    d = str(tmp_path / 'data')
    run(capsys, '--data-dir', d, 'init', '--admin', 'howard')
    run(capsys, '--data-dir', d, 'ingest', 'examples/SIMULATED_charter.md')
    archive = Path(run(capsys, '--data-dir', d, 'backup', str(tmp_path / 'b'))['archive'])
    with tarfile.open(archive) as t:
        members = {m.name: t.extractfile(m).read() for m in t.getmembers()}
    members['living_city.sqlite3'] += b'\0'                             # corrupt the database copy
    altered = tmp_path / 'altered.tar.gz'
    with tarfile.open(altered, 'w:gz') as t:
        import io
        for name, data in members.items():
            info = tarfile.TarInfo(name); info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    out = run(capsys, '--data-dir', str(tmp_path / 'r'), 'restore', str(altered), ok=False)
    assert 'manifest hash' in out['detail']


def test_369_cli_is_opt_in(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv('AXIOM0_ENABLE_SYMBOLIC', raising=False)
    out = run(capsys, '--data-dir', str(tmp_path), '369-list', ok=False)
    assert 'disabled' in out['detail']
    monkeypatch.setenv('AXIOM0_ENABLE_SYMBOLIC', '1')
    assert run(capsys, '--data-dir', str(tmp_path), '369-list') == []
