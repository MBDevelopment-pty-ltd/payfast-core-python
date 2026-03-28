"""Feature tests for SubscriptionService — payment data, URL building, API calls."""

import pytest
import responses as resp_lib
import responses

from payfast_core.models import SubscriptionFrequency, SubscriptionStatus
from payfast_core.exceptions import SubscriptionException
from payfast_core.services import SubscriptionService

LIVE_API = "https://api.payfast.co.za/subscriptions"


class TestGenerateSubscriptionPaymentData:
    def test_includes_subscription_type_1(self, subscription_service):
        data = subscription_service.generate_subscription_payment_data(
            amount=299.00, item_name="Pro Plan"
        )
        assert data["subscription_type"] == 1

    def test_defaults_to_monthly_frequency(self, subscription_service):
        data = subscription_service.generate_subscription_payment_data(
            amount=299.00, item_name="Pro Plan"
        )
        assert data["frequency"] == SubscriptionFrequency.MONTHLY.value

    def test_defaults_to_indefinite_cycles(self, subscription_service):
        data = subscription_service.generate_subscription_payment_data(
            amount=299.00, item_name="Pro Plan"
        )
        assert data["cycles"] == 0

    def test_respects_custom_frequency(self, subscription_service):
        data = subscription_service.generate_subscription_payment_data(
            amount=299.00, item_name="Pro Plan",
            frequency=SubscriptionFrequency.ANNUALLY,
        )
        assert data["frequency"] == SubscriptionFrequency.ANNUALLY.value

    def test_respects_custom_cycles(self, subscription_service):
        data = subscription_service.generate_subscription_payment_data(
            amount=299.00, item_name="Pro Plan", cycles=12,
        )
        assert data["cycles"] == 12

    def test_injects_custom_str1(self, subscription_service):
        data = subscription_service.generate_subscription_payment_data(
            amount=299.00, item_name="Pro Plan", custom_str1="user_99",
        )
        assert data["custom_str1"] == "user_99"

    def test_includes_signature(self, subscription_service):
        data = subscription_service.generate_subscription_payment_data(
            amount=299.00, item_name="Pro Plan"
        )
        assert "signature" in data
        assert len(data["signature"]) == 32

    def test_includes_merchant_credentials(self, subscription_service):
        data = subscription_service.generate_subscription_payment_data(
            amount=299.00, item_name="Pro Plan"
        )
        assert data["merchant_id"]  == "10000100"
        assert data["merchant_key"] == "46f0cd694581a"


class TestGenerateTrialSubscriptionPaymentData:
    def test_first_billing_uses_trial_amount(self, subscription_service):
        data = subscription_service.generate_trial_subscription_payment_data(
            amount=299.00, item_name="Pro Plan", trial_amount=0.00
        )
        assert float(data["amount"]) == 0.00

    def test_free_trial_by_default(self, subscription_service):
        data = subscription_service.generate_trial_subscription_payment_data(
            amount=299.00, item_name="Pro Plan"
        )
        assert float(data["amount"]) == 0.00


class TestBuildSubscriptionUrl:
    def test_url_contains_subscription_type(self, subscription_service):
        url = subscription_service.build_subscription_url(amount=299.00, item_name="Plan")
        assert "subscription_type=1" in url

    def test_url_points_to_sandbox(self, subscription_service):
        url = subscription_service.build_subscription_url(amount=299.00, item_name="Plan")
        assert "sandbox.payfast.co.za" in url


class TestSyncFromItn:
    def test_builds_subscription_from_payload(self, subscription_service, subscription_itn_payload):
        sub = subscription_service.sync_from_itn(subscription_itn_payload)
        assert sub.token       == "tok_abc123"
        assert sub.is_active() is True
        assert sub.amount      == 299.00
        assert sub.frequency   == SubscriptionFrequency.MONTHLY
        assert sub.cycles      == 12

    def test_raises_without_token(self, subscription_service):
        from payfast_core.exceptions import PayfastException
        with pytest.raises(PayfastException):
            subscription_service.sync_from_itn({"payment_status": "COMPLETE"})


class TestSubscriptionApiCalls:
    TOKEN = "tok_api_test"

    @responses.activate
    def test_pause_calls_payfast_api(self, subscription_service):
        responses.add(responses.PUT, f"{LIVE_API}/{self.TOKEN}/pause", status=200)
        result = subscription_service.pause(self.TOKEN)
        assert result is True

    @responses.activate
    def test_unpause_calls_payfast_api(self, subscription_service):
        responses.add(responses.PUT, f"{LIVE_API}/{self.TOKEN}/unpause", status=200)
        result = subscription_service.unpause(self.TOKEN)
        assert result is True

    @responses.activate
    def test_cancel_calls_payfast_api(self, subscription_service):
        responses.add(responses.PUT, f"{LIVE_API}/{self.TOKEN}/cancel", status=200)
        result = subscription_service.cancel(self.TOKEN)
        assert result is True

    @responses.activate
    def test_fetch_subscription_returns_json(self, subscription_service):
        responses.add(
            responses.GET,
            f"{LIVE_API}/{self.TOKEN}/fetch",
            json={"token": self.TOKEN, "status": "active"},
            status=200,
        )
        data = subscription_service.fetch_subscription(self.TOKEN)
        assert data["token"]  == self.TOKEN
        assert data["status"] == "active"

    @responses.activate
    def test_update_amount_sends_cents(self, subscription_service):
        responses.add(responses.PATCH, f"{LIVE_API}/{self.TOKEN}/update", status=200)
        result = subscription_service.update_amount(self.TOKEN, amount=349.00)
        assert result is True
        # Verify the request body contained the amount in cents
        request_body = responses.calls[0].request.body
        assert "34900" in str(request_body)

    @responses.activate
    def test_pause_raises_on_api_error(self, subscription_service):
        responses.add(responses.PUT, f"{LIVE_API}/{self.TOKEN}/pause", status=500)
        with pytest.raises(SubscriptionException):
            subscription_service.pause(self.TOKEN)

    @responses.activate
    def test_cancel_raises_on_api_error(self, subscription_service):
        responses.add(responses.PUT, f"{LIVE_API}/{self.TOKEN}/cancel", status=403)
        with pytest.raises(SubscriptionException):
            subscription_service.cancel(self.TOKEN)
