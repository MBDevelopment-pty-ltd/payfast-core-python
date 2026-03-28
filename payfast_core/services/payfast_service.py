"""
payfast_core.services.payfast_service
--------------------------------------
Core service: payment data assembly, URL building, ITN validation.

All cryptographic and IP-validation logic is delegated to
:mod:`payfast_core.security` — this service is concerned only with
PayFast-specific business logic (building payloads, constructing URLs).
"""

from __future__ import annotations

from urllib.parse import urlencode

from payfast_core.config import PayfastConfig
from payfast_core import security

LIVE_URL    = "https://www.payfast.co.za/eng/process"
SANDBOX_URL = "https://sandbox.payfast.co.za/eng/process"


class PayfastService:
    """
    Core PayFast service.

    Assembles payment data, builds URLs, and validates ITNs by delegating
    all security operations to :mod:`payfast_core.security`.

    Parameters
    ----------
    config:
        A :class:`~payfast_core.config.PayfastConfig` instance.
    """

    def __init__(self, config: PayfastConfig) -> None:
        self.config = config

    # -------------------------------------------------------------------------
    # Signature (thin delegation to security module)
    # -------------------------------------------------------------------------

    def generate_signature(self, data: dict, passphrase: str | None = None) -> str:
        """Generate an MD5 signature. Delegates to :func:`payfast_core.security.generate_signature`."""
        return security.generate_signature(data, passphrase)

    # -------------------------------------------------------------------------
    # Payment data
    # -------------------------------------------------------------------------

    def generate_payment_data(self, params: dict) -> dict:
        """
        Assemble the full signed payment data dict.

        Merchant credentials and redirect URLs are merged in from config.
        A ``signature`` field is appended last.
        """
        data = {
            "merchant_id":  self.config.merchant_id,
            "merchant_key": self.config.merchant_key,
            "return_url":   self.config.return_url,
            "cancel_url":   self.config.cancel_url,
            "notify_url":   self.config.notify_url,
            **params,
        }
        data["signature"] = security.generate_signature(data, self.config.passphrase)
        return data

    def build_payment_url(self, params: dict) -> str:
        """Build a fully-signed PayFast payment URL for a GET redirect."""
        data     = self.generate_payment_data(params)
        base_url = SANDBOX_URL if self.config.sandbox else LIVE_URL
        return f"{base_url}?{urlencode(data)}"

    def get_payment_endpoint(self) -> str:
        """Return the correct PayFast process URL based on config."""
        return SANDBOX_URL if self.config.sandbox else LIVE_URL

    # -------------------------------------------------------------------------
    # ITN validation (delegates entirely to security module)
    # -------------------------------------------------------------------------

    def validate_itn(self, data: dict, remote_ip: str | None = None) -> bool:
        """
        Validate an ITN payload. Delegates to :func:`payfast_core.security.validate_itn`.

        Returns ``True`` on success, raises on failure.
        """
        security.validate_itn(
            payload     = data,
            passphrase  = self.config.passphrase,
            remote_ip   = remote_ip,
            validate_ip = self.config.validate_ip,
        )
        return True
