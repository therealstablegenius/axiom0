# AXIOM0 Living City v0.6 — Deployment Runbook

## Stage A: single-workstation local pilot

1. Extract the ZIP to a trusted, non-cloud-synced path, ideally without spaces in the path until Windows installer validation is complete.
2. Verify Python 3.11+, a network connection for dependency installation, and a user account with write access to the extracted folder.
3. Install via `deploy/windows/Install-AXIOM0.ps1` or `deploy/linux/install.sh`; scripts create the venv, install the package, initialize the local admin label, generate distinct secrets, and run `doctor`.
4. Run the unit suite: `.venv/bin/python -m pytest -q` on Linux, `.venv\Scripts\python.exe -m pytest -q` on Windows (install the `[test]` extra if needed).
5. Start the loopback server with `deploy/linux/start.sh` or `deploy/windows/Start-AXIOM0.ps1`; verify `GET /health` and use the separate service key for `GET /v1/status`.
6. Import only **fictional** sample content, review citations and ledger entries, then test fresh startup from the same data directory and compare SemiSoul ID.
7. Do a fresh encrypted backup and a disconnected restore test. No real municipal data until explicit authorization.

## Stage B: controlled authorized sources

1. Obtain written authorization and a source owner, exact canonical URL, terms/robots policy, document ID, jurisdiction, effective date policy and retention schedule.
2. Add one source with `axiom0 feed-add ...`; run one `fetch-once` manually and inspect extracted text.
3. Confirm it did not misparse headings or accidentally drop sections; review each `changed`/`removed` report before relying on it.
4. Run the loop only after monitoring is stable, as a single restricted process via your chosen scheduler. The loop sleeps six hours by default; TTL and conditional requests reduce redundant downloads. Transient failures are logged without superseding previously ingested versions.
5. Check source retrieval relevance, quote-gate accuracy, false alerts, and document security labeling before any staff pilot.

## Stage C: cross-device apps (NOT included)

Before Clerk Access, Chambers Desk, a district dashboard or another computer can connect, implement OIDC/SSO with MFA, separate service identities, scoped tokens, authentic human reviewer attribution, API throttling, TLS transport, network segmentation, replay protection, approved integrations, change control, accessibility testing, independent security review, and a formal data-sharing agreement. Do not expose the loopback secret API directly.

## Upgrade from v0.3/v0.4/v0.5

1. Stop AXIOM0 entirely and take an encrypted full backup of the existing `axiom0_data/` directory, including `identity.ed25519` and `living_city.sqlite3` and any WAL files.
2. Place the new code in a **new directory** while pointing `AXIOM0_DATA_DIR` at the backed-up existing data directory. Do not replace your identity key or reinitialize it as a new identity.
3. Run `axiom0 doctor` and `axiom0 verify`; compare the stored `semisoul_id` and audit head with the pre-upgrade snapshot.
4. Run the smoke checks and only then enable scheduled imports or Ollama. If anything fails, stop and restore the whole snapshot. There is no automatically supported rollback migration.

The old `axiom0-v0.2.zip` is **preserved for reference**, not automatically migrated into a v0.6 SQLite database. Read its original data schema if an old v0.2 **database** must be migrated: that requires an explicit, audited conversion, not copying raw SQLite tables over.

## Scheduling examples (explicit operator opt-in)

**Windows Task Scheduler:** create one task under the restricted operator account, run only when the account has the necessary permissions, program `C:\path\to\AXIOM0\.venv\Scripts\python.exe`, arguments `-m axiom0 --data-dir "C:\path\to\AXIOM0\axiom0_data" fetch-once`, start-in directory `C:\path\to\AXIOM0`; trigger every six hours. Validate the task history and signed `feed_cycle` events.

**Linux cron:** after one successful manual fetch, add a single cron entry using your actual paths:

```cron
0 */6 * * * /absolute/path/AXIOM0/.venv/bin/python -m axiom0 --data-dir /absolute/path/AXIOM0/axiom0_data fetch-once >> /absolute/path/AXIOM0/fetch.log 2>&1
```

Avoid scheduling `fetch-loop` *and* the six-hour task. For systemd, use a dedicated service identity and supervised timer after testing permissions, resource limits, and restart behavior. The installer deliberately does not schedule the task for you.
