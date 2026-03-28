"""
payfast_core.exceptions
-----------------------
Exception hierarchy for the PayFast SDK.
"""


class PayfastException(Exception):
    """Base exception for all PayFast SDK errors."""


class InvalidSignatureException(PayfastException):
    """Raised when an ITN or webhook payload signature does not match."""


class InvalidSourceIPException(PayfastException):
    """Raised when an ITN request originates from an unrecognised IP address."""


class SubscriptionException(PayfastException):
    """Raised when a subscription API call fails."""
