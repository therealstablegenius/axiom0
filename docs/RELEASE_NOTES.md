# AXIOM0 Living City v0.6 Release Notes — 2026-11-15

## Preserved
- Original AXIOM0 numerical implementation and original mathematical draft specification.
- Legacy v0.2 municipal source and proof-gate concepts, with the user-provided original ZIP archived intact.
- v0.3 occurrence, evidence and local LLM infrastructure.
- v0.4 optional 3-6-9 intention tracker.
- v0.5 SemiSoul memory, signed profile, and continuity attestations.

## Added and corrected
- `from axiom0.core import Axiom0` facade with `library.ingest_text`, `ask`, `warn`, `queue`, `review` and verified content.
- `axiom0 --json` CLI and `init --admin ...`, `doctor`, legal ingestion, queue and warning commands.
- Loopback-only compatibility API (`/ask`, `/ingest`, `/warn`, `/queue`, `/queue/review`) with distinct service and reviewer secrets.
- 3-6-9 evidence inquiry: three phases, six checks, nine review steps, always labeled non-proof.
- Explicit opt-in resilient fetcher; exact hostname allowlist, public DNS checks, no redirects, ETag/Last-Modified requests, TTL cache, jitter, content-hash caching and signed change events.
- Local model retrieval expanded to current legal-section texts; prompt includes provenance and explicit uncertainty.
- Fetcher stores sourced, epistemically labeled SemiSoul memory when a monitored text revision changes.
- Legal-source snapshot commitments in the signed event ledger, plus separate full-content integrity checks on demand and server startup.
- Windows and Linux installer/startup scripts; README with project origin, legal/philosophical boundaries and operator runbook.
- Source inputs remain read-only; there is no automatic law enforcement, legal determination, administrative decision, money transfer, or live City integration.

## Verification

- 27 automated Python tests (historical tests plus integration, API/permissions, HTTP caching and SSRF guards, ledger, SemiSoul, source-tampering detection).
- Wheel installation and import in isolated target verified on Linux in this environment.
- Actual localhost Uvicorn `/health` + authenticated `/v1/status` smoke verified on Linux in this environment.
- Empty preexisting v0.4 data directory opened under v0.6 and stable key-derived SemiSoul ID verified.
- No live municipal source polling, Ollama model demonstration, actual Windows installer, long-duration scheduler, penetration testing, accessibility certification, or full enterprise identity integration performed.

**Status:** local pilot deployable; production readiness is **not claimed**.
