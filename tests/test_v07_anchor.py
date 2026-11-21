"""v0.7: external anchoring detects coherent rewrites and rollbacks by a full-host attacker."""
import json

import pytest

from axiom0 import anchor
from axiom0.engine import LivingCity
from axiom0.store import canonical, digest


def _city_with_history(tmp_path, n=3):
    city = LivingCity(tmp_path)
    for i in range(n):
        city.swap_mind(f'model-{i}', 'howard', f'reason {i}')
    return city


def _coherent_rewrite(store, seq_to_change):
    """What a host attacker holding the key can do: edit an event, re-hash and re-sign everything."""
    with store.connect() as conn:
        rows = [dict(r) for r in conn.execute('SELECT * FROM events ORDER BY seq')]
    prev = 'GENESIS'
    with store.write() as conn:
        for r in rows:
            payload = json.loads(r['payload_json'])
            if r['seq'] == seq_to_change:
                payload['reason'] = 'quietly changed'
            h = digest(canonical({'event_at': r['event_at'], 'event_type': r['event_type'], 'payload': payload,
                                  'prev_hash': prev, 'identity_id': store.identity.id}))
            conn.execute('UPDATE events SET payload_json=?,prev_hash=?,event_hash=?,signature=? WHERE seq=?',
                         (canonical(payload), prev, h, store.identity.sign(h.encode('ascii')), r['seq']))
            prev = h


def test_receipt_is_signed_and_consistent(tmp_path):
    city = _city_with_history(tmp_path)
    receipt = anchor.create_receipt(city.store, actor='howard')
    assert receipt['seq'] == 3 and receipt['format'] == anchor.FORMAT
    anchor.check_receipt_signature(receipt)
    assert anchor.verify_receipt(city.store, receipt)['status'] == 'consistent'
    city.swap_mind('model-x', 'howard', 'later work')                     # new history is fine
    assert anchor.verify_receipt(city.store, receipt)['status'] == 'consistent'


def test_coherent_rewrite_passes_local_checks_but_fails_anchor(tmp_path):
    city = _city_with_history(tmp_path)
    receipt = anchor.create_receipt(city.store, actor='howard')
    _coherent_rewrite(city.store, seq_to_change=2)
    city.store.verify_ledger()                                            # local verification is fooled...
    result = anchor.verify_receipt(city.store, receipt)
    assert result['status'] == 'conflict' and 'rewritten' in result['detail']   # ...the anchor is not


def test_rollback_is_detected(tmp_path):
    city = _city_with_history(tmp_path)
    receipt = anchor.create_receipt(city.store, actor='howard')
    with city.store.write() as conn:
        conn.execute('DELETE FROM events WHERE seq>=?', (2,))
    result = anchor.verify_receipt(city.store, receipt)
    assert result['status'] == 'conflict' and 'rolled back' in result['detail']


def test_forged_or_foreign_receipts(tmp_path):
    city = _city_with_history(tmp_path)
    receipt = anchor.create_receipt(city.store, actor='howard')
    forged = {**receipt, 'head': '0' * 64}
    with pytest.raises(ValueError, match='signature'):
        anchor.check_receipt_signature(forged)
    other = _city_with_history(tmp_path / 'other')
    foreign = anchor.create_receipt(other.store, actor='howard')
    assert anchor.verify_receipt(city.store, foreign)['status'] == 'different_identity'


def test_files_and_folder_verification(tmp_path):
    city = _city_with_history(tmp_path / 'data')
    folder = tmp_path / 'anchors'
    anchor.write_receipt(anchor.create_receipt(city.store, actor='howard'), folder)
    city.swap_mind('m', 'howard', 'r')
    anchor.write_receipt(anchor.create_receipt(city.store, actor='howard'), folder)
    (folder / 'junk.json').write_text('{"format": "nope"}')
    out = anchor.verify_many(city.store, [folder])
    assert out['checked'] == 3 and out['consistent'] == 2 and not out['ok']
    assert out['problems'][0]['status'] == 'invalid'


def test_empty_ledger_cannot_be_anchored(tmp_path):
    with pytest.raises(ValueError, match='empty'):
        anchor.create_receipt(LivingCity(tmp_path).store, actor='howard')
