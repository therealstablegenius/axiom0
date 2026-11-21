# Ledger anchoring: making rollback and rewrites detectable

## The problem it solves

AXIOM0 signs and hash-chains every event, so editing history without the signing key
is detected. But whoever controls the computer controls **both** the database and the
key. They could rewrite an old event, then re-hash and re-sign everything after it. The
result verifies perfectly on that machine. The v0.6 review called this the missing piece
for an accountability system.

## How anchoring closes it

```bash
axiom0 anchor
```

writes a small signed **receipt**: "event number N had hash H, signed by identity X, at
time T". It contains no ledger content, so it is safe to publish. Once a copy exists
somewhere this computer cannot edit, any later rewrite of events 1..N, or a rollback
to fewer than N events, fails:

```bash
axiom0 anchor-verify path/to/receipts/
```

Auditors do not need AXIOM0 itself; they can check an audit export against published
receipts with a separate script that needs only Python and `cryptography`:

```bash
axiom0 export-audit audit.jsonl
python3 tools/axiom0_audit_verify.py audit.jsonl receipts/*.json
```

## Where to publish (your decision)

| Option | Strength | Effort |
|---|---|---|
| **Public GitHub repo** (e.g. `axiom0-anchors`), pushed daily | History held by GitHub and every clone; anyone can check it | Recommended; automated below |
| Email the receipt to another office (e.g. the Clerk's shared inbox) | Held by a separate system and custodian | Manual or scripted |
| Print and file with meeting records | Physical, independent | Manual |
| RFC 3161 timestamping authority | Third-party time proof | Not built in yet |

Publishing more than one way is stronger. Anchor often (daily): a rewrite of events
*after* the newest published receipt is not covered until the next anchor.

## Automating it (Linux / Raspberry Pi)

1. Create an empty **public** GitHub repository, for example `axiom0-anchors`.
2. On the Pi, install with `--enable-anchors` (or re-run the installer with it). This
   creates `/var/lib/axiom0-anchors` and a daily timer.
3. Make that folder a clone of the repo, owned by the service account, with a deploy key
   that can push only to that one repository:

   ```bash
   sudo -u axiom0 install -d -m 700 /var/lib/axiom0/.ssh
   sudo -u axiom0 ssh-keygen -t ed25519 -N '' -f /var/lib/axiom0/.ssh/anchors_deploy
   # GitHub → axiom0-anchors → Settings → Deploy keys → add the .pub file, allow write
   sudo -u axiom0 git clone git@github.com:<you>/axiom0-anchors.git /var/lib/axiom0-anchors
   sudo -u axiom0 git -C /var/lib/axiom0-anchors config core.sshCommand \
        "ssh -i /var/lib/axiom0/.ssh/anchors_deploy -o IdentitiesOnly=yes"
   ```

4. Test once: `sudo systemctl start axiom0-anchor.service; journalctl -u axiom0-anchor -n 20`.

Each run **first** checks every receipt already published. If any no longer matches, it
logs an ALERT, exits with code 3 and does not issue a new receipt. Then it issues and
pushes a new one.

Elsewhere: `AXIOM0_ANCHOR_DIR=/path/to/clone deploy/anchor/axiom0-anchor-publish.sh`
works on any Linux or macOS machine. On Windows, run `axiom0 anchor --out <folder>` from
Task Scheduler and publish the folder by your chosen route.

## What anchoring does not do

- It does not stop someone with the key from **adding** false new events; it makes
  changes to *already anchored* history detectable.
- It cannot detect anything about events after the newest published receipt.
- If the identity key is stolen, the thief can sign receipts too. Receipts already
  published still pin the old history. There is no automated key rotation yet: treat
  the install as compromised, keep its data and receipts as evidence, and start a new
  identity in a fresh data directory.
