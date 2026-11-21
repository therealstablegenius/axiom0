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
import re
import uuid
from .legacy_v02.truth import parse_source, section_hash, normalize
from .legacy_v02.warning import load_requests, spikes, SpikeRule
from .spikes_v2 import spikes_v2, SpikeRuleV2
from .store import Store, now, canonical, digest
from .semisoul import checked

FORBIDDEN_ACTIONS={
    'issue_citation','enforcement_decision','authorize_spending',
    'modify_official_record','person_level_risk_score',
}

# v0.7 guardrail: pattern families over normalised text (case, punctuation and spacing
# removed), covering common phrasings and word forms rather than one exact phrase.
# This is a GUARDRAIL that catches ordinary wording, NOT a security control: a
# determined user can still rephrase. The real controls are that AXIOM0 has no
# capability to perform these actions, and that every recommendation needs a
# separate human reviewer.
_FORBIDDEN_PATTERNS={
    'issue_citation':[r'\b(issue|write|serve|send|give|hand)\w*\s+(an?\s+|the\s+)?(citation|ticket|fine|summons|violation notice)s?\b',
                      r'\bcite\s+(the\s+)?(resident|owner|tenant|landlord|property|business|driver)s?\b',
                      r'\bissue citation\b'],
    'enforcement_decision':[r'\b(enforce|enforcement|penali[sz]e|penalty|penalties|evict\w*|condemn\w*|arrest\w*|tow(ed|ing)?\b|shut\s*off|red\s*tag\w*|padlock\w*)'],
    'authorize_spending':[r'\b(authori[sz]\w*|approv\w*|allocat\w*|spend\w*|disburs\w*|pay\w*|transfer\w*|award\w*|release\w*)\b.{0,60}\b(fund\w*|money|payment\w*|budget\w*|dollars?|grant\w*|contract\w*|expenditure\w*|\d[\d,]*\s*(usd|dollars))\b',
                          r'\bauthori[sz]e spending\b'],
    'modify_official_record':[r'\b(modif\w*|chang\w*|edit\w*|alter\w*|delet\w*|amend\w*|rewrit\w*|backdat\w*|expung\w*|remov\w*)\b.{0,60}\b(official record\w*|minutes|ordinance\w*|resolution\w*|council record\w*|journal|legislative record\w*|public record\w*)\b'],
    'person_level_risk_score':[r'\b(risk\s*scor\w*|scor\w*|rank\w*|profil\w*|predict\w*|blacklist\w*|watch\s*list\w*)\b.{0,60}\b(person|people|resident\w*|individual\w*|tenant\w*|owner\w*|household\w*|famil\w*|citizen\w*)\b'],
}


def forbidden_action(text: str) -> str | None:
    """Return the forbidden action family a recommendation appears to request, if any."""
    norm=re.sub(r'\s+',' ',re.sub(r'[^a-z0-9$]+',' ',text.casefold().replace('_',' '))).strip()
    for action,patterns in _FORBIDDEN_PATTERNS.items():
        if any(re.search(p,norm) for p in patterns):
            return action
    return None

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
                       as_of: str | None = None, method: str='v2') -> list[dict]:
        """Area-level spike scan. v2 (default): count model + seasonality + FDR control.
        v1 is kept only for comparison with earlier results."""
        actor=checked(actor,'actor',120)
        rows=load_requests(str(csv_path))
        when=date.fromisoformat(as_of) if as_of else None
        if method=='v2':
            found,summary=spikes_v2(rows,SpikeRuleV2(),when)
            flags=[asdict(x) for x in found]
        elif method=='v1':
            flags=[asdict(x) for x in spikes(rows,SpikeRule(),when)]
            summary={'rule':'SPIKE-v1','flags':len(flags),
                     'caution':'v1 has no multiple-testing correction or seasonality; expect false alarms'}
        else:
            raise ValueError('method must be v2 or v1')
        # Every scan is recorded, including scans that found nothing (absence of flags is also a result).
        with self.store.write() as conn:
            self.store.append(conn,'service_spike_scan',{'actor':actor,'flags':flags,'summary':summary,
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
        blocked=forbidden_action(recommendation)
        if blocked:
            raise ValueError(f'Recommendation appears to request a prohibited action ({blocked}). '
                             'AXIOM0 can only recommend human follow-up (inspect, review, notify, schedule); '
                             'enforcement, spending, record changes and person-level scoring stay with '
                             'authorized officials outside AXIOM0.')
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

    def review(self, id_:str, *, reviewer: str, decision: str, rationale: str,
               reviewer_auth: str='local_label') -> dict:
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
            self.store.append(conn,'action_reviewed',{'id':id_,'reviewed_by':reviewer,'reviewer_auth':reviewer_auth,
                'decision':decision,'rationale':rationale,
                'note':'Human follow-up only; does not authorize enforcement or expenditure'})
        return self.queue_entry(id_)
