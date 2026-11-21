# AXIOM0 Living City v0.7 — Local Municipal Research Pilot · Raspberry Pi 5 Edition

**Author and concept originator: Howard Rice**  
**Build status:** local pilot reference implementation; **not** certified for production, not an official City of Kansas City, Missouri system.  
**Key distinction:** *Truth may exist before proof. A claim is not established by the fact that someone believes it, a model predicts it, or a number resembles a pattern.*

## The story behind AXIOM0

Howard Rice's career has been spent where residents' questions, legislative records, public meetings, and administrative accountability intersect: Kansas City's City Clerk's Office. He has supported committee and commission work, researched municipal matters, and seen how a resident's concern can disappear between intake, assignment, research, decision, and follow-through. Alongside that work, Rice has studied cybersecurity and developed software concepts that bring mathematical structure and human judgment into public-service workflows.

AXIOM0 began with mathematical and philosophical questions: Can a numerical language represent a system's condition? Can an intelligent agent retain a durable identity when its model changes? Can an accountability system preserve the memory of what it knew, what it did, and what it later corrected? And can that system search for truth **before proof has been assembled** without ever pretending the missing proof exists?

These questions grew into the **SemiSoul** concept: not a claim that software has a theological soul or conscious experience, but an *engineered continuity envelope* joining a stable identity, attributed memory, human-defined purpose, replaceable reasoning engine, constraints, and signed history. The architecture mimics selected **functions associated with a responsible conscious actor**—personal continuity, recall, self-correction, and commitment—without establishing subjective experience.

Rice's spiritual thesis is that the existence of intelligible mathematical order may point toward a divine source. AXIOM0 preserves that idea as philosophy and a subject of open inquiry. **No code, harmony score, 3·6·9 pattern, or local LLM output here proves that God exists, that God exists inside AI, or that AXIOM0 is conscious.** The mathematical and theological claims must remain distinguishable.

The resulting municipal purpose is practical: preserve the source, keep every version, identify contradictions, explain uncertainty, and route meaningful questions to authorized people before they become crises.

## What is included

| Layer | Implementation |
|---|---|
| **Numerical AXIOM0** | Original v0.1 protected-reduction and five-coordinate `GENESIS=(1,2,8,7,5)` / `SOUL=(5,12,5,12,5)` code, kept unchanged in `axiom0/numerics.py` |
| **Persistent SemiSoul** | Ed25519 local identity; signed, hash-chained ledger; epistemically labeled autobiographical memories; corrections; versioned purpose and commitments; signed attestation |
| **Municipal Truth Library** | Original v0.2 versioned legal-section ingestion, content hashes, superseded-section history, quote matching, source attribution |
| **Proof Gate** | Rejects purported source quotations not present in the referenced version; quotation matching does **not** establish legal or factual truth |
| **Living City intelligence** | Evidence-based occurrences, hypotheses, contrary evidence, recurring-signal scans, human verification |
| **Early warning** | Area-level service-request spike detection (SPIKE-v2: count model, seasonality, false-discovery control) from authorized CSV; not person-level prediction |
| **3·6·9 intention practice** | Optional personal module, **off by default** (`AXIOM0_ENABLE_SYMBOLIC=1`); tracked separately from municipal evidence |
| **3·6·9 inquiry** | 3 inquiry phases, 6 evidence checks, 9 review stages; no mystical truth scoring |
| **Local model** | Ollama adapter; query-grounded document/section excerpts; strict citation-ID validation; no cloud fallback |
| **Resilient fetcher** | Opt-in feeds; HTTPS hostname allowlist; DNS public-address guard with connection pinning (no rebinding window); ETag/Last-Modified; TTL cache; jitter; HTML-to-text; versioned ingestion and audit records |
| **Ledger anchoring** | Signed head receipts to publish off-host; `anchor-verify` detects rewrites and rollback even by someone holding the key ([`docs/ANCHORING.md`](docs/ANCHORING.md)) |
| **Reviewer identities** | Personal reviewer keys (stored as hashes, revocable, ledgered); the API derives *who* reviewed from the key |
| **Backup and audit** | Consistent backup with verified restore; signed audit export checkable by a stand-alone verifier |
| **Grounding evaluation** | `tools/eval_grounding.py` scores a real model's citations and refusals |
| **Three integration methods** | Import `Axiom0` from Python, `axiom0 --json ...` CLI, or loopback HTTP API |
| **Operator UI** | Local dashboard served at `http://127.0.0.1:8765` |

### 3·6·9 is a reasoning discipline, not a proof function

* **3 phases:** observe → challenge → provisional explanation.
* **6 checks:** source provenance, timeliness, independence, corroboration, contradictions, human authority.
* **9 steps:** capture → identify source → timestamp → contextualize → hypothesize → seek support → seek counterevidence → human review → reassess.

Use `axiom0 inquire369 HYPOTHESIS_ID` after adding occurrences and opening a hypothesis. It **cannot** change a hypothesis to verified. The 3·6·9 intention practice is a separate personal goal-tracking workflow and cannot influence a legal finding.

