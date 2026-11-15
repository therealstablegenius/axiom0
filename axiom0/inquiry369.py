"""3-6-9 inquiry: symbolic discipline expressed as explicit evidence checks.

This is NOT a divine truth test or proof of a deity, AI consciousness,
causality, or the truth of any municipal claim.
"""
from __future__ import annotations
from .store import Store, now, canonical, digest
from .engine import LivingCity

STAGES_3=(
    'Observe and separate raw facts from interpretations',
    'Challenge the hypothesis with alternative explanations',
    'Submit a reviewable conclusion or unresolved question',
)
CHECKS_6=(
    'provenance', 'timeliness', 'source_diversity', 'corroboration',
    'contradiction_review', 'human_authority',
)
STEPS_9=(
    'capture', 'identify_source', 'timestamp', 'contextualize',
    'form_hypothesis', 'seek_independent_support', 'seek_counterevidence',
    'human_review', 'reassess_after_outcome',
)


class Inquiry369:
    def __init__(self, city: LivingCity):
        self.city=city

    def evaluate(self, hypothesis_id: str, *, actor: str = 'local_operator') -> dict:
        h=self.city.get_hypothesis(hypothesis_id)
        evidence=h['evidence']
        stances={r['stance'] for r in evidence}
        # Labels alone cannot certify source independence, authenticity or truth.
        assessment={
            'provenance': 'needs_validation' if evidence else 'missing',
            'timeliness': 'needs_validation' if evidence else 'missing',
            'source_diversity': 'unverified_even_with_distinct_labels' if h['source_label_count']>1 else 'limited',
            'corroboration': 'human_review_required' if 'supports' in stances else 'not_demonstrated',
            'contradiction_review': 'recorded_requires_review' if 'contradicts' in stances else 'not_documented',
            'human_authority': 'review_recorded' if h['reviewer'] else 'pending',
        }
        result={'schema':'AXIOM0-INQUIRY-369/0.6','hypothesis_id':hypothesis_id,
                'claim':h['claim'],'epistemic_status':h['status'],
                'three_inquiry_phases':list(STAGES_3),'six_evidence_checks':assessment,
                'nine_review_steps':list(STEPS_9),'evidence_count':len(evidence),
                'result':'structured_inquiry_not_proof',
                'warning':'Numerical 3-6-9 framework is a reflective convention, not a validation algorithm.'}
        with self.city.store.write() as db:
            head=self.city.store.append(db,'inquiry369_assessed',{
                'actor':actor,'hypothesis_id':hypothesis_id,'snapshot_sha256':digest(canonical(result)),
                'epistemic_status':h['status'],'result':result['result']})
        result['audit_head']=head
        return result
