"""Personal reviewer identities.

v0.6 had one shared reviewer key plus a configured label (AXIOM0_REVIEWER_ID), so
"who reviewed this" was whatever the label said. v0.7 enrolls each reviewer with
their own key. The API derives the reviewer's name from the key presented, so a
reviewer can no longer claim another name, and separation of duties compares
authenticated identities.

Limits (stated plainly): this is key-based identity on a single host. It is not
SSO, MFA or HR-verified identity. The local administrator who enrolls reviewers
is trusted. Production deployment still needs an identity provider (OIDC).
"""
from __future__ import annotations
import hashlib
import re
import secrets
from .store import Store, now

KEY_PREFIX = 'axr_'
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$')


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


class Reviewers:
    def __init__(self, store: Store):
        self.store = store

    def enroll(self, name: str, *, enrolled_by: str) -> dict:
        """Create (or re-issue after revocation) a reviewer key. The key is shown once, never stored."""
        if not isinstance(name, str) or not _NAME.match(name.strip()):
            raise ValueError('Reviewer name: 1-80 letters, digits, spaces, dot, dash or underscore')
        name = name.strip()
        if name.casefold() in ('api_service', 'local_operator'):
            raise ValueError('That name is reserved for service principals')
        key = KEY_PREFIX + secrets.token_urlsafe(32)
        key_sha = _hash(key)
        stamp = now()
        with self.store.write() as conn:
            row = conn.execute('SELECT revoked_at FROM reviewers WHERE name=? COLLATE NOCASE', (name,)).fetchone()
            if row and row['revoked_at'] is None:
                raise ValueError(f'Reviewer {name!r} already has an active key; revoke it first to re-issue')
            conn.execute('DELETE FROM reviewers WHERE name=? COLLATE NOCASE', (name,))
            conn.execute('INSERT INTO reviewers(name,key_sha256,enrolled_at,enrolled_by) VALUES(?,?,?,?)',
                         (name, key_sha, stamp, enrolled_by))
            self.store.append(conn, 'reviewer_enrolled', {'name': name, 'enrolled_by': enrolled_by,
                                                          'key_fingerprint': key_sha[:12],
                                                          'reissue': bool(row)})
        return {'name': name, 'key': key, 'key_fingerprint': key_sha[:12],
                'note': 'Give this key to the reviewer privately. It is shown once and only its hash is stored.'}

    def revoke(self, name: str, *, revoked_by: str) -> dict:
        stamp = now()
        with self.store.write() as conn:
            row = conn.execute('SELECT name FROM reviewers WHERE name=? COLLATE NOCASE AND revoked_at IS NULL',
                               (name,)).fetchone()
            if not row:
                raise ValueError(f'No active reviewer named {name!r}')
            conn.execute('UPDATE reviewers SET revoked_at=?,revoked_by=? WHERE name=?', (stamp, revoked_by, row['name']))
            self.store.append(conn, 'reviewer_revoked', {'name': row['name'], 'revoked_by': revoked_by})
        return {'name': row['name'], 'revoked_at': stamp}

    def list(self) -> list[dict]:
        with self.store.connect() as conn:
            rows = conn.execute('SELECT name,enrolled_at,enrolled_by,revoked_at,revoked_by,key_sha256 '
                                'FROM reviewers ORDER BY name COLLATE NOCASE').fetchall()
        return [{**{k: r[k] for k in ('name', 'enrolled_at', 'enrolled_by', 'revoked_at', 'revoked_by')},
                 'key_fingerprint': r['key_sha256'][:12], 'active': r['revoked_at'] is None} for r in rows]

    def authenticate(self, key: str | None) -> str | None:
        """Return the reviewer's name for an active personal key, else None."""
        if not key or not key.startswith(KEY_PREFIX) or len(key) > 200:
            return None
        with self.store.connect() as conn:
            row = conn.execute('SELECT name FROM reviewers WHERE key_sha256=? AND revoked_at IS NULL',
                               (_hash(key),)).fetchone()
        return row['name'] if row else None
