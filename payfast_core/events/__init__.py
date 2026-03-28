"""
payfast_core.events
--------------------
Event dataclasses fired when PayFast ITN payloads are processed.

The primary event is :class:`PayfastPaymentEvent` — it carries the payment
type, status, and all context needed to act on any PayFast payment.
Granular events are also provided for targeted use-cases.

Usage (framework-agnostic)
--------------------------
The SDK fires events by calling registered listeners. Register yours with
:func:`~payfast_core.client.PayfastClient.on`:

>>> client.on(PayfastPaymentEvent, handle_payment)

Or using Python's built-in ``blinker`` signals (optional dependency) for
more advanced pub/sub patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any

from payfast_core.models import PayfastTransaction, PayfastSubscription, PaymentStatus, PaymentType


# ---------------------------------------------------------------------------
# PayfastPaymentEvent  —  the primary unified event
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PayfastPaymentEvent:
    """
    Fired on every valid ITN received from PayFast.

    This is the **single event** you need to listen to in order to react to
    any PayFast payment. It exposes the payment type, status, the transaction
    record, and (for subscriptions) the subscription record.

    Attributes
    ----------
    payload:
        The full raw ITN payload dict as received from PayFast.
    transaction:
        The :class:`~payfast_core.models.PayfastTransaction` built from the payload.
    subscription:
        The :class:`~payfast_core.models.PayfastSubscription` for subscription
        payments. ``None`` for once-off payments.
    payment_type:
        ``PaymentType.ONCE_OFF`` or ``PaymentType.SUBSCRIPTION``.
    payment_status:
        ``PaymentStatus.COMPLETE``, ``FAILED``, ``PENDING``, or ``CANCELLED``.

    Examples
    --------
    >>> def handle_payment(event: PayfastPaymentEvent) -> None:
    ...     if event.is_once_off() and event.is_complete():
    ...         activate_order(event.custom_str(1))
    ...     if event.is_subscription() and event.is_complete():
    ...         grant_access(event.custom_str(1))
    ...     if event.is_failed():
    ...         notify_customer(event.buyer_email())
    """

    payload:       dict
    transaction:   PayfastTransaction
    subscription:  PayfastSubscription | None = None

    # Derived — computed in __post_init__ via object.__setattr__ (frozen dataclass)
    payment_type:   PaymentType   = field(init=False)
    payment_status: PaymentStatus = field(init=False)

    def __post_init__(self) -> None:
        status_raw = self.payload.get("payment_status", "UNKNOWN").upper()
        try:
            status = PaymentStatus(status_raw)
        except ValueError:
            status = PaymentStatus.UNKNOWN

        ptype = (
            PaymentType.SUBSCRIPTION
            if int(self.payload.get("subscription_type", 0)) == 1
            else PaymentType.ONCE_OFF
        )

        object.__setattr__(self, "payment_status", status)
        object.__setattr__(self, "payment_type",   ptype)

    # ---- Payment type helpers ----

    def is_once_off(self) -> bool:
        """Return ``True`` if this is a standard once-off payment."""
        return self.payment_type == PaymentType.ONCE_OFF

    def is_subscription(self) -> bool:
        """Return ``True`` if this is a recurring subscription payment."""
        return self.payment_type == PaymentType.SUBSCRIPTION

    # ---- Payment status helpers ----

    def is_complete(self) -> bool:
        """Return ``True`` when PayFast confirmed the payment as successful."""
        return self.payment_status == PaymentStatus.COMPLETE

    def is_failed(self) -> bool:
        """Return ``True`` when the payment failed."""
        return self.payment_status == PaymentStatus.FAILED

    def is_pending(self) -> bool:
        """Return ``True`` when the payment is still pending."""
        return self.payment_status == PaymentStatus.PENDING

    def is_cancelled(self) -> bool:
        """Return ``True`` when the payment was cancelled."""
        return self.payment_status == PaymentStatus.CANCELLED

    # ---- Payload accessors ----

    def amount_gross(self) -> float:
        """Gross payment amount before PayFast fees."""
        return float(self.payload.get("amount_gross", 0))

    def amount_net(self) -> float:
        """Net payment amount after PayFast fees."""
        return float(self.payload.get("amount_net", 0))

    def pf_payment_id(self) -> str | None:
        """PayFast's own payment reference (``pf_payment_id``)."""
        return self.payload.get("pf_payment_id")

    def subscription_token(self) -> str | None:
        """Subscription token. Present only for subscription payments."""
        return self.payload.get("token")

    def custom_str(self, index: int = 1) -> str | None:
        """Return the value of ``custom_str{index}`` (1–3) from the payload."""
        return self.payload.get(f"custom_str{index}")

    def custom_int(self, index: int = 1) -> int | None:
        """Return the value of ``custom_int{index}`` (1–2) from the payload as an int."""
        val = self.payload.get(f"custom_int{index}")
        return int(val) if val is not None else None

    def buyer_first_name(self) -> str | None:
        return self.payload.get("name_first")

    def buyer_last_name(self) -> str | None:
        return self.payload.get("name_last")

    def buyer_email(self) -> str | None:
        return self.payload.get("email_address")

    def item_name(self) -> str | None:
        return self.payload.get("item_name")

    def summary(self) -> str:
        """
        Human-readable summary string, useful for logging.

        Example: ``"COMPLETE once_off — R299.00 — Order #42"``
        """
        return (
            f"{self.payment_status.value} {self.payment_type.value} "
            f"— R{self.amount_gross():.2f} "
            f"— {self.item_name() or 'n/a'}"
        )

    def __repr__(self) -> str:
        return f"<PayfastPaymentEvent {self.summary()!r}>"


# ---------------------------------------------------------------------------
# Granular events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PayfastItnReceived:
    """Fired on every valid ITN, before any processing occurs."""
    payload: dict


@dataclass(frozen=True)
class PayfastPaymentComplete:
    """Fired when an ITN has ``payment_status = COMPLETE``."""
    payload: dict


@dataclass(frozen=True)
class PayfastPaymentFailed:
    """Fired when an ITN has any status other than ``COMPLETE``."""
    payload: dict


@dataclass(frozen=True)
class PayfastSubscriptionCreated:
    """Fired when the first successful billing for a new subscription token is processed."""
    subscription: PayfastSubscription
    payload:      dict


@dataclass(frozen=True)
class PayfastSubscriptionRenewed:
    """Fired when a recurring billing cycle completes successfully."""
    subscription: PayfastSubscription
    transaction:  PayfastTransaction
    payload:      dict


@dataclass(frozen=True)
class PayfastSubscriptionCancelled:
    """Fired when a subscription is cancelled."""
    subscription: PayfastSubscription
    payload:      dict
