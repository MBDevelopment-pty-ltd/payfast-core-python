"""Unit tests for PayfastConfig."""

import os
import pytest

from payfast_core.config import PayfastConfig


class TestPayfastConfig:
    def test_defaults(self):
        cfg = PayfastConfig(merchant_id="id", merchant_key="key")
        assert cfg.sandbox     is True
        assert cfg.validate_ip is True
        assert cfg.passphrase  is None

    def test_from_env_reads_variables(self, monkeypatch):
        monkeypatch.setenv("PAYFAST_MERCHANT_ID",  "env_id")
        monkeypatch.setenv("PAYFAST_MERCHANT_KEY", "env_key")
        monkeypatch.setenv("PAYFAST_PASSPHRASE",   "env_pass")
        monkeypatch.setenv("PAYFAST_SANDBOX",      "false")
        monkeypatch.setenv("PAYFAST_RETURN_URL",   "https://example.com/return")
        monkeypatch.setenv("PAYFAST_CANCEL_URL",   "https://example.com/cancel")
        monkeypatch.setenv("PAYFAST_NOTIFY_URL",   "https://example.com/notify")
        monkeypatch.setenv("PAYFAST_VALIDATE_IP",  "false")

        cfg = PayfastConfig.from_env()

        assert cfg.merchant_id  == "env_id"
        assert cfg.merchant_key == "env_key"
        assert cfg.passphrase   == "env_pass"
        assert cfg.sandbox      is False
        assert cfg.validate_ip  is False
        assert cfg.return_url   == "https://example.com/return"

    def test_from_env_raises_without_merchant_id(self, monkeypatch):
        monkeypatch.delenv("PAYFAST_MERCHANT_ID",  raising=False)
        monkeypatch.delenv("PAYFAST_MERCHANT_KEY", raising=False)
        with pytest.raises(ValueError, match="PAYFAST_MERCHANT_ID"):
            PayfastConfig.from_env()

    def test_from_env_sandbox_defaults_to_true(self, monkeypatch):
        monkeypatch.setenv("PAYFAST_MERCHANT_ID",  "id")
        monkeypatch.setenv("PAYFAST_MERCHANT_KEY", "key")
        monkeypatch.delenv("PAYFAST_SANDBOX", raising=False)
        cfg = PayfastConfig.from_env()
        assert cfg.sandbox is True

    def test_from_env_empty_passphrase_becomes_none(self, monkeypatch):
        monkeypatch.setenv("PAYFAST_MERCHANT_ID",  "id")
        monkeypatch.setenv("PAYFAST_MERCHANT_KEY", "key")
        monkeypatch.setenv("PAYFAST_PASSPHRASE",   "")
        cfg = PayfastConfig.from_env()
        assert cfg.passphrase is None
