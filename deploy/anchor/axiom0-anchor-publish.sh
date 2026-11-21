#!/usr/bin/env bash
# Issue a signed ledger anchor and publish it somewhere this computer cannot rewrite.
#
#   AXIOM0_ANCHOR_DIR=/path/to/anchors-repo  axiom0-anchor-publish.sh
#
# If AXIOM0_ANCHOR_DIR is a git clone with a remote (recommended: a separate PUBLIC
# repository such as github.com/<you>/axiom0-anchors), the receipt is committed and
# pushed, so its history is held by GitHub and every clone, not by this host.
# Receipts contain only the event number, its hash, timestamps and a signature: no
# ledger contents, so they are safe to publish.
set -euo pipefail
DIR=${AXIOM0_ANCHOR_DIR:?Set AXIOM0_ANCHOR_DIR to the anchors folder (ideally a git clone of a public repo)}
AXIOM0=${AXIOM0_CMD:-axiom0}

# 1. Check every receipt published so far BEFORE issuing a new one, so a rollback or
#    rewrite is reported even if the ledger is now too damaged to anchor.
if compgen -G "$DIR/*.json" >/dev/null; then
  if "$AXIOM0" --json anchor-verify "$DIR" >/dev/null; then
    echo "all previously published receipts are consistent with the ledger"
  else
    echo "ALERT: a published receipt no longer matches the ledger (rewrite or rollback)." >&2
    echo "       Details: axiom0 anchor-verify $DIR    No new anchor was issued." >&2
    exit 3
  fi
fi

# 2. Issue and publish a new receipt.
out=$("$AXIOM0" --json anchor --out "$DIR")
file=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["file"])' <<<"$out")
echo "anchor written: $file"

if git -C "$DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$DIR" add -- "$(basename "$file")"
  git -C "$DIR" -c user.name="${AXIOM0_ANCHOR_GIT_NAME:-AXIOM0 anchor}" \
      -c user.email="${AXIOM0_ANCHOR_GIT_EMAIL:-anchor@localhost}" \
      commit -q -m "AXIOM0 ledger anchor $(basename "$file" .json)"
  if git -C "$DIR" remote get-url origin >/dev/null 2>&1; then
    git -C "$DIR" push -q origin HEAD
    echo "published to $(git -C "$DIR" remote get-url origin)"
  else
    echo "WARNING: committed locally only. Add a remote so the anchor leaves this computer." >&2
  fi
else
  echo "NOTE: $DIR is not a git repository. Copy the receipt somewhere this computer cannot edit" >&2
  echo "      (email it to another office, print it, or use a git repo with a remote)." >&2
fi

