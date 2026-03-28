"""
payfast_core.models
--------------------
Dataclass models representing PayFast transactions and subscriptions.

These are framework-agnostic plain Python dataclasses. They carry the data
from an ITN payload or subscription API response and are attached to
:class:`~payfast_core.events.PayfastPaymentEvent`.

For database persistence, see the Django and Flask integration guides in the docs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class PaymentStatus(str, Enum):
    COMPLETE  = "COMPLETE"
    FAILED    = "FAILED"
    PENDING   = "PENDING"
    CANCELLED = "CANCELLED"
    UNKNOWN   = "UNKNOWN"


class PaymentType(str, Enum):
    ONCE_OFF     = "once_off"
    SUBSCRIPTION = "subscription"


class SubscriptionStatus(str, Enum):
    ACTIVE    = "active"
    PAUSED    = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class SubscriptionFrequency(int, Enum):
    MONTHLY    = 3
    QUARTERLY  = 4
    BIANNUALLY = 5
    ANNUALLY   = 6

    def label(self) -> str:
        return {
            self.MONTHLY:    "Monthly",
            self.QUARTERLY:  "Quarterly",
            self.BIANNUALLY: "Bi-Annually",
            self.ANNUALLY:   "Annually",
        }[self]


# ---------------------------------------------------------------------------
# PayfastTransaction
# ---------------------------------------------------------------------------

@dataclass
class PayfastTransaction:
    """
    Represents a single PayFast ITN (payment notification).

    Constructed from the raw POST payload via :meth:`from_payload`.

    Attributes
    ----------
    pf_payment_id:   PayFast's own payment reference.
    payment_status:  ``COMPLETE``, ``FAILED``, ``PENDING``, or ``CANCELLED``.
    item_name:       The item name passed when creating the payment.
    amount_gross:    Total amount before PayFast fees.
    amount_fee:      PayFast's processing fee.
    amount_net:      Amount after fees (what you receive).
    merchant_id:     Your merchant ID, echoed in the payload.
    custom_str1–3:   Your custom reference fields.
    custom_int1–2:   Your custom integer fields.
    name_first:      Buyer's first name.
    name_last:       Buyer's last name.
    email_address:   Buyer's email address.
    raw_payload:     The full unmodified ITN payload dict.
    created_at:      UTC timestamp when this object was created.
    """

    pf_payment_id:   str | None
    payment_status:  PaymentStatus
    item_name:       str
    amount_gross:    float
    merchant_id:     str
    raw_payload:     dict

    amount_fee:      float | None    = None
    amount_net:      float | None    = None
    item_description: str | None    = None
    custom_str1:     str | None      = None
    custom_str2:     str | None      = None
    custom_str3:     str | None      = None
    custom_int1:     int | None      = None
    custom_int2:     int | None      = None
    name_first:      str | None      = None
    name_last:       str | None      = None
    email_address:   str | None      = None
    created_at:      datetime        = field(default_factory=datetime.utcnow)

    # ---- Status helpers ----

    def is_complete(self) -> bool:
        return self.payment_status == PaymentStatus.COMPLETE

    def is_failed(self) -> bool:
        return self.payment_status == PaymentStatus.FAILED

    def is_pending(self) -> bool:
        return self.payment_status == PaymentStatus.PENDING

    # ---- Factory ----

    @classmethod
    def from_payload(cls, payload: dict) -> "PayfastTransaction":
        """Build a :class:`PayfastTransaction` from a raw ITN payload dict."""
        status_raw = payload.get("payment_status", "UNKNOWN").upper()
        try:
            status = PaymentStatus(status_raw)
        except ValueError:
            status = PaymentStatus.UNKNOWN

        return cls(
            pf_payment_id    = payload.get("pf_payment_id"),
            payment_status   = status,
            item_name        = payload.get("item_name", ""),
            item_description = payload.get("item_description"),
            amount_gross     = float(payload.get("amount_gross", 0)),
            amount_fee       = float(payload["amount_fee"]) if "amount_fee" in payload else None,
            amount_net       = float(payload["amount_net"]) if "amount_net" in payload else None,
            custom_str1      = payload.get("custom_str1"),
            custom_str2      = payload.get("custom_str2"),
            custom_str3      = payload.get("custom_str3"),
            custom_int1      = int(payload["custom_int1"]) if payload.get("custom_int1") else None,
            custom_int2      = int(payload["custom_int2"]) if payload.get("custom_int2") else None,
            name_first       = payload.get("name_first"),
            name_last        = payload.get("name_last"),
            email_address    = payload.get("email_address"),
            merchant_id      = payload.get("merchant_id", ""),
            raw_payload      = payload,
        )

    def __repr__(self) -> str:
        return (
            f"<PayfastTransaction pf_payment_id={self.pf_payment_id!r} "
            f"status={self.payment_status} amount={self.amount_gross}>"
        )


# ---------------------------------------------------------------------------
# PayfastSubscription
# ---------------------------------------------------------------------------

@dataclass
class PayfastSubscription:
    """
    Represents a PayFast recurring subscription.

    Constructed from an ITN payload via :meth:`from_itn_payload` or from a
    PayFast API response via :meth:`from_api_response`.

    Attributes
    ----------
    token:            PayFast subscription token (unique per subscription).
    status:           Current subscription status.
    amount:           Recurring billing amount.
    frequency:        Billing frequency.
    cycles:           Total number of billing cycles (0 = indefinite).
    cycles_complete:  Number of billing cycles completed so far.
    item_name:        The item name for this subscription.
    custom_str1:      Your custom reference field (often a user/subscriber ID).
    next_billing_date: When the next billing cycle will run.
    trial_ends_at:    When the trial period ends (``None`` if no trial).
    cancelled_at:     When the subscription was cancelled (``None`` if active).
    created_at:       UTC timestamp when this object was created.
    """

    token:            str
    status:           SubscriptionStatus
    amount:           float
    frequency:        SubscriptionFrequency
    item_name:        str

    cycles:           int            = 0
    cycles_complete:  int            = 0
    custom_str1:      str | None     = None
    next_billing_date: datetime | None = None
    trial_ends_at:    datetime | None = None
    cancelled_at:     datetime | None = None
    created_at:       datetime        = field(default_factory=datetime.utcnow)

    # ---- Status helpers ----

    def is_active(self) -> bool:
        return self.status == SubscriptionStatus.ACTIVE

    def is_paused(self) -> bool:
        return self.status == SubscriptionStatus.PAUSED

    def is_cancelled(self) -> bool:
        return self.status == SubscriptionStatus.CANCELLED

    def on_trial(self) -> bool:
        return self.trial_ends_at is not None and self.trial_ends_at > datetime.utcnow()

    def frequency_label(self) -> str:
        return self.frequency.label()

    # ---- Mutations (return new instance — immutable-style) ----

    def cancel(self) -> "PayfastSubscription":
        from dataclasses import replace
        return replace(self, status=SubscriptionStatus.CANCELLED, cancelled_at=datetime.utcnow())

    def pause(self) -> "PayfastSubscription":
        from dataclasses import replace
        return replace(self, status=SubscriptionStatus.PAUSED)

    def resume(self) -> "PayfastSubscription":
        from dataclasses import replace
        return replace(self, status=SubscriptionStatus.ACTIVE)

    def increment_cycle(self) -> "PayfastSubscription":
        from dataclasses import replace
        new_count = self.cycles_complete + 1
        new_status = (
            SubscriptionStatus.COMPLETED
            if self.cycles > 0 and new_count >= self.cycles
            else self.status
        )
        return replace(self, cycles_complete=new_count, status=new_status)

    # ---- Factory ----

    @classmethod
    def from_itn_payload(cls, payload: dict) -> "PayfastSubscription":
        """Build a :class:`PayfastSubscription` from a raw ITN payload."""
        token = payload.get("token")
        if not token:
            from payfast_core.exceptions import PayfastException
            raise PayfastException("ITN payload does not contain a subscription token.")

        freq_raw = int(payload.get("frequency", SubscriptionFrequency.MONTHLY.value))
        try:
            frequency = SubscriptionFrequency(freq_raw)
        except ValueError:
            frequency = SubscriptionFrequency.MONTHLY

        return cls(
            token           = token,
            status          = SubscriptionStatus.ACTIVE,
            amount          = float(payload.get("amount_gross", 0)),
            frequency       = frequency,
            cycles          = int(payload.get("billing_total", 0)),
            cycles_complete = 0,
            item_name       = payload.get("item_name", ""),
            custom_str1     = payload.get("custom_str1"),
        )

    def __repr__(self) -> str:
        return (
            f"<PayfastSubscription token={self.token!r} "
            f"status={self.status} amount={self.amount} freq={self.frequency.label()}>"
        )
