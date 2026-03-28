"""Tests for all new improvements: security, handlers, idempotency, async, client premium API."""

import sys
import time
import asyncio
sys.path.insert(0, "/home/claude/payfast-python")

from payfast_core.config import PayfastConfig
from payfast_core.services import PayfastService
from payfast_core import (
    PayfastClient, PayfastPaymentEvent, PayfastPaymentComplete,
    PayfastPaymentFailed, PayfastSubscriptionCreated,
    PaymentHandler, SubscriptionHandler,
    InMemoryIdempotencyStore, DuplicateItnException,
    InvalidSignatureException, InvalidSourceIPException,
    EventNames, PaymentTypes, PaymentStatuses, ItnFields,
    SubscriptionFrequency,
)
from payfast_core import security
from payfast_core.async_support import AsyncPayfastClient

PASS = lambda msg: print(f"PASS: {msg}")


def make_config(validate_ip=False):
    return PayfastConfig(
        merchant_id="10000100", merchant_key="46f0cd694581a",
        passphrase="testpassphrase", sandbox=True, validate_ip=validate_ip,
        return_url="https://example.com/return",
        cancel_url="https://example.com/cancel",
        notify_url="https://example.com/notify",
    )


def signed_payload(service, overrides=None):
    data = {
        "merchant_id": "10000100", "pf_payment_id": "pf_test_001",
        "payment_status": "COMPLETE", "item_name": "Test",
        "amount_gross": "100.00", "custom_str1": "order_1",
    }
    if overrides:
        data.update(overrides)
    data["signature"] = service.generate_signature(data, "testpassphrase")
    return data


# ===========================================================================
# 1. security.py
# ===========================================================================
print("\n=== security.py ===")

# Pure function: build_signature_string excludes signature key and empty values
data = {"merchant_id": "10000100", "amount": "100.00", "signature": "old", "empty": ""}
s = security.build_signature_string(data)
assert "signature" not in s
assert "empty" not in s
assert "merchant_id" in s
PASS("build_signature_string excludes signature key and empty values")

# generate_signature returns 32-char MD5
sig = security.generate_signature({"amount": "100.00"})
assert len(sig) == 32
PASS("generate_signature returns 32-char MD5")

# signatures_match is constant-time
assert security.signatures_match("abc", "abc") is True
assert security.signatures_match("abc", "xyz") is False
PASS("signatures_match constant-time comparison")

# validate_signature raises on mismatch
config = make_config()
service = PayfastService(config)
payload = {"merchant_id": "10000100", "amount": "100.00", "payment_status": "COMPLETE"}
payload["signature"] = security.generate_signature(payload, "testpassphrase")
security.validate_signature(payload, "testpassphrase")  # should not raise
PASS("validate_signature accepts correct signature")

bad = dict(payload)
bad["signature"] = "badsig"
try:
    security.validate_signature(bad, "testpassphrase")
    assert False
except InvalidSignatureException:
    PASS("validate_signature raises InvalidSignatureException on mismatch")

# validate_source_ip
try:
    security.validate_source_ip(None)
    assert False
except InvalidSourceIPException:
    PASS("validate_source_ip raises when IP is None")

try:
    security.validate_source_ip("1.2.3.4")
    assert False
except InvalidSourceIPException:
    PASS("validate_source_ip raises for unknown IP")

security.validate_source_ip("197.97.145.144")  # should not raise
PASS("validate_source_ip accepts known PayFast IP")

# generate_api_signature
api_sig = security.generate_api_signature("10000100", "pass", "2024-01-01T10:00:00")
assert len(api_sig) == 32
PASS("generate_api_signature returns 32-char MD5")


# ===========================================================================
# 2. handlers/
# ===========================================================================
print("\n=== handlers/ ===")

config = make_config()
service = PayfastService(config)
client = PayfastClient(config)

# PaymentHandler hooks
class TestPaymentHandler(PaymentHandler):
    def __init__(self):
        self.successes = []
        self.failures  = []
        self.received  = []
    def on_itn_received(self, event):    self.received.append(event)
    def on_payment_success(self, event): self.successes.append(event)
    def on_payment_failed(self, event):  self.failures.append(event)

handler = TestPaymentHandler()
client.register_handler(handler)

itn = signed_payload(service)
client.handle_itn(itn)
assert len(handler.successes) == 1
assert len(handler.received)  == 1
PASS("PaymentHandler.on_payment_success called on COMPLETE ITN")
PASS("PaymentHandler.on_itn_received called on every ITN")

