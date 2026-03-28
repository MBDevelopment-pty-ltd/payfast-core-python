"""
payfast_core.idempotency
-------------------------
Duplicate ITN detection and idempotency enforcement.

PayFast can POST the same ITN multiple times (retries, network hiccups).
Without idempotency protection your application may activate an order twice,
grant access twice, or credit a customer twice.

This module provides:

* :class:`IdempotencyStore` — abstract base, implement with your storage.
* :class:`InMemoryIdempotencyStore` — in-process store for development/testing.
* :class:`RedisIdempotencyStore` — production-ready store backed by Redis.
* :func:`idempotent_itn` — decorator that skips duplicate ITN payloads.

Usage
-----
::

    from payfast_core.idempotency import InMemoryIdempotencyStore

    store  = InMemoryIdempotencyStore()
    client = PayfastClient(config, idempotency_store=store)

    # handle_itn will now raise DuplicateItnException on repeated pf_payment_id
    event = client.handle_itn(payload, remote_ip=ip)

Custom store (e.g. Django ORM)
---------------------------------
::

    from payfast_core.idempotency import IdempotencyStore

    class DjangoIdempotencyStore(IdempotencyStore):
        def has_seen(self, transaction_id: str) -> bool:
            return ProcessedItn.objects.filter(pf_payment_id=transaction_id).exists()

        def mark_seen(self, transaction_id: str) -> None:
            ProcessedItn.objects.get_or_create(pf_payment_id=transaction_id)
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod

from payfast_core.exceptions import PayfastException

logger = logging.getLogger("payfast_core.idempotency")


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class DuplicateItnException(PayfastException):
    """
    Raised when an ITN with a previously-seen ``pf_payment_id`` is received.

    Catch this in your webhook endpoint and return ``200 OK`` to PayFast —
    you have already processed the payment, and returning an error would
    cause PayFast to keep retrying.

    Example
    -------
    ::

        try:
            event = client.handle_itn(payload, remote_ip=ip)
        except DuplicateItnException:
            return HttpResponse("OK")   # already handled, tell PayFast to stop
    """


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class IdempotencyStore(ABC):
    """
    Abstract interface for idempotency storage backends.

    Implement :meth:`has_seen` and :meth:`mark_seen` with your preferred
    persistence layer (Redis, database, cache, etc.).
    """

    @abstractmethod
    def has_seen(self, transaction_id: str) -> bool:
        """
        Return ``True`` if this ``transaction_id`` has already been processed.

        Parameters
        ----------
        transaction_id:
            The PayFast ``pf_payment_id`` from the ITN payload.
        """

    @abstractmethod
    def mark_seen(self, transaction_id: str) -> None:
        """
        Record ``transaction_id`` as processed.

        This must be called *after* your business logic succeeds so that a
        failure mid-processing does not block a legitimate retry.

        Parameters
        ----------
        transaction_id:
            The PayFast ``pf_payment_id`` from the ITN payload.
        """

    def check_and_mark(self, transaction_id: str) -> None:
        """
        Atomically check and mark a transaction ID.

        Raises :class:`DuplicateItnException` if already seen, otherwise
        marks it as seen. The default implementation is not atomic — override
        this method if your backend supports atomic check-and-set (e.g.
        Redis ``SET NX``).

        Parameters
        ----------
        transaction_id:
            The PayFast ``pf_payment_id``.

        Raises
        ------
        DuplicateItnException
            If the transaction has already been processed.
        """
        if self.has_seen(transaction_id):
            logger.warning("Duplicate ITN detected for pf_payment_id=%s", transaction_id)
            raise DuplicateItnException(
                f"Duplicate ITN received for pf_payment_id={transaction_id!r}. "
                "This ITN has already been processed. Return 200 OK to PayFast."
            )
        self.mark_seen(transaction_id)


# ---------------------------------------------------------------------------
# In-memory store (development / testing)
# ---------------------------------------------------------------------------

class InMemoryIdempotencyStore(IdempotencyStore):
    """
    Thread-safe in-memory idempotency store.

    Suitable for development, testing, and single-process applications.

    .. warning::
        State is lost on process restart. For production, use
        :class:`RedisIdempotencyStore` or implement your own DB-backed store.

    Parameters
    ----------
    ttl_seconds:
        How long (in seconds) to remember a processed transaction ID.
        Defaults to ``86400`` (24 hours). Set to ``None`` to never expire.
    """

    def __init__(self, ttl_seconds: int | None = 86_400) -> None:
        self._store: dict[str, float] = {}
        self._ttl   = ttl_seconds
        self._lock  = threading.Lock()

    def has_seen(self, transaction_id: str) -> bool:
        with self._lock:
            self._evict_expired()
            return transaction_id in self._store

    def mark_seen(self, transaction_id: str) -> None:
        with self._lock:
            self._store[transaction_id] = time.monotonic()
            logger.debug("Marked as seen: pf_payment_id=%s", transaction_id)

    def check_and_mark(self, transaction_id: str) -> None:
        """Atomic check-and-mark using a lock."""
        with self._lock:
            self._evict_expired()
            if transaction_id in self._store:
                logger.warning("Duplicate ITN: pf_payment_id=%s", transaction_id)
                raise DuplicateItnException(
                    f"Duplicate ITN for pf_payment_id={transaction_id!r}."
                )
            self._store[transaction_id] = time.monotonic()

    def _evict_expired(self) -> None:
        if self._ttl is None:
            return
        cutoff = time.monotonic() - self._ttl
        expired = [k for k, ts in self._store.items() if ts < cutoff]
        for k in expired:
            del self._store[k]

    def clear(self) -> None:
        """Clear all stored IDs. Useful in tests."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# ---------------------------------------------------------------------------
