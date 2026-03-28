"""Feature tests for PayfastClient — ITN handling and event dispatch."""

import pytest

from payfast_core import PayfastClient, PayfastConfig
from payfast_core.events import (
    PayfastPaymentEvent,
    PayfastItnReceived,
    PayfastPaymentComplete,
    PayfastPaymentFailed,
    PayfastSubscriptionCreated,
)
from payfast_core.exceptions import InvalidSignatureException


class TestHandleItn:
    def test_returns_payment_event_on_valid_itn(self, client, base_itn_payload):
        event = client.handle_itn(base_itn_payload)
        assert isinstance(event, PayfastPaymentEvent)

    def test_raises_on_invalid_signature(self, client, base_itn_payload):
        base_itn_payload["signature"] = "bad"
        with pytest.raises(InvalidSignatureException):
            client.handle_itn(base_itn_payload)

    def test_event_is_once_off_for_standard_payment(self, client, base_itn_payload):
        event = client.handle_itn(base_itn_payload)
        assert event.is_once_off() is True

    def test_event_is_complete_for_complete_status(self, client, base_itn_payload):
        event = client.handle_itn(base_itn_payload)
        assert event.is_complete() is True

    def test_event_is_failed_for_failed_status(self, client, service, base_itn_payload):
        base_itn_payload["payment_status"] = "FAILED"
        del base_itn_payload["signature"]
        base_itn_payload["signature"] = service.generate_signature(base_itn_payload, "testpassphrase")
        event = client.handle_itn(base_itn_payload)
        assert event.is_failed() is True

    def test_event_is_subscription_for_subscription_itn(self, client, subscription_itn_payload):
        event = client.handle_itn(subscription_itn_payload)
        assert event.is_subscription() is True

    def test_transaction_built_and_attached(self, client, base_itn_payload):
        event = client.handle_itn(base_itn_payload)
        assert event.transaction.pf_payment_id == "pf_abc123"
        assert event.transaction.amount_gross  == 199.99

    def test_custom_str_accessible_via_event(self, client, base_itn_payload):
        event = client.handle_itn(base_itn_payload)
        assert event.custom_str(1) == "order_42"

    def test_buyer_email_accessible_via_event(self, client, base_itn_payload):
        event = client.handle_itn(base_itn_payload)
        assert event.buyer_email() == "jane@example.com"


class TestEventDispatching:
    def test_dispatches_itn_received(self, client, base_itn_payload):
        received = []
        client.add_listener(PayfastItnReceived, lambda e: received.append(e))
        client.handle_itn(base_itn_payload)
        assert len(received) == 1

    def test_dispatches_payment_event(self, client, base_itn_payload):
        events = []
        client.add_listener(PayfastPaymentEvent, lambda e: events.append(e))
        client.handle_itn(base_itn_payload)
        assert len(events) == 1
        assert isinstance(events[0], PayfastPaymentEvent)

    def test_dispatches_payment_complete(self, client, base_itn_payload):
        complete_events = []
        client.add_listener(PayfastPaymentComplete, lambda e: complete_events.append(e))
        client.handle_itn(base_itn_payload)
        assert len(complete_events) == 1

    def test_dispatches_payment_failed_not_complete(self, client, service, base_itn_payload):
        base_itn_payload["payment_status"] = "FAILED"
        del base_itn_payload["signature"]
        base_itn_payload["signature"] = service.generate_signature(base_itn_payload, "testpassphrase")

        complete_events = []
        failed_events   = []
        client.add_listener(PayfastPaymentComplete, lambda e: complete_events.append(e))
        client.add_listener(PayfastPaymentFailed,   lambda e: failed_events.append(e))

        client.handle_itn(base_itn_payload)

        assert len(complete_events) == 0
        assert len(failed_events)   == 1

    def test_dispatches_subscription_created(self, client, subscription_itn_payload):
        created = []
        client.add_listener(PayfastSubscriptionCreated, lambda e: created.append(e))
        client.handle_itn(subscription_itn_payload)
        assert len(created) == 1
        assert created[0].subscription.token == "tok_abc123"

    def test_listener_decorator_registers_correctly(self, client, base_itn_payload):
        events = []

        @client.on(PayfastPaymentEvent)
        def handle(event: PayfastPaymentEvent) -> None:
            events.append(event)

        client.handle_itn(base_itn_payload)
        assert len(events) == 1

    def test_multiple_listeners_all_called(self, client, base_itn_payload):
        calls = []
        client.add_listener(PayfastPaymentEvent, lambda e: calls.append("listener_1"))
        client.add_listener(PayfastPaymentEvent, lambda e: calls.append("listener_2"))
        client.handle_itn(base_itn_payload)
        assert "listener_1" in calls
        assert "listener_2" in calls

    def test_failing_listener_does_not_raise(self, client, base_itn_payload):
        def bad_listener(event):
            raise RuntimeError("Boom")

        client.add_listener(PayfastPaymentEvent, bad_listener)
        # Should not raise — bad listeners are caught and logged
        event = client.handle_itn(base_itn_payload)
        assert event.is_complete()


class TestClientHelpers:
    def test_build_payment_url_returns_string(self, client):
        url = client.build_payment_url(amount="100.00", item_name="Test")
        assert isinstance(url, str)
        assert "sandbox.payfast.co.za" in url

    def test_generate_payment_data_returns_dict_with_signature(self, client):
        data = client.generate_payment_data(amount="100.00", item_name="Test")
        assert "signature" in data
        assert data["merchant_id"] == "10000100"

    def test_generate_signature(self, client):
        sig = client.generate_signature({"amount": "100.00"})
        assert len(sig) == 32

    def test_build_subscription_url(self, client):
        url = client.build_subscription_url(amount=299.00, item_name="Pro Plan")
        assert "subscription_type=1" in url
        assert "frequency=3" in url
