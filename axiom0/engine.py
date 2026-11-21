"""Living City: source-aware evidence, occurrence, hypothesis and feedback cycles."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from collections import Counter
import re
import uuid
from pathlib import Path
from .store import Store, now, canonical, digest
from .mca import MCAAtom
from . import numerics

AUTHORITY = {'charter','ordinance','state_law','federal_law','policy','public_record','other'}
STATUS = {'candidate','corroborated','verified','rejected'}


def _nonempty(v: str, label: str, maximum: int = 20000) -> str:
    if not isinstance(v,str) or not v.strip() or len(v)>maximum:
        raise ValueError(f'{label} must be a nonempty string of at most {maximum} characters')
    return v.strip()


def _date(v: str, label: str) -> str:
    _nonempty(v,label,64)
    try:
        parsed = datetime.fromisoformat(v.replace('Z','+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('timezone required')
        return parsed.astimezone(timezone.utc).isoformat(timespec='seconds')
    except ValueError as e:
        raise ValueError(f'{label} must be timezone-aware ISO-8601') from e


def _row(row):
    return dict(row) if row is not None else None


def _tokens(text: str) -> list[str]:
    from .legacy_v02.retrieve import tokens
    return tokens(text)


def _excerpt(body: str, q_terms: list[str], before: int = 240, after: int = 1250) -> str:
    """Window around the sentence sharing the most query terms (first sentence on ties)."""
    best_pos, best_hits = 0, 0
    q = set(q_terms)
    for m in re.finditer(r'[^.;:\n]+[.;:\n]?', body):
        hits = len(q & set(_tokens(m.group(0))))
        if hits > best_hits:
            best_pos, best_hits = m.start(), hits
    return body[max(0, best_pos - before):best_pos + after]


class LivingCity:
    def __init__(self, data_dir: str | Path):
        self.store = Store(data_dir)

    def identity(self) -> dict:
        with self.store.connect() as conn:
            mind = conn.execute('SELECT model,authorized_by,changed_at FROM mind_history ORDER BY changed_at DESC LIMIT 1').fetchone()
        return {'semisoul_id':self.store.identity.id,
                'public_key':self.store.identity.public_raw.hex(),
                'mission':'Local-first municipal early warning with evidence, constraints and human review',
                'mind':_row(mind), 'model_replaceable':True}

    def swap_mind(self, model: str, authorized_by: str, reason: str) -> dict:
        model = _nonempty(model,'model',100)
        authorized_by = _nonempty(authorized_by,'authorized_by',100)
        reason = _nonempty(reason,'reason',1000)
        stamp = now()
        id_ = str(uuid.uuid4())
        with self.store.write() as conn:
            conn.execute('INSERT INTO mind_history(event_id,model,authorized_by,reason,changed_at) '
                         'VALUES(?,?,?,?,?)', (id_,model,authorized_by,reason,stamp))
            self.store.append(conn,'mind_replaced',{'model':model,'authorized_by':authorized_by,
                                                    'reason':reason,'event_id':id_})
        return self.identity()

    def add_document(self, *, title: str, authority: str, jurisdiction: str,
                     citation: str, version: str, content: str,
                     source_url: str, effective_at: str | None = None,
                     source_reviewed: bool = False) -> dict:
        if authority not in AUTHORITY:
            raise ValueError(f'authority must be one of {sorted(AUTHORITY)}')
        title = _nonempty(title,'title',300)
        jurisdiction = _nonempty(jurisdiction,'jurisdiction',150)
        citation = _nonempty(citation,'citation',200)
        version = _nonempty(version,'version',100)
        content = _nonempty(content,'content',2_000_000)
        source_url = _nonempty(source_url,'source_url',2048)
        stamp = now()
        if effective_at is not None:
            effective_at = _date(effective_at,'effective_at')
        doc_id = digest(canonical({'title':title,'citation':citation,'version':version,
                                   'content_hash':digest(content)}))[:32]
        with self.store.write() as conn:
            if conn.execute('SELECT 1 FROM documents WHERE id=?',(doc_id,)).fetchone():
                return {'id':doc_id,'duplicate':True}
            conn.execute('''INSERT INTO documents(id,title,authority,jurisdiction,citation,version,
                effective_at,source_url,source_reviewed,acquired_at,content,content_hash)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (doc_id,title,authority,jurisdiction,citation,version,effective_at,
                 source_url,int(source_reviewed),stamp,content,digest(content)))
            self.store.append(conn,'document_imported',{'id':doc_id,'content_sha256':digest(content),
                 'citation':citation,'authority':authority,'source_reviewed':bool(source_reviewed)})
        return {'id':doc_id,'duplicate':False,'content_sha256':digest(content)}

    def add_occurrence(self, *, external_id: str, event_at: str,
                       area: str, category: str, summary: str,
                       source_label: str, source_url: str,
                       confidence_note: str, source_document_id: str | None = None) -> dict:
        # Area is an aggregate/service geography, never a named person's dossier.
        external_id = _nonempty(external_id,'external_id',200)
        event_at = _date(event_at,'event_at')
        if datetime.fromisoformat(event_at) > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('An occurrence cannot be dated in the future; future conditions belong to hypotheses or forecasts')
        area = _nonempty(area,'area',180)
        category = _nonempty(category,'category',120)
        summary = _nonempty(summary,'summary',4000)
        source_label = _nonempty(source_label,'source_label',200)
        source_url = _nonempty(source_url,'source_url',2048)
        confidence_note = _nonempty(confidence_note,'confidence_note',500)
        if source_document_id:
            _nonempty(source_document_id,'source_document_id',64)
        external_key = digest(canonical([source_label,external_id]))
        payload = {'external_id':external_id,'event_at':event_at,'area':area,'category':category,
                   'summary':summary,'source_label':source_label,'source_url':source_url,
                   'confidence_note':confidence_note,'source_document_id':source_document_id}
        content_hash = digest(canonical(payload))
        id_ = str(uuid.uuid4())
        with self.store.write() as conn:
            prior = conn.execute('SELECT id,content_hash FROM occurrences WHERE external_key=?',(external_key,)).fetchone()
            if prior:
                if prior['content_hash'] != content_hash:
                    raise ValueError('Occurrence external ID already exists with different content; submit an amended record under a new external ID')
                return {'id':prior['id'],'duplicate':True}
            if source_document_id and not conn.execute('SELECT 1 FROM documents WHERE id=?',(source_document_id,)).fetchone():
                raise ValueError('source_document_id does not exist')
            conn.execute('''INSERT INTO occurrences(id,external_key,event_at,observed_at,area,category,
                summary,source_label,source_url,confidence_note,source_document_id,content_hash)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (id_,external_key,event_at,now(),area,category,summary,source_label,
                 source_url,confidence_note,source_document_id,content_hash))
            self.store.append(conn,'occurrence_observed',{'id':id_,'event_at':event_at,
                   'area':area,'category':category,'content_hash':content_hash,'source_label':source_label})
        return {'id':id_,'duplicate':False}

    def occurrences(self, limit: int = 100) -> list[dict]:
        with self.store.connect() as conn:
            return [dict(x) for x in conn.execute(
                'SELECT id,event_at,observed_at,area,category,summary,source_label,source_url,confidence_note,source_document_id FROM occurrences ORDER BY event_at DESC LIMIT ?',
                (min(max(limit,1),1000),)).fetchall()]

    def documents(self, limit: int = 100) -> list[dict]:
        with self.store.connect() as conn:
            return [dict(x) for x in conn.execute(
                'SELECT id,title,authority,jurisdiction,citation,version,effective_at,source_url,source_reviewed,acquired_at,content_hash FROM documents ORDER BY acquired_at DESC LIMIT ?',
                (min(max(limit,1),1000),)).fetchall()]

    def search_documents(self, query: str, limit: int = 6) -> list[dict]:
        """Rank imported documents and current legal sections with BM25 (v0.7).

        Same tokenizer and stop-words as the quote path's retriever, so short common
        words do not count and long documents are length-normalised. Excerpts are
        centred on the best-matching sentence. Deterministic: same library + question
        -> same sources in the same order.
        """
        query = _nonempty(query,'query',1000)
        q_terms = list(dict.fromkeys(_tokens(query)))[:24]
        if not q_terms:
            return []
        with self.store.connect() as conn:
            rows = conn.execute('SELECT * FROM documents ORDER BY acquired_at DESC LIMIT 2500').fetchall()
            legal_rows = conn.execute('''SELECT * FROM legal_sections WHERE superseded_at IS NULL
                ORDER BY ingested_at DESC LIMIT 2500''').fetchall()
        candidates = []
        for row in rows:
            candidates.append((f"{row['title']} {row['citation']} {row['content']}", row['content'],
                {'id':row['id'],'title':row['title'],'citation':row['citation'],
                 'authority':row['authority'],'version':row['version'],
                 'source_url':row['source_url'],'source_reviewed':bool(row['source_reviewed'])}))
        for law in legal_rows:
            candidates.append((f"{law['section_id']} {law['title']} {law['body']}", law['body'],
                {'id':f"legal:{law['source_id']}:{law['section_id']}:v{law['version']}",
                 'title':law['title'],'citation':f"{law['source_id']}:{law['section_id']}@v{law['version']}",
                 'authority':law['authority'],'version':str(law['version']),
                 'source_url':law['source_url'] or '', 'source_reviewed':False}))
        if not candidates:
            return []
        docs = [_tokens(text) for text,_,_ in candidates]
        n = len(docs); avgdl = (sum(len(d) for d in docs)/n) or 1.0
        df = Counter()
        for d in docs:
            df.update(set(d))
        k1, b = 1.5, 0.75
        scored = []
        for (searchable, body, meta), d in zip(candidates, docs):
            tf = Counter(d); score = 0.0
            for term in q_terms:
                f = tf.get(term)
                if f:
                    idf = math.log(1 + (n - df[term] + 0.5)/(df[term] + 0.5))
                    score += idf * f * (k1 + 1)/(f + k1*(1 - b + b*len(d)/avgdl))
            if score > 0:
                scored.append((score, {**meta, 'retrieval_score': round(score, 4),
                                       'excerpt': _excerpt(body, q_terms)}))
        scored.sort(key=lambda x:(-x[0],x[1]['citation']))
        return [r for _,r in scored[:min(max(limit,1),20)]]

    def _evidence(self, conn, hypothesis_id):
        rows = conn.execute('''SELECT o.id,o.event_at,o.area,o.category,o.summary,o.source_label,o.source_url, e.stance, e.note
            FROM occurrences o JOIN hypothesis_evidence e ON e.occurrence_id=o.id
            WHERE e.hypothesis_id=? ORDER BY o.event_at''',(hypothesis_id,)).fetchall()
        return [dict(r) for r in rows]

    def _attach(self, conn, hypothesis_id: str, occurrence_ids: list[str]) -> int:
        added = 0
        for occurrence_id in dict.fromkeys(occurrence_ids):
            if not conn.execute('SELECT 1 FROM occurrences WHERE id=?',(occurrence_id,)).fetchone():
                raise ValueError(f'Occurrence not found: {occurrence_id}')
            cur = conn.execute('INSERT OR IGNORE INTO hypothesis_evidence(hypothesis_id,occurrence_id) VALUES(?,?)',
                               (hypothesis_id,occurrence_id))
            added += cur.rowcount
        return added

    def create_hypothesis(self, *, claim: str, area: str, category: str,
                          occurrence_ids: list[str], signal_key: str | None = None) -> dict:
        claim = _nonempty(claim,'claim',1500)
        area = _nonempty(area,'area',180)
        category = _nonempty(category,'category',120)
        if not occurrence_ids:
            raise ValueError('A hypothesis needs at least one source occurrence')
        hyp_id = str(uuid.uuid4())
        stamp = now()
        with self.store.write() as conn:
            conn.execute('''INSERT INTO hypotheses(id,signal_key,claim,area,category,status,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?)''',
                         (hyp_id,signal_key,claim,area,category,'candidate',stamp,stamp))
            added = self._attach(conn,hyp_id,occurrence_ids)
            self.store.append(conn,'hypothesis_proposed',{'id':hyp_id,'claim':claim,'status':'candidate',
                     'evidence_count':added,'signal_key':signal_key})
        return self.get_hypothesis(hyp_id)

    def attach_evidence(self, hypothesis_id: str, occurrence_id: str, *, stance: str = 'neutral', note: str = '') -> dict:
        if stance not in {'neutral','supports','contradicts'}:
            raise ValueError('Invalid evidence stance')
        if not isinstance(note,str) or len(note)>2000:
            raise ValueError('Evidence note too long')
        with self.store.write() as conn:
            if not conn.execute('SELECT 1 FROM hypotheses WHERE id=?',(hypothesis_id,)).fetchone():
                raise ValueError('Hypothesis not found')
            self._attach(conn,hypothesis_id,[occurrence_id])
            conn.execute('UPDATE hypothesis_evidence SET stance=?,note=? WHERE hypothesis_id=? AND occurrence_id=?',
                         (stance,note,hypothesis_id,occurrence_id))
            conn.execute('UPDATE hypotheses SET updated_at=? WHERE id=?',(now(),hypothesis_id))
            self.store.append(conn,'hypothesis_evidence_reviewed',{'id':hypothesis_id,'occurrence_id':occurrence_id,
                          'stance':stance,'note':note})
        return self.get_hypothesis(hypothesis_id)

    def get_hypothesis(self, id_: str) -> dict:
        with self.store.connect() as conn:
            h = conn.execute('SELECT * FROM hypotheses WHERE id=?',(id_,)).fetchone()
            if not h:
                raise ValueError('Hypothesis not found')
            result = dict(h)
            result['evidence'] = self._evidence(conn,id_)
            result['source_label_count'] = len({e['source_label'] for e in result['evidence']})
            result['independence_verified'] = False
            return result

    def hypotheses(self, limit: int = 100) -> list[dict]:
        with self.store.connect() as conn:
            ids = [r['id'] for r in conn.execute('SELECT id FROM hypotheses ORDER BY updated_at DESC LIMIT ?',
                                                 (min(max(limit,1),1000),)).fetchall()]
        return [self.get_hypothesis(id_) for id_ in ids]

    def review_hypothesis(self, id_: str, *, status: str, reviewer: str, note: str, proof_reference: str | None = None,
                          reviewer_auth: str = 'local_label') -> dict:
        if status not in {'corroborated','verified','rejected','candidate'}:
            raise ValueError('Invalid review status')
        reviewer = _nonempty(reviewer,'reviewer',100)
        note = _nonempty(note,'note',3000)
        if status=='verified':
            proof_reference = _nonempty(proof_reference,'proof_reference (auditable basis for verification)',1500)
        elif proof_reference is not None:
            proof_reference = _nonempty(proof_reference,'proof_reference',1500)
        with self.store.write() as conn:
            h = conn.execute('SELECT status FROM hypotheses WHERE id=?',(id_,)).fetchone()
            if not h:
                raise ValueError('Hypothesis not found')
            evidence = self._evidence(conn,id_)
            if status in {'corroborated','verified'} and not evidence:
                raise ValueError('Evidence required for positive finding')
            conn.execute('UPDATE hypotheses SET status=?,reviewer=?,review_note=?,proof_reference=?,updated_at=? WHERE id=?',
                         (status,reviewer,note,proof_reference,now(),id_))
            self.store.append(conn,'human_review_recorded',{'id':id_,'from':h['status'],'to':status,
                            'reviewer':reviewer,'reviewer_auth':reviewer_auth,'note':note,'proof_reference':proof_reference,
                            'evidence_ids':[e['id'] for e in evidence]})
        return self.get_hypothesis(id_)

    def scan_signals(self, *, days: int = 30, min_occurrences: int = 3,
                     min_source_labels: int = 2) -> list[dict]:
        """Deterministic aggregation; never a calibrated forecast or proof of violation."""
        if not (1<=days<=3650 and 2<=min_occurrences<=100 and 1<=min_source_labels<=100):
            raise ValueError('Invalid scan thresholds')
        since = (datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
        with self.store.connect() as conn:
            rows = conn.execute('SELECT * FROM occurrences WHERE event_at >= ? ORDER BY event_at',(since,)).fetchall()
        clusters = defaultdict(list)
        for r in rows:
            clusters[(r['area'].casefold(),r['category'].casefold())].append(dict(r))
        signals = []
        for (_, _), events in sorted(clusters.items()):
            sources = {e['source_label'] for e in events}
            if len(events)<min_occurrences or len(sources)<min_source_labels:
                continue
            area,cat = events[0]['area'],events[0]['category']
            signal_key = digest(canonical([area.casefold(),cat.casefold(),days,min_occurrences,min_source_labels]))
            with self.store.connect() as conn:
                h = conn.execute('SELECT id FROM hypotheses WHERE signal_key=?',(signal_key,)).fetchone()
            if not h:
                claim = f'Recurring {cat} reports in {area} merit investigation; no underlying cause or violation is established.'
                try:
                    hypothesis = self.create_hypothesis(claim=claim,area=area,category=cat,
                            occurrence_ids=[e['id'] for e in events],signal_key=signal_key)
                except Exception:
                    # Concurrent scan may have produced the signal; non-integrity errors should propagate.
                    with self.store.connect() as conn:
                        concurrent = conn.execute('SELECT id FROM hypotheses WHERE signal_key=?',(signal_key,)).fetchone()
                    if not concurrent: raise
                    hypothesis = self.get_hypothesis(concurrent['id'])
            else:
                with self.store.write() as conn:
                    added = self._attach(conn,h['id'],[e['id'] for e in events])
                    if added:
                        conn.execute('UPDATE hypotheses SET updated_at=? WHERE id=?',(now(),h['id']))
                        self.store.append(conn,'hypothesis_revisited',{'id':h['id'], 'new_evidence_count':added})
                hypothesis = self.get_hypothesis(h['id'])
            signals.append({'hypothesis_id':hypothesis['id'],'area':area,'category':cat,
                      'report_count':len(events),'distinct_source_labels':len(sources),
                      'source_independence_verified':False,'status':hypothesis['status'],
                      'meaning':'Threshold exceeded; investigate, not an asserted prediction'})
        return signals

    def mca_record(self, *, identity: str, purpose: str, observation: str,
                   constraint: str, feedback: str) -> dict:
        atom = MCAAtom(*[_nonempty(x,n,2000) for n,x in
                        [('identity',identity),('purpose',purpose),('observation',observation),
                         ('constraint',constraint),('feedback',feedback)]])
        with self.store.write() as conn:
            self.store.append(conn,'mca_atom_recorded',atom.as_dict())
        return atom.as_dict()

    def symbolic_state(self, vector: list[int]) -> dict:
        x = numerics.normalize(vector)
        return {'vector':list(x),'genesis':list(numerics.GENESIS),
                'soul':list(numerics.SOUL),'resonance_genesis':numerics.resonance(x,numerics.GENESIS),
                'resonance_soul':numerics.resonance(x,numerics.SOUL),
                'harmony':numerics.harmony(x),
                'validity':'Experimental symbolic telemetry only. Never factual proof or calibrated risk.'}

    def stats(self) -> dict:
        with self.store.connect() as conn:
            names = ('documents','occurrences','hypotheses','events')
            counts = {n: conn.execute(f'SELECT COUNT(*) AS n FROM {n}').fetchone()['n'] for n in names}
        return {**counts,'semisoul_id':self.store.identity.id,'run_mode':'local-first',
                'official_sources_bundled':False}