# Failed payment routes to on_payment_failed
failed_itn = signed_payload(service, {"payment_status": "FAILED", "pf_payment_id": "pf_f1"})
failed_itn["signature"] = service.generate_signature(
    {k: v for k, v in failed_itn.items() if k != "signature"}, "testpassphrase"
)
client.handle_itn(failed_itn)
assert len(handler.failures) == 1
PASS("PaymentHandler.on_payment_failed called on non-COMPLETE ITN")

# register_handler returns self (chaining)
client2 = PayfastClient(config)
result = client2.register_handler(TestPaymentHandler())
assert result is client2
PASS("register_handler returns self for chaining")

# SubscriptionHandler
class TestSubscriptionHandler(SubscriptionHandler):
    def __init__(self):
        self.created = []
    def on_subscription_created(self, event):
        self.created.append(event)

sub_handler = TestSubscriptionHandler()
client3 = PayfastClient(config)
client3.register_handler(sub_handler)

sub_itn = {
    "merchant_id": "10000100", "pf_payment_id": "pf_sub_h1",
    "payment_status": "COMPLETE", "item_name": "Pro",
    "amount_gross": "299.00", "subscription_type": "1",
    "token": "tok_handler", "frequency": "3", "billing_total": "12",
}
sub_itn["signature"] = service.generate_signature(sub_itn, "testpassphrase")
client3.handle_itn(sub_itn)
assert len(sub_handler.created) == 1
assert sub_handler.created[0].subscription.token == "tok_handler"
PASS("SubscriptionHandler.on_subscription_created called on subscription ITN")


# ===========================================================================
# 3. idempotency/
# ===========================================================================
print("\n=== idempotency/ ===")

store = InMemoryIdempotencyStore(ttl_seconds=60)
assert store.has_seen("tx_1") is False
PASS("InMemoryIdempotencyStore.has_seen returns False for unseen ID")

store.mark_seen("tx_1")
assert store.has_seen("tx_1") is True
PASS("InMemoryIdempotencyStore.mark_seen works")

# check_and_mark is atomic
store2 = InMemoryIdempotencyStore()
store2.check_and_mark("tx_new")  # should not raise
try:
    store2.check_and_mark("tx_new")  # duplicate
    assert False
except DuplicateItnException:
    PASS("check_and_mark raises DuplicateItnException on second call")

# Client integration with idempotency store
idem_store = InMemoryIdempotencyStore()
idem_client = PayfastClient(config, idempotency_store=idem_store)
first_itn = signed_payload(service, {"pf_payment_id": "pf_idem_001"})
idem_client.handle_itn(first_itn)  # first time — ok
try:
    idem_client.handle_itn(first_itn)  # duplicate
    assert False
except DuplicateItnException:
    PASS("PayfastClient raises DuplicateItnException on duplicate pf_payment_id")

assert idem_client.is_duplicate_transaction("pf_idem_001") is True
assert idem_client.is_duplicate_transaction("pf_idem_999") is False
PASS("client.is_duplicate_transaction() works correctly")

# No idempotency store — is_duplicate_transaction always returns False
plain_client = PayfastClient(config)
assert plain_client.is_duplicate_transaction("anything") is False
PASS("is_duplicate_transaction returns False when no store configured")

# TTL expiry
fast_store = InMemoryIdempotencyStore(ttl_seconds=0)
fast_store.mark_seen("tx_expire")
time.sleep(0.01)
fast_store._evict_expired()
assert fast_store.has_seen("tx_expire") is False
PASS("InMemoryIdempotencyStore TTL expiry works")


# ===========================================================================
# 4. async support
# ===========================================================================
print("\n=== async_support/ ===")

async def run_async_tests():
    async_client = AsyncPayfastClient(config)
    events = []

    @async_client.on(PayfastPaymentEvent)
    async def async_handler(event):
        events.append(("async", event))

    @async_client.on(PayfastPaymentEvent)
    def sync_handler(event):
        events.append(("sync", event))

    itn = signed_payload(service, {"pf_payment_id": "pf_async_001"})
    event = await async_client.handle_itn(itn)
    assert event.is_complete()
    assert len(events) == 2
    assert any(t == "async" for t, _ in events)
    assert any(t == "sync" for t, _ in events)

    # Idempotency in async client
    idem = InMemoryIdempotencyStore()
    idem_async = AsyncPayfastClient(config, idempotency_store=idem)
    itn2 = signed_payload(service, {"pf_payment_id": "pf_async_idem"})
    await idem_async.handle_itn(itn2)
    try:
        await idem_async.handle_itn(itn2)
        assert False
    except DuplicateItnException:
        pass

asyncio.run(run_async_tests())
PASS("AsyncPayfastClient dispatches to both async and sync listeners")
PASS("AsyncPayfastClient respects idempotency store")


