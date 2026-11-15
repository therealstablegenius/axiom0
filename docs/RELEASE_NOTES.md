# AXIOM0 Living City v0.6.1 — Raspberry Pi 5 Edition — 2026-11-15

## Added
- `deploy/pi5/install.sh`: one-command Raspberry Pi 5 appliance install. It sets up AXIOM0 in
  `/opt/axiom0` under a sandboxed `axiom0` service account, installs Ollama with a Pi 5 tuning
  drop-in (localhost only, 1 request, 1 model, flash attention, 8-bit KV cache), and
  downloads and preloads the model. Optional zram and CPU governor. Includes `--dry-run`.
- RAM profiles `pi5-4gb` (llama3.2:1b), `pi5-8gb` (llama3.2:3b), `pi5-16gb` (llama3.2:3b, always loaded).
- systemd units `axiom0.service` (hardened sandbox, CPU priority over Ollama) and `axiom0-warmup.service`.
- `axiom0-pi5-doctor.sh` (power, thermals, storage, Ollama, AXIOM0, localhost-only checks, ledger),
  `axiom0-pi5-bench.sh` (tokens/s and answer-time estimate against the configured timeout), `uninstall.sh`.
- `docs/PI5.md` operator guide.

## Changed
- `axiom0/llm.py`: optional, validated tuning settings: `AXIOM0_LLM_TIMEOUT`, `AXIOM0_LLM_SOURCES`,
  `AXIOM0_NUM_CTX`, `AXIOM0_NUM_THREAD`, `AXIOM0_NUM_PREDICT`, `AXIOM0_KEEP_ALIVE`. When they are
  unset, behaviour is identical to v0.6. Timeouts now report a specific error naming the setting
  to change, instead of "Could not reach local Ollama".

## Verification
- 40 automated tests pass (13 new). All scripts pass shellcheck. A full install, re-install,
  ingest, ask --llm, doctor, speed test and uninstall were exercised on Linux with Ollama and
  systemd stand-ins. Not yet run on physical Pi 5 hardware.

---

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
