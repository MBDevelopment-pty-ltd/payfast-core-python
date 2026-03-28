"""
payfast-core — Python SDK for the PayFast payment gateway.
Developed and maintained by MB Development Pty Ltd <dev@mbdevelopment.co.za>
"""

from payfast_core.client import PayfastClient
from payfast_core.config import PayfastConfig
from payfast_core.events import (
    PayfastPaymentEvent,
    PayfastItnReceived,
    PayfastPaymentComplete,
    PayfastPaymentFailed,
    PayfastSubscriptionCreated,
    PayfastSubscriptionRenewed,
    PayfastSubscriptionCancelled,
)
from payfast_core.exceptions import (
    PayfastException,
    InvalidSignatureException,
    InvalidSourceIPException,
    SubscriptionException,
)
from payfast_core.handlers import PaymentHandler, SubscriptionHandler
from payfast_core.idempotency import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
    RedisIdempotencyStore,
    DuplicateItnException,
)
from payfast_core.models import (
    PayfastTransaction,
    PayfastSubscription,
    PaymentStatus,
    PaymentType,
    SubscriptionStatus,
    SubscriptionFrequency,
)
from payfast_core.services import PayfastService, SubscriptionService
from payfast_core.standards import EventNames, PaymentTypes, PaymentStatuses, ItnFields

__version__ = "1.0.0"
__author__  = "MB Development Pty Ltd"
__email__   = "dev@mbdevelopment.co.za"

__all__ = [
    # Client
    "PayfastClient",
    "PayfastConfig",
    # Services
    "PayfastService",
    "SubscriptionService",
    # Events
    "PayfastPaymentEvent",
    "PayfastItnReceived",
    "PayfastPaymentComplete",
    "PayfastPaymentFailed",
    "PayfastSubscriptionCreated",
    "PayfastSubscriptionRenewed",
    "PayfastSubscriptionCancelled",
    # Exceptions
    "PayfastException",
    "InvalidSignatureException",
    "InvalidSourceIPException",
    "SubscriptionException",
    "DuplicateItnException",
    # Handlers
    "PaymentHandler",
    "SubscriptionHandler",
    # Idempotency
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "RedisIdempotencyStore",
    # Models
    "PayfastTransaction",
    "PayfastSubscription",
    "PaymentStatus",
    "PaymentType",
    "SubscriptionStatus",
    "SubscriptionFrequency",
    # Standards
    "EventNames",
    "PaymentTypes",
    "PaymentStatuses",
    "ItnFields",
]
