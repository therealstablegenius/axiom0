"""External anchoring of the signed ledger: detects rollback and history rewrites.

Why: whoever controls the host controls both the database and the signing key, so
a *coherent* rewrite of local history (re-hashed and re-signed) cannot be detected
from local data alone. An anchor receipt fixes "event N had hash H" outside the
machine. Once a receipt has been published somewhere the host operator cannot edit
(a public git repository, an email to another office, a printed record, a
timestamping service), any later rewrite or rollback of events 1..N on this host
makes verification fail.

A receipt is small, self-describing JSON signed by the AXIOM0 identity key. It
does not contain ledger payloads, so it is safe to publish.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
from .identity import Identity
from .store import IntegrityError, Store, canonical, digest, now

FORMAT = 'axiom0-anchor-v1'
_FIELDS = ('format', 'identity_id', 'public_key', 'seq', 'head', 'head_event_at', 'issued_at')


def create_receipt(store: Store, *, actor: str) -> dict:
    """Sign the current ledger head, record that a receipt was issued, return the receipt."""
    store.verify_ledger()  # never anchor a head that does not itself verify
    with store.write() as conn:
        last = conn.execute('SELECT seq,event_hash,event_at FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        if not last:
            raise ValueError('The ledger is empty; there is nothing to anchor yet')
        body = {'format': FORMAT, 'identity_id': store.identity.id,
                'public_key': store.identity.public_raw.hex(), 'seq': last['seq'],
                'head': last['event_hash'], 'head_event_at': last['event_at'], 'issued_at': now()}
        receipt = {**body, 'signature': store.identity.sign(canonical(body).encode('utf-8'))}
        receipt_sha = digest(canonical(receipt))
        conn.execute('INSERT INTO ledger_anchors(receipt_sha256,seq,head,created_at) VALUES(?,?,?,?)',
                     (receipt_sha, body['seq'], body['head'], body['issued_at']))
        store.append(conn, 'ledger_anchored', {'actor': actor, 'seq': body['seq'], 'head': body['head'],
                                               'receipt_sha256': receipt_sha,
                                               'note': 'publish the receipt outside this host to make it an anchor'})
    return receipt


def check_receipt_signature(receipt: Any) -> dict:
    """Stand-alone check: well-formed, signed by the key it names. Needs no ledger."""
    if not isinstance(receipt, dict) or receipt.get('format') != FORMAT:
        raise ValueError('Not an AXIOM0 anchor receipt')
    missing = [f for f in (*_FIELDS, 'signature') if f not in receipt]
    if missing:
        raise ValueError(f'Receipt is missing fields: {missing}')
    if type(receipt['seq']) is not int or receipt['seq'] < 1:
        raise ValueError('Receipt seq must be a positive integer')
    body = {k: receipt[k] for k in _FIELDS}
    try:
        public = bytes.fromhex(receipt['public_key'])
        Identity.verify_with_public_key(receipt['public_key'], canonical(body).encode('utf-8'), receipt['signature'])
    except Exception as e:
        raise ValueError('Receipt signature is invalid') from e
    if hashlib.sha256(public).hexdigest()[:32] != receipt['identity_id']:
        raise ValueError('Receipt identity_id does not match its public key')
    return body


def verify_receipt(store: Store, receipt: Any) -> dict:
    """Compare a previously published receipt with this host's ledger."""
    body = check_receipt_signature(receipt)
    if body['identity_id'] != store.identity.id:
        return {'status': 'different_identity', 'seq': body['seq'],
                'detail': 'Receipt was signed by a different AXIOM0 identity (wrong host, or the identity key was replaced)'}
    try:
        local = store.verify_ledger()
    except IntegrityError as e:
        return {'status': 'conflict', 'seq': body['seq'], 'detail': f'Local ledger fails verification: {e}'}
    with store.connect() as conn:
        row = conn.execute('SELECT event_hash FROM events WHERE seq=?', (body['seq'],)).fetchone()
    if row is None:
        return {'status': 'conflict', 'seq': body['seq'],
                'detail': f'Ledger has only {local["verified_events"]} events but the receipt anchors event '
                          f'{body["seq"]}: history was rolled back or truncated'}
    if row['event_hash'] != body['head']:
        return {'status': 'conflict', 'seq': body['seq'],
                'detail': f'Event {body["seq"]} differs from the anchored hash: history up to that point was rewritten'}
    return {'status': 'consistent', 'seq': body['seq'], 'issued_at': body['issued_at'],
            'detail': f'Events 1..{body["seq"]} match the anchor'}


def load_receipts(paths: list[str | Path]) -> list[tuple[str, Any]]:
    """Read receipts from files and/or folders (*.json)."""
    out: list[tuple[str, Any]] = []
    for p in map(Path, paths):
        files = sorted(p.glob('*.json')) if p.is_dir() else [p]
        for f in files:
            if f.stat().st_size > 64_000:
                raise ValueError(f'{f} is too large to be an anchor receipt')
            out.append((str(f), json.loads(f.read_text(encoding='utf-8'))))
    return out


def verify_many(store: Store, paths: list[str | Path]) -> dict:
    results = []
    for name, receipt in load_receipts(paths):
        try:
            results.append({'file': name, **verify_receipt(store, receipt)})
        except ValueError as e:
            results.append({'file': name, 'status': 'invalid', 'detail': str(e)})
    bad = [r for r in results if r['status'] != 'consistent']
    return {'checked': len(results), 'consistent': len(results) - len(bad), 'problems': bad,
            'ok': bool(results) and not bad}


def write_receipt(receipt: dict, folder: str | Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"axiom0-anchor-{receipt['identity_id'][:12]}-{receipt['seq']:08d}.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return path
