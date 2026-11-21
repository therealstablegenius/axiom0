"""Tests for symbolic 3-6-9 protocol: no alleged physical manifestation is tested."""
from datetime import date, timedelta
from unittest.mock import patch
import sqlite3
import pytest

from axiom0.engine import LivingCity
from axiom0.intention369 import IntentionLab, TOTAL_SESSIONS, TOTAL_REPETITIONS
from axiom0.store import IntegrityError


def sample(lab):
    return lab.start(goal='Reduce average research turnaround',
                     affirmation='I take measurable action daily',
                     metric='Minutes per request',baseline=60,target=30)


def test_369_start_three_six_nine_and_separate_evidence(tmp_path):
    city=LivingCity(tmp_path)
    lab=IntentionLab(city.store)
    entry=sample(lab)
    assert entry['protocol']=={'repetitions_per_session':3,'sessions_per_day':6,
                               'days':9,'total_sessions':54,'total_repetitions':162}
    assert entry['completed_sessions']==0
    assert city.stats()['occurrences']==0
    assert city.stats()['hypotheses']==0
    changed=lab.session(entry['id'],action_taken='Completed a baseline audit')
    assert changed['completed_sessions']==1
    assert changed['completed_repetitions']==3
    assert changed['sessions'][0]['action_taken']=='Completed a baseline audit'
    measured=lab.outcome(entry['id'],value=52,source_reference='local://measured-1',note='Three timed records')
    assert measured['latest_observed_value']==52
    assert measured['outcomes'][0]['source_reference']=='local://measured-1'
    assert measured['epistemic_status'].lower().find('causal')>=0
    assert city.stats()['occurrences']==0
    assert city.stats()['hypotheses']==0
    assert city.store.verify_ledger()['verified_events']==3


def test_369_limits_six_per_day_and_requires_three_repetitions(tmp_path):
    lab=IntentionLab(LivingCity(tmp_path).store)
    practice=sample(lab)
    with pytest.raises(ValueError,match='exactly 3'):
        lab.session(practice['id'],repetitions=9)
    with pytest.raises(ValueError,match='exactly 3'):
        lab.session(practice['id'],repetitions=True)
    for _ in range(6): lab.session(practice['id'])
    with pytest.raises(ValueError,match='Six recorded sessions'):
        lab.session(practice['id'])
    assert lab.get(practice['id'])['days'][0]['complete']


def test_369_nine_consecutive_days_completion_and_close(tmp_path):
    lab=IntentionLab(LivingCity(tmp_path).store)
    start_day=date(2026,11,15)
    with patch('axiom0.intention369.local_today',return_value=start_day):
        practice=sample(lab)
    for offset in range(9):
        day=start_day+timedelta(days=offset)
        with patch('axiom0.intention369.local_today',return_value=day):
            for _ in range(6): lab.session(practice['id'])
    with patch('axiom0.intention369.local_today',return_value=start_day+timedelta(days=8)):
        final=lab.get(practice['id'])
    assert final['practice_complete'] is True
    assert final['completed_sessions']==TOTAL_SESSIONS
    assert final['completed_repetitions']==TOTAL_REPETITIONS
    assert all(x['complete'] for x in final['days'])
    with patch('axiom0.intention369.local_today',return_value=start_day+timedelta(days=9)):
        assert lab.get(practice['id'])['window_closed'] is True
        with pytest.raises(ValueError,match='window has closed'): lab.session(practice['id'])


def test_369_future_starts_no_backdating_and_finite_outcome(tmp_path):
    lab=IntentionLab(LivingCity(tmp_path).store)
    today=date(2026,11,15)
    with patch('axiom0.intention369.local_today',return_value=today):
        with pytest.raises(ValueError,match='backdated'):
            lab.start(goal='Target',affirmation='Can do',metric='Count',baseline=1,target=2,
                      start_date=(today-timedelta(days=1)).isoformat())
        with pytest.raises(ValueError,match='timezone'):
            lab.start(goal='Target',affirmation='Can do',metric='Count',baseline=1,target=2,
                      timezone_name='The/Moon')
        campaign=lab.start(goal='Target',affirmation='Can do',metric='Count',baseline=1,target=2,
                      start_date=(today+timedelta(days=1)).isoformat())
        with pytest.raises(ValueError,match='not started'):
            lab.session(campaign['id'])
    with pytest.raises(ValueError,match='finite'):
        lab.outcome(campaign['id'],value=float('nan'))
    assert lab.get(campaign['id'])['completed_sessions']==0


def test_369_events_are_signed_and_tampering_is_detected(tmp_path):
    city=LivingCity(tmp_path)
    lab=IntentionLab(city.store)
    campaign=sample(lab)
    lab.session(campaign['id'])
    lab.outcome(campaign['id'],value=55,note='One recorded measure')
    assert LivingCity(tmp_path).identity()['semisoul_id']==city.identity()['semisoul_id']
    with sqlite3.connect(tmp_path/'living_city.sqlite3') as conn:
        conn.execute("UPDATE events SET payload_json='{}' WHERE event_type='369_session_self_reported'")
    with pytest.raises(IntegrityError): LivingCity(tmp_path)


def test_369_api_auth_and_session_records(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from axiom0.api import app,core
    monkeypatch.setenv('AXIOM0_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('AXIOM0_API_KEY','X'*48)
    monkeypatch.setenv('AXIOM0_REVIEWER_KEY','Y'*48)
    monkeypatch.setenv('AXIOM0_ENABLE_SYMBOLIC','1')  # v0.7: optional module, enabled for this test
    core.cache_clear()
    try:
        client=TestClient(app)
        assert client.get('/v1/369/intentions').status_code==401
        h={'X-AXIOM0-Key':'X'*48}
        entry=client.post('/v1/369/intentions',headers=h,json={'goal':'Grow awareness',
              'affirmation':'I learn by taking action','metric':'Hours learned','baseline':0,
              'target':9}).json()
        assert entry['protocol']['days']==9
        pid=entry['id']
        assert client.get('/v1/369/intentions',headers=h).json()[0]['id']==pid
        assert client.post(f'/v1/369/intentions/{pid}/sessions',headers=h,
                           json={'repetitions':2}).status_code==400
        response=client.post(f'/v1/369/intentions/{pid}/sessions',headers=h,
                             json={'repetitions':3,'action_taken':'Practiced'})
        assert response.status_code==200
        assert response.json()['completed_repetitions']==3
        out=client.post(f'/v1/369/intentions/{pid}/outcomes',headers=h,
                        json={'value':1,'note':'Observed self-report'})
        assert out.status_code==200
        assert client.get('/v1/status',headers=h).json()['stats']['occurrences']==0
        assert client.get('/v1/verify',headers=h).json()['verified_events']==3
        assert 'intention-lab' in client.get('/').text
    finally:
        core.cache_clear()
