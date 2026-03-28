"""Feature tests for the verify_itn_payload middleware helper."""

import pytest

from payfast_core.middleware import verify_itn_payload
from payfast_core.config import PayfastConfig
from payfast_core.exceptions import InvalidSignatureException, InvalidSourceIPException
from payfast_core.services import PayfastService


@pytest.fixture
def strict_config():
    return PayfastConfig(
        merchant_id  = "10000100",
        merchant_key = "46f0cd694581a",
        passphrase   = "testpassphrase",
        sandbox      = True,
        validate_ip  = True,
    )


@pytest.fixture
def signed_payload(config):
    service = PayfastService(config)
    data = {
        "merchant_id":    "10000100",
        "payment_status": "COMPLETE",
        "item_name":      "Widget",
        "amount_gross":   "50.00",
    }
    data["signature"] = service.generate_signature(data, "testpassphrase")
    return data


class TestVerifyItnPayload:
    def test_returns_true_for_valid_payload(self, config, signed_payload):
        assert verify_itn_payload(signed_payload, config) is True

    def test_raises_on_bad_signature(self, config, signed_payload):
        signed_payload["signature"] = "tampered"
        with pytest.raises(InvalidSignatureException):
            verify_itn_payload(signed_payload, config)

    def test_raises_on_invalid_ip_when_validate_ip_enabled(self, strict_config, signed_payload):
        # Re-sign with strict config (same passphrase)
        service = PayfastService(strict_config)
        del signed_payload["signature"]
        signed_payload["signature"] = service.generate_signature(signed_payload, "testpassphrase")

        with pytest.raises(InvalidSourceIPException):
            verify_itn_payload(signed_payload, strict_config, remote_ip="9.9.9.9")

    def test_accepts_known_payfast_ip(self, strict_config, signed_payload):
        service = PayfastService(strict_config)
        del signed_payload["signature"]
        signed_payload["signature"] = service.generate_signature(signed_payload, "testpassphrase")

        result = verify_itn_payload(
            signed_payload, strict_config, remote_ip="197.97.145.144"
        )
        assert result is True

    def test_raises_when_ip_required_but_not_provided(self, strict_config, signed_payload):
        service = PayfastService(strict_config)
        del signed_payload["signature"]
        signed_payload["signature"] = service.generate_signature(signed_payload, "testpassphrase")

        with pytest.raises(InvalidSourceIPException):
            verify_itn_payload(signed_payload, strict_config, remote_ip=None)
