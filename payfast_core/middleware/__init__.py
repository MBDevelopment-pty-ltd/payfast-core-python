"""
payfast_core.middleware
-----------------------
Framework-specific middleware for verifying PayFast webhook signatures.

Django
------
Add ``PayfastWebhookMiddleware`` to ``MIDDLEWARE`` in your ``settings.py``,
or use ``verify_payfast_webhook`` as a view decorator.

Flask
-----
Use the ``payfast_webhook`` decorator on your notify endpoint.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Callable

from payfast_core.config import PayfastConfig, VALID_PAYFAST_IPS
from payfast_core.exceptions import InvalidSignatureException, InvalidSourceIPException
from payfast_core.services import PayfastService

logger = logging.getLogger("payfast_core")


def _verify(payload: dict, remote_ip: str | None, config: PayfastConfig) -> None:
    """
    Core verification logic shared by all framework integrations.

    Raises
    ------
    InvalidSignatureException
        If the signature does not match.
    InvalidSourceIPException
        If the source IP is not in the PayFast allow-list and
        ``config.validate_ip`` is ``True``.
    """
    service = PayfastService(config)
    service.validate_itn(payload, remote_ip=remote_ip)


# ---------------------------------------------------------------------------
# Django integration
# ---------------------------------------------------------------------------

class DjangoPayfastWebhookMiddleware:
    """
    Django middleware that verifies PayFast ITN signatures on a configurable path.

    Only requests to ``notify_path`` (default ``/payfast/notify``) are verified.
    All other requests pass through untouched.

    Settings
    --------
    Add to ``MIDDLEWARE`` in ``settings.py``::

        MIDDLEWARE = [
            ...
            "payfast_core.middleware.DjangoPayfastWebhookMiddleware",
        ]

    And configure PayFast in your Django settings::

        PAYFAST_CONFIG = PayfastConfig(
            merchant_id="10000100",
            merchant_key="46f0cd694581a",
            passphrase="secret",
        )
        PAYFAST_NOTIFY_PATH = "/payfast/notify"  # optional, this is the default

    Example view
    ------------
    ::

        from django.http import HttpResponse
        from django.views.decorators.csrf import csrf_exempt
        from payfast_core import PayfastClient

        client = PayfastClient(settings.PAYFAST_CONFIG)

        @csrf_exempt
        def payfast_notify(request):
            payload = request.POST.dict()
            event   = client.handle_itn(payload, remote_ip=request.META.get("REMOTE_ADDR"))
            return HttpResponse("OK")
    """

    def __init__(self, get_response: Callable) -> None:
        from django.conf import settings

        self.get_response  = get_response
        self.config        = getattr(settings, "PAYFAST_CONFIG", None)
        self.notify_path   = getattr(settings, "PAYFAST_NOTIFY_PATH", "/payfast/notify")

    def __call__(self, request):
        if request.path == self.notify_path and self.config:
            try:
                payload    = request.POST.dict()
                remote_ip  = request.META.get("REMOTE_ADDR")
                _verify(payload, remote_ip, self.config)
            except (InvalidSignatureException, InvalidSourceIPException) as exc:
                from django.http import HttpResponse
                logger.warning("PayFast webhook rejected: %s", exc)
                return HttpResponse("Forbidden", status=403)

        return self.get_response(request)


def django_verify_payfast_webhook(config: PayfastConfig) -> Callable:
    """
    Django view decorator that rejects requests with invalid PayFast signatures.

    Parameters
    ----------
    config:
        A :class:`~payfast_core.config.PayfastConfig` instance.

    Usage
    -----
    ::

        from django.views.decorators.csrf import csrf_exempt
        from payfast_core.middleware import django_verify_payfast_webhook

        @csrf_exempt
        @django_verify_payfast_webhook(settings.PAYFAST_CONFIG)
        def payfast_notify(request):
            ...
    """
    def decorator(view_fn: Callable) -> Callable:
        @wraps(view_fn)
        def inner(request, *args, **kwargs):
            try:
                payload   = request.POST.dict()
                remote_ip = request.META.get("REMOTE_ADDR")
                _verify(payload, remote_ip, config)
            except (InvalidSignatureException, InvalidSourceIPException) as exc:
                from django.http import HttpResponse
                logger.warning("PayFast webhook rejected: %s", exc)
                return HttpResponse("Invalid PayFast signature", status=400)
            return view_fn(request, *args, **kwargs)
        return inner
    return decorator


# ---------------------------------------------------------------------------
# Flask integration
# ---------------------------------------------------------------------------

def flask_verify_payfast_webhook(config: PayfastConfig) -> Callable:
    """
    Flask route decorator that rejects requests with invalid PayFast signatures.

    Parameters
    ----------
    config:
        A :class:`~payfast_core.config.PayfastConfig` instance.

    Usage
    -----
    ::

        from flask import request, Flask
        from payfast_core.middleware import flask_verify_payfast_webhook

        app    = Flask(__name__)
        config = PayfastConfig.from_env()

        @app.post("/payfast/notify")
        @flask_verify_payfast_webhook(config)
        def payfast_notify():
            payload = request.form.to_dict()
            event   = client.handle_itn(payload, remote_ip=request.remote_addr)
            return "OK", 200
    """
    def decorator(view_fn: Callable) -> Callable:
        @wraps(view_fn)
        def inner(*args, **kwargs):
            from flask import request, abort
            try:
                payload   = request.form.to_dict()
                remote_ip = request.remote_addr
                _verify(payload, remote_ip, config)
            except InvalidSignatureException as exc:
                logger.warning("PayFast webhook signature invalid: %s", exc)
                abort(400, description="Invalid PayFast signature.")
            except InvalidSourceIPException as exc:
                logger.warning("PayFast webhook IP rejected: %s", exc)
                abort(403, description="Request not from PayFast.")
            return view_fn(*args, **kwargs)
        return inner
    return decorator


# ---------------------------------------------------------------------------
# Framework-agnostic helper
# ---------------------------------------------------------------------------

def verify_itn_payload(payload: dict, config: PayfastConfig, remote_ip: str | None = None) -> bool:
    """
    Verify a PayFast ITN payload without any framework dependency.

    Parameters
    ----------
    payload:
        The full POST body as a flat dict.
    config:
        A :class:`~payfast_core.config.PayfastConfig` instance.
    remote_ip:
        The remote IP of the request (required when ``config.validate_ip`` is ``True``).

    Returns
    -------
    bool
        ``True`` if the payload is valid.

    Raises
    ------
    InvalidSignatureException
        If the signature does not match.
    InvalidSourceIPException
        If the source IP is not allowed.
    """
    _verify(payload, remote_ip, config)
    return True