# Redis store (production)
# ---------------------------------------------------------------------------

class RedisIdempotencyStore(IdempotencyStore):
    """
    Redis-backed idempotency store with atomic ``SET NX`` semantics.

    Uses Redis ``SET key 1 EX ttl NX`` which is atomic — no race condition
    between the ``has_seen`` and ``mark_seen`` operations.

    Parameters
    ----------
    redis_client:
        A ``redis.Redis`` (or ``redis.asyncio.Redis``) client instance.
    ttl_seconds:
        Key expiry time in seconds. Defaults to ``86400`` (24 hours).
    key_prefix:
        Prefix for all Redis keys. Defaults to ``"payfast:itn:"``.

    Example
    -------
    ::

        import redis
        from payfast_core.idempotency import RedisIdempotencyStore

        r     = redis.Redis.from_url("redis://localhost:6379/0")
        store = RedisIdempotencyStore(r, ttl_seconds=86400)
        client = PayfastClient(config, idempotency_store=store)
    """

    def __init__(
        self,
        redis_client,
        ttl_seconds: int = 86_400,
        key_prefix:  str = "payfast:itn:",
    ) -> None:
        self._redis  = redis_client
        self._ttl    = ttl_seconds
        self._prefix = key_prefix

    def _key(self, transaction_id: str) -> str:
        return f"{self._prefix}{transaction_id}"

    def has_seen(self, transaction_id: str) -> bool:
        return bool(self._redis.exists(self._key(transaction_id)))

    def mark_seen(self, transaction_id: str) -> None:
        self._redis.set(self._key(transaction_id), "1", ex=self._ttl)

    def check_and_mark(self, transaction_id: str) -> None:
        """Atomic SET NX — no race condition between check and mark."""
        key = self._key(transaction_id)
        # SET key 1 EX ttl NX — returns True only if key was newly set
        was_set = self._redis.set(key, "1", ex=self._ttl, nx=True)
        if not was_set:
            logger.warning("Duplicate ITN (Redis): pf_payment_id=%s", transaction_id)
            raise DuplicateItnException(
                f"Duplicate ITN for pf_payment_id={transaction_id!r}."
            )
        logger.debug("Redis: marked as seen pf_payment_id=%s", transaction_id)
