# AXIOM0 v0.7 — Pilot Security Boundaries

## Threat model

**Controls included:**
- loopback-only FastAPI, with distinct random service and reviewer secrets;
- response size limits, and no automatic cloud LLM fallback;
- Ed25519 signature checks and SHA-256 ledger chaining, with SemiSoul memory and profiles checked against the signed event history;
- **external ledger anchoring** (signed head receipts, `anchor-verify`, and an independent verifier), which makes coherent rewrites and rollbacks by a host operator detectable once a receipt is published;
- **personal reviewer keys**: the reviewer's identity comes from the key and is never taken from the request, keys are stored only as hashes, they can be revoked, and both enrolment and revocation are ledgered;
- versioned, ledgered **schema migrations**, with refusal to run older code against newer data;
- HTTPS feed registry, hostname allowlist and public-DNS checks, with **DNS pinning** (connect to the validated address; TLS still verifies the real hostname) and redirect refusal;
- no implicit feed registration from the API, staged CSV paths, and read-only source ingestion;
- no autonomous enforcement or spending, plus a forbidden-action guardrail;
- **consistent backups with manifest hashes and verified restore**, and a signed audit export;
- Windows secrets stored as owner-only **data**, never as an executed script;
- the optional 3·6·9 / symbolic module is **off by default**.

**Controls not provided:**
- Identity and access: enterprise identity proofing, SSO/OIDC/MFA, session expiry, full RBAC. Reviewer keys are a stronger single-host mechanism, not staff identity, and local `--admin` is an operator label, not a password-backed login.
- Keys and data protection: hardware-backed key protection, automated key rotation, and encryption at rest. Backups contain the private key and must be stored encrypted and offline by the operator.
- Assurance: adversarial review of the rendering browser, malware containment, CI build attestation and SBOM signing, production monitoring, and penetration testing.

The workstation account can always access its own key and database. Anchoring makes *anchored* history tamper-evident against that account; it does not stop the account from appending new false events.

## Operational rules

1. Run as a dedicated least-privilege OS account (the Pi 5 installer creates `axiom0`). Never as a domain administrator or root.
2. Store `axiom0_data/` off cloud-synced folders. On Windows the installer restricts the data folder and `axiom0-secrets.env` to your account; on Linux they are `700`/`640`.
3. **Back up** with `axiom0 backup`, encrypt the archive, keep it offline, and rehearse `axiom0 restore` on a spare machine. After a restore, run `anchor-verify` against your published receipts.
4. **Anchor daily** and publish the receipts outside the host (see `ANCHORING.md`).
5. Enroll each human reviewer with `axiom0 reviewer-add NAME` and set `AXIOM0_REQUIRE_PERSONAL_REVIEWERS=1` once everyone has a key. Revoke keys when people change roles.
6. Use a real identity provider (OIDC) for any multi-user or cross-device access. Do not put the local prototype behind a public reverse proxy.
7. Use only authorized public or contractually approved data. No personal profiling, person-level risk scoring, or inference of criminality from residence, demographics or complaint patterns.
8. Every municipal legal conclusion needs counsel and version/effective-date review. A matched quote is an excerpt, not an answer and not a legal opinion.
9. No autonomous enforcement, official-record edits, payment authorization or resident-directed adverse decisions. The forbidden-action check is a guardrail against ordinary wording; the real control is that AXIOM0 has no capability to act and every recommendation needs a separate reviewer.
10. Threat-model feed scraping before production: hostile pages can carry prompt injections, and the headless browser needs independent review.
11. Review retention, deletion, public-records, privacy, accessibility and procurement policies before onboarding any city department.

## Verify a pilot instance

```bash
axiom0 doctor
axiom0 verify
axiom0 anchor-verify <published receipts folder>
python -m pytest -q
```

The local ledger is **tamper-evident under its threat model**. With published anchors,
rewriting anchored history is detectable even by someone holding the key. A source's
content hash proves what bytes were stored, not that the source is authoritative or complete.
