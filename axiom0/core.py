"""Stable, trusted-local-code AXIOM0 facade for the v0.2 integration contract.

This is NOT an untrusted plugin security sandbox. Python executed under the same
OS account can access the SQLite database/private key. Remote clients must use
API keys on a loopback-bound server; public deployment requires OIDC and RBAC.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .engine import LivingCity
from .municipal import MunicipalCore
from .semisoul import SemiSoul
from .intention369 import IntentionLab
from .legacy_v02.retrieve import bm25, best_sentences
from .legacy_v02.truth import Section
from .store import canonical


class TruthLibraryBridge:
    def __init__(self, municipal: MunicipalCore):
        self._municipal = municipal

    def ingest_text(self, raw: str, *, actor: str = 'local_operator') -> dict:
        return self._municipal.ingest_sections(raw, actor=actor)

    def ingest_file(self, path: str | Path, *, actor: str = 'local_operator') -> dict:
        return self.ingest_text(Path(path).read_text(encoding='utf-8'), actor=actor)

    def current(self, limit: int = 200) -> list[dict]:
        return self._municipal.sections(limit=limit)

    def check_quote(self, cite: str, quote: str) -> dict:
        return self._municipal.check_quote(cite=cite, quote=quote)


class Axiom0:
    """Trusted local operator interface; all state changes use a signed ledger."""
    def __init__(self, data_dir: str | Path = './axiom0_data'):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.city = LivingCity(self.data_dir)
        self.store = self.city.store
        self.municipal = MunicipalCore(self.store)
        self.library = TruthLibraryBridge(self.municipal)
        self.semisoul = SemiSoul(self.store)
        self.intentions = IntentionLab(self.store)

    def set_admin(self, admin: str) -> dict:
        # Enrollment is a local-OS-operator action, not a remote untrusted API call.
        if not isinstance(admin, str) or not 1 <= len(admin.strip()) <= 100:
            raise ValueError('Admin name required')
        admin = admin.strip()
        with self.store.write() as db:
            row = db.execute('SELECT value FROM metadata WHERE key=?',('local_admin',)).fetchone()
            if row and row['value'] != admin:
                raise PermissionError('An administrator is already configured; do not silently replace')
            if not row:
                db.execute('INSERT INTO metadata(key,value) VALUES(?,?)',('local_admin',admin))
                self.store.append(db,'local_operator_enrolled',{'admin':admin,'scope':'local OS trust; not password authentication'})
        return {'admin':admin,'note':'Local operator label only; protect data directory with OS permissions'}

    def _local_authorize(self, user: str) -> None:
        if not isinstance(user,str) or not user.strip():
            raise PermissionError('Local actor name is required')
        with self.store.connect() as db:
            row=db.execute('SELECT value FROM metadata WHERE key=?',('local_admin',)).fetchone()
        if row and user.strip() not in (row['value'], 'api_service'):
            raise PermissionError('Unknown local operator; use the configured admin label')

    def ask(self, user: str, question: str, use_llm: bool | None = None) -> dict:
        self._local_authorize(user)
        if not isinstance(question,str) or not question.strip() or len(question)>1500:
            raise ValueError('Question required (max 1500 characters)')
        with self.store.connect() as db:
            rows=db.execute('''SELECT source_id,section_id,version,title,body,sha256,authority,effective,source_url
                                 FROM legal_sections WHERE superseded_at IS NULL''').fetchall()
        candidates=[Section(r['source_id'],r['section_id'],r['title'],r['body'],r['sha256'],
                            r['version'],r['authority'],r['effective'],r['source_url']) for r in rows]
        ranked=bm25(question,candidates,k=6)
        findings=[]
        for sec, score in ranked:
            for sentence in best_sentences(question,sec.text,n=2):
                checked=self.municipal.check_quote(cite=sec.cite,quote=sentence,version=sec.version)
                if checked['status']=='quote_matched':
                    findings.append({'text':sentence,'cite':checked['cite'],'source_url':sec.source_url,
                                     'authority':sec.authority,'effective':sec.effective,
                                     'proof_gate':'matching_source_quote_not_legal_conclusion'})
        draft=None
        if use_llm is True:
            from .llm import OllamaMind
            draft=OllamaMind().answer(self.city, question)
        result={'question':question,'mode':'legal_quotes' if draft is None else 'legal_quotes_plus_local_llm',
                'status':'source_excerpt_only' if findings else 'insufficient_evidence',
                'findings':findings,'rejected':[],
                'confidence':'not_calibrated','draft':draft,
                'disclaimer':'Quoted source material only; no independent authenticity or legal applicability determination'}
        with self.store.write() as db:
            ledger_head=self.store.append(db,'research_queried',{'actor':user,'question':question,
                'status':result['status'],'citations':[f['cite'] for f in findings],
                'has_model_draft':draft is not None})
        result['ledger_head']=ledger_head
        return result

    def ingest(self, user: str, path: str | Path) -> list[dict]:
        self._local_authorize(user)
        return self.municipal.monitor(path,actor=user) if Path(path).is_dir() else [self.library.ingest_file(path,actor=user)]

    monitor=ingest

    def warn(self, user: str, csv_path: str | Path) -> list[dict]:
        self._local_authorize(user)
        return self.municipal.service_spikes(csv_path,actor=user)

    def recommend(self, user: str, recommendation: str, evidence_refs: list[str]) -> dict:
        self._local_authorize(user)
        return self.municipal.propose(proposed_by=user,recommendation=recommendation,evidence_refs=evidence_refs)

    def queue(self) -> list[dict]:
        return self.municipal.queue()

    def review(self, user: str, recommendation_id: str, decision: str, note: str) -> dict:
        self._local_authorize(user)
        return self.municipal.review(recommendation_id,reviewer=user,decision=decision,rationale=note)

    def verify(self) -> dict:
        out=self.semisoul.verify()
        from .integrity import verify_content
        out['source_integrity']=verify_content(self.store)
        out['verified_events']=out['signed_events']
        return out

    def status(self) -> dict:
        return {'identity':self.city.identity(),'stats':self.city.stats(),
                'semisoul':self.semisoul.profile()}
