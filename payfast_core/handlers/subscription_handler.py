"""
payfast_core.handlers.subscription_handler
--------------------------------------------
Structured handler base for subscription lifecycle events.

Subclass :class:`SubscriptionHandler`, override the hooks you care about,
and register the instance with the client.

Usage
-----
::

    from payfast_core.handlers import SubscriptionHandler

    class PlanHandler(SubscriptionHandler):
        def on_subscription_created(self, event):
            user = User.get(event.subscription.custom_str1)
            user.activate_plan(event.subscription)

        def on_subscription_renewed(self, event):
            user = User.get(event.subscription.custom_str1)
            user.extend_plan(months=1)

        def on_subscription_cancelled(self, event):
            user = User.get(event.subscription.custom_str1)
            user.deactivate_plan()

    client.register_handler(PlanHandler())
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payfast_core.events import (
        PayfastPaymentEvent,
        PayfastSubscriptionCreated,
        PayfastSubscriptionRenewed,
        PayfastSubscriptionCancelled,
    )

logger = logging.getLogger("payfast_core.handlers")


class SubscriptionHandler:
    """
    Base class for structured subscription lifecycle handling.

    Override any of the hook methods below. Unoverridden hooks are no-ops.
    Register an instance with :meth:`~payfast_core.client.PayfastClient.register_handler`.

    Hooks
    ~~~~~
    * :meth:`on_subscription_payment`   — every complete subscription ITN
    * :meth:`on_subscription_created`   — first billing for a new token
    * :meth:`on_subscription_renewed`   — recurring billing cycle completes
    * :meth:`on_subscription_failed`    — subscription billing fails
    * :meth:`on_subscription_cancelled` — subscription is cancelled
    """

    # -------------------------------------------------------------------------
    # Hooks — override in subclasses
    # -------------------------------------------------------------------------

    def on_subscription_payment(self, event: "PayfastPaymentEvent") -> None:
        """Called on every complete subscription billing ITN."""

    def on_subscription_created(self, event: "PayfastSubscriptionCreated") -> None:
        """Called when the first billing for a new subscription token is received."""

    def on_subscription_renewed(self, event: "PayfastSubscriptionRenewed") -> None:
        """Called when a recurring billing cycle completes successfully."""

    def on_subscription_failed(self, event: "PayfastPaymentEvent") -> None:
        """Called when a subscription billing ITN fails."""

    def on_subscription_cancelled(self, event: "PayfastSubscriptionCancelled") -> None:
        """Called when a subscription is cancelled."""

    # -------------------------------------------------------------------------
    # Internal dispatchers — called by PayfastClient
    # -------------------------------------------------------------------------

    def _dispatch_payment_event(self, event: "PayfastPaymentEvent") -> None:
        """Route a PayfastPaymentEvent for subscription payments."""
        if not event.is_subscription():
            return
        try:
            if event.is_complete():
                self.on_subscription_payment(event)
            else:
                self.on_subscription_failed(event)
        except Exception:
            logger.exception(
                "%s raised an exception in on_subscription_payment/failed for %s",
                type(self).__name__,
                event.summary(),
            )

    def _dispatch_created(self, event: "PayfastSubscriptionCreated") -> None:
        try:
            self.on_subscription_created(event)
        except Exception:
            logger.exception(
                "%s raised an exception in on_subscription_created", type(self).__name__
            )

    def _dispatch_renewed(self, event: "PayfastSubscriptionRenewed") -> None:
        try:
            self.on_subscription_renewed(event)
        except Exception:
            logger.exception(
                "%s raised an exception in on_subscription_renewed", type(self).__name__
            )

    def _dispatch_cancelled(self, event: "PayfastSubscriptionCancelled") -> None:
        try:
            self.on_subscription_cancelled(event)
        except Exception:
            logger.exception(
                "%s raised an exception in on_subscription_cancelled", type(self).__name__
            )

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"
