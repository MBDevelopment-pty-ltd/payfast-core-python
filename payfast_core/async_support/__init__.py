"""
payfast_core.async_support
---------------------------
Async-native PayFast client for FastAPI, async workers, and high-throughput systems.

:class:`AsyncPayfastClient` mirrors the synchronous :class:`~payfast_core.client.PayfastClient`
API exactly, with ``await``-able versions of every method.

Usage (FastAPI)
---------------
::

    from fastapi import FastAPI, Request
    from payfast_core.async_support import AsyncPayfastClient
    from payfast_core import PayfastConfig, PayfastPaymentEvent

    app    = FastAPI()
    config = PayfastConfig.from_env()
    client = AsyncPayfastClient(config)

    @client.on(PayfastPaymentEvent)
    async def handle_payment(event: PayfastPaymentEvent) -> None:
        if event.is_complete():
            await activate_order(event.custom_str(1))

    @app.post("/payfast/notify")
    async def payfast_notify(request: Request):
        form_data = await request.form()
        payload   = dict(form_data)
        event     = await client.handle_itn(payload, remote_ip=request.client.host)
        return "OK"

Usage (async subscription API)
-------------------------------
::

    status = await client.subscription_service.fetch_subscription(token)
    await client.subscription_service.cancel(token)
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Coroutine

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

from payfast_core import security
from payfast_core.config import PayfastConfig
from payfast_core.events import (
    PayfastItnReceived,
    PayfastPaymentComplete,
    PayfastPaymentEvent,
    PayfastPaymentFailed,
    PayfastSubscriptionCreated,
    PayfastSubscriptionRenewed,
)
from payfast_core.exceptions import PayfastException, SubscriptionException
from payfast_core.idempotency import IdempotencyStore, DuplicateItnException
from payfast_core.models import PayfastSubscription, PayfastTransaction
from payfast_core.services import PayfastService, SubscriptionService

logger = logging.getLogger("payfast_core.async_support")

LIVE_API_BASE = "https://api.payfast.co.za/subscriptions"


class AsyncSubscriptionService:
    """
    Async version of :class:`~payfast_core.services.SubscriptionService`.

    Uses ``httpx.AsyncClient`` for non-blocking HTTP calls to the PayFast
    Subscription API.
    """

    def __init__(self, service: PayfastService) -> None:
        self._service = service
        self._config  = service.config

    async def fetch_subscription(self, token: str) -> dict:
        """Async fetch of subscription status from the PayFast API."""
        if httpx is None:
            raise ImportError("httpx is required for async support: pip install httpx")
        async with httpx.AsyncClient() as http:
            try:
                response = await http.get(
                    f"{LIVE_API_BASE}/{token}/fetch",
                    headers=self._headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                raise SubscriptionException(f"Failed to fetch subscription [{token}]: {exc}") from exc

    async def pause(self, token: str) -> bool:
        return await self._put(token, "pause")

    async def unpause(self, token: str) -> bool:
        return await self._put(token, "unpause")

    async def cancel(self, token: str) -> bool:
        return await self._put(token, "cancel")

    async def update_amount(self, token: str, amount: float, cycles: int | None = None) -> bool:
        body: dict = {"amount": int(amount * 100)}
        if cycles is not None:
            body["cycles"] = cycles
        if httpx is None:
            raise ImportError("httpx is required for async support: pip install httpx")
        async with httpx.AsyncClient() as http:
            try:
                response = await http.patch(
                    f"{LIVE_API_BASE}/{token}/update",
                    json=body,
                    headers=self._headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                return True
            except httpx.HTTPError as exc:
                raise SubscriptionException(f"Failed to update subscription [{token}]: {exc}") from exc

    async def _put(self, token: str, action: str) -> bool:
        if httpx is None:
            raise ImportError("httpx is required for async support: pip install httpx")
        async with httpx.AsyncClient() as http:
            try:
                response = await http.put(
                    f"{LIVE_API_BASE}/{token}/{action}",
                    headers=self._headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                return True
            except httpx.HTTPError as exc:
                raise SubscriptionException(f"Failed to {action} subscription [{token}]: {exc}") from exc

    def _headers(self) -> dict:
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        return {
            "merchant-id": self._config.merchant_id,
            "timestamp":   timestamp,
            "version":     "v1",
            "signature":   security.generate_api_signature(
                merchant_id = self._config.merchant_id,
                passphrase  = self._config.passphrase,
                timestamp   = timestamp,
            ),
        }


class AsyncPayfastClient:
    """
    Async-native PayFast client.

    Drop-in async equivalent of :class:`~payfast_core.client.PayfastClient`.
    Listeners may be either regular functions or ``async`` coroutines —
    both are supported transparently.

    Parameters
    ----------
    config:
        A :class:`~payfast_core.config.PayfastConfig` instance.
    idempotency_store:
        Optional :class:`~payfast_core.idempotency.IdempotencyStore`.
        When provided, duplicate ITNs raise :class:`~payfast_core.idempotency.DuplicateItnException`.
    """

    def __init__(
        self,
        config: PayfastConfig,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self.config               = config
        self.service              = PayfastService(config)
        self.subscription_service = AsyncSubscriptionService(self.service)
        self._idempotency         = idempotency_store
        self._listeners: dict[type, list[Callable]] = defaultdict(list)

    # -------------------------------------------------------------------------
    # Listener registration (identical API to sync client)
    # -------------------------------------------------------------------------

    def on(self, event_class: type) -> Callable:
        """Decorator to register a sync or async listener for an event class."""
        def decorator(fn: Callable) -> Callable:
            self.add_listener(event_class, fn)
            return fn
        return decorator

    def add_listener(self, event_class: type, fn: Callable) -> None:
        self._listeners[event_class].append(fn)

    async def _dispatch(self, event: object) -> None:
        for fn in self._listeners.get(type(event), []):
            try:
                result = fn(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Async listener %r raised for %r", fn, event)

    # -------------------------------------------------------------------------
    # ITN handling
    # -------------------------------------------------------------------------

    async def handle_itn(
        self,
        payload:   dict,
        remote_ip: str | None = None,
    ) -> PayfastPaymentEvent:
        """
        Async ITN processing — validates, builds models, dispatches events.

        Parameters
        ----------
        payload:
            The full POST body from the ITN request as a flat dict.
        remote_ip:
            The IP address of the incoming request.

        Returns
        -------
        PayfastPaymentEvent

        Raises
        ------
        PayfastException
            Signature or IP validation failure.
        DuplicateItnException
            When an idempotency store is configured and the ITN was already
            processed. Catch this and return ``200 OK`` to PayFast.
        """
        # Security validation (sync — pure CPU work, no I/O)
        self.service.validate_itn(payload, remote_ip=remote_ip)

        # Idempotency check
        if self._idempotency is not None:
            tx_id = payload.get("pf_payment_id", "")
            if tx_id:
                self._idempotency.check_and_mark(tx_id)

        # Build models and dispatch
        await self._dispatch(PayfastItnReceived(payload=payload))
        transaction   = PayfastTransaction.from_payload(payload)
        is_sub        = int(payload.get("subscription_type", 0)) == 1
        subscription  = self._handle_subscription_sync(payload) if is_sub else None

        event = PayfastPaymentEvent(
            payload      = payload,
            transaction  = transaction,
            subscription = subscription,
        )

        await self._dispatch(event)

        if event.is_complete():
            await self._dispatch(PayfastPaymentComplete(payload=payload))
        else:
            await self._dispatch(PayfastPaymentFailed(payload=payload))

        logger.info("Async ITN processed: %s", event.summary())
        return event

    # -------------------------------------------------------------------------
    # Payment helpers
    # -------------------------------------------------------------------------

    def build_payment_url(self, **params) -> str:
        return self.service.build_payment_url(params)

    def generate_payment_data(self, **params) -> dict:
        return self.service.generate_payment_data(params)

    def generate_signature(self, data: dict, passphrase: str | None = None) -> str:
        return self.service.generate_signature(data, passphrase)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _handle_subscription_sync(self, payload: dict) -> PayfastSubscription | None:
        token = payload.get("token")
        if not token:
            return None
        sub = PayfastSubscription.from_itn_payload(payload)
        # Fire-and-forget: schedule dispatch without awaiting (sync context)
        # Full async dispatch happens via handle_itn's event loop
        return sub
