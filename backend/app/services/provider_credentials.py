"""Authenticated encryption bound to a provider identity and endpoint origin."""
import hmac
import json
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.errors import AppError


def endpoint_origin(url):
    parts = urlsplit(url)
    return [parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)]


def crypto(settings):
    try:
        values = settings.external_ocr_encryption_keys.get_secret_value().split(",")
        if not 1 <= len(values) <= 3 or any(not value.strip() for value in values):
            raise ValueError("Missing key")
        return MultiFernet([Fernet(value.strip().encode()) for value in values])
    except (ValueError, TypeError):
        raise AppError("Credential encryption is unavailable. Contact the server operator.", 503) from None


def encrypt_credential(settings, value, provider_id, endpoint):
    payload = {"value": value, "provider_id": provider_id, "origin": endpoint_origin(endpoint)}
    return crypto(settings).encrypt(json.dumps(payload).encode()).decode()


def decrypt_credential(settings, value, provider_id, endpoint):
    try:
        payload = json.loads(crypto(settings).decrypt(value.encode()))
        if (payload.get("provider_id") != provider_id or payload.get("origin") != endpoint_origin(endpoint)
                or not isinstance(payload.get("value"), str)):
            raise ValueError("Credential binding mismatch")
        return payload["value"]
    except (InvalidToken, ValueError, TypeError, KeyError):
        raise AppError("Stored credential is unavailable for this provider and origin.", 503) from None


def same_credential(first, second):
    return hmac.compare_digest(first.encode(), second.encode())
