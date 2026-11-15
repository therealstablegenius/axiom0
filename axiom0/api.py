"""Loopback-only prototype API. Requires service and separate reviewer secrets."""
from __future__ import annotations
from functools import lru_cache
import os
import secrets
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .engine import LivingCity
from .llm import OllamaMind, LocalMindError
from .store import IntegrityError
from .intention369 import IntentionLab

app = FastAPI(title='AXIOM0 Living City',version='0.6.1',docs_url=None,redoc_url=None)


@lru_cache(maxsize=1)
def core() -> LivingCity:
    return LivingCity(os.environ.get('AXIOM0_DATA_DIR','./axiom0_data'))


def _secret(env_key: str, supplied: str | None) -> None:
    secret = os.environ.get(env_key)
    if os.environ.get('AXIOM0_API_KEY') and os.environ.get('AXIOM0_API_KEY') == os.environ.get('AXIOM0_REVIEWER_KEY'):
        raise HTTPException(status_code=503,detail='Service and reviewer keys must be different')
    if not secret or len(secret)<24:
        raise HTTPException(status_code=503,detail=f'{env_key} must be configured to a strong random secret')
    if not supplied or not secrets.compare_digest(supplied,secret):
        raise HTTPException(status_code=401,detail='Invalid credentials')


def service_key(x_axiom0_key: str | None = Header(None)):
    _secret('AXIOM0_API_KEY',x_axiom0_key)


def reviewer_key(x_axiom0_reviewer_key: str | None = Header(None)):
    _secret('AXIOM0_REVIEWER_KEY',x_axiom0_reviewer_key)


class DocumentIn(BaseModel):
    title: str
    authority: str
    jurisdiction: str
    citation: str
    version: str
    content: str
    source_url: str
    effective_at: str | None = None
    source_reviewed: bool = False


class OccurrenceIn(BaseModel):
    external_id: str
    event_at: str
    area: str
    category: str
    summary: str
    source_label: str
    source_url: str
    confidence_note: str
    source_document_id: str | None = None


class HypothesisIn(BaseModel):
    claim: str
    area: str
    category: str
    occurrence_ids: list[str]


class ReviewIn(BaseModel):
    status: str
    reviewer: str
    note: str
    proof_reference: str | None = None


class EvidenceIn(BaseModel):
    occurrence_id: str
    stance: str = 'neutral'
    note: str = ''


class QuestionIn(BaseModel):
    question: str


class MindIn(BaseModel):
    model: str
    authorized_by: str
    reason: str


class MCAIn(BaseModel):
    identity: str
    purpose: str
    observation: str
    constraint: str
    feedback: str


class VectorIn(BaseModel):
    vector: list[int]


class IntentionIn(BaseModel):
    goal: str
    affirmation: str
    metric: str
    baseline: float
    target: float
    start_date: str | None = None
    timezone_name: str = 'America/Chicago'


class Session369In(BaseModel):
    repetitions: int = 3
    action_taken: str = ''
    reflection: str = ''


class Outcome369In(BaseModel):
    value: float
    source_reference: str = ''
    note: str = ''


def lab() -> IntentionLab:
    return IntentionLab(core().store)


@app.get('/v1/369/intentions',dependencies=[Depends(service_key)])
def intentions():
    return lab().list()


@app.post('/v1/369/intentions',dependencies=[Depends(service_key)])
def start_intention(entry:IntentionIn):
    return lab().start(**entry.model_dump())


@app.get('/v1/369/intentions/{id_}',dependencies=[Depends(service_key)])
def get_intention(id_:str):
    return lab().get(id_)


@app.post('/v1/369/intentions/{id_}/sessions',dependencies=[Depends(service_key)])
def add_intention_session(id_:str,entry:Session369In):
    return lab().session(id_,**entry.model_dump())


@app.post('/v1/369/intentions/{id_}/outcomes',dependencies=[Depends(service_key)])
def add_intention_outcome(id_:str,entry:Outcome369In):
    return lab().outcome(id_,**entry.model_dump())


