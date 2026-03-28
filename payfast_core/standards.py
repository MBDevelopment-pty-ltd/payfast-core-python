"""
payfast_core.standards
-----------------------
Cross-language PayFast ecosystem standards.

MB Development maintains PayFast SDKs in multiple languages:

* PHP/Laravel — ``mb-development/payfast-core``
* Python       — ``mb-development/payfast-core-python`` (this package)

This module defines the canonical constants, event names, and terminology
shared across all SDK implementations. If you maintain an integration that
uses both the PHP and Python packages, use the names from this module
to ensure consistent behaviour across languages.

Stripe's approach is the inspiration: the same event name (``payment.complete``)
means the same thing in every SDK, regardless of language.

Event name standards
--------------------
Every SDK fires events with these canonical names. Use them in logs,
monitoring, analytics, and cross-service messaging.

Payment type standards
----------------------
``"once_off"`` and ``"subscription"`` are the canonical payment type strings
used by both SDKs. Do not use ``"one_time"``, ``"single"``, or ``"recurring"``.

Status standards
----------------
PayFast returns ``COMPLETE``, ``FAILED``, ``PENDING``, and ``CANCELLED`` — all
SDKs use these exact strings (uppercased). Do not normalise to ``"success"``
or ``"failure"`` in your application layer — keep the PayFast terms.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Canonical event names
# Identical in PHP (Laravel) and Python SDKs
# ---------------------------------------------------------------------------

class EventNames:
    """
    Canonical event name strings shared across all SDK implementations.

    Use these in logs, monitoring dashboards, and cross-service message buses
    so that event names are consistent regardless of which language SDK
    produced them.

    Example
    -------
    ::

        import logging
        from payfast_core.standards import EventNames

        logger.info(EventNames.PAYMENT_COMPLETE, extra={"amount": event.amount_gross()})
    """

    #: Fired for every valid ITN before any processing.
    ITN_RECEIVED          = "payfast.itn.received"

    #: Fired for every valid ITN after the transaction is built.
    #: The primary event — carries type, status, transaction, and subscription.
    PAYMENT_EVENT         = "payfast.payment.event"

    #: Fired when ``payment_status == COMPLETE`` for any payment type.
    PAYMENT_COMPLETE      = "payfast.payment.complete"

    #: Fired when the payment status is not ``COMPLETE``.
    PAYMENT_FAILED        = "payfast.payment.failed"

    #: Fired on the first successful billing for a new subscription token.
    SUBSCRIPTION_CREATED  = "payfast.subscription.created"

    #: Fired when a recurring billing cycle completes.
    SUBSCRIPTION_RENEWED  = "payfast.subscription.renewed"

    #: Fired when a subscription is cancelled.
    SUBSCRIPTION_CANCELLED = "payfast.subscription.cancelled"


# ---------------------------------------------------------------------------
# Canonical payment type strings
# ---------------------------------------------------------------------------

class PaymentTypes:
    """
    Canonical payment type strings.

    Both PHP and Python SDKs set ``payment_type`` to one of these values.
    """

    #: A standard once-off (non-recurring) payment.
    ONCE_OFF     = "once_off"

    #: A recurring subscription payment.
    SUBSCRIPTION = "subscription"


# ---------------------------------------------------------------------------
# Canonical status strings (mirrors PayFast values)
# ---------------------------------------------------------------------------

class PaymentStatuses:
    """
    Canonical payment status strings.

    Mirrors the values returned by PayFast in the ITN payload. Both SDKs
    normalise status strings to uppercase before comparison.
    """

    COMPLETE  = "COMPLETE"
    FAILED    = "FAILED"
    PENDING   = "PENDING"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Canonical subscription frequency values
# ---------------------------------------------------------------------------

class SubscriptionFrequencies:
    """
    PayFast subscription frequency values.

    Both SDKs use these integer values to represent billing frequency.
    They map directly to the ``frequency`` field in the PayFast API.
    """

    MONTHLY    = 3
    QUARTERLY  = 4
    BIANNUALLY = 5
    ANNUALLY   = 6

    LABELS: dict[int, str] = {
        MONTHLY:    "Monthly",
        QUARTERLY:  "Quarterly",
        BIANNUALLY: "Bi-Annually",
        ANNUALLY:   "Annually",
    }

    @classmethod
    def label(cls, frequency: int) -> str:
        """Return the human-readable label for a frequency integer."""
        return cls.LABELS.get(frequency, "Unknown")


# ---------------------------------------------------------------------------
# Canonical ITN field names
# These are the exact keys PayFast sends in the ITN POST body.
# Using these constants prevents typos and makes refactoring easier.
# ---------------------------------------------------------------------------

class ItnFields:
    """
    Canonical ITN field name strings.

    Use these as dict keys when reading from the raw ITN payload to avoid
    typos and to make your code self-documenting.

    Example
    -------
    ::

        from payfast_core.standards import ItnFields

        order_id = payload[ItnFields.CUSTOM_STR1]
        amount   = float(payload[ItnFields.AMOUNT_GROSS])
    """

    MERCHANT_ID      = "merchant_id"
    PF_PAYMENT_ID    = "pf_payment_id"
    PAYMENT_STATUS   = "payment_status"
    ITEM_NAME        = "item_name"
    ITEM_DESCRIPTION = "item_description"
    AMOUNT_GROSS     = "amount_gross"
    AMOUNT_FEE       = "amount_fee"
    AMOUNT_NET       = "amount_net"
    NAME_FIRST       = "name_first"
    NAME_LAST        = "name_last"
    EMAIL_ADDRESS    = "email_address"
    SIGNATURE        = "signature"

    # Subscription fields
    SUBSCRIPTION_TYPE = "subscription_type"
    TOKEN             = "token"
    FREQUENCY         = "frequency"
    BILLING_DATE      = "billing_date"
    BILLING_TOTAL     = "billing_total"

    # Custom fields
    CUSTOM_STR1 = "custom_str1"
    CUSTOM_STR2 = "custom_str2"
    CUSTOM_STR3 = "custom_str3"
    CUSTOM_INT1 = "custom_int1"
    CUSTOM_INT2 = "custom_int2"


# ---------------------------------------------------------------------------
# SDK version manifest
# Useful for cross-SDK diagnostics and support
# ---------------------------------------------------------------------------

SDK_MANIFEST: dict[str, str] = {
    "name":      "payfast-core-python",
    "vendor":    "MB Development Pty Ltd",
    "version":   "1.0.0",
    "language":  "python",
    "php_equivalent": "mb-development/payfast-core",
}
