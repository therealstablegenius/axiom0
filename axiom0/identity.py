"""Persistent Ed25519 SemiSoul identity. Model is replaceable; identity is not.

Prototype: protects against edits without the private key, not full-host compromise,
key theft, or coherent rollback. Store private keys in a secured directory.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization


class Identity:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == 'posix':
            self.folder.chmod(0o700)
        key_path = self.folder / 'identity.ed25519'
        if not key_path.exists():
            # Atomic exclusive creation protects against accidentally replacing an identity.
            key = Ed25519PrivateKey.generate()
            raw = key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            try:
                fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'wb') as f:
                    f.write(raw)
                    f.flush()
                    os.fsync(f.fileno())
            except FileExistsError:
                pass
        if os.name == 'posix' and (key_path.stat().st_mode & 0o077):
            raise PermissionError('Private identity key has insecure permissions')
        raw = key_path.read_bytes()
        if len(raw) != 32:
            raise ValueError('Invalid persisted identity key')
        self.private = Ed25519PrivateKey.from_private_bytes(raw)
        self.public = self.private.public_key()
        self.public_raw = self.public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.id = hashlib.sha256(self.public_raw).hexdigest()[:32]

    def sign(self, message: bytes) -> str:
        return self.private.sign(message).hex()

    def verify_signature(self, message: bytes, signature: str) -> None:
        self.public.verify(bytes.fromhex(signature), message)

    @staticmethod
    def verify_with_public_key(public_hex: str, message: bytes, signature: str) -> None:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(bytes.fromhex(signature), message)
