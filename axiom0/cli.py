"""AXIOM0 v0.6 trusted-local CLI; --json yields machine-readable output."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from .core import Axiom0
from .engine import LivingCity
from .semisoul import SemiSoul
from .intention369 import IntentionLab
from .inquiry369 import Inquiry369
from .fetcher import ResilientFetcher
from .llm import OllamaMind


def execute(argv: list[str] | None = None) -> None:
    parser=argparse.ArgumentParser(prog='axiom0',description='AXIOM0 local-first municipal research pilot')
    parser.add_argument('--data-dir',default=os.getenv('AXIOM0_DATA_DIR','./axiom0_data'))
    parser.add_argument('--json',action='store_true',help='Machine-readable JSON (including errors)')
    parser.add_argument('--actor',default=os.getenv('AXIOM0_LOCAL_ACTOR'))
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--admin',default=None)
    for name in ('status','verify','doctor','signals','hypotheses','occurrences','documents','queue','serve','369-list','feed-list'):
        sub.add_parser(name)
    ing=sub.add_parser('ingest');ing.add_argument('path',type=Path)
    d=sub.add_parser('add-document');d.add_argument('file',type=Path)
    for f in ('title','authority','jurisdiction','citation','version','source-url'):
        d.add_argument('--'+f,required=True)
    d.add_argument('--effective-at');d.add_argument('--source-reviewed',action='store_true')
    occ=sub.add_parser('add-occurrence');occ.add_argument('json_file',type=Path)
    batch=sub.add_parser('ingest-jsonl');batch.add_argument('file',type=Path)
    q=sub.add_parser('ask');q.add_argument('question');q.add_argument('--llm',action='store_true')
    w=sub.add_parser('warn');w.add_argument('csv_file',type=Path)
    pr=sub.add_parser('propose');pr.add_argument('text');pr.add_argument('--evidence',action='append',required=True)
    qr=sub.add_parser('queue-review');qr.add_argument('id')
    qr.add_argument('decision',choices=('approved_for_human_followup','rejected'))
    qr.add_argument('--reviewer',required=True);qr.add_argument('--note',required=True)
    mind=sub.add_parser('mind-swap');mind.add_argument('model');mind.add_argument('--authorized-by',required=True);mind.add_argument('--reason',required=True)
    review=sub.add_parser('review');review.add_argument('id')
    review.add_argument('status',choices=('candidate','corroborated','verified','rejected'))
    review.add_argument('--reviewer',required=True);review.add_argument('--note',required=True);review.add_argument('--proof-reference')
    ev=sub.add_parser('evidence');ev.add_argument('hypothesis_id');ev.add_argument('occurrence_id')
    ev.add_argument('--stance',choices=('neutral','supports','contradicts'),default='neutral');ev.add_argument('--note',default='')
    inq=sub.add_parser('inquire369');inq.add_argument('hypothesis_id')
    i=sub.add_parser('369-start');i.add_argument('--goal',required=True);i.add_argument('--affirmation',required=True)
    i.add_argument('--metric',required=True);i.add_argument('--baseline',type=float,required=True)
    i.add_argument('--target',type=float,required=True);i.add_argument('--start-date');i.add_argument('--timezone',default='America/Chicago')
    show=sub.add_parser('369-show');show.add_argument('id')
    ses=sub.add_parser('369-session');ses.add_argument('id');ses.add_argument('--action',default='');ses.add_argument('--reflection',default='')
    out=sub.add_parser('369-outcome');out.add_argument('id');out.add_argument('--value',type=float,required=True)
    out.add_argument('--source',default='');out.add_argument('--note',default='')
    feed=sub.add_parser('feed-add');feed.add_argument('feed_id');feed.add_argument('url');feed.add_argument('doc_id')
    feed.add_argument('--authority',required=True,choices=('charter','ordinance','policy','procedure'))
    feed.add_argument('--title',required=True);feed.add_argument('--effective');feed.add_argument('--render',action='store_true')
    feed.add_argument('--ttl-minutes',type=int,default=60)
    fetch=sub.add_parser('fetch-once');fetch.add_argument('feed_id',nargs='?');fetch.add_argument('--force',action='store_true')
    loop=sub.add_parser('fetch-loop');loop.add_argument('--hours',type=float,default=6)
    args=parser.parse_args(argv)

    def emit(value):
        if args.json: print(json.dumps(value,ensure_ascii=False,default=str))
        else: print(json.dumps(value,ensure_ascii=False,indent=2,default=str))
    try:
        if args.command=='serve':
            service=os.environ.get('AXIOM0_API_KEY','')
            reviewer=os.environ.get('AXIOM0_REVIEWER_KEY','')
            if min(len(service),len(reviewer))<24 or service==reviewer:
                raise ValueError('Set distinct AXIOM0_API_KEY and AXIOM0_REVIEWER_KEY, at least 24 characters each')
            import uvicorn
            os.environ['AXIOM0_DATA_DIR']=str(Path(args.data_dir).expanduser().resolve())
            Axiom0(os.environ['AXIOM0_DATA_DIR']).verify()  # fail closed on supported integrity checks
            uvicorn.run('axiom0.api:app',host='127.0.0.1',port=8765,log_level='info')
            return
        ax=Axiom0(args.data_dir)
        actor=args.actor
        if not actor:
            with ax.store.connect() as db:
                row=db.execute('SELECT value FROM metadata WHERE key=?',('local_admin',)).fetchone()
            actor=row['value'] if row else 'local_operator'
        city=ax.city;lab=ax.intentions
        cmd=args.command
        if cmd=='init': value={'identity':city.identity(),'local_operator':ax.set_admin(args.admin) if args.admin else None}
        elif cmd=='status': value=ax.status()
        elif cmd=='verify': value=ax.verify()
        elif cmd=='doctor':
            ver=ax.verify()
            value={'status':'ok','semisoul':ver,'data_dir':str(ax.data_dir),
                   'loopback_only':True,'remote_idp_configured':False,'feeds':len(ResilientFetcher(args.data_dir).feeds()),
                   'readiness':'local_pilot_only; official municipal deployment requires security and data-owner authorization'}
        elif cmd=='signals': value=city.scan_signals()
        elif cmd=='hypotheses': value=city.hypotheses()
        elif cmd=='occurrences': value=city.occurrences()
        elif cmd=='documents': value=city.documents()
        elif cmd=='ingest': value=ax.ingest(actor,args.path)
        elif cmd=='ask': value=ax.ask(actor,args.question,use_llm=args.llm)
        elif cmd=='warn': value=ax.warn(actor,args.csv_file)
        elif cmd=='queue': value=ax.queue()
        elif cmd=='propose': value=ax.recommend(actor,args.text,args.evidence)
        elif cmd=='queue-review': value=ax.municipal.review(args.id,reviewer=args.reviewer,decision=args.decision,rationale=args.note)
        elif cmd=='add-document':
            value=city.add_document(title=args.title,authority=args.authority,jurisdiction=args.jurisdiction,
                 citation=args.citation,version=args.version,content=args.file.read_text(encoding='utf-8'),
                 source_url=args.source_url,effective_at=args.effective_at,source_reviewed=args.source_reviewed)
        elif cmd=='add-occurrence': value=city.add_occurrence(**json.loads(args.json_file.read_text('utf-8')))
        elif cmd=='ingest-jsonl':
            value=[]
            for i,line in enumerate(args.file.read_text('utf-8').splitlines(),1):
                if line.strip():
                    try: value.append(city.add_occurrence(**json.loads(line)))
                    except Exception as e: raise ValueError(f'Line {i}: {e}') from e
        elif cmd=='mind-swap': value=city.swap_mind(args.model,args.authorized_by,args.reason)
        elif cmd=='review': value=city.review_hypothesis(args.id,status=args.status,reviewer=args.reviewer,
                                note=args.note,proof_reference=args.proof_reference)
        elif cmd=='evidence': value=city.attach_evidence(args.hypothesis_id,args.occurrence_id,stance=args.stance,note=args.note)
        elif cmd=='inquire369': value=Inquiry369(city).evaluate(args.hypothesis_id,actor=actor)
        elif cmd=='369-start': value=lab.start(goal=args.goal,affirmation=args.affirmation,metric=args.metric,
                           baseline=args.baseline,target=args.target,start_date=args.start_date,timezone_name=args.timezone)
        elif cmd=='369-list': value=lab.list()
        elif cmd=='369-show': value=lab.get(args.id)
        elif cmd=='369-session': value=lab.session(args.id,action_taken=args.action,reflection=args.reflection)
        elif cmd=='369-outcome': value=lab.outcome(args.id,value=args.value,source_reference=args.source,note=args.note)
        elif cmd=='feed-list': value=ResilientFetcher(args.data_dir).feeds()
        elif cmd=='feed-add': value=ResilientFetcher(args.data_dir).register(feed_id=args.feed_id,
                    url=args.url,doc_id=args.doc_id,authority=args.authority,title=args.title,
                    effective=args.effective,render=args.render,ttl_minutes=args.ttl_minutes)
        elif cmd=='fetch-once':
            f=ResilientFetcher(args.data_dir)
            value=f.poll(args.feed_id,bypass_ttl=args.force) if args.feed_id else f.poll_all(bypass_ttl=args.force)
        elif cmd=='fetch-loop': asyncio.run(ResilientFetcher(args.data_dir).continuous(hours=args.hours));return
        else: raise ValueError('Unrecognized subcommand')
        emit(value)
    except (ValueError,PermissionError,RuntimeError,OSError,KeyError) as e:
        if args.json: emit({'error':type(e).__name__,'detail':str(e)})
        else: print(f'{type(e).__name__}: {e}',file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':
    execute()
