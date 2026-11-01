"""MQTT wire format for per-node HMAC secrets.

Plaintext ``node_secret`` must not be published. When a wrap passphrase is
configured (the same value as the node's ``mqtt.password``), the secret is
sent as ``node_secret_enc``:

    base64(nonce_12 || ciphertext || tag_16)

AES-256-GCM, key = SHA-256("hydro.node_secret.wrap.v1" || passphrase),
AAD = node_uid (UTF-8). Firmware unwraps with the MQTT password stored in NVS
and keeps the previous secret when the field is absent or unwrap fails.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_WRAP_LABEL = b"hydro.node_secret.wrap.v1"
_NONCE_LEN = 12
_TAG_LEN = 16


def _wrap_key(passphrase: str) -> bytes:
    return hashlib.sha256(_WRAP_LABEL + passphrase.encode("utf-8")).digest()


def wrap_node_secret(
    secret: str,
    passphrase: str,
    node_uid: str,
    *,
    nonce: bytes | None = None,
) -> str:
    """Encrypt ``secret`` for the MQTT NodeConfig payload."""
    if not secret or not passphrase or not node_uid:
        raise ValueError("secret, passphrase and node_uid are required")
    nonce_bytes = nonce if nonce is not None else os.urandom(_NONCE_LEN)
    if len(nonce_bytes) != _NONCE_LEN:
        raise ValueError("nonce must be 12 bytes")
    ciphertext = AESGCM(_wrap_key(passphrase)).encrypt(
        nonce_bytes,
        secret.encode("utf-8"),
        node_uid.encode("utf-8"),
    )
    return base64.b64encode(nonce_bytes + ciphertext).decode("ascii")


def unwrap_node_secret(token: str, passphrase: str, node_uid: str) -> str:
    """Decrypt a ``node_secret_enc`` value. Raises on authentication failure."""
    raw = base64.b64decode(token, validate=True)
    if len(raw) < _NONCE_LEN + _TAG_LEN:
        raise ValueError("node_secret_enc is too short")
    nonce = raw[:_NONCE_LEN]
    ciphertext = raw[_NONCE_LEN:]
    plain = AESGCM(_wrap_key(passphrase)).decrypt(
        nonce,
        ciphertext,
        node_uid.encode("utf-8"),
    )
    return plain.decode("utf-8")


def _wrap_passphrase() -> str:
    return (
        os.getenv("NODE_SECRET_WRAP_PASSPHRASE")
        or os.getenv("MQTT_ESP32_NODE_PASS")
        or ""
    ).strip()


def prepare_node_config_for_mqtt(
    config: dict[str, Any],
    *,
    node_uid: str,
    node_secret: str | None = None,
) -> dict[str, Any]:
    """Remove plaintext ``node_secret`` and attach ``node_secret_enc`` when possible."""
    incoming = config.get("node_secret")
    secret = node_secret if isinstance(node_secret, str) and node_secret != "" else None
    if secret is None and isinstance(incoming, str) and incoming != "":
        secret = incoming

    config.pop("node_secret", None)
    config.pop("node_secret_enc", None)

    passphrase = _wrap_passphrase()
    if secret and passphrase and node_uid:
        config["node_secret_enc"] = wrap_node_secret(secret, passphrase, node_uid)
    elif secret:
        logger.warning(
            "NodeConfig node_secret withheld from MQTT (wrap passphrase unset): node_uid=%s",
            node_uid,
        )
    return config
