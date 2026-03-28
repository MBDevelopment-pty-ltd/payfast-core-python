"""Unit tests for PayfastService — signature, payment data, ITN validation."""

import pytest

from payfast_core.exceptions import InvalidSignatureException, InvalidSourceIPException
from payfast_core.services import PayfastService
from payfast_core.config import PayfastConfig


class TestGenerateSignature:
    def test_returns_32_char_md5(self, service):
        sig = service.generate_signature({"merchant_id": "10000100", "amount": "100.00"})
        assert len(sig) == 32

    def test_excludes_empty_values(self, service):
        with_empty    = service.generate_signature({"merchant_id": "10000100", "item_name": ""})
        without_empty = service.generate_signature({"merchant_id": "10000100"})
        assert with_empty == without_empty

    def test_strips_signature_key_before_hashing(self, service):
        dirty  = service.generate_signature({"merchant_id": "10000100", "signature": "old"})
        clean  = service.generate_signature({"merchant_id": "10000100"})
        assert dirty == clean

    def test_appends_passphrase_when_provided(self, service):
        with_pp    = service.generate_signature({"amount": "100.00"}, passphrase="secret")
        without_pp = service.generate_signature({"amount": "100.00"})
        assert with_pp != without_pp

    def test_empty_passphrase_treated_as_none(self, service):
        sig_none  = service.generate_signature({"amount": "100.00"}, passphrase=None)
        sig_empty = service.generate_signature({"amount": "100.00"}, passphrase="")
        assert sig_none == sig_empty


class TestGeneratePaymentData:
    def test_injects_merchant_credentials(self, service, config):
        data = service.generate_payment_data({"amount": "100.00", "item_name": "Test"})
        assert data["merchant_id"]  == config.merchant_id
        assert data["merchant_key"] == config.merchant_key

    def test_injects_redirect_urls(self, service, config):
        data = service.generate_payment_data({"amount": "100.00", "item_name": "Test"})
        assert data["return_url"] == config.return_url
        assert data["cancel_url"] == config.cancel_url
        assert data["notify_url"] == config.notify_url

    def test_includes_signature(self, service):
        data = service.generate_payment_data({"amount": "100.00", "item_name": "Test"})
        assert "signature" in data
        assert len(data["signature"]) == 32


class TestBuildPaymentUrl:
    def test_points_to_sandbox_when_sandbox_true(self, service):
        url = service.build_payment_url({"amount": "99.99", "item_name": "Item"})
        assert url.startswith("https://sandbox.payfast.co.za")

    def test_points_to_live_when_sandbox_false(self, config):
        live_service = PayfastService(PayfastConfig(
            merchant_id="10000100", merchant_key="key", sandbox=False
        ))
        url = live_service.build_payment_url({"amount": "99.99", "item_name": "Item"})
        assert url.startswith("https://www.payfast.co.za")

    def test_url_contains_amount_and_signature(self, service):
        url = service.build_payment_url({"amount": "99.99", "item_name": "Item"})
        assert "amount=99.99" in url
        assert "signature=" in url


class TestValidateItn:
    def test_accepts_valid_payload(self, service, base_itn_payload):
        assert service.validate_itn(base_itn_payload) is True

    def test_raises_on_invalid_signature(self, service, base_itn_payload):
        base_itn_payload["signature"] = "badsignature"
        with pytest.raises(InvalidSignatureException):
            service.validate_itn(base_itn_payload)

    def test_raises_on_missing_signature(self, service, base_itn_payload):
        del base_itn_payload["signature"]
        with pytest.raises(InvalidSignatureException):
            service.validate_itn(base_itn_payload)

    def test_raises_on_tampered_payload(self, service, base_itn_payload):
        base_itn_payload["amount_gross"] = "1.00"  # tamper after signing
        with pytest.raises(InvalidSignatureException):
            service.validate_itn(base_itn_payload)

    def test_raises_on_invalid_ip_when_validate_ip_enabled(self, base_itn_payload):
        strict_config = PayfastConfig(
            merchant_id="10000100", merchant_key="46f0cd694581a",
            passphrase="testpassphrase", validate_ip=True
        )
        strict_service = PayfastService(strict_config)
        # Regenerate signature with this config
        del base_itn_payload["signature"]
        base_itn_payload["signature"] = strict_service.generate_signature(
            base_itn_payload, "testpassphrase"
        )
        with pytest.raises(InvalidSourceIPException):
            strict_service.validate_itn(base_itn_payload, remote_ip="1.2.3.4")

    def test_accepts_valid_payfast_ip_when_validate_ip_enabled(self, base_itn_payload):
        strict_config = PayfastConfig(
            merchant_id="10000100", merchant_key="46f0cd694581a",
            passphrase="testpassphrase", validate_ip=True
        )
        strict_service = PayfastService(strict_config)
        del base_itn_payload["signature"]
        base_itn_payload["signature"] = strict_service.generate_signature(
            base_itn_payload, "testpassphrase"
        )
        assert strict_service.validate_itn(base_itn_payload, remote_ip="197.97.145.144") is True
