"""Unit tests for PayfastTransaction and PayfastSubscription models."""

import pytest
from datetime import datetime, timedelta

from payfast_core.models import (
    PayfastTransaction,
    PayfastSubscription,
    PaymentStatus,
    SubscriptionStatus,
    SubscriptionFrequency,
)


# ---------------------------------------------------------------------------
# PayfastTransaction
# ---------------------------------------------------------------------------

class TestPayfastTransaction:
    @pytest.fixture
    def payload(self):
        return {
            "pf_payment_id":  "pf_001",
            "payment_status": "COMPLETE",
            "item_name":      "Test Product",
            "amount_gross":   "199.99",
            "amount_fee":     "5.99",
            "amount_net":     "194.00",
            "merchant_id":    "10000100",
            "custom_str1":    "order_42",
            "custom_int1":    "7",
            "name_first":     "Jane",
            "name_last":      "Doe",
            "email_address":  "jane@example.com",
        }

    def test_builds_from_payload(self, payload):
        tx = PayfastTransaction.from_payload(payload)
        assert tx.pf_payment_id  == "pf_001"
        assert tx.payment_status == PaymentStatus.COMPLETE
        assert tx.amount_gross   == 199.99
        assert tx.custom_str1    == "order_42"
        assert tx.custom_int1    == 7

    def test_amounts_are_floats(self, payload):
        tx = PayfastTransaction.from_payload(payload)
        assert isinstance(tx.amount_gross, float)
        assert isinstance(tx.amount_fee, float)
        assert isinstance(tx.amount_net, float)

    def test_custom_int_is_int(self, payload):
        tx = PayfastTransaction.from_payload(payload)
        assert isinstance(tx.custom_int1, int)

    def test_raw_payload_preserved(self, payload):
        tx = PayfastTransaction.from_payload(payload)
        assert tx.raw_payload == payload

    def test_is_complete(self, payload):
        tx = PayfastTransaction.from_payload(payload)
        assert tx.is_complete() is True
        assert tx.is_failed()   is False

    def test_is_failed(self, payload):
        payload["payment_status"] = "FAILED"
        tx = PayfastTransaction.from_payload(payload)
        assert tx.is_failed()   is True
        assert tx.is_complete() is False

    def test_unknown_status_maps_to_unknown(self, payload):
        payload["payment_status"] = "WEIRD_VALUE"
        tx = PayfastTransaction.from_payload(payload)
        assert tx.payment_status == PaymentStatus.UNKNOWN

    def test_missing_optional_fields_are_none(self):
        tx = PayfastTransaction.from_payload({
            "payment_status": "COMPLETE",
            "item_name": "Item",
            "amount_gross": "10.00",
            "merchant_id": "1",
        })
        assert tx.custom_str1 is None
        assert tx.custom_int1 is None
        assert tx.name_first  is None
        assert tx.amount_fee  is None


# ---------------------------------------------------------------------------
# PayfastSubscription
# ---------------------------------------------------------------------------

class TestPayfastSubscription:
    @pytest.fixture
    def active_sub(self):
        return PayfastSubscription(
            token     = "tok_xyz",
            status    = SubscriptionStatus.ACTIVE,
            amount    = 299.00,
            frequency = SubscriptionFrequency.MONTHLY,
            item_name = "Pro Plan",
            cycles    = 12,
            cycles_complete = 0,
        )

    def test_is_active(self, active_sub):
        assert active_sub.is_active()    is True
        assert active_sub.is_paused()    is False
        assert active_sub.is_cancelled() is False

    def test_cancel_returns_new_cancelled_instance(self, active_sub):
        cancelled = active_sub.cancel()
        assert cancelled.is_cancelled()    is True
        assert cancelled.cancelled_at      is not None
        assert active_sub.is_active()      is True  # original unchanged

    def test_pause_and_resume(self, active_sub):
        paused   = active_sub.pause()
        resumed  = paused.resume()
        assert paused.is_paused()   is True
        assert resumed.is_active()  is True

    def test_increment_cycle_increases_count(self, active_sub):
        updated = active_sub.increment_cycle()
        assert updated.cycles_complete == 1
        assert updated.is_active()     is True

    def test_increment_cycle_completes_when_all_cycles_done(self, active_sub):
        sub = PayfastSubscription(
            token="tok", status=SubscriptionStatus.ACTIVE, amount=10.00,
            frequency=SubscriptionFrequency.MONTHLY, item_name="Plan",
            cycles=2, cycles_complete=1,
        )
        completed = sub.increment_cycle()
        assert completed.status == SubscriptionStatus.COMPLETED

    def test_indefinite_subscription_never_completes(self, active_sub):
        sub = PayfastSubscription(
            token="tok", status=SubscriptionStatus.ACTIVE, amount=10.00,
            frequency=SubscriptionFrequency.MONTHLY, item_name="Plan",
            cycles=0, cycles_complete=99,
        )
        updated = sub.increment_cycle()
        assert updated.is_active() is True

    def test_on_trial_true_when_trial_in_future(self, active_sub):
        sub = PayfastSubscription(
            token="tok", status=SubscriptionStatus.ACTIVE, amount=10.00,
            frequency=SubscriptionFrequency.MONTHLY, item_name="Plan",
            trial_ends_at=datetime.utcnow() + timedelta(days=7),
        )
        assert sub.on_trial() is True

    def test_on_trial_false_when_trial_expired(self, active_sub):
        sub = PayfastSubscription(
            token="tok", status=SubscriptionStatus.ACTIVE, amount=10.00,
            frequency=SubscriptionFrequency.MONTHLY, item_name="Plan",
            trial_ends_at=datetime.utcnow() - timedelta(days=1),
        )
        assert sub.on_trial() is False

    def test_frequency_label(self, active_sub):
        assert active_sub.frequency_label() == "Monthly"
        annual = PayfastSubscription(
            token="tok", status=SubscriptionStatus.ACTIVE, amount=10.00,
            frequency=SubscriptionFrequency.ANNUALLY, item_name="Plan"
        )
        assert annual.frequency_label() == "Annually"

    def test_from_itn_payload(self):
        payload = {
            "token": "tok_itn",
            "payment_status": "COMPLETE",
            "amount_gross": "299.00",
            "frequency": "3",
            "billing_total": "12",
            "item_name": "Pro Plan",
            "custom_str1": "user_1",
        }
        sub = PayfastSubscription.from_itn_payload(payload)
        assert sub.token           == "tok_itn"
        assert sub.is_active()     is True
        assert sub.amount          == 299.00
        assert sub.frequency       == SubscriptionFrequency.MONTHLY
        assert sub.cycles          == 12
        assert sub.custom_str1     == "user_1"

    def test_from_itn_payload_raises_without_token(self):
        from payfast_core.exceptions import PayfastException
        with pytest.raises(PayfastException):
            PayfastSubscription.from_itn_payload({"payment_status": "COMPLETE"})
