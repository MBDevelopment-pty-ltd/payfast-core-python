"""
payfast_core.security
---------------------
Single, auditable module for every security-sensitive operation in the SDK.

All signature generation, ITN validation, and IP allow-list checking lives
here. If you are doing a security audit, this is the only file you need to
read.

Design goals
~~~~~~~~~~~~
* Zero side-effects — every function is pure (takes inputs, returns outputs).
* Constant-time comparisons everywhere to prevent timing attacks.
* Explicit over implicit — no global state, no hidden config reads.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from urllib.parse import quote_plus

from payfast_core.exceptions import (
    InvalidSignatureException,
    InvalidSourceIPException,
)

logger = logging.getLogger("payfast_core.security")

# ---------------------------------------------------------------------------
# PayFast IP allow-list
# Source: https://developers.payfast.co.za/docs#notify_handling
# ---------------------------------------------------------------------------

PAYFAST_IP_ALLOWLIST: frozenset[str] = frozenset({
    "197.97.145.144",
    "197.97.145.145",
    "197.97.145.146",
    "197.97.145.147",
    "41.74.179.194",
    "41.74.179.195",
    "41.74.179.196",
    "41.74.179.197",
})


# ---------------------------------------------------------------------------
# Signature generation
# ---------------------------------------------------------------------------

def build_signature_string(data: dict, passphrase: str | None = None) -> str:
    """
    Build the pre-hash string PayFast uses for MD5 signing.

    Rules (from PayFast docs):
    * Remove the ``signature`` key if present.
    * Skip fields whose value (after stripping whitespace) is empty.
    * URL-encode each value with ``quote_plus``.
    * Join as ``key=value&key=value``.
    * Append ``&passphrase=<value>`` if a passphrase is provided.

    Parameters
    ----------
    data:
        Arbitrary key/value pairs (payment data, ITN payload, etc.).
    passphrase:
        Optional passphrase configured in the PayFast merchant account.

    Returns
    -------
    str
        The pre-hash string, ready to be MD5-digested.
    """
    filtered = {
        k: str(v).strip()
        for k, v in data.items()
        if k != "signature" and str(v).strip() != ""
    }

    pf_string = "&".join(
        f"{k}={quote_plus(v)}" for k, v in filtered.items()
    )

    if passphrase and passphrase.strip():
        pf_string += f"&passphrase={quote_plus(passphrase.strip())}"

    return pf_string


def generate_signature(data: dict, passphrase: str | None = None) -> str:
    """
    Generate the MD5 signature for ``data``.

    Parameters
    ----------
    data:
        Payment data or ITN payload.
    passphrase:
        Optional merchant passphrase.

    Returns
    -------
    str
        32-character lowercase MD5 hex digest.
    """
    pf_string = build_signature_string(data, passphrase)
    digest    = hashlib.md5(pf_string.encode()).hexdigest()  # noqa: S324 — PayFast mandates MD5
    logger.debug("Signature generated for keys: %s", list(data.keys()))
    return digest


def signatures_match(expected: str, received: str) -> bool:
    """
    Compare two signature strings in constant time.

    Uses :func:`hmac.compare_digest` to prevent timing-based side-channel
    attacks. Always compare the *expected* signature (computed by us) against
    the *received* one (from the untrusted payload) — never the other way.

    Parameters
    ----------
    expected:
        The signature we computed from the payload.
    received:
        The signature submitted in the ITN or webhook request.

    Returns
    -------
    bool
        ``True`` only when both strings are identical.
    """
    return hmac.compare_digest(
        expected.encode("utf-8"),
        received.encode("utf-8"),
    )


# ---------------------------------------------------------------------------
# ITN signature validation
# ---------------------------------------------------------------------------

def validate_signature(
    payload: dict,
    passphrase: str | None = None,
) -> None:
    """
    Validate the ``signature`` field inside an ITN payload.

    Parameters
    ----------
    payload:
        The full ITN POST body as a flat dict, including the ``signature`` key.
    passphrase:
        Merchant passphrase (must match what is configured in PayFast).

    Raises
    ------
    InvalidSignatureException
        If the signature field is missing or does not match the expected value.
    """
    received = payload.get("signature", "")
    expected = generate_signature(payload, passphrase)

    if not signatures_match(expected, received):
        logger.warning(
            "ITN signature mismatch. Expected=%s Received=%s",
            expected,
            received,
        )
        raise InvalidSignatureException(
            "PayFast ITN signature mismatch. "
            "Ensure your passphrase configuration matches your PayFast account."
        )

    logger.debug("ITN signature validated successfully.")


# ---------------------------------------------------------------------------
# Source IP validation
# ---------------------------------------------------------------------------

def validate_source_ip(remote_ip: str | None) -> None:
    """
    Verify that the request originates from a known PayFast IP address.

    Parameters
    ----------
    remote_ip:
        The ``REMOTE_ADDR`` of the incoming request, or ``None`` if unavailable.

    Raises
    ------
    InvalidSourceIPException
        If ``remote_ip`` is ``None`` or not in :data:`PAYFAST_IP_ALLOWLIST`.
    """
    if not remote_ip:
        raise InvalidSourceIPException(
            "Remote IP address was not provided. "
            "Cannot validate ITN source. Set validate_ip=False to skip this check."
        )

    if remote_ip not in PAYFAST_IP_ALLOWLIST:
        logger.warning("ITN rejected from unrecognised IP: %s", remote_ip)
        raise InvalidSourceIPException(
            f"ITN request from unrecognised IP address: {remote_ip}. "
            f"Expected one of the PayFast server IPs."
        )

    logger.debug("Source IP validated: %s", remote_ip)


# ---------------------------------------------------------------------------
# Combined ITN validation
# ---------------------------------------------------------------------------

def validate_itn(
    payload:    dict,
    passphrase: str | None = None,
    remote_ip:  str | None = None,
    validate_ip: bool = True,
) -> None:
    """
    Full ITN validation: signature check + optional IP check.

    This is the single function to call when you receive an ITN. It delegates
    to :func:`validate_signature` and :func:`validate_source_ip` so both
    concerns are validated in one call.

    Parameters
    ----------
    payload:
        The full ITN POST body as a flat dict.
    passphrase:
        Merchant passphrase, or ``None`` if not configured.
    remote_ip:
        Remote IP of the request. Required when ``validate_ip=True``.
    validate_ip:
        When ``True``, the source IP is checked against the PayFast allow-list.

    Raises
    ------
    InvalidSignatureException
        Signature mismatch.
    InvalidSourceIPException
        IP not in allow-list (only when ``validate_ip=True``).
    """
    validate_signature(payload, passphrase)

    if validate_ip:
        validate_source_ip(remote_ip)


# ---------------------------------------------------------------------------
# API request signing (for Subscription API calls)
# ---------------------------------------------------------------------------

def generate_api_signature(
    merchant_id: str,
    passphrase:  str | None,
    timestamp:   str,
    version:     str = "v1",
) -> str:
    """
    Generate the HMAC signature required for PayFast Subscription API calls.

    Parameters
    ----------
    merchant_id:
        Your PayFast merchant ID.
    passphrase:
        Merchant passphrase (empty string if not set).
    timestamp:
        ISO-8601 timestamp string (e.g. ``"2024-01-15T10:30:00"``).
    version:
        API version string. Defaults to ``"v1"``.

    Returns
    -------
    str
        32-character MD5 hex digest.
    """
    data = {
        "merchant-id": merchant_id,
        "passphrase":  passphrase or "",
        "timestamp":   timestamp,
        "version":     version,
    }
    # PayFast API signing requires keys to be sorted alphabetically
    pf_string = "&".join(
        f"{k}={quote_plus(str(v))}" for k, v in sorted(data.items())
    )
    return hashlib.md5(pf_string.encode()).hexdigest()  # noqa: S324
