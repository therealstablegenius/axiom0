#!/usr/bin/env python3
"""Independent verifier for AXIOM0 audit exports and anchor receipts.

Needs only Python 3.9+ and the `cryptography` package. It does NOT import AXIOM0,
so an auditor can check the evidence without trusting the software that produced it.

  python3 axiom0_audit_verify.py export.jsonl                  # chain + signatures
  python3 axiom0_audit_verify.py export.jsonl anchors/*.json   # ...and published anchors

Checks:
  1. Every event's hash is recomputed from its contents and its predecessor's hash.
  2. Every event is signed by the public key in the export header, and that key
     matches the identity id (first 32 hex of SHA-256 of the key).
  3. Each anchor receipt is signed by the same identity, and the export contains
     exactly the anchored hash at the anchored position (no rewrite, no rollback).
Exit code 0 = all checks pass; 1 = a problem was found; 2 = unreadable input.
"""
import hashlib
import json
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    try:
        with open(argv[0], encoding='utf-8') as f:
            lines = [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError) as e:
        print(f'Cannot read export: {e}')
        return 2
    header, events = lines[0], lines[1:]
    if header.get('format') != 'axiom0-audit-v1':
        print('Not an AXIOM0 audit export')
        return 2
    problems = []
    pub_hex = header['public_key']
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
    if hashlib.sha256(bytes.fromhex(pub_hex)).hexdigest()[:32] != header['identity_id']:
        problems.append('Header identity_id does not match its public key')
    prev = 'GENESIS'
    hashes = {}
    for n, ev in enumerate(events, 1):
        if ev['seq'] != n:
            problems.append(f'Event numbering breaks at {n} (found {ev["seq"]})')
            break
        expected = sha(canonical({'event_at': ev['event_at'], 'event_type': ev['event_type'],
                                  'payload': ev['payload'], 'prev_hash': prev,
                                  'identity_id': header['identity_id']}))
        if ev['prev_hash'] != prev or ev['event_hash'] != expected:
            problems.append(f'Event {n}: hash chain broken (content or order was changed)')
            break
        try:
            key.verify(bytes.fromhex(ev['signature']), expected.encode('ascii'))
        except Exception:
            problems.append(f'Event {n}: signature invalid')
            break
        hashes[n] = expected
        prev = expected
    if not problems and (len(events) != header['events'] or prev != header['head']):
        problems.append('Export header does not match its events (truncated or padded file)')
    print(f'Ledger: {len(hashes)} of {len(events)} events verified; identity {header["identity_id"]}')

    fields = ('format', 'identity_id', 'public_key', 'seq', 'head', 'head_event_at', 'issued_at')
    for path in argv[1:]:
        try:
            with open(path, encoding='utf-8') as f:
                r = json.load(f)
            body = {k: r[k] for k in fields}
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(r['public_key'])).verify(
                bytes.fromhex(r['signature']), canonical(body).encode('utf-8'))
        except Exception as e:
            problems.append(f'{path}: not a valid signed receipt ({type(e).__name__})')
            continue
        if r['identity_id'] != header['identity_id']:
            problems.append(f'{path}: receipt is from a different identity')
        elif hashes.get(r['seq']) is None:
            problems.append(f'{path}: anchors event {r["seq"]}, which the export does not contain (rollback?)')
        elif hashes[r['seq']] != r['head']:
            problems.append(f'{path}: event {r["seq"]} differs from the anchored hash (history rewritten)')
        else:
            print(f'Anchor {path}: events 1..{r["seq"]} match (issued {r["issued_at"]})')
    for p in problems:
        print('PROBLEM:', p)
    print('RESULT:', 'PASS' if not problems else 'FAIL')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
