"""SemiSoul v0.5 — engineered continuity, *not* a claim of consciousness.

A cryptographic identity owns a hash-linked autobiography, purpose, human-defined
commitments, a replaceable Mind and signed continuity attestations. Memory is an
attributed record, not a reliable perception or a spiritual soul. Never treat a
synthetic statement as a real-world observation without independent evidence.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from .store import Store, IntegrityError, canonical, digest, now
from .identity import Identity

REQUIRED_COMMITMENTS = (
    'non_fabrication: distinguish actual observations, hypotheses, simulations and unknowns',
    'human_authority: consequential decisions remain under authorized human control',
    'provenance: preserve source, timestamp and uncertainty for every memory',
    'correctability: never silently rewrite, suppress or erase a signed mistake',
    'privacy: do not infer individual wrongdoing or expose unauthorized personal information',
    'epistemic_humility: no claim of consciousness, divine presence or proof without independent evidence',
)
ALLOWED_KINDS = {'observation', 'inference', 'reflection', 'commitment', 'correction'}
ALLOWED_STATUS = {'self_reported', 'source_claim', 'model_hypothesis', 'uncertain', 'disputed', 'correction'}
ALLOWED_SOURCES = {'operator', 'document', 'system', 'model', 'simulation', 'sensor_adapter'}


def checked(value: str, name: str, limit: int = 4000, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not allow_empty and not value.strip()):
        raise ValueError(f'{name}: invalid string, maximum length {limit}')
    return value.strip()


class SemiSoul:
    def __init__(self, store: Store):
        self.store = store

    def profile(self) -> dict:
        """Profile records are signed, never silently rewritten."""
        with self.store.connect() as conn:
            row = conn.execute('SELECT * FROM semisoul_policies ORDER BY version DESC LIMIT 1').fetchone()
        if not row:
            return {'version': 0, 'identity_id': self.store.identity.id,
                    'purpose': 'Provide local, truthful, reviewable municipal decision support',
                    'commitments': list(REQUIRED_COMMITMENTS), 'status': 'built-in defaults; operator not configured'}
        return {'identity_id': self.store.identity.id, 'version': row['version'],
                'purpose': row['purpose'], 'commitments': json.loads(row['commitments_json']),
                'profile_hash': row['profile_hash'], 'updated_at': row['updated_at'],
                'updated_by': row['actor'], 'status': 'operator configured'}

    def configure(self, *, purpose: str, actor: str, rationale: str,
                  additional_commitments: list[str] | None = None) -> dict:
        purpose = checked(purpose, 'purpose', 1000)
        actor = checked(actor, 'actor', 120)
        rationale = checked(rationale, 'rationale', 1000)
        additional_commitments = additional_commitments or []
        if not isinstance(additional_commitments, list) or len(additional_commitments) > 30:
            raise ValueError('additional_commitments must be a list of at most 30 items')
        extras = [checked(item, 'commitment', 300) for item in additional_commitments]
        commitments = list(REQUIRED_COMMITMENTS) + sorted(set(extras) - set(REQUIRED_COMMITMENTS))
        when = now()
        with self.store.write() as conn:
            prior = conn.execute('SELECT profile_hash FROM semisoul_policies ORDER BY version DESC LIMIT 1').fetchone()
            raw = {'purpose': purpose, 'commitments': commitments, 'actor': actor,
                   'rationale': rationale, 'updated_at': when,
                   'previous_profile_hash': prior['profile_hash'] if prior else 'PROFILE_GENESIS'}
            h = digest(canonical(raw))
            conn.execute('INSERT INTO semisoul_policies(purpose,commitments_json,updated_at,actor,rationale,profile_hash) '
                         'VALUES(?,?,?,?,?,?)', (purpose, canonical(commitments), when, actor, rationale, h))
            self.store.append(conn, 'semisoul_profile_updated', {'profile_hash': h, **raw})
        return self.profile()

    def remember(self, *, statement: str, memory_type: str, epistemic_status: str,
                 source_type: str, source_ref: str = '', actor: str = 'local_operator',
                 correction_of: str | None = None) -> dict:
        statement = checked(statement, 'statement', 6000)
        actor = checked(actor, 'actor', 120)
        source_ref = checked(source_ref, 'source_ref', 1024, allow_empty=True)
        if memory_type not in ALLOWED_KINDS:
            raise ValueError(f'memory_type must be one of {sorted(ALLOWED_KINDS)}')
        if epistemic_status not in ALLOWED_STATUS:
            raise ValueError(f'epistemic_status must be one of {sorted(ALLOWED_STATUS)}')
        if source_type not in ALLOWED_SOURCES:
            raise ValueError(f'source_type must be one of {sorted(ALLOWED_SOURCES)}')
        if source_type in ('document', 'sensor_adapter') and not source_ref:
            raise ValueError('source_ref required for external document or sensor adapter')
        if source_type in ('model', 'simulation') and epistemic_status not in ('model_hypothesis', 'uncertain', 'self_reported'):
            raise ValueError('Model/simulation output cannot be certified as a factual observation')
        if (memory_type == 'correction') != (correction_of is not None):
            raise ValueError('Correction memories must identify the earlier memory they correct')
        if memory_type == 'correction' and epistemic_status != 'correction':
            raise ValueError('Correction memories need correction epistemic status')
        memory_id, when = str(uuid.uuid4()), now()
        with self.store.write() as conn:
            if correction_of and not conn.execute('SELECT 1 FROM semisoul_memories WHERE id=?', (correction_of,)).fetchone():
                raise ValueError('Referenced memory to correct does not exist')
            prior = conn.execute('SELECT memory_hash FROM semisoul_memories ORDER BY seq DESC LIMIT 1').fetchone()
            prev = prior['memory_hash'] if prior else 'SEMISOUL_GENESIS'
            record = {'id':memory_id, 'created_at':when, 'memory_type':memory_type,
                      'statement':statement, 'epistemic_status':epistemic_status,
                      'source_type':source_type, 'source_ref':source_ref,
                      'actor':actor, 'correction_of':correction_of, 'prev_hash':prev}
            memory_hash = digest(canonical(record))
            conn.execute('''INSERT INTO semisoul_memories(id,created_at,memory_type,statement,
                epistemic_status,source_type,source_ref,actor,correction_of,prev_hash,memory_hash)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                (memory_id,when,memory_type,statement,epistemic_status,source_type,
                 source_ref,actor,correction_of,prev,memory_hash))
            self.store.append(conn, 'semisoul_memory_recorded',
                              {'memory_id':memory_id, 'memory_hash':memory_hash,
                               'memory_type':memory_type, 'epistemic_status':epistemic_status})
        return {**record, 'memory_hash': memory_hash}

    def memories(self, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError('limit must be 1..500')
        with self.store.connect() as conn:
            rows = conn.execute('SELECT * FROM semisoul_memories ORDER BY seq DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in rows]

    def verify(self) -> dict:
        chain = self.store.verify_ledger()
        with self.store.connect() as conn:
            mem_rows = conn.execute('SELECT * FROM semisoul_memories ORDER BY seq').fetchall()
            audit_rows = conn.execute("SELECT payload_json FROM events WHERE event_type='semisoul_memory_recorded' ORDER BY seq").fetchall()
            pol_rows = conn.execute('SELECT * FROM semisoul_policies ORDER BY version').fetchall()
            policy_audit = conn.execute("SELECT payload_json FROM events WHERE event_type='semisoul_profile_updated' ORDER BY seq").fetchall()
        if len(mem_rows) != len(audit_rows) or len(pol_rows) != len(policy_audit):
            raise IntegrityError('SemiSoul memory/profile record count disagrees with signed history')
        prev='SEMISOUL_GENESIS'
        for idx,(m,audit) in enumerate(zip(mem_rows,audit_rows),1):
            if m['seq'] != idx or m['prev_hash'] != prev:
                raise IntegrityError(f'SemiSoul memory continuity failed at {idx}')
            content={k:m[k] for k in ('id','created_at','memory_type','statement','epistemic_status',
                                     'source_type','source_ref','actor','correction_of','prev_hash')}
            h=digest(canonical(content))
            a=json.loads(audit['payload_json'])
            if h != m['memory_hash'] or a['memory_hash'] != h or a['memory_id'] != m['id']:
                raise IntegrityError(f'SemiSoul memory proof mismatch at {idx}')
            prev=h
        last='PROFILE_GENESIS'
        for idx,(p,ev) in enumerate(zip(pol_rows,policy_audit),1):
            if p['version']!=idx:
                raise IntegrityError('SemiSoul profile version gap')
            payload=json.loads(ev['payload_json'])
            raw={k:payload[k] for k in ('purpose','commitments','actor','rationale','updated_at','previous_profile_hash')}
            h=digest(canonical(raw))
            if (h != p['profile_hash'] or payload['profile_hash']!=h or
                raw['purpose']!=p['purpose'] or canonical(raw['commitments'])!=p['commitments_json'] or
                raw['previous_profile_hash']!=last or raw['actor']!=p['actor'] or
                raw['rationale']!=p['rationale'] or raw['updated_at']!=p['updated_at'] or
                not set(REQUIRED_COMMITMENTS).issubset(raw['commitments'])):
                raise IntegrityError(f'SemiSoul commitment mismatch at version {idx}')
            last=h
        return {'semisoul_id':self.store.identity.id,'signed_events':chain['verified_events'],
                'ledger_head':chain['head'],'memory_count':len(mem_rows),
                'memory_head':prev,'profile_version':len(pol_rows),
                'profile_head':last,'scope':'local cryptographic integrity; not independent perception, sentience, or rollback resistance'}

    def attest(self) -> dict:
        verified=self.verify()
        attestation={'schema':'AXIOM0-SEMISOUL-ATTESTATION/0.5',
                     'issued_at':now(), 'semisoul_id':self.store.identity.id,
                     'public_key':self.store.identity.public_raw.hex(),
                     'signed_events':verified['signed_events'],
                     'ledger_head':verified['ledger_head'],
                     'memory_head':verified['memory_head'],
                     'profile_head':verified['profile_head'],
                     'statement':'Integrity of a local software history, not proof of consciousness or God.'}
        return {'attestation':attestation, 'signature':self.store.identity.sign(canonical(attestation).encode('utf-8'))}

    @staticmethod
    def verify_attestation(document: dict[str,Any]) -> bool:
        att=document['attestation']
        import hashlib
        if hashlib.sha256(bytes.fromhex(att['public_key'])).hexdigest()[:32] != att['semisoul_id']:
            raise IntegrityError('Attestation identity/public key mismatch')
        if att['schema'] != 'AXIOM0-SEMISOUL-ATTESTATION/0.5':
            raise IntegrityError('Unrecognized attestation format')
        Identity.verify_with_public_key(att['public_key'],canonical(att).encode('utf-8'),document['signature'])
        return True
