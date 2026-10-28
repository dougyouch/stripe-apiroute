"""Authentication for the generated Stripe client.

This file is written by hand: the generated client extends StripeAuth (through the
`base_class` entry in apis.yaml), so regenerating never touches it.
"""

import dataclasses
from collections.abc import Callable
from typing import Any

from apiroute import Client, RequestSpec, UnexpectedResponse

from stripe_apiroute.spec_info import OPERATION_SERVERS, STRIPE_VERSION

ApiKey = str | Callable[[], str]

API_HOST = "https://api.stripe.com"

# What Stripe's SDKs retry when Stripe-Should-Retry doesn't say: a lock timeout (409), rate
# limiting (429) and server errors
RETRY_STATUSES = frozenset({409, 429, 500, 502, 503, 504})


class StripeAuth(Client):
    """A Stripe secret or restricted key, and the API version the client was generated for.

        stripe = StripeApi(api_key=os.environ["STRIPE_SECRET_KEY"])
        stripe.customers.create(body={"email": "jenny@example.com"})
        stripe.with_options(retries=3).payment_intents.create(body={...})

    api_key is a secret key (sk_live_..., sk_test_...), a restricted key (rk_...), or a
    function returning the current one. stripe_account acts on behalf of a Connect account
    (the Stripe-Account header). stripe_version defaults to the version of the spec this
    client was generated from, which the typed models describe; responses for another version
    may not match them.

    Every POST carries an Idempotency-Key, a new UUID per call and the same on each retry of
    it, so with retries on (they're off by default) a payment can't be created twice. As in
    Stripe's SDKs, an error response is retried when its Stripe-Should-Retry header says so,
    or without the header, for a 409 (lock timeout), a 429 or a server error. The
    few operations Stripe serves from another host (file uploads, on files.stripe.com) are
    sent there, unless base_url points somewhere else (a proxy or stripe-mock).
    """

    headers = {
        "Authorization": lambda self: f"Bearer {self.current_api_key()}",
        "Stripe-Version": lambda self: self.stripe_version,
        "Stripe-Account": lambda self: self.stripe_account,
    }
    idempotency_key = "Idempotency-Key"

    def __init__(
        self,
        api_key: ApiKey,
        *,
        stripe_account: str | None = None,
        stripe_version: str = STRIPE_VERSION,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._api_key = api_key
        self.stripe_account = stripe_account
        self.stripe_version = stripe_version

    def current_api_key(self) -> str:
        return self._api_key() if callable(self._api_key) else self._api_key

    def should_retry(self, error: Exception, attempt: int) -> bool:
        if not isinstance(error, UnexpectedResponse):
            return super().should_retry(error, attempt)
        advice = error.response.headers.get("Stripe-Should-Retry")
        if advice is not None:
            return advice == "true"
        return error.response.status_code in RETRY_STATUSES

    def on_request(self, request: RequestSpec) -> RequestSpec | None:
        server = OPERATION_SERVERS.get(request.operation)
        if server is None or not request.url.startswith(f"{API_HOST}/"):
            return None
        return dataclasses.replace(request, url=server + request.url[len(API_HOST) :])