@app.exception_handler(ValueError)
async def invalid_input(_request, e):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400,content={'detail':str(e)})


@app.get('/')
def home():
    return FileResponse(Path(__file__).parent/'web'/'index.html',media_type='text/html')


@app.get('/health')
def health():
    return {'status':'ok','version':'0.6.1','authenticated_status_requires_key':True}


@app.get('/v1/status',dependencies=[Depends(service_key)])
def status():
    return {'identity':core().identity(),'stats':core().stats()}


@app.get('/v1/documents',dependencies=[Depends(service_key)])
def documents():
    return core().documents()


@app.post('/v1/documents',dependencies=[Depends(service_key)])
def add_document(doc:DocumentIn):
    return core().add_document(**doc.model_dump())


@app.get('/v1/occurrences',dependencies=[Depends(service_key)])
def occurrences():
    return core().occurrences()


@app.post('/v1/occurrences',dependencies=[Depends(service_key)])
def add_occurrence(entry:OccurrenceIn):
    return core().add_occurrence(**entry.model_dump())


@app.post('/v1/signals',dependencies=[Depends(service_key)])
def signals(days:int=30,min_occurrences:int=3,min_source_labels:int=2):
    return core().scan_signals(days=days,min_occurrences=min_occurrences,
                               min_source_labels=min_source_labels)


@app.post('/v1/hypotheses',dependencies=[Depends(service_key)])
def create_hypothesis(h:HypothesisIn):
    return core().create_hypothesis(**h.model_dump())


@app.get('/v1/hypotheses',dependencies=[Depends(service_key)])
def hypotheses():
    return core().hypotheses()


@app.post('/v1/hypotheses/{id_}/evidence',dependencies=[Depends(service_key),Depends(reviewer_key)])
def annotate_evidence(id_:str,entry:EvidenceIn):
    return core().attach_evidence(id_,**entry.model_dump())


@app.post('/v1/hypotheses/{id_}/review',dependencies=[Depends(service_key),Depends(reviewer_key)])
def review(id_:str,entry:ReviewIn):
    data=entry.model_dump()
    data['reviewer']=os.environ.get('AXIOM0_REVIEWER_ID','api_reviewer')
    return core().review_hypothesis(id_,**data)


@app.post('/v1/ask',dependencies=[Depends(service_key)])
def ask(q:QuestionIn):
    try:
        return OllamaMind().answer(core(),q.question)
    except LocalMindError as e:
        raise HTTPException(status_code=503,detail=str(e)) from e


@app.post('/v1/mind',dependencies=[Depends(service_key),Depends(reviewer_key)])
def replace_mind(m:MindIn):
    return core().swap_mind(m.model,os.environ.get('AXIOM0_REVIEWER_ID','api_reviewer'),m.reason)


@app.post('/v1/mca',dependencies=[Depends(service_key)])
def mca(atom:MCAIn):
    return core().mca_record(**atom.model_dump())


@app.post('/v1/symbolic-state',dependencies=[Depends(service_key)])
def state(v:VectorIn):
    return core().symbolic_state(v.vector)


@app.get('/v1/verify',dependencies=[Depends(service_key)])
def verify():
    try:
        return compat().verify()
    except IntegrityError as e:
        raise HTTPException(status_code=503,detail=str(e)) from e

# v0.6 extension: compatibility routes use the existing loopback-only secret boundary.
# Service/reviewer identity is supplied from server configuration, never from
# request JSON. These are service principals, NOT verified human identities.
from .core import Axiom0
from .inquiry369 import Inquiry369
from .semisoul import SemiSoul
from .municipal import MunicipalCore


class AskCompatIn(BaseModel):
    question: str
    use_llm: bool = False


class WarnCompatIn(BaseModel):
    csv_filename: str


class IngestCompatIn(BaseModel):
    content: str


class ProposeCompatIn(BaseModel):
    recommendation: str
    evidence_refs: list[str]


class QueueReviewCompatIn(BaseModel):
    id: str
    decision: str
    note: str


