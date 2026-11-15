# AXIOM0 Living City v0.3 local verification

Date: 2026-11-15

## Tests performed

- `PYTHONPATH=. pytest -q`: **12 passed**.
- `python -m compileall -q axiom0`: success.
- Preserved numerical module `axiom0/numerics.py`: SHA-256 equals the recovered original `axiom0.py`.
- `python -m axiom0 --data-dir /tmp/axiom0-smoke init`: created stable persistent identity.
- `python -m axiom0 --data-dir /tmp/axiom0-smoke ingest-jsonl examples/DEMO_NOT_REAL.jsonl`: loaded 3 synthetic occurrences.
- `python -m axiom0 --data-dir /tmp/axiom0-smoke signals`: identified exactly 1 candidate investigatory signal.
- `python -m axiom0 --data-dir /tmp/axiom0-smoke verify`: validated 4 signed audit events.
- FastAPI TestClient: checked local dashboard HTML, health, API key enforcement, separate reviewer key, occurrence write/read, model-change review gate and verification.

## Not tested

- Actual Ollama model inference: this container did not have a downloaded Ollama model / active local server. The API shape was cross-checked with official Ollama docs; live LLM grounding, speed, and citation validity need on-device evaluation.
- Windows desktop runtime, GPU/CPU performance, official city systems, municipal legal content, real feed ingestion, security penetration, external validation, long-duration stress, backup/recovery and WCAG audit.
- Independent confirmation that numerical harmony predicts anything about municipal events. No such predictive claim is made.

## Status

**Verified reference prototype, not production certified.** Controls demonstrate a reproducible boundary between reported occurrence, hypothesis, reviewed finding and local model answer. Citywide deployment requires additional authorization and validation gates.

## v0.4 extension (November 15, 2026)

The previous test suite plus six additional tests for the 3-6-9 tracker pass: **18 passed**. New coverage includes authenticated REST operations, 3×6×9 limits, nine-day completion, start-date controls, numeric value validation, symbolic/evidence separation, and audit-ledger tamper detection. This is software verification only; no behavioral, scientific or predictive efficacy claim is made.
