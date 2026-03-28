"""
payfast_core.client
--------------------
The premium entry point for the PayFast SDK.

One import. One object. Full control.

    from payfast_core import PayfastClient

    client = PayfastClient.from_env()

    # Once-off payment
    url = client.generate_payment(amount=349.99, item_name="Order #1042", custom_str1="42")

    # Subscription
    url = client.create_subscription(amount=299.00, item_name="Pro Plan", custom_str1="user_1")

    # Structured handlers
    client.register_handler(MyPaymentHandler())
    client.register_handler(MySubscriptionHandler())

    # Low-level event listeners (for one-off logic)
    @client.on(PayfastPaymentEvent)
    def handle(event): ...

    # In your webhook endpoint
    event = client.handle_itn(payload, remote_ip=ip)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable
from urllib.parse import urlencode

from payfast_core.config import PayfastConfig
from payfast_core.events import (
    PayfastItnReceived,
    PayfastPaymentComplete,
    PayfastPaymentEvent,
    PayfastPaymentFailed,
    PayfastSubscriptionCreated,
    PayfastSubscriptionRenewed,
    PayfastSubscriptionCancelled,
)
from payfast_core.exceptions import PayfastException
from payfast_core.handlers import PaymentHandler, SubscriptionHandler
from payfast_core.idempotency import IdempotencyStore, DuplicateItnException
from payfast_core.models import (
    PayfastSubscription,
    PayfastTransaction,
    SubscriptionFrequency,
)
from payfast_core.services import PayfastService, SubscriptionService

logger = logging.getLogger("payfast_core")


class PayfastClient:
    """
    The single entry point for everything PayFast.

    Create one instance per application (treat it like a service singleton)
    and configure it once at startup. Everything flows through here.

    Parameters
    ----------
    config:
        A :class:`~payfast_core.config.PayfastConfig` instance.
    idempotency_store:
        Optional :class:`~payfast_core.idempotency.IdempotencyStore`.
        When provided, duplicate ITNs (same ``pf_payment_id``) raise
        :class:`~payfast_core.idempotency.DuplicateItnException`.

    Quick start
    -----------
    ::

        client = PayfastClient.from_env()

        @client.on(PayfastPaymentEvent)
        def handle_payment(event):
            if event.is_complete():
                activate_order(event.custom_str(1))

        # In your webhook view:
        event = client.handle_itn(request.POST.dict(), remote_ip=request.META["REMOTE_ADDR"])
    """

    def __init__(
        self,
        config: PayfastConfig,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self.config               = config
        self.service              = PayfastService(config)
        self.subscription_service = SubscriptionService(self.service)
        self._idempotency         = idempotency_store
        self._listeners:          dict[type, list[Callable]] = defaultdict(list)
        self._payment_handlers:   list[PaymentHandler]      = []
        self._subscription_handlers: list[SubscriptionHandler] = []

    # -------------------------------------------------------------------------
    # Alternative constructors
    # -------------------------------------------------------------------------

    @classmethod
    def from_env(cls, idempotency_store: IdempotencyStore | None = None) -> "PayfastClient":
        """
        Build a :class:`PayfastClient` directly from environment variables.

        Equivalent to ``PayfastClient(PayfastConfig.from_env())``.

        Raises
        ------
        ValueError
            If required environment variables are not set.
        """
        return cls(PayfastConfig.from_env(), idempotency_store=idempotency_store)

    # -------------------------------------------------------------------------
    # Handler registration
    # -------------------------------------------------------------------------

    def register_handler(self, handler: PaymentHandler | SubscriptionHandler) -> "PayfastClient":
        """
        Register a structured handler instance.

        Handlers are the recommended way to organise payment logic —
        they group related hooks (success, failed, pending) in one class
        and are easier to test in isolation.

        Parameters
        ----------
        handler:
            An instance of :class:`~payfast_core.handlers.PaymentHandler`
            or :class:`~payfast_core.handlers.SubscriptionHandler`.

        Returns
        -------
        PayfastClient
            ``self``, so calls can be chained:
            ``client.register_handler(A()).register_handler(B())``.

        Example
        -------
        ::

            class OrderHandler(PaymentHandler):
                def on_payment_success(self, event):
                    Order.get(event.custom_str(1)).mark_paid()

            client.register_handler(OrderHandler())
        """
        if isinstance(handler, PaymentHandler):
            self._payment_handlers.append(handler)
            logger.debug("Registered PaymentHandler: %r", handler)
        elif isinstance(handler, SubscriptionHandler):
            self._subscription_handlers.append(handler)
            logger.debug("Registered SubscriptionHandler: %r", handler)
        else:
            raise TypeError(
                f"handler must be a PaymentHandler or SubscriptionHandler, got {type(handler)}"
            )
        return self

    # -------------------------------------------------------------------------
    # Low-level listener registration (for one-off / functional style)
    # -------------------------------------------------------------------------

    def on(self, event_class: type) -> Callable:
        """
        Decorator to register a listener for an event class.

        Use this for simple, one-off callbacks. For structured logic,
        prefer :meth:`register_handler`.

        Example
        -------
        ::

            @client.on(PayfastPaymentEvent)
            def handle(event: PayfastPaymentEvent) -> None:
                if event.is_complete():
                    print(event.summary())
        """
        def decorator(fn: Callable) -> Callable:
            self.add_listener(event_class, fn)
            return fn
        return decorator

    def add_listener(self, event_class: type, fn: Callable) -> None:
        """Register ``fn`` as a listener for ``event_class``."""
        self._listeners[event_class].append(fn)

    def remove_listener(self, event_class: type, fn: Callable) -> None:
        """Remove ``fn`` from the listeners for ``event_class``."""
        self._listeners[event_class] = [
            f for f in self._listeners[event_class] if f is not fn
        ]

    # -------------------------------------------------------------------------
    # Named convenience hooks (client.on_payment_success style)
    # -------------------------------------------------------------------------

    def on_payment_success(self, fn: Callable) -> Callable:
        """
        Register a listener called only when a payment completes successfully.

        Equivalent to checking ``event.is_complete()`` inside a
        ``PayfastPaymentEvent`` listener.

        Example
        -------
        ::

            @client.on_payment_success
            def activate(event):
                Order.get(event.custom_str(1)).mark_paid()
        """
        def _wrapper(event: PayfastPaymentEvent) -> None:
            if event.is_complete():
                fn(event)
        _wrapper.__name__ = fn.__name__
        self.add_listener(PayfastPaymentEvent, _wrapper)
        return fn

    def on_payment_failed(self, fn: Callable) -> Callable:
        """
        Register a listener called only when a payment fails.

        Example
        -------
        ::

            @client.on_payment_failed
            def notify(event):
                send_failure_email(event.buyer_email())
        """
        def _wrapper(event: PayfastPaymentEvent) -> None:
            if event.is_failed():
                fn(event)
        _wrapper.__name__ = fn.__name__
        self.add_listener(PayfastPaymentEvent, _wrapper)
        return fn

    def on_subscription_created(self, fn: Callable) -> Callable:
        """
        Register a listener called when a new subscription is first created.

        Example
        -------
        ::

            @client.on_subscription_created
            def activate_plan(event):
                User.get(event.subscription.custom_str1).activate()
        """
        self.add_listener(PayfastSubscriptionCreated, fn)
        return fn

    def on_subscription_renewed(self, fn: Callable) -> Callable:
        """Register a listener called on each recurring billing cycle."""
        self.add_listener(PayfastSubscriptionRenewed, fn)
        return fn

    def on_subscription_cancelled(self, fn: Callable) -> Callable:
        """Register a listener called when a subscription is cancelled."""
        self.add_listener(PayfastSubscriptionCancelled, fn)
        return fn

    # -------------------------------------------------------------------------
    # Idempotency helpers
    # -------------------------------------------------------------------------

    def is_duplicate_transaction(self, transaction_id: str) -> bool:
        """
        Check if a ``pf_payment_id`` has already been processed.

        Requires an :class:`~payfast_core.idempotency.IdempotencyStore` to
        have been passed to the constructor. Returns ``False`` if no store
        is configured (safe default — duplicate checking is opt-in).

        Parameters
        ----------
        transaction_id:
            The ``pf_payment_id`` from the ITN payload.

        Example
        -------
        ::

            if client.is_duplicate_transaction(payload["pf_payment_id"]):
                return HttpResponse("OK")   # already handled
        """
        if self._idempotency is None:
            return False
        return self._idempotency.has_seen(transaction_id)

    # -------------------------------------------------------------------------
    # ITN processing (the main webhook handler)
    # -------------------------------------------------------------------------

    def handle_itn(
        self,
        payload:   dict,
        remote_ip: str | None = None,
    ) -> PayfastPaymentEvent:
        """
        Validate and fully process a PayFast ITN payload.

        This is the method to call inside your webhook endpoint. It:

        1. Validates the ITN signature (and optionally the source IP).
        2. Checks idempotency if a store is configured.
        3. Builds a :class:`~payfast_core.models.PayfastTransaction`.
        4. Handles subscription lifecycle.
        5. Dispatches :class:`~payfast_core.events.PayfastPaymentEvent`
           and all granular events to both listeners and registered handlers.
        6. Returns the :class:`~payfast_core.events.PayfastPaymentEvent`.

        Parameters
        ----------
        payload:
            The full POST body from the ITN request as a flat dict.
        remote_ip:
            The IP address of the incoming request. Required when
            ``config.validate_ip`` is ``True``.

        Returns
        -------
        PayfastPaymentEvent

        Raises
        ------
        PayfastException
            Signature or IP validation failure.
        DuplicateItnException
            When an idempotency store is configured and the ITN was already
            processed. **Catch this and return 200 OK** to stop PayFast retrying.
        """
        # Step 1 — Security validation
        self.service.validate_itn(payload, remote_ip=remote_ip)

        # Step 2 — Idempotency check
        if self._idempotency is not None:
            tx_id = payload.get("pf_payment_id", "")
            if tx_id:
                self._idempotency.check_and_mark(tx_id)

        # Step 3 — Pre-processing event
        self._dispatch(PayfastItnReceived(payload=payload))

        # Step 4 — Build models
        transaction   = PayfastTransaction.from_payload(payload)
        is_sub        = int(payload.get("subscription_type", 0)) == 1
        subscription  = self._handle_subscription(payload, transaction) if is_sub else None

        # Step 5 — Build unified event
        event = PayfastPaymentEvent(
            payload      = payload,
            transaction  = transaction,
            subscription = subscription,
        )

        # Step 6 — Dispatch to listeners and handlers
        self._dispatch(event)
        for handler in self._payment_handlers:
            handler._dispatch(event)

        if event.is_complete():
            self._dispatch(PayfastPaymentComplete(payload=payload))
        else:
            self._dispatch(PayfastPaymentFailed(payload=payload))

        logger.info("ITN processed: %s", event.summary())
        return event

    # -------------------------------------------------------------------------
    # Payment generation (premium interface)
    # -------------------------------------------------------------------------

    def generate_payment(
        self,
        amount:    float | str,
        item_name: str,
        **params,
    ) -> str:
        """
        Generate a signed PayFast payment URL.

        The cleanest way to redirect a user to PayFast for a once-off payment.

        Parameters
        ----------
        amount:
            Payment amount in ZAR (e.g. ``349.99``).
        item_name:
            Description shown on the PayFast checkout page.
        **params:
            Any additional PayFast fields: ``custom_str1``, ``name_first``,
            ``email_address``, ``item_description``, etc.

        Returns
        -------
        str
            Fully-signed payment URL for a GET redirect.

        Example
        -------
        ::

            url = client.generate_payment(
                amount        = 349.99,
                item_name     = "Order #1042",
                custom_str1   = str(order.id),
                email_address = user.email,
            )
            return redirect(url)
        """
        payload = {"amount": f"{float(amount):.2f}", "item_name": item_name, **params}
        return self.service.build_payment_url(payload)

    def generate_payment_form_data(
        self,
        amount:    float | str,
        item_name: str,
        **params,
    ) -> tuple[str, dict]:
        """
        Generate signed form data for a POST-based PayFast checkout.

        Returns a ``(endpoint, data)`` tuple — pass both to your template.

        Parameters
        ----------
        amount:
            Payment amount in ZAR.
        item_name:
            Description shown on the PayFast checkout page.
        **params:
            Any additional PayFast fields.

        Returns
        -------
        tuple[str, dict]
            ``(endpoint_url, signed_payment_data_dict)``

        Example
        -------
        ::

            endpoint, data = client.generate_payment_form_data(
                amount    = 349.99,
                item_name = "Order #1042",
            )
            return render(request, "checkout.html", {"endpoint": endpoint, "data": data})
        """
        payload = {"amount": f"{float(amount):.2f}", "item_name": item_name, **params}
        data    = self.service.generate_payment_data(payload)
        return self.service.get_payment_endpoint(), data

    # -------------------------------------------------------------------------
    # Subscription generation (premium interface)
    # -------------------------------------------------------------------------

    def create_subscription(
        self,
        amount:    float,
        item_name: str,
        frequency: SubscriptionFrequency = SubscriptionFrequency.MONTHLY,
        cycles:    int = 0,
        **params,
    ) -> str:
        """
        Generate a signed PayFast subscription payment URL.

        Parameters
        ----------
        amount:
            Recurring billing amount in ZAR.
        item_name:
            Description shown on the PayFast checkout page.
        frequency:
            A :class:`~payfast_core.models.SubscriptionFrequency` value.
            Defaults to ``MONTHLY``.
        cycles:
            Total billing cycles. ``0`` = indefinite.
        **params:
            Any additional fields: ``custom_str1``, ``billing_date``, etc.

        Returns
        -------
        str
            Fully-signed subscription payment URL.

        Example
        -------
        ::

            url = client.create_subscription(
                amount      = 299.00,
                item_name   = "Pro Plan",
                frequency   = SubscriptionFrequency.MONTHLY,
                custom_str1 = str(user.id),
            )
            return redirect(url)
        """
        return self.subscription_service.build_subscription_url(
            amount    = amount,
            item_name = item_name,
            frequency = frequency,
            cycles    = cycles,
            **params,
        )

    def create_trial_subscription(
        self,
        amount:       float,
        item_name:    str,
        trial_amount: float = 0.00,
        **params,
    ) -> str:
        """
        Generate a signed URL for a trial subscription payment.

        Parameters
        ----------
        amount:
            Regular recurring amount after the trial.
        item_name:
            Description shown on the PayFast checkout page.
        trial_amount:
            Amount charged for the first (trial) billing. Defaults to ``0.00``.
        **params:
            Additional fields forwarded to the subscription payment data builder.

        Returns
        -------
        str
            Fully-signed trial subscription payment URL.
        """
        data = self.subscription_service.generate_trial_subscription_payment_data(
            amount=amount, item_name=item_name, trial_amount=trial_amount, **params
        )
        endpoint = self.service.get_payment_endpoint()
        return f"{endpoint}?{urlencode(data)}"

    # -------------------------------------------------------------------------
    # Low-level helpers (passthrough to service)
    # -------------------------------------------------------------------------

    def build_payment_url(self, **params) -> str:
        """Build a signed payment URL. Prefer :meth:`generate_payment` for new code."""
        return self.service.build_payment_url(params)

    def generate_payment_data(self, **params) -> dict:
        """Generate signed payment data dict. Prefer :meth:`generate_payment_form_data`."""
        return self.service.generate_payment_data(params)

    def generate_signature(self, data: dict, passphrase: str | None = None) -> str:
        """Generate an MD5 signature for an arbitrary data dict."""
        return self.service.generate_signature(data, passphrase)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _dispatch(self, event: object) -> None:
        for fn in self._listeners.get(type(event), []):
            try:
                fn(event)
            except Exception:
                logger.exception("Listener %r raised for %r", fn, event)

    def _handle_subscription(
        self, payload: dict, transaction: PayfastTransaction
    ) -> PayfastSubscription | None:
        token = payload.get("token")
        if not token:
            return None

        subscription = PayfastSubscription.from_itn_payload(payload)
        created_event = PayfastSubscriptionCreated(subscription=subscription, payload=payload)
        self._dispatch(created_event)
        for handler in self._subscription_handlers:
            handler._dispatch_created(created_event)

        return subscription
