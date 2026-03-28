"""
Shared pytest fixtures for payfast-core tests.
"""

import pytest

from payfast_core import PayfastClient, PayfastConfig
from payfast_core.services import PayfastService, SubscriptionService


@pytest.fixture
def config() -> PayfastConfig:
    return PayfastConfig(
        merchant_id  = "10000100",
        merchant_key = "46f0cd694581a",
        passphrase   = "testpassphrase",
        sandbox      = True,
        return_url   = "https://example.com/return",
        cancel_url   = "https://example.com/cancel",
        notify_url   = "https://example.com/notify",
        validate_ip  = False,
    )


@pytest.fixture
def service(config) -> PayfastService:
    return PayfastService(config)


@pytest.fixture
def subscription_service(service) -> SubscriptionService:
    return SubscriptionService(service)


@pytest.fixture
def client(config) -> PayfastClient:
    return PayfastClient(config)


@pytest.fixture
def base_itn_payload(service) -> dict:
    """A minimal valid ITN payload with a correct signature."""
    data = {
        "merchant_id":    "10000100",
        "pf_payment_id":  "pf_abc123",
        "payment_status": "COMPLETE",
        "item_name":      "Test Product",
        "amount_gross":   "199.99",
        "amount_fee":     "5.99",
        "amount_net":     "194.00",
        "custom_str1":    "order_42",
        "name_first":     "Jane",
        "name_last":      "Doe",
        "email_address":  "jane@example.com",
    }
    data["signature"] = service.generate_signature(data, "testpassphrase")
    return data


@pytest.fixture
def subscription_itn_payload(service) -> dict:
    """A valid ITN payload for a subscription payment."""
    data = {
        "merchant_id":       "10000100",
        "pf_payment_id":     "pf_sub_001",
        "payment_status":    "COMPLETE",
        "item_name":         "Pro Plan",
        "amount_gross":      "299.00",
        "amount_fee":        "8.50",
        "amount_net":        "290.50",
        "subscription_type": "1",
        "token":             "tok_abc123",
        "frequency":         "3",
        "billing_total":     "12",
        "custom_str1":       "user_99",
    }
    data["signature"] = service.generate_signature(data, "testpassphrase")
    return data
