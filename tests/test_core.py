import json
import sqlite3
from datetime import datetime,timezone
import pytest
from axiom0.numerics import GENESIS, SOUL, reduce, normalize, harmony
from axiom0.engine import LivingCity
from axiom0.store import Store, IntegrityError


def _entry(id_:str,source:str,area='Example Area'):
    return {'external_id':id_, 'event_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'area':area,'category':'Streetlight outages', 'summary':'Simulated public lighting concern',
        'source_label':source,'source_url':'local://test/'+id_,
        'confidence_note':'Simulated observation only'}


def test_numeric_original_unchanged():
    assert GENESIS==(1,2,8,7,5)
    assert SOUL==(5,12,5,12,5)
    assert reduce(39)==12
    assert reduce(-39)==-12
    assert len(normalize([1,2,3,4,5]))==5
    assert 0 <= harmony(GENESIS) <= 1
    with pytest.raises(Exception): normalize([1,2,3])


def test_identity_mind_swap_persists(tmp_path):
    a=LivingCity(tmp_path)
    identity=a.identity()['semisoul_id']
    a.swap_mind('test-model:1','operator','Test authorized exchange')
    b=LivingCity(tmp_path)
    assert b.identity()['semisoul_id']==identity
    assert b.identity()['mind']['model']=='test-model:1'
    assert b.store.verify_ledger()['verified_events']==1


def test_occurrences_idempotence_and_scan(tmp_path):
    a=LivingCity(tmp_path)
    data=[_entry(id_,src) for id_,src in [('1','A'),('2','B'),('3','A')]]
    for record in data: a.add_occurrence(**record)
    assert a.add_occurrence(**data[0])['duplicate'] is True
    signals=a.scan_signals()
    assert len(signals)==1
    assert signals[0]['status']=='candidate'
    assert signals[0]['report_count']==3
    assert signals[0]['distinct_source_labels']==2
    assert len(a.scan_signals())==1
    assert len(a.hypotheses())==1
    assert len(a.hypotheses()[0]['evidence'])==3
    assert a.store.verify_ledger()['verified_events']==4


def test_scan_never_verifies_and_reviewer_can_reject(tmp_path):
    city=LivingCity(tmp_path)
    for i,src in [('a','Public Log'),('b','Citizen Portal'),('c','Public Log')]:
        city.add_occurrence(**_entry(i,src))
    h=city.get_hypothesis(city.scan_signals()[0]['hypothesis_id'])
    assert h['status']=='candidate'
    assert h['source_label_count']==2
    assert not h['independence_verified']
    revised=city.review_hypothesis(h['id'],status='rejected',reviewer='Tester',note='Synthetic samples are not evidence')
    assert revised['status']=='rejected'
    assert city.scan_signals()[0]['status']=='rejected'
    assert city.store.verify_ledger()['verified_events']==5


def test_document_versioning_and_search(tmp_path):
    city=LivingCity(tmp_path)
    base={'title':'SIMULATED charter section','authority':'other','jurisdiction':'Fiction City',
          'citation':'Demo-1','version':'v1','content':'Streetlights need annual inspection.',
          'source_url':'local://demo','source_reviewed':False}
    first=city.add_document(**base)
    assert first['duplicate'] is False
    assert city.add_document(**base)['duplicate'] is True
    found=city.search_documents('streetlights annual inspection')
    assert found[0]['id']==first['id']
    newer={**base,'version':'v2','content':'Streetlights need quarterly inspection.'}
    assert city.add_document(**newer)['id']!=first['id']
    assert len(city.documents())==2


def test_signed_ledger_detects_edit(tmp_path):
    city=LivingCity(tmp_path)
    city.add_occurrence(**_entry('x','A'))
    with sqlite3.connect(tmp_path/'living_city.sqlite3') as conn:
        conn.execute("UPDATE events SET payload_json='{}' WHERE seq=1")
    with pytest.raises(IntegrityError): LivingCity(tmp_path)


def test_same_external_id_modified_payload_rejected(tmp_path):
    city=LivingCity(tmp_path)
    entry=_entry('x','A')
    city.add_occurrence(**entry)
    with pytest.raises(ValueError): city.add_occurrence(**{**entry,'summary':'Changed without an amendment ID'})


def test_missing_source_or_model_never_invents_answer(tmp_path):
    from axiom0.llm import OllamaMind,LocalMindError
    city=LivingCity(tmp_path)
    assert OllamaMind(model='not-installed').answer(city,'What about stormwater?')['classification']=='insufficient_evidence'
    with pytest.raises(LocalMindError): OllamaMind(endpoint='https://example.com')


def test_mca_atom_and_symbolic_state_are_not_truth(tmp_path):
    city=LivingCity(tmp_path)
    result=city.mca_record(identity='council',purpose='service',observation='reported issue',
                           constraint='human review',feedback='revisit')
    assert result['constraint']=='human review'
    state=city.symbolic_state([1,2,8,7,5])
    assert 'never factual proof' in state['validity'].lower()


def test_local_api_requires_keys_and_separates_reviewer(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from axiom0.api import app,core
    monkeypatch.setenv('AXIOM0_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('AXIOM0_API_KEY','A'*48)
    monkeypatch.setenv('AXIOM0_REVIEWER_KEY','B'*48)
    core.cache_clear()
    try:
        client=TestClient(app)
        assert client.get('/').status_code==200
        assert 'AXIOM0' in client.get('/').text
        assert client.get('/health').status_code==200
        assert client.get('/v1/status').status_code==401
        h={'X-AXIOM0-Key':'A'*48}
        assert client.get('/v1/status',headers=h).status_code==200
        assert client.post('/v1/signals',headers=h).json()==[]
        record=client.post('/v1/occurrences',headers=h,json=_entry('api','C'))
        assert record.status_code==200
        assert client.get('/v1/occurrences',headers=h).json()[0]['id']==record.json()['id']
        m={'model':'local-model','authorized_by':'Test','reason':'Test only'}
        assert client.post('/v1/mind',headers=h,json=m).status_code==401
        reviewer={**h,'X-AXIOM0-Reviewer-Key':'B'*48}
        assert client.post('/v1/mind',headers=reviewer,json=m).status_code==200
        assert client.get('/v1/verify',headers=h).json()['verified_events']==2
    finally:
        core.cache_clear()


def test_contradictory_evidence_and_verification_basis(tmp_path):
    city=LivingCity(tmp_path)
    first=city.add_occurrence(**_entry('one','A'))['id']
    second=city.add_occurrence(**_entry('two','B'))['id']
    h=city.create_hypothesis(claim='Testable service condition',area='Example Area',
                           category='Streetlight outages',occurrence_ids=[first])
    h=city.attach_evidence(h['id'],second,stance='contradicts',note='Independent field check')
    assert any(e['stance']=='contradicts' for e in h['evidence'])
    with pytest.raises(ValueError): city.review_hypothesis(h['id'],status='verified',reviewer='Approver',note='Checked')
    h=city.review_hypothesis(h['id'],status='verified',reviewer='Approver',
                             note='Human assessment with explicit document',proof_reference='local://signed-review-1')
    assert h['proof_reference']=='local://signed-review-1'
    assert city.store.verify_ledger()['verified_events']==5


def test_future_forecast_cannot_be_registered_as_occurrence(tmp_path):
    from datetime import timedelta
    city=LivingCity(tmp_path)
    event=_entry('future','A')
    event['event_at']=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
    with pytest.raises(ValueError,match='future'):
        city.add_occurrence(**event)