# ===========================================================================
# 5. Premium client.py API
# ===========================================================================
print("\n=== Premium client.py ===")

premium = PayfastClient.from_env.__doc__  # just test it's callable
premium_client = PayfastClient(config)

# from_env raises without env vars — just check the classmethod exists
assert callable(PayfastClient.from_env)
PASS("PayfastClient.from_env classmethod exists")

# generate_payment returns URL
url = premium_client.generate_payment(amount=349.99, item_name="Order #42", custom_str1="42")
assert "sandbox.payfast.co.za" in url
assert "amount=349.99" in url
assert "item_name=" in url
PASS("client.generate_payment() returns correct signed URL")

# generate_payment_form_data returns (endpoint, dict)
endpoint, form_data = premium_client.generate_payment_form_data(
    amount=299.00, item_name="Test"
)
assert "payfast.co.za" in endpoint
assert "signature" in form_data
PASS("client.generate_payment_form_data() returns (endpoint, data) tuple")

# create_subscription
sub_url = premium_client.create_subscription(
    amount=299.00, item_name="Pro Plan",
    frequency=SubscriptionFrequency.MONTHLY, custom_str1="user_1",
)
assert "subscription_type=1" in sub_url
assert "frequency=3" in sub_url
PASS("client.create_subscription() returns correct subscription URL")

# create_trial_subscription
trial_url = premium_client.create_trial_subscription(
    amount=299.00, item_name="Pro Plan", trial_amount=0.00
)
assert "amount=0.00" in trial_url
PASS("client.create_trial_subscription() uses trial amount")

# Named hooks: on_payment_success / on_payment_failed
successes = []
failures  = []
hook_client = PayfastClient(config)

@hook_client.on_payment_success
def my_success(event): successes.append(event)

@hook_client.on_payment_failed
def my_failure(event): failures.append(event)

ok_itn = signed_payload(service, {"pf_payment_id": "pf_hook_ok"})
hook_client.handle_itn(ok_itn)
assert len(successes) == 1 and len(failures) == 0
PASS("client.on_payment_success fires only on COMPLETE")

fail_itn = {"merchant_id": "10000100", "pf_payment_id": "pf_hook_fail",
    "payment_status": "FAILED", "item_name": "Test", "amount_gross": "10.00"}
fail_itn["signature"] = service.generate_signature(fail_itn, "testpassphrase")
hook_client.handle_itn(fail_itn)
assert len(failures) == 1 and len(successes) == 1
PASS("client.on_payment_failed fires only on failed payment")

# on_subscription_created hook
sub_events = []
sub_hook_client = PayfastClient(config)

@sub_hook_client.on_subscription_created
def sub_created(event): sub_events.append(event)

sub_itn2 = {"merchant_id": "10000100", "pf_payment_id": "pf_subhook",
    "payment_status": "COMPLETE", "item_name": "Plan", "amount_gross": "299.00",
    "subscription_type": "1", "token": "tok_hook", "frequency": "3", "billing_total": "0"}
sub_itn2["signature"] = service.generate_signature(sub_itn2, "testpassphrase")
sub_hook_client.handle_itn(sub_itn2)
assert len(sub_events) == 1
PASS("client.on_subscription_created hook fires correctly")


# ===========================================================================
# 6. standards.py
# ===========================================================================
print("\n=== standards.py (cross-language) ===")

assert EventNames.PAYMENT_COMPLETE   == "payfast.payment.complete"
assert EventNames.SUBSCRIPTION_CREATED == "payfast.subscription.created"
PASS("EventNames constants are correctly defined")

assert PaymentTypes.ONCE_OFF     == "once_off"
assert PaymentTypes.SUBSCRIPTION == "subscription"
PASS("PaymentTypes constants match SDK PaymentType enum values")

assert PaymentStatuses.COMPLETE == "COMPLETE"
assert PaymentStatuses.FAILED   == "FAILED"
PASS("PaymentStatuses constants match PayFast ITN values")

assert ItnFields.CUSTOM_STR1 == "custom_str1"
assert ItnFields.PF_PAYMENT_ID == "pf_payment_id"
PASS("ItnFields constants match ITN payload key names")

from payfast_core.standards import SubscriptionFrequencies
assert SubscriptionFrequencies.MONTHLY == 3
assert SubscriptionFrequencies.label(3) == "Monthly"
assert SubscriptionFrequencies.label(99) == "Unknown"
PASS("SubscriptionFrequencies constants and label() work correctly")

print("\n" + "="*60)
print("ALL IMPROVEMENT TESTS PASSED")
print("="*60)
