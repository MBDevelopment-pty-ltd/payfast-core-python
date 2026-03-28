"""
payfast_core.config
-------------------
Typed configuration for the PayFast SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field


VALID_PAYFAST_IPS: frozenset[str] = frozenset({
    "197.97.145.144",
    "197.97.145.145",
    "197.97.145.146",
    "197.97.145.147",
    "41.74.179.194",
    "41.74.179.195",
    "41.74.179.196",
    "41.74.179.197",
})


@dataclass
class PayfastConfig:
    """
    All configuration required to interact with PayFast.

    Parameters
    ----------
    merchant_id:
        Your PayFast merchant ID (from your PayFast dashboard).
    merchant_key:
        Your PayFast merchant key.
    passphrase:
        Optional security passphrase set in your PayFast account.
        Leave as ``None`` if you have not configured one.
    sandbox:
        When ``True``, all requests are directed to the PayFast sandbox
        environment. Set to ``False`` for live transactions.
    return_url:
        URL PayFast redirects the buyer to after a successful payment.
    cancel_url:
        URL PayFast redirects the buyer to if they cancel.
    notify_url:
        URL PayFast POSTs the ITN to (your webhook endpoint).
    validate_ip:
        When ``True``, ITN validation will reject requests that do not
        originate from a known PayFast IP address. Recommended in production.
    """

    merchant_id:  str
    merchant_key: str
    passphrase:   str | None = None
    sandbox:      bool = True
    return_url:   str = ""
    cancel_url:   str = ""
    notify_url:   str = ""
    validate_ip:  bool = True

    @classmethod
    def from_env(cls) -> "PayfastConfig":
        """
        Build a :class:`PayfastConfig` from environment variables.

        Expected variables::

            PAYFAST_MERCHANT_ID
            PAYFAST_MERCHANT_KEY
            PAYFAST_PASSPHRASE       (optional)
            PAYFAST_SANDBOX          (default: "true")
            PAYFAST_RETURN_URL
            PAYFAST_CANCEL_URL
            PAYFAST_NOTIFY_URL
            PAYFAST_VALIDATE_IP      (default: "true")

        Raises
        ------
        ValueError
            If ``PAYFAST_MERCHANT_ID`` or ``PAYFAST_MERCHANT_KEY`` are not set.
        """
        import os

        merchant_id  = os.environ.get("PAYFAST_MERCHANT_ID", "")
        merchant_key = os.environ.get("PAYFAST_MERCHANT_KEY", "")

        if not merchant_id or not merchant_key:
            raise ValueError(
                "PAYFAST_MERCHANT_ID and PAYFAST_MERCHANT_KEY must be set in the environment."
            )

        return cls(
            merchant_id  = merchant_id,
            merchant_key = merchant_key,
            passphrase   = os.environ.get("PAYFAST_PASSPHRASE") or None,
            sandbox      = os.environ.get("PAYFAST_SANDBOX", "true").lower() != "false",
            return_url   = os.environ.get("PAYFAST_RETURN_URL", ""),
            cancel_url   = os.environ.get("PAYFAST_CANCEL_URL", ""),
            notify_url   = os.environ.get("PAYFAST_NOTIFY_URL", ""),
            validate_ip  = os.environ.get("PAYFAST_VALIDATE_IP", "true").lower() != "false",
        )
