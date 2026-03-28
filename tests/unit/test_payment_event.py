"""Unit tests for PayfastPaymentEvent."""

import pytest

from payfast_core.events import PayfastPaymentEvent
from payfast_core.models import PayfastTransaction, PayfastSubscription, SubscriptionStatus, SubscriptionFrequency


def make_transaction(payload: dict) -> PayfastTransaction:
    return PayfastTransaction.from_payload(payload)


class TestPaymentType:
    def test_once_off_when_no_subscription_type(self):
        payload = {"payment_status": "COMPLETE", "amount_gross": "100.00", "item_name": "Item", "merchant_id": "1"}
        event = PayfastPaymentEvent(payload=payload, transaction=make_transaction(payload))
        assert event.is_once_off() is True
        assert event.is_subscription() is False

    def test_subscription_when_subscription_type_is_1(self):
        payload = {"payment_status": "COMPLETE", "subscription_type": "1", "amount_gross": "100.00", "item_name": "Plan", "merchant_id": "1"}
        event = PayfastPaymentEvent(payload=payload, transaction=make_transaction(payload))
        assert event.is_subscription() is True
        assert event.is_once_off() is False


class TestPaymentStatus:
    @pytest.mark.parametrize("status,method", [
        ("COMPLETE",  "is_complete"),
        ("FAILED",    "is_failed"),
        ("PENDING",   "is_pending"),
        ("CANCELLED", "is_cancelled"),
    ])
    def test_status_helpers(self, status, method):
        payload = {"payment_status": status, "amount_gross": "100.00", "item_name": "Item", "merchant_id": "1"}
        event   = PayfastPaymentEvent(payload=payload, transaction=make_transaction(payload))
        assert getattr(event, method)() is True

    def test_status_is_case_insensitive(self):
        payload = {"payment_status": "complete", "amount_gross": "0", "item_name": "Item", "merchant_id": "1"}
        event   = PayfastPaymentEvent(payload=payload, transaction=make_transaction(payload))
        assert event.is_complete() is True


class TestPayloadAccessors:
    @pytest.fixture
    def event(self):
        payload = {
            "payment_status": "COMPLETE",
            "amount_gross":   "299.00",
            "amount_net":     "290.50",
            "pf_payment_id":  "pf_xyz",
            "item_name":      "Pro Plan",
            "name_first":     "Alice",
            "name_last":      "Smith",
            "email_address":  "alice@smith.com",
            "custom_str1":    "order_77",
            "custom_str2":    "promo_10",
            "custom_int1":    "5",
            "token":          "tok_999",
            "merchant_id":    "10000100",
        }
        return PayfastPaymentEvent(payload=payload, transaction=make_transaction(payload))

    def test_amount_gross(self, event):
        assert event.amount_gross() == 299.00

    def test_amount_net(self, event):
        assert event.amount_net() == 290.50

    def test_pf_payment_id(self, event):
        assert event.pf_payment_id() == "pf_xyz"

    def test_item_name(self, event):
        assert event.item_name() == "Pro Plan"

    def test_buyer_details(self, event):
        assert event.buyer_first_name() == "Alice"
        assert event.buyer_last_name()  == "Smith"
        assert event.buyer_email()      == "alice@smith.com"

    def test_custom_str(self, event):
        assert event.custom_str(1) == "order_77"
        assert event.custom_str(2) == "promo_10"
        assert event.custom_str(3) is None

    def test_custom_int(self, event):
        assert event.custom_int(1) == 5
        assert isinstance(event.custom_int(1), int)
        assert event.custom_int(2) is None

    def test_subscription_token(self, event):
        assert event.subscription_token() == "tok_999"

    def test_summary_string(self, event):
        s = event.summary()
        assert "COMPLETE" in s
        assert "once_off" in s
        assert "299.00" in s
        assert "Pro Plan" in s


class TestSubscriptionAttachment:
    def test_subscription_is_none_for_once_off(self):
        payload = {"payment_status": "COMPLETE", "amount_gross": "0", "item_name": "Item", "merchant_id": "1"}
        event   = PayfastPaymentEvent(payload=payload, transaction=make_transaction(payload))
        assert event.subscription is None

    def test_subscription_attached_when_provided(self):
        payload = {"payment_status": "COMPLETE", "subscription_type": "1", "amount_gross": "0", "item_name": "Plan", "merchant_id": "1", "token": "tok"}
        sub = PayfastSubscription(
            token="tok", status=SubscriptionStatus.ACTIVE, amount=299.00,
            frequency=SubscriptionFrequency.MONTHLY, item_name="Pro Plan"
        )
        event = PayfastPaymentEvent(payload=payload, transaction=make_transaction(payload), subscription=sub)
        assert event.subscription is not None
        assert event.subscription.token == "tok"