class InquiryCompatIn(BaseModel):
    hypothesis_id: str


class QuoteCompatIn(BaseModel):
    cite: str
    quote: str
    version: int | None = None


class MemoryCompatIn(BaseModel):
    statement: str
    memory_type: str
    epistemic_status: str
    source_type: str
    source_ref: str = ''
    correction_of: str | None = None


@lru_cache(maxsize=1)
def compat() -> Axiom0:
    return Axiom0(os.environ.get('AXIOM0_DATA_DIR','./axiom0_data'))


@app.exception_handler(PermissionError)
async def forbidden_input(_request, e):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=403,content={'detail':str(e)})


@app.post('/ask',dependencies=[Depends(service_key)])
def compat_ask(q: AskCompatIn):
    try:
        return compat().ask('api_service',q.question,use_llm=q.use_llm)
    except LocalMindError as e:
        raise HTTPException(status_code=503,detail=str(e)) from e


@app.post('/ingest',dependencies=[Depends(service_key)])
def compat_ingest(payload: IngestCompatIn):
    return compat().library.ingest_text(payload.content,actor='api_service')


@app.post('/warn',dependencies=[Depends(service_key)])
def compat_warn(payload: WarnCompatIn):
    # Read only files explicitly staged into the data root's imports folder.
    filename=payload.csv_filename
    if not isinstance(filename,str) or not filename.endswith('.csv') or Path(filename).name!=filename:
        raise HTTPException(status_code=400,detail='Supply a CSV filename in the local imports directory')
    base=(compat().data_dir/'imports').resolve()
    target=(base/filename).resolve()
    if target.parent!=base or not target.is_file():
        raise HTTPException(status_code=404,detail='CSV not found in authorized imports directory')
    return compat().municipal.service_spikes(target,actor='api_service')


@app.get('/queue',dependencies=[Depends(service_key)])
def compat_queue():
    return compat().queue()


@app.post('/queue',dependencies=[Depends(service_key)])
def compat_propose(payload: ProposeCompatIn):
    return compat().municipal.propose(proposed_by='api_service',
                            recommendation=payload.recommendation,evidence_refs=payload.evidence_refs)


@app.post('/queue/review',dependencies=[Depends(service_key),Depends(reviewer_key)])
def compat_queue_review(payload: QueueReviewCompatIn):
    reviewer=os.environ.get('AXIOM0_REVIEWER_ID','api_reviewer')
    if reviewer.casefold()=='api_service':
        raise HTTPException(status_code=503,detail='Reviewer principal must be separate from service principal')
    return compat().municipal.review(payload.id,reviewer=reviewer,
                                   decision=payload.decision,rationale=payload.note)


@app.get('/v1/legal/sections',dependencies=[Depends(service_key)])
def get_legal_sections():
    return compat().municipal.sections()


@app.post('/v1/legal/quote',dependencies=[Depends(service_key)])
def verify_legal_quote(payload: QuoteCompatIn):
    return compat().municipal.check_quote(**payload.model_dump())


@app.post('/v1/inquiry369',dependencies=[Depends(service_key)])
def inquiry369(payload: InquiryCompatIn):
    return Inquiry369(core()).evaluate(payload.hypothesis_id,actor='api_service')


@app.get('/v1/semisoul/profile',dependencies=[Depends(service_key)])
def semisoul_profile():
    return SemiSoul(core().store).profile()


@app.get('/v1/semisoul/memories',dependencies=[Depends(service_key)])
def semisoul_memories():
    return SemiSoul(core().store).memories()


@app.post('/v1/semisoul/memories',dependencies=[Depends(service_key),Depends(reviewer_key)])
def semisoul_record_memory(payload: MemoryCompatIn):
    return SemiSoul(core().store).remember(**payload.model_dump(),actor='api_reviewer')


@app.get('/v1/semisoul/attestation',dependencies=[Depends(service_key)])
def semisoul_attestation():
    return SemiSoul(core().store).attest()
