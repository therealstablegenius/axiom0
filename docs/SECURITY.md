# AXIOM0 v0.6 — Pilot Security Boundaries

## Threat model

**Controls included:** loopback-only FastAPI, distinct random service/reviewer secrets, response size limits, no automatic cloud LLM fallbacks, Ed25519 signature checks, SHA-256 ledger chaining, SemiSoul memory/profiles checked against signed event history, HTTPS feed registry, hostname allowlist, public-DNS checks, redirect refusal, no implicit feed registration from API, staged CSV paths, read-only source ingestion, no autonomous enforcement or spending, and separation of reviewer/service credentials.

**Controls not provided:** enterprise identity proofing, SSO/OIDC, session expiry, full RBAC, hardware-backed key protection, tamper-proof remote witnessing, comprehensive DNS-rebinding defense, browser sandbox adversarial assessment, malware containment, encryption at rest for all records, robust backups, secrets rotation, CI attestation, or production-grade service monitoring. The workstation account can access its own key/database. Local `--admin` is an operator label, not a password-backed login.

## Operational rules

1. Run as a dedicated least-privilege OS account. Never as a domain administrator or root.
2. Store `axiom0_data/` off cloud-synced folders. Protect `identity.ed25519` and the separate secrets file with OS filesystem ACLs and private backup.
3. Back up the database **and** private key together, encrypt backups, and exercise restores to a disconnected host. Consider remote hash-head anchoring so coherent rollback cannot go unnoticed.
4. Use real identity provider/OIDC for any multiuser or cross-device access. Do not place the local prototype behind a public reverse proxy.
5. Use only authorized public or contractually approved data. Avoid personal profiling, person-level risk scoring, or inference of criminality from residence, demographics, or complaint patterns.
6. Every municipal legal conclusion needs counsel and version/effective-date review. A matched quote is not a legal opinion.
7. No autonomous enforcement, official-record edits, payment authorization, or resident-directed adverse decisions.
8. Threat-model feed scraping before production: hostile pages can contain prompt injections; remote DNS could rebind between validation and request, and headless browser behavior needs independent auditing.
9. Review retention, deletion, public-record, privacy, accessibility, and procurement policies before onboarding any city department.
10. Only the API's **service principals** are authenticated by secrets. `reviewer` fields on the local CLI are operator assertions, not verified human signatures. For human-specific audit accountability, integrate identity provider before deployment.

## Verify a pilot instance

```bash
axiom0 doctor
axiom0 verify
python -m pytest -q
```

The local ledger is **tamper-evident under its threat model**, not immutable against complete host compromise. A source's content hash proves what bytes were stored, not that the source itself is authoritative or historically complete.
