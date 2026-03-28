"""
payfast_core.services.subscription_service
------------------------------------------
Service for building subscription payment data and calling the PayFast
Subscription API (pause, unpause, cancel, update amount, fetch).
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from urllib.parse import urlencode, quote_plus

import requests

from payfast_core.config import PayfastConfig
from payfast_core import security
from payfast_core.exceptions import SubscriptionException
from payfast_core.models import PayfastSubscription, SubscriptionFrequency
from payfast_core.services.payfast_service import PayfastService

LIVE_API_BASE = "https://api.payfast.co.za/subscriptions"


class SubscriptionService:
    """
    Handles PayFast recurring subscription payment data and API interactions.

    Parameters
    ----------
    service:
        A configured :class:`~payfast_core.services.PayfastService` instance.

    Examples
    --------
    >>> from payfast_core import PayfastConfig
    >>> from payfast_core.services import PayfastService, SubscriptionService
    >>> config = PayfastConfig(merchant_id="10000100", merchant_key="46f0cd694581a", sandbox=True)
    >>> svc = SubscriptionService(PayfastService(config))
    >>> data = svc.generate_subscription_payment_data(amount=299.00, item_name="Pro Plan")
    """

    def __init__(self, service: PayfastService) -> None:
        self._service = service
        self._config  = service.config

    # -------------------------------------------------------------------------
    # Payment data builders
    # -------------------------------------------------------------------------

    def generate_subscription_payment_data(
        self,
        amount:            float,
        item_name:         str,
        frequency:         SubscriptionFrequency = SubscriptionFrequency.MONTHLY,
        cycles:            int  = 0,
        billing_date:      str | None = None,
        custom_str1:       str | None = None,
        **extra_params,
    ) -> dict:
        """
        Assemble the signed payment data dict for a new subscription.

        Parameters
        ----------
        amount:
            The recurring billing amount in ZAR.
        item_name:
            Description of the subscription item shown on PayFast.
        frequency:
            A :class:`~payfast_core.models.SubscriptionFrequency` value.
            Defaults to ``MONTHLY``.
        cycles:
            Total billing cycles. ``0`` means indefinite.
        billing_date:
            First billing date in ``YYYY-MM-DD`` format.
            Defaults to today.
        custom_str1:
            Optional custom reference string (e.g. your user ID).
        **extra_params:
            Any additional PayFast payment fields.

        Returns
        -------
        dict
            Complete signed payment data dict.
        """
        params: dict = {
            "subscription_type": 1,
            "frequency":         frequency.value,
            "cycles":            cycles,
            "billing_date":      billing_date or date.today().isoformat(),
            "amount":            f"{amount:.2f}",
            "item_name":         item_name,
            **extra_params,
        }
        if custom_str1 is not None:
            params["custom_str1"] = custom_str1

        return self._service.generate_payment_data(params)

    def generate_trial_subscription_payment_data(
        self,
        amount:      float,
        item_name:   str,
        trial_amount: float = 0.00,
        **kwargs,
    ) -> dict:
        """
        Assemble signed payment data for a trial subscription.

        The first billing will be charged at ``trial_amount`` (default ``0.00``).
        Subsequent cycles will be charged at ``amount``.

        Parameters
        ----------
        amount:
            The regular recurring billing amount.
        item_name:
            Description of the subscription.
        trial_amount:
            The amount to charge for the first (trial) billing cycle.
        **kwargs:
            Forwarded to :meth:`generate_subscription_payment_data`.
        """
        return self.generate_subscription_payment_data(
            amount=trial_amount,
            item_name=item_name,
            **kwargs,
        )

    def build_subscription_url(self, amount: float, item_name: str, **kwargs) -> str:
        """
        Build a fully-signed subscription payment URL for a GET redirect.

        Parameters
        ----------
        amount:
            The recurring billing amount.
        item_name:
            Description of the subscription.
        **kwargs:
            Forwarded to :meth:`generate_subscription_payment_data`.

        Returns
        -------
        str
            Full URL including query string.
        """
        from payfast_core.services.payfast_service import LIVE_URL, SANDBOX_URL
        data     = self.generate_subscription_payment_data(amount=amount, item_name=item_name, **kwargs)
        base_url = SANDBOX_URL if self._config.sandbox else LIVE_URL
        return f"{base_url}?{urlencode(data)}"

    # -------------------------------------------------------------------------
    # PayFast Subscription API
    # -------------------------------------------------------------------------

    def fetch_subscription(self, token: str) -> dict:
        """
        Fetch the current status of a subscription from the PayFast API.

        Parameters
        ----------
        token:
            The subscription token returned by PayFast in the ITN.

        Returns
        -------
        dict
            Raw API response JSON.

        Raises
        ------
        SubscriptionException
            If the API call fails.
        """
        try:
            response = requests.get(
                f"{LIVE_API_BASE}/{token}/fetch",
                headers=self._api_headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise SubscriptionException(f"Failed to fetch subscription [{token}]: {exc}") from exc

    def pause(self, token: str) -> bool:
        """
        Pause a subscription via the PayFast API.

        Parameters
        ----------
        token: The subscription token.

        Returns
        -------
        bool
            ``True`` on success.

        Raises
        ------
        SubscriptionException
        """
        return self._put(token, "pause")

    def unpause(self, token: str) -> bool:
        """
        Unpause (resume) a subscription via the PayFast API.

        Parameters
        ----------
        token: The subscription token.
        """
        return self._put(token, "unpause")

    def cancel(self, token: str) -> bool:
        """
        Cancel a subscription via the PayFast API.

        Parameters
        ----------
        token: The subscription token.
        """
        return self._put(token, "cancel")

    def update_amount(self, token: str, amount: float, cycles: int | None = None) -> bool:
        """
        Update the billing amount for a subscription.

        Parameters
        ----------
        token:
            The subscription token.
        amount:
            New billing amount in ZAR.
        cycles:
            Optional new cycles value.

        Returns
        -------
        bool
            ``True`` on success.
        """
        body: dict = {"amount": int(amount * 100)}  # PayFast expects cents
        if cycles is not None:
            body["cycles"] = cycles

        try:
            response = requests.patch(
                f"{LIVE_API_BASE}/{token}/update",
                json=body,
                headers=self._api_headers(),
                timeout=30,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            raise SubscriptionException(
                f"Failed to update subscription [{token}]: {exc}"
            ) from exc

    def sync_from_itn(self, payload: dict) -> PayfastSubscription:
        """
        Build a :class:`~payfast_core.models.PayfastSubscription` from an ITN payload.

        Call this after receiving the first billing ITN for a new subscription
        to create a local record of the subscription.

        Parameters
        ----------
        payload:
            The full raw ITN payload dict.

        Returns
        -------
        PayfastSubscription

        Raises
        ------
        PayfastException
            If the payload does not contain a ``token`` field.
        """
        return PayfastSubscription.from_itn_payload(payload)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _put(self, token: str, action: str) -> bool:
        try:
            response = requests.put(
                f"{LIVE_API_BASE}/{token}/{action}",
                headers=self._api_headers(),
                timeout=30,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            raise SubscriptionException(
                f"Failed to {action} subscription [{token}]: {exc}"
            ) from exc

    def _api_headers(self) -> dict:
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        return {
            "merchant-id": self._config.merchant_id,
            "timestamp":   timestamp,
            "version":     "v1",
            "signature":   self._api_signature(timestamp),
        }

    def _api_signature(self, timestamp: str) -> str:
        return security.generate_api_signature(
            merchant_id = self._config.merchant_id,
            passphrase  = self._config.passphrase,
            timestamp   = timestamp,
        )
