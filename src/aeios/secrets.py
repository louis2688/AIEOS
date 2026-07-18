"""Local secret sealing for at-rest API keys (stdlib only).

Stored format: ``enc:v1:<salt_b64>:<mac_b64>:<ct_b64>``

Uses PBKDF2-HMAC-SHA256 key derivation, SHA-256 keystream XOR, and HMAC-SHA256
for integrity. Intended for local SQLite at-rest protection with
``AEIOS_SECRETS_KEY`` — not a substitute for OS keychain / KMS in multi-tenant
deployments.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

PREFIX = "enc:v1:"
_PBKDF2_ROUNDS = 120_000


def is_sealed(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def seal(plaintext: str, master_key: str) -> str:
    if not master_key:
        raise ValueError("master_key is required to seal a secret")
    if not plaintext:
        raise ValueError("plaintext is required to seal a secret")
    salt = os.urandom(16)
    enc_key, mac_key = _split_keys(master_key, salt)
    ct = _xor_keystream(plaintext.encode("utf-8"), enc_key)
    mac = hmac.new(mac_key, salt + ct, hashlib.sha256).digest()
    return (
        PREFIX
        + _b64(salt)
        + ":"
        + _b64(mac)
        + ":"
        + _b64(ct)
    )


def unseal(token: str, master_key: str) -> str:
    if not master_key:
        raise ValueError("master_key is required to unseal a secret")
    if not is_sealed(token):
        raise ValueError("value is not a sealed secret")
    body = token[len(PREFIX) :]
    parts = body.split(":")
    if len(parts) != 3:
        raise ValueError("malformed sealed secret")
    salt = _b64d(parts[0])
    mac = _b64d(parts[1])
    ct = _b64d(parts[2])
    enc_key, mac_key = _split_keys(master_key, salt)
    expected = hmac.new(mac_key, salt + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("sealed secret MAC mismatch (wrong AEIOS_SECRETS_KEY?)")
    return _xor_keystream(ct, enc_key).decode("utf-8")


def _split_keys(master_key: str, salt: bytes) -> tuple[bytes, bytes]:
    material = hashlib.pbkdf2_hmac(
        "sha256",
        master_key.encode("utf-8"),
        salt,
        _PBKDF2_ROUNDS,
        dklen=64,
    )
    return material[:32], material[32:]


def _xor_keystream(data: bytes, enc_key: bytes) -> bytes:
    out = bytearray(len(data))
    counter = 0
    offset = 0
    while offset < len(data):
        block = hashlib.sha256(enc_key + counter.to_bytes(8, "big")).digest()
        for b in block:
            if offset >= len(data):
                break
            out[offset] = data[offset] ^ b
            offset += 1
        counter += 1
    return bytes(out)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode("ascii"))
