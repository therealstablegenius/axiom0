# AXIOM0 Living City v0.7.0 — External review fixes — 2026-11-21

Every finding in the external v0.6 review is addressed below. Some items need a real-world
step that cannot be done in software (marked **you**).

## Serious gaps
- **Ledger rollback by a host operator:** added signed anchor receipts (`axiom0 anchor`), `anchor-verify`,
  a publishing script that checks old receipts before issuing new ones, a daily Pi timer
  (`--enable-anchors`), and `docs/ANCHORING.md`. A coherent re-signed rewrite now fails against a
  published receipt. **You:** choose where receipts are published (public repo recommended).
- **Reviewer was a label:** added personal reviewer keys (`reviewer-add/-revoke/-list`), stored as
  SHA-256 hashes. The API takes the reviewer's name from the key, and ledger events record
  `reviewer_auth`. The shared key can be disabled with `AXIOM0_REQUIRE_PERSONAL_REVIEWERS=1`.
  Still not SSO.
- **Windows unverified:** added a GitHub Actions job that runs the real installer on Windows, starts the
  server, checks authentication, owner-only secrets and the full CLI cycle, and checks conversion of
  old secrets. Tests now also run on Windows and macOS.
- **LLM never tested with a model:** added `tools/eval_grounding.py` with fictional fixtures and 12
  cases, including unanswerable questions and a keyword trap. **You:** run it on the Pi with the
  real model.
- **DNS rebinding:** the fetcher connects to the address it validated. TLS SNI and certificate
  checks use the real hostname, and the rendering browser is pinned with host-resolver rules.
- **Naive spike statistics:** SPIKE-v2 (Poisson or negative binomial tail test, seasonal baseline,
  Benjamini–Hochberg FDR) is now the default for `warn`. v1 remains available with `--method v1`,
  for comparison only.

## Credibility
- **3·6·9 in the municipal package:** the Intention Lab and `symbolic-state` are off by default
  (404 / hidden / refused). Enable with `AXIOM0_ENABLE_SYMBOLIC=1`. The 3·6·9 evidence-review
  checklist stays.
- **Doc drift:** `ARCHITECTURE`, `VERIFICATION`, `SECURITY`, `DEPLOYMENT` and `NEXT_GATES` were
  updated. Test counts in `VERIFICATION.md` are now generated, and CI fails if they are stale.
- **Excerpts that look like answers:** findings are labelled `source_excerpt` with a `how_to_read`
  note. Model-path retrieval now uses BM25, the same as the quote path, instead of substring counting.

## Smaller items
- `mind_history.purpose` was renamed to `reason` through the new **schema migration** system
  (ordered, ledgered, refuses newer data).
- The forbidden-action check now uses normalised pattern families, covering rephrasings, and
  reports which rule fired. It is documented as a guardrail, not a control.
- Added `backup` / `restore` (consistent copy, manifest hashes, empty-target-only restore with head
  check) and `export-audit` with the stand-alone `tools/axiom0_audit_verify.py`.
- Windows secrets are now owner-only **data** (`axiom0-secrets.env`). The old executable `.ps1` is
  converted by parsing (never running) and removed. The README no longer tells operators to
  dot-source secrets.
- The WCAG audit is still open (listed in `NEXT_GATES.md`).

## Verification
92 automated tests pass (see the generated table in `VERIFICATION.md`). Windows scripts parse
under PowerShell 7.4, and `Start-AXIOM0.ps1` was run for real. The anchor publishing script was
exercised against a git remote, including a simulated rollback.

---

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