## Quick start — Raspberry Pi 5 (with local AI model)

```bash
sudo bash deploy/pi5/install.sh
```

Installs AXIOM0 and Ollama, picks a model to suit the board's RAM, tunes both for the Pi 5, and starts
everything as local-only services. Full guide: [`docs/PI5.md`](docs/PI5.md).

## Quick start — Windows PowerShell

**Requirements:** Windows 10/11, Python **3.11 or newer**, internet access for initial dependency installation. From the extracted project folder:

```powershell
.\deploy\windows\Install-AXIOM0.ps1 -Admin howard
.\deploy\windows\Start-AXIOM0.ps1
```

Then open `http://127.0.0.1:8765/`. The installer prints a local health report and creates unique service and reviewer keys stored under `axiom0_data` with an attempted user-only Windows file ACL. Inspect the ACL before handling sensitive sources. PowerShell execution policy or Python launcher configuration may require ordinary local setup adjustments. **Windows installer and startup have not been exercised on a real Windows host in this build environment.**

If running commands manually:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
axiom0 init --admin howard
axiom0 doctor
```

## Quick start — Linux/macOS

```bash
bash deploy/linux/install.sh
bash deploy/linux/start.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
axiom0 init --admin howard
axiom0 doctor
```

The supplied Linux installer uses local-user permissions (`700` data directory, `600` secrets file). Startup binds the API to **127.0.0.1 only**. It does **not** silently install services, schedule web scrapes, or expose AXIOM0 over the internet.

## 1. Run AXIOM0 inside a Python program

```python
from axiom0.core import Axiom0

ax = Axiom0('./axiom0_data')
# For a new local data directory (once):
ax.set_admin('howard')

# Ingest a correctly headed, authorized source document:
with open('examples/SIMULATED_charter.md', encoding='utf-8') as f:
    report = ax.library.ingest_text(f.read(), actor='howard')

result = ax.ask('howard', 'What does the sample charter say about public records?')
for finding in result['findings']:
    print(finding['text'], '->', finding['cite'])

# Deterministic area-level statistical flags using an example fixture:
flags = ax.warn('howard', 'examples/SIMULATED_service_requests.csv')
print(flags)
```

The imported sample files are **fictional fixtures, not Kansas City law or live service statistics**. The local Python interface enforces actor-label checks *within its facade*, but Python executed under the same operating-system account can still access private files or import lower-level modules. **This is not an untrusted-code sandbox.**

## 2. Use the machine-readable command line

```bash
axiom0 --json status
axiom0 --json ingest examples/SIMULATED_charter.md
axiom0 --json ask 'What does the fictional charter say about public records?'
axiom0 --json warn examples/SIMULATED_service_requests.csv
axiom0 --json queue
axiom0 --json verify
axiom0 --json doctor

