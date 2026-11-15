"""Versioned legal sources, quote-verification, area-level warnings and review queue.

Adapted from the user's AXIOM0 Municipal Intelligence Core v0.2. Changes are
atomic with the v0.4/v0.5 signed event ledger. A matching quote is *not* a legal
ruling or proof that the claim is semantically entailed by the excerpt.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any
import json
import uuid
from .legacy_v02.truth import parse_source, section_hash, normalize
from .legacy_v02.warning import load_requests, spikes, SpikeRule
from .store import Store, now, canonical, digest
from .semisoul import checked

FORBIDDEN_ACTIONS={
    'issue_citation','enforcement_decision','authorize_spending',
    'modify_official_record','person_level_risk_score',
}

class MunicipalCore:
    def __init__(self, store: Store):
        self.store=store

    def ingest_sections(self, raw: str, *, actor: str='local_operator') -> dict:
        actor=checked(actor,'actor',120)
        if not isinstance(raw,str) or not raw.strip() or len(raw)>2_000_000:
            raise ValueError('source must be a nonempty legal text <= 2 MB')
        metadata, sections=parse_source(raw)
        doc_id=checked(metadata['doc_id'],'doc_id',200)
        if not sections:
            raise ValueError('No recognizable sections; refusing to remove an entire prior source')
        ids=[sid for sid,_,_ in sections]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate legal section headings in source')
        authority=metadata['authority']
        if authority not in ('charter','ordinance','policy','procedure'):
            raise ValueError('Invalid municipal authority label')
        report={'doc_id':doc_id,'added':[],'changed':[],'removed':[],'unchanged':0}
        stamp=now()
        with self.store.write() as conn:
            prev={r['section_id']:r for r in conn.execute('''SELECT * FROM legal_sections
                WHERE source_id=? AND superseded_at IS NULL''',(doc_id,)).fetchall()}
            for sid,title,body in sections:
                sid=checked(sid,'section_id',120)
                title=checked(title,'section title',400,allow_empty=True)
                body=checked(body,'section body',200000,allow_empty=True)
                sha=section_hash(title,body)
                old=prev.get(sid)
                # even unchanged text must be versioned if source authority/effectivity changes.
                same=old and all((old['sha256']==sha,old['authority']==authority,
                                  old['effective']==metadata.get('effective'),
                                  old['source_url']==metadata.get('source_url')))
                if same:
                    report['unchanged']+=1
                    continue
                version=1
                if old:
                    version=old['version']+1
                    conn.execute('''UPDATE legal_sections SET superseded_at=?
                        WHERE source_id=? AND section_id=? AND version=?''',
                        (stamp,doc_id,sid,old['version']))
                    report['changed'].append({'section':sid,'old_hash':old['sha256'],'new_hash':sha})
                else:
                    # If a section was previously removed, do not reuse version 1.
                    maxversion=conn.execute('''SELECT COALESCE(MAX(version),0) AS ver FROM legal_sections
                        WHERE source_id=? AND section_id=?''',(doc_id,sid)).fetchone()['ver']
                    version=maxversion+1
                    report['added'].append(sid)
                conn.execute('''INSERT INTO legal_sections(source_id,section_id,version,title,body,sha256,
                    authority,effective,source_url,ingested_at,superseded_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,NULL)''',
                    (doc_id,sid,version,title,body,sha,authority,metadata.get('effective'),
                     metadata.get('source_url'),stamp))
            for sid,old in prev.items():
                if sid not in ids:
                    conn.execute('''UPDATE legal_sections SET superseded_at=?
                        WHERE source_id=? AND section_id=? AND version=?''',
                        (stamp,doc_id,sid,old['version']))
                    report['removed'].append(sid)
            if report['added'] or report['changed'] or report['removed']:
                snapshot_rows=conn.execute('''SELECT section_id,version,sha256 FROM legal_sections
                    WHERE source_id=? AND superseded_at IS NULL ORDER BY section_id''',(doc_id,)).fetchall()
                snapshot_sha256=digest(canonical([[r['section_id'],r['version'],r['sha256']]
                                                  for r in snapshot_rows]))
                self.store.append(conn,'legal_source_changed',{'actor':actor,'source_hash':digest(raw),
                    'snapshot_sha256':snapshot_sha256,
                    'document_id':doc_id,'report':report,'authority':authority,
                    'note':'source labels are operator supplied; legal authenticity is not independently verified'})
        return report

    def monitor(self, folder: str | Path, *, actor: str='local_operator') -> list[dict]:
        path=Path(folder)
        if not path.is_dir():
            raise ValueError('Expected an existing directory of plain-text source files')
        files=sorted([*path.glob('*.md'),*path.glob('*.txt')])
        if not files:
            raise ValueError('No .md or .txt source files found')
        return [{'file':str(file),**self.ingest_sections(file.read_text('utf-8'),actor=actor)} for file in files]

    def sections(self, *, current_only: bool=True, limit: int=200) -> list[dict]:
        if type(limit)!=int or not 1<=limit<=1000:
            raise ValueError('limit must be 1..1000')
        with self.store.connect() as conn:
            rows=conn.execute('''SELECT source_id,section_id,version,title,sha256,authority,effective,
                        source_url,ingested_at,superseded_at FROM legal_sections
                        WHERE (?=0 OR superseded_at IS NULL)
                        ORDER BY source_id,section_id,version DESC LIMIT ?''',(int(current_only),limit)).fetchall()
        return [dict(x) for x in rows]

    def _resolve(self, cite: str, version: int | None = None):
        if not isinstance(cite,str) or ':' not in cite:
            return None
        doc,sec=cite.split(':',1)
        with self.store.connect() as conn:
            if version is None:
                return conn.execute('''SELECT * FROM legal_sections WHERE source_id=? AND section_id=?
                    AND superseded_at IS NULL ORDER BY version DESC LIMIT 1''',(doc,sec)).fetchone()
            return conn.execute('''SELECT * FROM legal_sections WHERE source_id=? AND section_id=?
                    AND version=?''',(doc,sec,version)).fetchone()

    def check_quote(self, *, cite: str, quote: str, version: int | None = None) -> dict:
        cite=checked(cite,'cite',400)
        quote=checked(quote,'quote',2000)
        if len(normalize(quote).split()) < 5:
            return {'status':'rejected','reason':'quote shorter than five words','cite':cite}
        s=self._resolve(cite,version=version)
        if not s:
            return {'status':'rejected','reason':'source section not available','cite':cite}
        if normalize(quote).casefold() not in normalize(s['body']).casefold():
            return {'status':'rejected','reason':'quote not found verbatim in cited section','cite':cite}
        return {'status':'quote_matched','cite':f"{cite}@v{s['version']}#{s['sha256'][:12]}",
                'source_url':s['source_url'],'authority':s['authority'],
                'quoted_text':normalize(quote),
                'note':'Matching text is not proof of semantic truth, legal applicability, or source authenticity'}

    def service_spikes(self, csv_path: str | Path, *, actor: str='local_operator',
                       as_of: str | None = None) -> list[dict]:
        actor=checked(actor,'actor',120)
        rows=load_requests(str(csv_path))
        flags=[asdict(x) for x in spikes(rows,SpikeRule(),date.fromisoformat(as_of) if as_of else None)]
        if flags:
            with self.store.write() as conn:
                self.store.append(conn,'service_spike_scan',{'actor':actor,'flags':flags,
                    'input_hash':digest(Path(csv_path).read_text('utf-8')),
                    'warning':'Area-level statistical signals only; not predictions of individuals'})
        return flags

    def propose(self, *, proposed_by: str, recommendation: str, evidence_refs: list[str]) -> dict:
        proposed_by=checked(proposed_by,'proposed_by',120)
        recommendation=checked(recommendation,'recommendation',2500)
        if not isinstance(evidence_refs,list) or len(evidence_refs)>100:
            raise ValueError('evidence_refs must be a list')
        refs=[checked(item,'evidence_ref',250) for item in evidence_refs]
        if not refs:
            raise ValueError('Recommendations need at least one evidence reference')
        text_lower=recommendation.lower()
        if any(forbidden.replace('_',' ') in text_lower for forbidden in FORBIDDEN_ACTIONS):
            raise ValueError('Request names an action that cannot be performed by AXIOM0')
        id_=str(uuid.uuid4()); stamp=now()
        with self.store.write() as conn:
            conn.execute('''INSERT INTO action_queue(id,proposed_at,proposed_by,recommendation,evidence_json,status)
                VALUES(?,?,?,?,?,?)''',(id_,stamp,proposed_by,recommendation,canonical(refs),'pending'))
            self.store.append(conn,'action_proposed',{'id':id_,'proposed_by':proposed_by,
                'recommendation':recommendation,'evidence_refs':refs})
        return self.queue_entry(id_)

    def queue_entry(self,id_:str) -> dict:
        with self.store.connect() as conn:
            r=conn.execute('SELECT * FROM action_queue WHERE id=?',(id_,)).fetchone()
        if not r:
            raise ValueError('Recommendation not found')
        result=dict(r)
        result['evidence_refs']=json.loads(result.pop('evidence_json'))
        return result

    def queue(self, *, include_reviewed: bool=False) -> list[dict]:
        with self.store.connect() as conn:
            rows=conn.execute('SELECT id FROM action_queue WHERE (?=1 OR status=\'pending\') ORDER BY proposed_at DESC',
                              (int(include_reviewed),)).fetchall()
        return [self.queue_entry(r['id']) for r in rows]

    def review(self, id_:str, *, reviewer: str, decision: str, rationale: str) -> dict:
        reviewer=checked(reviewer,'reviewer',120)
        rationale=checked(rationale,'rationale',1500)
        if decision not in ('approved_for_human_followup','rejected'):
            raise ValueError('Review must approve for human follow-up or reject')
        with self.store.write() as conn:
            r=conn.execute('SELECT * FROM action_queue WHERE id=?',(id_,)).fetchone()
            if not r or r['status'] != 'pending':
                raise ValueError('No pending recommendation for this ID')
            if reviewer.casefold()==r['proposed_by'].casefold():
                raise PermissionError('Separation of duties: proposer cannot review own recommendation')
            stamp=now()
            conn.execute('''UPDATE action_queue SET status=?,reviewed_at=?,reviewed_by=?,review_note=? WHERE id=?''',
                         (decision,stamp,reviewer,rationale,id_))
            self.store.append(conn,'action_reviewed',{'id':id_,'reviewed_by':reviewer,
                'decision':decision,'rationale':rationale,
                'note':'Human follow-up only; does not authorize enforcement or expenditure'})
        return self.queue_entry(id_)
