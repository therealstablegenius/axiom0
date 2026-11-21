"""v0.7: personal reviewer identities replace the self-asserted reviewer label."""
import json

import pytest
from fastapi.testclient import TestClient

from axiom0.api import app, compat, core
from axiom0.engine import LivingCity
from axiom0.reviewers import Reviewers

SVC = {'X-AXIOM0-Key': 'A' * 48}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('AXIOM0_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('AXIOM0_API_KEY', 'A' * 48)
    monkeypatch.setenv('AXIOM0_REVIEWER_KEY', 'B' * 48)
    monkeypatch.setenv('AXIOM0_REVIEWER_ID', 'shared_label')
    core.cache_clear(); compat.cache_clear()
    yield TestClient(app), tmp_path
    core.cache_clear(); compat.cache_clear()


def _events(path, kind):
    with LivingCity(path).store.connect() as conn:
        return [json.loads(r['payload_json']) for r in
                conn.execute('SELECT payload_json FROM events WHERE event_type=? ORDER BY seq', (kind,))]


def test_enroll_list_revoke_and_key_is_never_stored(tmp_path):
    r = Reviewers(LivingCity(tmp_path).store)
    issued = r.enroll('Daliah West', enrolled_by='howard')
    assert issued['key'].startswith('axr_')
    with r.store.connect() as conn:
        dump = '\n'.join(str(tuple(row)) for row in conn.execute('SELECT * FROM reviewers'))
    assert issued['key'] not in dump
    assert r.authenticate(issued['key']) == 'Daliah West'
    with pytest.raises(ValueError, match='already has an active key'):
        r.enroll('daliah west', enrolled_by='howard')
    r.revoke('Daliah West', revoked_by='howard')
    assert r.authenticate(issued['key']) is None
    reissued = r.enroll('Daliah West', enrolled_by='howard')
    assert r.authenticate(reissued['key']) == 'Daliah West' and r.authenticate(issued['key']) is None
    assert [e['name'] for e in _events(tmp_path, 'reviewer_enrolled')] == ['Daliah West', 'Daliah West']
    with pytest.raises(ValueError):
        r.enroll('api_service', enrolled_by='howard')


def test_api_takes_reviewer_identity_from_the_key(api):
    client, path = api
    key = Reviewers(core().store).enroll('Bertha Ross', enrolled_by='howard')['key']
    proposal = client.post('/queue', headers=SVC, json={'recommendation': 'Inspect storm drains on Prospect',
                                                        'evidence_refs': ['occ-1']}).json()
    r = client.post('/queue/review', headers={**SVC, 'X-AXIOM0-Reviewer-Key': key},
                    json={'id': proposal['id'], 'decision': 'approved_for_human_followup', 'note': 'ok'})
    assert r.status_code == 200 and r.json()['reviewed_by'] == 'Bertha Ross'
    ev = _events(path, 'action_reviewed')[-1]
    assert ev['reviewed_by'] == 'Bertha Ross' and ev['reviewer_auth'] == 'personal_key'


def test_shared_key_still_works_but_is_marked_and_can_be_disabled(api, monkeypatch):
    client, path = api
    shared = {**SVC, 'X-AXIOM0-Reviewer-Key': 'B' * 48}
    p = client.post('/queue', headers=SVC, json={'recommendation': 'Review trash pickup', 'evidence_refs': ['x']}).json()
    r = client.post('/queue/review', headers=shared, json={'id': p['id'], 'decision': 'rejected', 'note': 'n'})
    assert r.status_code == 200 and _events(path, 'action_reviewed')[-1]['reviewer_auth'] == 'shared_key'
    monkeypatch.setenv('AXIOM0_REQUIRE_PERSONAL_REVIEWERS', '1')
    p2 = client.post('/queue', headers=SVC, json={'recommendation': 'Review lights', 'evidence_refs': ['x']}).json()
    assert client.post('/queue/review', headers=shared,
                       json={'id': p2['id'], 'decision': 'rejected', 'note': 'n'}).status_code == 401


def test_revoked_or_bogus_personal_key_rejected(api):
    client, _ = api
    rv = Reviewers(core().store)
    key = rv.enroll('Temp Reviewer', enrolled_by='howard')['key']
    rv.revoke('Temp Reviewer', revoked_by='howard')
    p = client.post('/queue', headers=SVC, json={'recommendation': 'Check signage', 'evidence_refs': ['x']}).json()
    for bad in (key, 'axr_' + 'x' * 43):
        r = client.post('/queue/review', headers={**SVC, 'X-AXIOM0-Reviewer-Key': bad},
                        json={'id': p['id'], 'decision': 'rejected', 'note': 'n'})
        assert r.status_code == 401
