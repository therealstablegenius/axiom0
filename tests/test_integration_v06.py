"""New v0.6 integration and security regression checks; all data is synthetic."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
import httpx
from fastapi.testclient import TestClient
from axiom0.core import Axiom0
from axiom0.fetcher import ResilientFetcher
from axiom0.inquiry369 import Inquiry369
from axiom0.semisoul import SemiSoul

SAMPLE='''---
doc_id: demo-chambers
title: SIMULATED chambers rule
authority: policy
effective: 2026-02-01
source_url: https://example.com/fictional
---
Section 101. Chamber schedule
A fictional chamber reservation must be requested five working days before a meeting. This is only a test fixture.
'''


def fixture_event(i):
    return {'external_id':str(i),'event_at':datetime.now(timezone.utc).isoformat(),
            'area':'Sample Block','category':'Lighting','summary':'Fictional maintenance report',
            'source_label':'Demo','source_url':'local://fixture','confidence_note':'Synthetic'}


def test_import_bridge_quote_and_local_research(tmp_path):
    ax=Axiom0(tmp_path)
    ax.set_admin('howard')
    report=ax.library.ingest_text(SAMPLE)
    assert report['added']==['101']
    assert ax.library.ingest_text(SAMPLE)['unchanged']==1
    found=ax.ask('howard','chamber reservation requested five working days')
    assert found['status']=='source_excerpt_only'
    assert found['findings'] and found['findings'][0]['proof_gate']=='matching_source_quote_not_legal_conclusion'
    assert found['findings'][0]['cite'].startswith('demo-chambers:101@v1')
    assert ax.city.search_documents('chamber reservation')
    with pytest.raises(PermissionError):ax.ask('random','chamber reservation')
    assert ax.verify()['signed_events'] >= 3


def test_inquiry_369_does_not_claim_divinity(tmp_path):
    ax=Axiom0(tmp_path)
    ev=ax.city.add_occurrence(**fixture_event('1'))
    h=ax.city.create_hypothesis(claim='Sample streetlamp needs review',area='Sample Block',
                                 category='Lighting',occurrence_ids=[ev['id']])
    result=Inquiry369(ax.city).evaluate(h['id'])
    assert len(result['three_inquiry_phases'])==3
    assert len(result['six_evidence_checks'])==6
    assert len(result['nine_review_steps'])==9
    assert result['result']=='structured_inquiry_not_proof'
    assert ax.city.get_hypothesis(h['id'])['status']=='candidate'
    assert ax.verify()['signed_events']==3


def test_fetcher_conditional_ttl_and_new_version(tmp_path):
    requests=[]
    content=['<h2>Section 101. Working hours</h2><p>The hypothetical office must provide a public notice of meetings.</p>']
    def responder(req):
        requests.append(req)
        if req.headers.get('If-None-Match')=='"a"' and len(requests)==2:
            return httpx.Response(304,headers={'ETag':'"a"'})
        return httpx.Response(200,content=content[0],headers={'ETag':'"a"','Content-Type':'text/html; charset=utf-8'})
    resolver=lambda *a,**k: [(None,None,None,None,('93.184.215.14',443))]
    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        f=ResilientFetcher(tmp_path,client=client,resolver=resolver,sleep_fn=lambda s:None)
        f.register(feed_id='demo',url='https://example.com/legal',doc_id='sample-office',
                   title='Simulated office rule',authority='policy')
        first=f.poll('demo',bypass_ttl=True)
        assert first['status']=='changed'
        assert len(requests)==1
        cached=f.poll('demo')
        assert cached['status']=='fresh_cache_no_request' and len(requests)==1
        assert f.poll('demo',bypass_ttl=True)['status']=='http_not_modified'
        assert len(requests)==2
        content[0]='<h2>Section 101. Working hours</h2><p>The hypothetical office must publish a notice seven days before the meeting.</p>'
        assert f.poll('demo',bypass_ttl=True)['status']=='changed'
        assert len(requests)==3
        secs=f.ax.municipal.sections(current_only=False)
        assert len(secs)==2
        assert len([s for s in secs if s['superseded_at'] is None])==1
        assert f.ax.verify()['signed_events']>=7


def test_fetcher_refuses_redirects_and_nonpublic_network(tmp_path):
    fake=lambda *a,**kw: [(None,None,None,None,('127.0.0.1',443))]
    f=ResilientFetcher(tmp_path,resolver=fake)
    f.register(feed_id='t',url='https://example.com/page',doc_id='demo',
               title='Demo feed',authority='policy')
    report=f.poll('t')
    assert report['status']=='failed' and report['reason']=='PermissionError'
    assert f.ax.municipal.sections()==[]
    with pytest.raises(ValueError):f.register(feed_id='evil',url='http://169.254.169.254/latest',
                                               doc_id='no',title='No',authority='policy')
    resolver=lambda *a,**kw: [(None,None,None,None,('93.184.215.14',443))]
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(302,headers={'Location':'http://localhost'}))) as client:
        g=ResilientFetcher(tmp_path,client=client,resolver=resolver)
        err=g.poll('t',bypass_ttl=True)
        assert err['status']=='failed' and 'Redirect' in err['message']


def test_compat_api_keys_queue_and_fixed_reviewer(tmp_path,monkeypatch):
    from axiom0.api import app, core, compat
    monkeypatch.setenv('AXIOM0_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('AXIOM0_API_KEY','A'*48)
    monkeypatch.setenv('AXIOM0_REVIEWER_KEY','B'*48)
    monkeypatch.setenv('AXIOM0_REVIEWER_ID','site_reviewer')
    core.cache_clear();compat.cache_clear()
    try:
        client=TestClient(app)
        assert client.post('/ask',json={'question':'reservations'}).status_code==401
        auth={'X-AXIOM0-Key':'A'*48}
        reviewer={**auth,'X-AXIOM0-Reviewer-Key':'B'*48}
        assert client.post('/ingest',headers=auth,json={'content':SAMPLE}).status_code==200
        answer=client.post('/ask',headers=auth,json={'question':'reservation requested five working days'}).json()
        assert answer['findings']
        assert client.get('/v1/semisoul/profile',headers=auth).status_code==200
        quote=client.post('/v1/legal/quote',headers=auth,json={
            'cite':'demo-chambers:101',
            'quote':'A fictional chamber reservation must be requested five working days before a meeting.'}).json()
        assert quote['status']=='quote_matched'
        rec=client.post('/queue',headers=auth,json={'recommendation':'Review chamber public notices',
                                                    'evidence_refs':[quote['cite']]}).json()
        assert rec['status']=='pending'
        assert len(client.get('/queue',headers=auth).json())==1
        assert client.post('/queue/review',headers=auth,json={'id':rec['id'],
                          'decision':'rejected','note':'Not verified'}).status_code==401
        done=client.post('/queue/review',headers=reviewer,json={'id':rec['id'],
                               'decision':'rejected','note':'Not verified'}).json()
        assert done['reviewed_by']=='site_reviewer'
        assert done['status']=='rejected'
        missing=client.post('/warn',headers=auth,json={'csv_filename':'../../private.csv'})
        assert missing.status_code==400
    finally:
        core.cache_clear();compat.cache_clear()


def test_semisoul_continuity_and_attestation(tmp_path):
    ax=Axiom0(tmp_path)
    ax.semisoul.remember(statement='The demo issue is unresolved',memory_type='reflection',
                         epistemic_status='uncertain',source_type='operator',actor='howard')
    att=ax.semisoul.attest()
    assert SemiSoul.verify_attestation(att)
    original=ax.city.identity()['semisoul_id']
    ax.city.swap_mind('demo-replaceable-model','howard','Local upgrade')
    newer=Axiom0(tmp_path)
    assert newer.city.identity()['semisoul_id']==original
    assert newer.verify()['memory_count']==1
    bad=json.loads(json.dumps(att));bad['attestation']['statement']='This proves divinity'
    with pytest.raises(Exception):SemiSoul.verify_attestation(bad)


def test_cli_json_contract(tmp_path):
    cwd=Path(__file__).resolve().parents[1]
    def cli(*argv):
        cp=subprocess.run([sys.executable,'-m','axiom0','--data-dir',str(tmp_path),'--json',*argv],
                          capture_output=True,text=True,cwd=cwd,env={**os.environ,'PYTHONPATH':str(cwd)})
        return cp,json.loads(cp.stdout) if cp.stdout else None
    code,result=cli('init','--admin','howard')
    assert code.returncode==0 and result['local_operator']['admin']=='howard'
    file=tmp_path/'demo.md';file.write_text(SAMPLE,encoding='utf-8')
    code,result=cli('ingest',str(file));assert code.returncode==0 and result[0]['added']==['101']
    code,result=cli('ask','reservation requested five working days')
    assert code.returncode==0 and result['findings']
    code,result=cli('verify');assert code.returncode==0 and result['signed_events']>=3
    code,result=cli('doctor');assert code.returncode==0 and result['status']=='ok'


def test_source_snapshot_detects_coherent_section_rewrite(tmp_path):
    import sqlite3
    from axiom0.store import IntegrityError
    ax=Axiom0(tmp_path)
    ax.library.ingest_text(SAMPLE)
    assert ax.verify()['source_integrity']['signed_current_source_snapshots']==1
    with sqlite3.connect(tmp_path/'living_city.sqlite3') as db:
        # Recompute the local row hash to imitate a more sophisticated attacker,
        # but not the signed audit event.
        from axiom0.legacy_v02.truth import section_hash
        amended='Fictional new text that was never actually ingested.'
        db.execute('''UPDATE legal_sections SET body=?,sha256=? WHERE source_id=?''',
            (amended,section_hash('Chamber schedule',amended),'demo-chambers'))
    with pytest.raises(IntegrityError,match='snapshot'):
        ax.verify()


def test_content_integrity_detects_modified_document(tmp_path):
    import sqlite3
    from axiom0.store import IntegrityError
    ax=Axiom0(tmp_path)
    ax.city.add_document(title='Fake',authority='policy',jurisdiction='Fictional',
        citation='F-1',version='1',content='Six month deadline',source_url='local://fixture')
    with sqlite3.connect(tmp_path/'living_city.sqlite3') as db:
        db.execute('UPDATE documents SET content=?',('Seventh month deadline',))
    with pytest.raises(IntegrityError,match='Document'):
        ax.verify()
