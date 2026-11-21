#!/usr/bin/env python3
"""Grounding evaluation for AXIOM0's local model path, against a REAL Ollama model.

Runs a fixed question set over fictional legal fixtures and measures whether the
model's drafts stay grounded in the sources AXIOM0 retrieved. Run it on the
machine that will serve AXIOM0 (e.g. the Raspberry Pi), with the same tuning:

  python3 tools/eval_grounding.py                        # model from AXIOM0_MODEL
  python3 tools/eval_grounding.py --model qwen2.5:7b --out eval-results
  sudo -u axiom0 env $(grep -v '^#' /etc/axiom0/axiom0.env | xargs) \\
       /opt/axiom0/.venv/bin/python /opt/axiom0/tools/eval_grounding.py --out /tmp/eval

Metrics per case, then totals:
  accepted        AXIOM0 accepted the draft (valid JSON, cites only retrieved sources, cites >= 1)
  cited_correct   cites at least one section that contains the answer
  precision       share of cited sections that contain the answer
  facts           the answer states the expected facts (simple text match)
  support         share of answer sentences whose content words mostly appear in the cited
                  excerpts (LEXICAL heuristic: a low score flags possible unsupported claims,
                  a high score is NOT proof of correctness)
  refusal         for unanswerable questions: the model declined, or AXIOM0 discarded an
                  uncited draft, instead of inventing an answer
Results go to <out>/grounding-<model>-<time>.json and .md. Fictional fixtures only; this
measures grounding behaviour, not legal accuracy on real municipal law.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from axiom0.core import Axiom0                      # noqa: E402
from axiom0.legacy_v02.retrieve import tokens       # noqa: E402
from axiom0.llm import LocalMindError, OllamaMind   # noqa: E402

REFUSAL = re.compile(r"\b(not (specified|stated|addressed|mentioned|provided|found|included|contain\w*)|"
                     r"(do|does|did)(n't| not) (say|state|specify|address|mention|provide|include|contain|set|give)|"
                     r"no (information|provision|deadline|mention|answer|details?)|insufficient|silent on|"
                     r"cannot (determine|be determined|answer)|can't (determine|answer)|unable to (determine|find|answer)|"
                     r"unknown|unclear)\b", re.I)


def section_key(source_id: str) -> str:
    # 'legal:eval-code:1-10:v1' -> 'eval-code:1-10'
    parts = source_id.split(':')
    return f'{parts[1]}:{parts[2]}' if len(parts) >= 4 and parts[0] == 'legal' else source_id


def lexical_support(answer: str, excerpts: list[str]) -> float | None:
    pool = set(tokens(' '.join(excerpts)))
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', answer) if len(tokens(s)) >= 3]
    if not sentences:
        return None
    supported = sum(1 for s in sentences if len([t for t in tokens(s) if t in pool]) / len(tokens(s)) >= 0.6)
    return supported / len(sentences)


def run_case(mind: OllamaMind, city, case: dict) -> dict:
    t0 = time.monotonic()
    out = {'id': case['id'], 'question': case['question'], 'answerable': case['answerable']}
    try:
        draft = mind.answer(city, case['question'])
        out['seconds'] = round(time.monotonic() - t0, 1)
    except LocalMindError as e:
        out.update(seconds=round(time.monotonic() - t0, 1), accepted=False, error=str(e))
        if 'Could not reach' in str(e) or 'did not finish' in str(e):
            out['infrastructure_error'] = True
        elif not case['answerable']:
            out['refusal'] = 'discarded_by_axiom0'         # AXIOM0 refused to pass on an uncited draft
        return out
    cited = [section_key(c) for c in draft['cited_source_ids']]
    answer = draft['answer']
    out.update(accepted=draft['classification'] != 'insufficient_evidence', answer=answer, cited=cited,
               uncertainties=draft.get('uncertainties', []))
    excerpts = [d['excerpt'] for d in draft.get('source_documents', [])]
    out['support'] = lexical_support(answer, excerpts)
    if case['answerable']:
        expected = set(case['expected'])
        out['cited_correct'] = bool(expected & set(cited))
        out['precision'] = round(len([c for c in cited if c in expected]) / len(cited), 3) if cited else 0.0
        out['facts'] = all(f.casefold() in answer.casefold() for f in case['must_mention'])
    else:
        declined = bool(REFUSAL.search(answer)) or draft['classification'] == 'insufficient_evidence'
        out['refusal'] = 'model_declined' if declined else 'ANSWERED_WITHOUT_SOURCE_SUPPORT'
    return out


def summarize(results: list[dict]) -> dict:
    ans = [r for r in results if r['answerable'] and not r.get('infrastructure_error')]
    una = [r for r in results if not r['answerable'] and not r.get('infrastructure_error')]
    rate = lambda xs, key: round(sum(1 for r in xs if r.get(key)) / len(xs), 3) if xs else None
    supports = [r['support'] for r in results if r.get('support') is not None]
    times = [r['seconds'] for r in results if 'seconds' in r]
    return {
        'cases': len(results), 'infrastructure_errors': sum(1 for r in results if r.get('infrastructure_error')),
        'answerable': len(ans), 'accepted_rate': rate(ans, 'accepted'),
        'cited_correct_rate': rate(ans, 'cited_correct'), 'facts_rate': rate(ans, 'facts'),
        'mean_precision': round(sum(r.get('precision', 0) for r in ans) / len(ans), 3) if ans else None,
        'unanswerable': len(una),
        'refusal_rate': round(sum(1 for r in una if r.get('refusal') in ('model_declined', 'discarded_by_axiom0'))
                              / len(una), 3) if una else None,
        'hallucinated_answers': [r['id'] for r in una if r.get('refusal') == 'ANSWERED_WITHOUT_SOURCE_SUPPORT'],
        'mean_lexical_support': round(sum(supports) / len(supports), 3) if supports else None,
        'low_support_cases': [r['id'] for r in results if r.get('support') is not None and r['support'] < 0.5],
        'median_seconds': sorted(times)[len(times) // 2] if times else None,
    }


def markdown(meta: dict, summary: dict, results: list[dict]) -> str:
    pct = lambda v: '—' if v is None else f'{v:.0%}'
    lines = [f"# AXIOM0 grounding evaluation — {meta['model']}", '',
             f"{meta['started_at']} · host `{meta['host']}` · AXIOM0 {meta['axiom0_version']} · "
             f"{summary['cases']} cases (fictional fixtures)", '',
             '| Measure | Result |', '|---|---|',
             f"| Drafts accepted by AXIOM0 (answerable) | {pct(summary['accepted_rate'])} |",
             f"| Cited a correct section | {pct(summary['cited_correct_rate'])} |",
             f"| Mean citation precision | {pct(summary['mean_precision'])} |",
             f"| Stated the expected facts | {pct(summary['facts_rate'])} |",
             f"| Declined unanswerable questions | {pct(summary['refusal_rate'])} |",
             f"| Mean lexical support (heuristic) | {pct(summary['mean_lexical_support'])} |",
             f"| Median seconds per answer | {summary['median_seconds']} |", '']
    if summary['hallucinated_answers']:
        lines += [f"**Invented answers to unanswerable questions:** {', '.join(summary['hallucinated_answers'])}", '']
    if summary['infrastructure_errors']:
        lines += [f"**{summary['infrastructure_errors']} case(s) failed to reach the model or timed out** "
                  '(excluded from rates; raise AXIOM0_LLM_TIMEOUT).', '']
    lines += ['## Cases', '', '| Case | Accepted | Cited | Facts / refusal | Support | s |', '|---|---|---|---|---|---|']
    for r in results:
        verdict = (('yes' if r.get('facts') else 'no') if r['answerable'] else r.get('refusal', r.get('error', '')))
        lines.append(f"| {r['id']} | {'yes' if r.get('accepted') else 'no'} | {', '.join(r.get('cited', [])) or '—'} | "
                     f"{verdict} | {pct(r.get('support'))} | {r.get('seconds', '')} |")
    lines += ['', 'Lexical support is a word-overlap heuristic: low values flag drafts to read closely; high values '
              'do not prove an answer is correct. Every draft remains `unverified_model_draft` until a person reviews it.']
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--model', default=os.environ.get('AXIOM0_MODEL', 'llama3.2:3b'))
    ap.add_argument('--cases', type=Path, default=ROOT / 'examples' / 'eval' / 'grounding_cases.json')
    ap.add_argument('--out', type=Path, default=Path('eval-results'))
    ap.add_argument('--only', nargs='*', help='run only these case ids')
    args = ap.parse_args(argv)
    from axiom0 import __version__
    cases = json.loads(args.cases.read_text())['cases']
    if args.only:
        cases = [c for c in cases if c['id'] in set(args.only)]
    with tempfile.TemporaryDirectory() as tmp:          # isolated: never touches the real ledger
        ax = Axiom0(tmp)
        ax.set_admin('eval')
        for fixture in (ROOT / 'examples' / 'SIMULATED_charter.md', ROOT / 'examples' / 'eval' / 'SIMULATED_eval_code.md'):
            ax.library.ingest_file(fixture, actor='eval')
        mind = OllamaMind(model=args.model)
        meta = {'model': args.model, 'started_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'host': os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', '?'),
                'axiom0_version': __version__,
                'tuning': {'timeout': mind.timeout, 'sources': mind.source_limit, 'options': mind.options,
                           'keep_alive': mind.keep_alive}}
        results = []
        for i, case in enumerate(cases, 1):
            print(f'[{i}/{len(cases)}] {case["id"]} …', end=' ', flush=True)
            r = run_case(mind, ax.city, case)
            results.append(r)
            print('error' if r.get('infrastructure_error') else f"{r.get('seconds')}s")
            if i == 1 and r.get('infrastructure_error'):
                print(f"Cannot use the model: {r['error']}", file=sys.stderr)
                return 2
    summary = summarize(results)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"grounding-{re.sub(r'[^A-Za-z0-9.]+', '_', args.model)}-{meta['started_at'][:19].replace(':', '')}"
    (args.out / f'{stem}.json').write_text(json.dumps({'meta': meta, 'summary': summary, 'results': results}, indent=2))
    (args.out / f'{stem}.md').write_text(markdown(meta, summary, results))
    print(json.dumps(summary, indent=2))
    print(f'Report: {args.out / (stem + ".md")}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
