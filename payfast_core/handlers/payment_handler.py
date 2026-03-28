"""
payfast_core.handlers.payment_handler
---------------------------------------
Structured handler base for once-off payment events.

Instead of registering bare callables on ``PayfastPaymentEvent``, subclass
:class:`PaymentHandler`, override the hooks you care about, and register the
instance with the client. This makes handler code self-documenting and keeps
related logic grouped together.

Usage
-----
::

    from payfast_core.handlers import PaymentHandler

    class OrderHandler(PaymentHandler):
        def on_payment_success(self, event):
            order = Order.get(event.custom_str(1))
            order.mark_paid()
            send_receipt(event.buyer_email())

        def on_payment_failed(self, event):
            notify_ops_team(event.summary())

    client.register_handler(OrderHandler())
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payfast_core.events import PayfastPaymentEvent

logger = logging.getLogger("payfast_core.handlers")


class PaymentHandler:
    """
    Base class for structured once-off payment handling.

    Override any of the hook methods below. Unoverridden hooks are no-ops.
    Register an instance with :meth:`~payfast_core.client.PayfastClient.register_handler`.

    Hooks (in the order they are called)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * :meth:`on_itn_received`     — fired for every valid ITN before status check
    * :meth:`on_payment_success`  — fired when ``payment_status == COMPLETE``
    * :meth:`on_payment_failed`   — fired when ``payment_status != COMPLETE``
    * :meth:`on_payment_pending`  — fired when ``payment_status == PENDING``
    * :meth:`on_payment_cancelled`— fired when ``payment_status == CANCELLED``
    """

    # -------------------------------------------------------------------------
    # Hooks — override in subclasses
    # -------------------------------------------------------------------------

    def on_itn_received(self, event: "PayfastPaymentEvent") -> None:
        """Called for every valid ITN, before the status is inspected."""

    def on_payment_success(self, event: "PayfastPaymentEvent") -> None:
        """Called when ``payment_status == COMPLETE`` for any payment type."""

    def on_payment_failed(self, event: "PayfastPaymentEvent") -> None:
        """Called when the payment status is anything other than ``COMPLETE``."""

    def on_payment_pending(self, event: "PayfastPaymentEvent") -> None:
        """Called when ``payment_status == PENDING``."""

    def on_payment_cancelled(self, event: "PayfastPaymentEvent") -> None:
        """Called when ``payment_status == CANCELLED``."""

    # -------------------------------------------------------------------------
    # Internal dispatcher — called by PayfastClient
    # -------------------------------------------------------------------------

    def _dispatch(self, event: "PayfastPaymentEvent") -> None:
        """Route the event to the appropriate hooks. Called by the client."""
        try:
            self.on_itn_received(event)

            if event.is_complete():
                self.on_payment_success(event)
            elif event.is_pending():
                self.on_payment_pending(event)
                self.on_payment_failed(event)
            elif event.is_cancelled():
                self.on_payment_cancelled(event)
                self.on_payment_failed(event)
            else:
                self.on_payment_failed(event)

        except Exception:
            logger.exception(
                "%s raised an exception while handling %s",
                type(self).__name__,
                event.summary(),
            )

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"
