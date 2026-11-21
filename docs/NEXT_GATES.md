# The next engineering gates

Status as of v0.7.0. ✅ done · 🟡 partly done (tooling exists, real-world step remains) · ⬜ open

## 1. Authority and jurisdiction

- ⬜ Reproduce and verify the official Kansas City, Missouri City Charter and municipal code, section by section, with authoritative links and legal effective dates.
- ✅ Versioned legal sections with hashes; amended and repealed provisions are detected (`legal_sections`, since v0.6).
- ⬜ Require review by legal experts where hierarchy, statutory preemption or legal ambiguity arises.

## 2. Data quality and signals

- ⬜ Source-specific authorized connectors, retention and redaction rules.
- ⬜ Verify whether allegedly independent source labels represent independent evidence.
- 🟡 Service-request spike detection: v0.7 adds a count model, seasonality and false-discovery control (SPIKE-v2). Still open: validation against real 311 history (sensitivity, specificity, drift) and disparate-impact checks.
- ✅ Refuses person-identifying columns; area level only.

## 3. Secure deployment

- 🟡 Identity: personal reviewer keys with hashing, revocation and ledgering (v0.7). Still open: SSO/OIDC with MFA and RBAC for multi-user or cross-device use.
- 🟡 Audit witness: signed anchor receipts, a publishing script, a daily Pi timer and an independent verifier (v0.7). Still open: choose and start the publication channel (see `ANCHORING.md`).
- ✅ Backups with verified restore and audit export (v0.7). ⬜ Encrypted backup storage and recovery drills are operator procedures.
- ✅ DNS-rebinding window closed by connection pinning (v0.7).
- 🟡 Windows: the installer is exercised on Windows in CI (v0.7). Still open: a run on a managed City workstation image.
- ⬜ Threat modeling, penetration testing, encryption at rest, compliance and legal review, key rotation.

## 4. Model and human review

- 🟡 Grounding evaluation: `tools/eval_grounding.py` measures citation correctness, stated facts, refusal and lexical support (v0.7). Still open: run it against the real model on the target hardware and record the results in `VERIFICATION.md`; then add prompt-injection cases.
- ✅ Excerpts are labelled as excerpts, not answers (v0.7).
- ⬜ Human fact-check protocol and time-bounded statuses; findings can be disputed or superseded.
- ✅ No automatic public-action execution.

## 5. Broader product system

- ⬜ Optional, permission-controlled read-only adapters to Clerk Access and Chambers Desk.
- ⬜ WCAG 2.1 AA audit of the dashboard (it has labels, focus styles and live regions, but no audit yet).
- 🟡 Reproducible deployment: CI on Linux, Windows and macOS (v0.7). ⬜ Signed builds and a dependency SBOM.
- ✅ The 3·6·9 / symbolic module is optional and off by default (v0.7). Splitting it into a separate package is possible later if a deployment must not ship the code at all.
