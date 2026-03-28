# Changelog

All notable changes to `payfast-core` (Python) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2024-01-01

### Added
- `PayfastConfig` dataclass with `from_env()` factory
- `PayfastService` — MD5 signature generation, payment data assembly, ITN validation
- `SubscriptionService` — subscription payment data builders and PayFast API calls
- `PayfastClient` — high-level client with `handle_itn()` and `on()` event decorator
- `PayfastPaymentEvent` — unified event with full type/status/payload API
- Granular events: `PayfastItnReceived`, `PayfastPaymentComplete`, `PayfastPaymentFailed`,
  `PayfastSubscriptionCreated`, `PayfastSubscriptionRenewed`, `PayfastSubscriptionCancelled`
- `PayfastTransaction` and `PayfastSubscription` dataclass models with status helpers
- `SubscriptionFrequency` and `SubscriptionStatus` enumerations
- Django middleware (`DjangoPayfastWebhookMiddleware`) and view decorator
- Flask route decorator (`flask_verify_payfast_webhook`)
- Framework-agnostic `verify_itn_payload` helper
- Full test suite with pytest — unit and feature tests, `responses` mock for API calls
- GitHub Actions CI for Python 3.10, 3.11, 3.12 with auto-publish to PyPI on tag
