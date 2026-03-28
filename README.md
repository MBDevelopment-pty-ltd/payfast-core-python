# PayFast Core — Python

[![Tests](https://github.com/mb-development/payfast-core-python/actions/workflows/tests.yml/badge.svg)](https://github.com/mb-development/payfast-core-python/actions)
[![PyPI version](https://img.shields.io/pypi/v/payfast-core.svg)](https://pypi.org/project/payfast-core/)
[![Python versions](https://img.shields.io/pypi/pyversions/payfast-core.svg)](https://pypi.org/project/payfast-core/)
[![License](https://img.shields.io/pypi/l/payfast-core.svg)](LICENSE)

A Python SDK for the [PayFast](https://www.payfast.co.za) payment gateway. Handles once-off payments, recurring subscriptions, ITN (Instant Transaction Notification) validation, transaction modelling, and webhook verification — framework-agnostic, with first-class support for **Django** and **Flask**.

Developed and maintained by **[MB Development Pty Ltd](https://mbdevelopment.co.za)**.

---

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Once-Off Payments](#once-off-payments)
- [Handling ITN Callbacks](#handling-itn-callbacks)
- [The PayfastPaymentEvent](#the-payfastpaymentevent)
- [Transaction Model](#transaction-model)
- [Recurring Subscriptions](#recurring-subscriptions)
- [Webhook Middleware](#webhook-middleware)
- [Django Integration](#django-integration)
- [Flask Integration](#flask-integration)
- [Client API Reference](#client-api-reference)
- [Events Reference](#events-reference)
- [Testing](#testing)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

---

## Requirements

| Requirement | Version |
|---|---|
| Python | `3.10`, `3.11`, `3.12` |
| requests | `>=2.28` |
| pydantic | `>=2.0` |

---

## Installation

```bash
pip install payfast-core
```

With Django extras:

```bash
pip install "payfast-core[django]"
```

With Flask extras:

```bash
pip install "payfast-core[flask]"
```

---

## Configuration

### Using a dataclass directly

```python
from payfast_core import PayfastConfig

config = PayfastConfig(
    merchant_id  = "10000100",
    merchant_key = "46f0cd694581a",
    passphrase   = "your_passphrase",   # omit if not set in PayFast account
    sandbox      = True,                # set False for live transactions
    return_url   = "https://yourapp.com/payment/return",
    cancel_url   = "https://yourapp.com/payment/cancel",
    notify_url   = "https://yourapp.com/payfast/notify",
    validate_ip  = True,                # recommended in production
)
```

### Loading from environment variables

```python
from payfast_core import PayfastConfig

config = PayfastConfig.from_env()
```

Expected environment variables:

```env
PAYFAST_MERCHANT_ID=10000100
PAYFAST_MERCHANT_KEY=46f0cd694581a
PAYFAST_PASSPHRASE=your_passphrase
PAYFAST_SANDBOX=true
PAYFAST_RETURN_URL=https://yourapp.com/payment/return
PAYFAST_CANCEL_URL=https://yourapp.com/payment/cancel
PAYFAST_NOTIFY_URL=https://yourapp.com/payfast/notify
PAYFAST_VALIDATE_IP=true
```

---

## Once-Off Payments

### Create the client

```python
from payfast_core import PayfastClient, PayfastConfig

config = PayfastConfig.from_env()
client = PayfastClient(config)
```

### Build a redirect URL (GET)

```python
url = client.build_payment_url(
    amount        = "349.99",
    item_name     = "Order #1042",
    custom_str1   = str(order.id),      # returned in the ITN
    name_first    = user.first_name,
    email_address = user.email,
)

# Django
return redirect(url)

# Flask
from flask import redirect as flask_redirect
return flask_redirect(url)
```

### Build a POST form payload

```python
payment_data = client.generate_payment_data(
    amount        = "349.99",
    item_name     = "Order #1042",
    custom_str1   = str(order.id),
)
endpoint = client.service.get_payment_endpoint()

# Pass payment_data and endpoint to your template
```

```html
<!-- your_checkout_template.html -->
<form action="{{ endpoint }}" method="POST">
  {% for key, value in payment_data.items() %}
    <input type="hidden" name="{{ key }}" value="{{ value }}">
  {% endfor %}
  <button type="submit">Pay R349.99</button>
</form>
```

### Generate a signature manually

```python
signature = client.generate_signature(data_dict, passphrase="optional")
```

---

## Handling ITN Callbacks

PayFast POSTs a notification to your `notify_url` after every payment. Call `client.handle_itn()` inside that endpoint — it validates the payload, builds the event objects, dispatches your listeners, and returns a `PayfastPaymentEvent`.

### Django view

```python
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from payfast_core import PayfastClient, PayfastConfig

config = PayfastConfig.from_env()
client = PayfastClient(config)

@csrf_exempt
def payfast_notify(request):
    payload    = request.POST.dict()
    remote_ip  = request.META.get("REMOTE_ADDR")
    event      = client.handle_itn(payload, remote_ip=remote_ip)
    return HttpResponse("OK", status=200)
```

### Flask view

```python
from flask import request, Flask
from payfast_core import PayfastClient, PayfastConfig

app    = Flask(__name__)
config = PayfastConfig.from_env()
client = PayfastClient(config)

@app.post("/payfast/notify")
def payfast_notify():
    payload   = request.form.to_dict()
    remote_ip = request.remote_addr
    event     = client.handle_itn(payload, remote_ip=remote_ip)
    return "OK", 200
```

---

## The PayfastPaymentEvent

`PayfastPaymentEvent` is the **single event you need to listen to** for any PayFast payment — once-off or subscription, successful or failed. Register listeners with the `@client.on()` decorator or `client.add_listener()`.

### Register a listener

```python
from payfast_core import PayfastPaymentEvent

@client.on(PayfastPaymentEvent)
def handle_payment(event: PayfastPaymentEvent) -> None:

    # Activate an order after a successful once-off payment
    if event.is_once_off() and event.is_complete():
        order_id = event.custom_str(1)   # value from custom_str1
        activate_order(order_id)

    # Grant access after a successful subscription billing
    if event.is_subscription() and event.is_complete():
        user_id = event.custom_str(1)
        grant_subscription_access(user_id)

    # Notify the customer on any failure
    if event.is_failed():
        send_payment_failed_email(
            to      = event.buyer_email(),
            amount  = event.amount_gross(),
            item    = event.item_name(),
        )
```

### PayfastPaymentEvent API reference

| Member | Type | Description |
|---|---|---|
| `.payment_type` | `PaymentType` | `PaymentType.ONCE_OFF` or `PaymentType.SUBSCRIPTION` |
| `.payment_status` | `PaymentStatus` | `COMPLETE`, `FAILED`, `PENDING`, or `CANCELLED` |
| `.transaction` | `PayfastTransaction` | The transaction built from the ITN payload (always present) |
| `.subscription` | `PayfastSubscription \| None` | Subscription record for subscription payments, else `None` |
| `.payload` | `dict` | The full raw ITN payload from PayFast |
| `.is_once_off()` | `bool` | `True` for standard once-off payments |
| `.is_subscription()` | `bool` | `True` for recurring subscription payments |
| `.is_complete()` | `bool` | `True` when PayFast confirmed success |
| `.is_failed()` | `bool` | `True` when the payment failed |
| `.is_pending()` | `bool` | `True` when the payment is still pending |
| `.is_cancelled()` | `bool` | `True` when the payment was cancelled |
| `.amount_gross()` | `float` | Gross amount before PayFast fees |
| `.amount_net()` | `float` | Net amount after PayFast fees |
| `.pf_payment_id()` | `str \| None` | PayFast's own payment reference |
| `.subscription_token()` | `str \| None` | Subscription token (subscriptions only) |
| `.custom_str(n)` | `str \| None` | Value of `custom_str1`, `custom_str2`, or `custom_str3` |
| `.custom_int(n)` | `int \| None` | Value of `custom_int1` or `custom_int2` |
| `.buyer_first_name()` | `str \| None` | Buyer's first name |
| `.buyer_last_name()` | `str \| None` | Buyer's last name |
| `.buyer_email()` | `str \| None` | Buyer's email address |
| `.item_name()` | `str \| None` | The `item_name` from the payment |
| `.summary()` | `str` | Human-readable log string e.g. `COMPLETE once_off — R349.99 — Order #1042` |

---

## Transaction Model

`PayfastTransaction` is built automatically from the ITN payload inside `handle_itn()` and attached to `PayfastPaymentEvent.transaction`. You can also build one manually:

```python
from payfast_core import PayfastTransaction

tx = PayfastTransaction.from_payload(itn_payload_dict)

tx.pf_payment_id    # str | None
tx.payment_status   # PaymentStatus enum
tx.amount_gross     # float
tx.amount_fee       # float | None
tx.amount_net       # float | None
tx.custom_str1      # str | None
tx.custom_int1      # int | None
tx.name_first       # str | None
tx.email_address    # str | None
tx.raw_payload      # dict — full original payload

tx.is_complete()    # bool
tx.is_failed()      # bool
tx.is_pending()     # bool
```

---

## Recurring Subscriptions

### Create a subscription payment

```python
from payfast_core.services import SubscriptionService
from payfast_core.models import SubscriptionFrequency

sub_service = client.subscription_service

payment_data = sub_service.generate_subscription_payment_data(
    amount      = 299.00,
    item_name   = "Pro Plan — Monthly",
    frequency   = SubscriptionFrequency.MONTHLY,
    cycles      = 0,               # 0 = indefinite
    custom_str1 = str(user.id),
)

endpoint = client.service.get_payment_endpoint()
# Render payment_data and endpoint in your checkout template
```

Or get a ready-made redirect URL directly:

```python
url = client.build_subscription_url(
    amount      = 299.00,
    item_name   = "Pro Plan",
    frequency   = SubscriptionFrequency.MONTHLY,
    custom_str1 = str(user.id),
)
return redirect(url)
```

### Trial subscriptions

```python
payment_data = sub_service.generate_trial_subscription_payment_data(
    amount       = 299.00,
    item_name    = "Pro Plan",
    trial_amount = 0.00,          # first billing is free
    custom_str1  = str(user.id),
)
```

### Frequency options

| Constant | Value | Billing interval |
|---|---|---|
| `SubscriptionFrequency.MONTHLY` | `3` | Every month |
| `SubscriptionFrequency.QUARTERLY` | `4` | Every 3 months |
| `SubscriptionFrequency.BIANNUALLY` | `5` | Every 6 months |
| `SubscriptionFrequency.ANNUALLY` | `6` | Every year |

### Managing subscriptions via the PayFast API

```python
sub_service = client.subscription_service

sub_service.fetch_subscription(token)        # dict — raw API response
sub_service.pause(token)                     # bool
sub_service.unpause(token)                   # bool
sub_service.cancel(token)                    # bool
sub_service.update_amount(token, 349.00)     # bool
```

### PayfastSubscription model

`PayfastSubscription` is an immutable dataclass. Mutations return a new instance, leaving the original unchanged:

```python
from payfast_core import PayfastSubscription

sub = PayfastSubscription.from_itn_payload(payload)

sub.token             # str
sub.status            # SubscriptionStatus enum
sub.amount            # float
sub.frequency         # SubscriptionFrequency enum
sub.cycles            # int — total cycles (0 = indefinite)
sub.cycles_complete   # int — completed so far
sub.custom_str1       # str | None

sub.is_active()       # bool
sub.is_paused()       # bool
sub.is_cancelled()    # bool
sub.on_trial()        # bool

sub.frequency_label() # "Monthly", "Quarterly", etc.

# State transitions (return new instances)
cancelled = sub.cancel()
paused    = sub.pause()
resumed   = paused.resume()
updated   = sub.increment_cycle()
```

### Listening to subscription events

```python
from payfast_core.events import (
    PayfastSubscriptionCreated,
    PayfastSubscriptionRenewed,
    PayfastSubscriptionCancelled,
)

@client.on(PayfastSubscriptionCreated)
def on_created(event: PayfastSubscriptionCreated) -> None:
    # event.subscription — the new PayfastSubscription
    # event.payload      — the raw ITN dict
    grant_access(event.subscription.custom_str1)

@client.on(PayfastSubscriptionRenewed)
def on_renewed(event: PayfastSubscriptionRenewed) -> None:
    # event.subscription — updated PayfastSubscription
    # event.transaction  — the PayfastTransaction for this cycle
    extend_access(event.subscription.custom_str1)
```

---

## Webhook Middleware

### Framework-agnostic helper

```python
from payfast_core.middleware import verify_itn_payload
from payfast_core.exceptions import InvalidSignatureException, InvalidSourceIPException

try:
    verify_itn_payload(payload_dict, config, remote_ip="41.74.179.194")
except InvalidSignatureException:
    return "Bad signature", 400
except InvalidSourceIPException:
    return "Forbidden", 403
```

---

## Django Integration

### Option 1 — Middleware (global)

Add to `MIDDLEWARE` in `settings.py`:

```python
MIDDLEWARE = [
    ...
    "payfast_core.middleware.DjangoPayfastWebhookMiddleware",
]

# Also required in settings.py:
from payfast_core import PayfastConfig
PAYFAST_CONFIG      = PayfastConfig.from_env()
PAYFAST_NOTIFY_PATH = "/payfast/notify"   # default, change if needed
```

### Option 2 — View decorator

```python
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from payfast_core.middleware import django_verify_payfast_webhook

@csrf_exempt
@django_verify_payfast_webhook(settings.PAYFAST_CONFIG)
def payfast_notify(request):
    event = client.handle_itn(request.POST.dict(), remote_ip=request.META.get("REMOTE_ADDR"))
    return HttpResponse("OK")
```

### Exclude from CSRF

Since PayFast posts from its own servers, exclude the notify URL from Django's CSRF middleware:

```python
# app/middleware.py  (or use django-cors-headers)
class ExemptPayfastCsrf:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        if request.path == "/payfast/notify":
            request._dont_enforce_csrf_checks = True
        return self.get_response(request)
```

---

## Flask Integration

```python
from flask import request, Flask
from payfast_core import PayfastClient, PayfastConfig
from payfast_core.middleware import flask_verify_payfast_webhook

app    = Flask(__name__)
config = PayfastConfig.from_env()
client = PayfastClient(config)

@app.post("/payfast/notify")
@flask_verify_payfast_webhook(config)
def payfast_notify():
    # Signature already verified by the decorator
    event = client.handle_itn(
        request.form.to_dict(),
        remote_ip=request.remote_addr,
    )
    return "OK", 200
```

---

## Client API Reference

```python
# PayfastClient
client.build_payment_url(**params) -> str
client.generate_payment_data(**params) -> dict
client.generate_signature(data, passphrase=None) -> str
client.build_subscription_url(amount, item_name, **kwargs) -> str
client.generate_subscription_payment_data(amount, item_name, **kwargs) -> dict
client.handle_itn(payload, remote_ip=None) -> PayfastPaymentEvent

# Register event listeners
client.on(EventClass)           # decorator
client.add_listener(EventClass, fn)
client.remove_listener(EventClass, fn)

# Direct service access
client.service               # PayfastService
client.subscription_service  # SubscriptionService
```

---

## Events Reference

| Event | Fired when | Key attributes |
|---|---|---|
| `PayfastItnReceived` | Every valid ITN, before processing | `.payload` |
| `PayfastPaymentEvent` | Every valid ITN, after transaction is built | `.transaction`, `.subscription`, type/status helpers |
| `PayfastPaymentComplete` | ITN with `payment_status = COMPLETE` | `.payload` |
| `PayfastPaymentFailed` | ITN with any other status | `.payload` |
| `PayfastSubscriptionCreated` | First billing for a new subscription token | `.subscription`, `.payload` |
| `PayfastSubscriptionRenewed` | Recurring billing cycle completes | `.subscription`, `.transaction`, `.payload` |
| `PayfastSubscriptionCancelled` | `cancel()` called on a subscription | `.subscription`, `.payload` |

> **Recommendation:** Use `PayfastPaymentEvent` for all core logic. The granular events are available for targeted integrations.

---

## Testing

Install dev dependencies:

```bash
pip install -e ".[dev]"
```

Run the full test suite:

```bash
pytest
```

With coverage:

```bash
pytest --cov=payfast_core --cov-report=term-missing
```

Lint and type check:

```bash
ruff check payfast_core/
mypy payfast_core/
```

---

## Contributing

Contributions, issues, and feature requests are welcome.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request against `main`

Please ensure all tests pass and the code passes `ruff` and `mypy` checks before submitting.

---

## Security

If you discover a security vulnerability, please **do not** open a public issue. Email us at [dev@mbdevelopment.co.za](mailto:dev@mbdevelopment.co.za) and we will address it promptly.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">Built with ❤️ by <a href="https://mbdevelopment.co.za">MB Development Pty Ltd</a></p>