# Accountability (v0.7)
axiom0 reviewer-add "Daliah West"        # prints a personal reviewer key once
axiom0 anchor                            # signed receipt to publish outside this computer
axiom0 anchor-verify ./anchors           # detects rewritten or rolled-back history
axiom0 backup ./backups                  # database + identity key + manifest (keep encrypted, offline)
axiom0 restore BACKUP.tar.gz --data-dir NEW_EMPTY_DIR
axiom0 export-audit audit.jsonl          # verify anywhere: python3 tools/axiom0_audit_verify.py audit.jsonl
```

From PowerShell, `axiom0 --json status | ConvertFrom-Json` returns a structured object. The command exits nonzero and emits a JSON `error` object for validation errors when `--json` is used. The local CLI relies on trusted computer-user/OS permissions and is **not** per-employee authentication.

## 3. Use the local web API

With the server started, pass the installer-generated service key as the `X-AXIOM0-Key` header. Routes include:

| Route | Intent |
|---|---|
| `POST /ask` | Source-matched citations; optional local model draft |
| `POST /ingest` | Ingest structured legal text into versioned Truth Library |
| `POST /warn` | Analyze a named CSV staged under `axiom0_data/imports/` |
| `GET /queue`, `POST /queue` | Review-queue listing and recommendation proposals |
| `POST /queue/review` | Needs the service key **and** a reviewer key; a personal key (`axr_…`) identifies the reviewer by name |
| `POST /v1/inquiry369` | Run the 3·6·9 evidence-review checklist over an existing hypothesis |
| `/v1/369/*`, `POST /v1/symbolic-state` | Optional personal module; 404 unless `AXIOM0_ENABLE_SYMBOLIC=1` |
| `GET /v1/legal/sections`, `POST /v1/legal/quote` | Source history and quote verification |
| `GET /v1/semisoul/profile`, `/memories`, `/attestation` | SemiSoul profile, memory and signed continuity attestation |
| `GET /v1/verify` | Verify local signed event history |

Example PowerShell. The key is read from the secrets file as data, into one variable, and never executed:

```powershell
$key = (Get-Content .\axiom0_data\axiom0-secrets.env | ConvertFrom-StringData).AXIOM0_API_KEY
$headers = @{ 'X-AXIOM0-Key' = $key }
$body = @{ question = 'What does the fictional charter say about records?' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8765/ask' -Headers $headers -ContentType 'application/json' -Body $body
```

**Other computers/apps:** AXIOM0 is a **localhost integration endpoint**, not an internet-ready API. A Clerk Access or Chambers Desk backend running on the same trusted workstation can call it through a server-side integration, but browser clients must not be given permanent service secrets. Cross-device access awaits a reverse proxy with approved SSO/OIDC, real staff identities and roles, TLS, audit integration, rate limits, origin restrictions, and security review.

## Optional local Ollama

1. Install Ollama independently and pull an instruction model supported by your computer, e.g. `ollama pull llama3.2:3b`.
2. Leave it bound to localhost at `http://127.0.0.1:11434`.
3. Import authorized sources first.
4. Run `axiom0 ask 'What is the sample policy?' --llm`.

If the model is missing, the command reports a local model error. There is no external model fallback. The LLM can generate a **draft** with validated **source IDs**, but there is no general semantic-entailment guarantee that each sentence follows from its citations. That requires a separate review process.

## Opt-in resilient feed monitoring

No sources are auto-scraped or bundled as official law. To monitor an official or authorized HTTPS source, register its **exact** hostname (DNS and private-network checks occur at fetch time):

```bash
axiom0 feed-add city-policy https://example.com/policy demo-policy --authority policy --title 'DEMO NOT OFFICIAL'
axiom0 --json fetch-once city-policy
axiom0 --json feed-list
axiom0 fetch-loop --hours 6
```

`example.com` above is only a syntax example. Register a real authorized source **only after confirming ownership, permission, applicability, and acceptable scraping rules**. Prefer official feeds/APIs where possible. The fetcher supports conditional HTTP checks and TTL: no download occurs during the locally configured freshness window; after the window, a conditional request may return `304 Not Modified`. A content hash alone cannot prevent the initial request.

The optional headless browser is disabled unless a feed is explicitly registered using `--render`; install its extra requirements with `pip install -e '.[render]'` and `playwright install chromium`. JavaScript rendering and hostile-site defenses require further testing before production use. Do not run multiple overlapping feed-loop processes. For unattended operation, configure **one** Windows Task Scheduler job or cron/systemd timer under a restricted user after local validation.

## SemiSoul: inspect, correct, and attest

```python
from axiom0.core import Axiom0
from axiom0.semisoul import SemiSoul
ax = Axiom0('./axiom0_data')
ax.semisoul.remember(statement='Research result needs an independent check',
    memory_type='reflection', epistemic_status='uncertain',
    source_type='operator', actor='howard')
attestation = ax.semisoul.attest()
assert SemiSoul.verify_attestation(attestation)
```

SemiSoul memories carry attribution and epistemic labels; corrections add signed records referencing earlier entries. The model can be replaced without resetting identity. `axiom0 verify` checks both the signed ledger and SemiSoul memory/profile histories. The private identity key must be backed up securely **with** its database and never shared.

## Deployment and assurance limits

A **local pilot** can be deployed from this package after the listed installation steps. This build has automated tests for the software, API and data/ledger pathways (see [`docs/VERIFICATION.md`](docs/VERIFICATION.md)), and CI runs the Windows installer on Windows. It has **not** been validated against live municipal infrastructure, a managed City workstation image, production identity providers, or a real model on target hardware (run `tools/eval_grounding.py` there).

**Do not operate as a City enforcement system or process restricted records until the data owner authorizes the use.** A municipal production decision requires penetration testing, threat modeling, data classification, legal review, signed-off access controls, an operating anchor-publication routine, rehearsed backups/restores, WCAG accessibility testing, incident response, and an identity provider with human-specific authentication. HTTPS URL allowlisting is not complete SSRF mitigation, and history *after* the newest published anchor can still be rewritten by someone who controls the whole host.

Read [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md), [`docs/SECURITY.md`](docs/SECURITY.md), and [`docs/PHILOSOPHY.md`](docs/PHILOSOPHY.md) before using real sources.

## Package lineage

This build combines the recovered v0.1 AXIOM0 numerical specification and Python code; the original v0.2 Municipal Intelligence Core (preserved under `reference/axiom0-v0.2-original.zip`); v0.3 occurrence intelligence; v0.4 intention practice; v0.5 SemiSoul and municipal-source libraries; v0.6.1 Raspberry Pi 5 edition; and v0.7 fixes from an external review (anchoring, reviewer identities, DNS pinning, SPIKE-v2, migrations, backups, Windows CI, grounding evaluation). It is not a complete implementation of earlier Ezmerelda hardware, remote witnessing or production authorization components.

**Licensing:** no general-purpose redistribution license is granted here. Review intellectual-property rights, third-party dependencies, and data licenses before distribution or commercial licensing.
