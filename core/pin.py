"""
PIN-Hashing für den Zugriffsschutz des Einstellungen-Modals.
"""

import hashlib
import hmac
import secrets

_ITERATIONS = 200_000


def hash_pin(pin: str) -> str:
    """Hasht eine PIN mit einem zufälligen Salt (PBKDF2-HMAC-SHA256)."""

    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    )

    return f"{salt}${digest.hex()}"


def verify_pin(pin: str, pin_hash: str) -> bool:
    """Prüft eine PIN gegen einen zuvor mit hash_pin() erzeugten Hash."""

    if not pin_hash or "$" not in pin_hash:
        return False

    salt, expected = pin_hash.split("$", 1)

    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    )

    return hmac.compare_digest(digest.hex(), expected)
