"""Best-effort integrity consistency check for ingested legal and document records.

Signed source snapshots were introduced in v0.6; older v0.5 source events
have no snapshot commitment and are reported as legacy coverage.
"""
from __future__ import annotations
import json
from .store import Store,IntegrityError,canonical,digest
from .legacy_v02.truth import section_hash


def verify_content(store: Store) -> dict:
    with store.connect() as db:
        docs=db.execute('SELECT id,content,content_hash FROM documents').fetchall()
        secs=db.execute('SELECT * FROM legal_sections').fetchall()
        audits=db.execute("SELECT payload_json FROM events WHERE event_type='legal_source_changed' ORDER BY seq").fetchall()
    for d in docs:
        if digest(d['content'])!=d['content_hash']:
            raise IntegrityError('Document content mismatch: '+d['id'])
    for s in secs:
        if section_hash(s['title'],s['body'])!=s['sha256']:
            raise IntegrityError('Legal section content mismatch: '+s['source_id']+':'+s['section_id'])
    snap_latest={}
    legacy_ids=set()
    for a in audits:
        obj=json.loads(a['payload_json'])
        doc_id=obj['document_id']
        if 'snapshot_sha256' in obj:
            snap_latest[doc_id]=obj['snapshot_sha256']
        else:
            legacy_ids.add(doc_id)
    for doc_id,hash_ in snap_latest.items():
        active=sorted((s for s in secs if s['source_id']==doc_id and s['superseded_at'] is None),
                      key=lambda r:r['section_id'])
        current=digest(canonical([[s['section_id'],s['version'],s['sha256']] for s in active]))
        if current!=hash_:
            raise IntegrityError('Active legal-source history disagrees with signed ledger snapshot: '+doc_id)
    return {'documents_checked':len(docs),'legal_versions_checked':len(secs),
            'signed_current_source_snapshots':len(snap_latest),
            'legacy_sources_without_signed_snapshot':len(legacy_ids-set(snap_latest)),
            'boundary':'historical database/key rollback remains outside local-only threat model'}
