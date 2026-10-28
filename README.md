# stripe-apiroute

[![Build](https://github.com/dougyouch/stripe-apiroute/actions/workflows/build.yml/badge.svg)](https://github.com/dougyouch/stripe-apiroute/actions/workflows/build.yml)
[![Release](https://github.com/dougyouch/stripe-apiroute/actions/workflows/release.yml/badge.svg)](https://github.com/dougyouch/stripe-apiroute/actions/workflows/release.yml)

A Python client for the [Stripe API](https://docs.stripe.com/api), generated with [apiroute](https://github.com/dougyouch/apiroute) from [Stripe's published OpenAPI spec](https://github.com/stripe/openapi) and kept current by a weekly build. Methods carry the names Stripe's own SDKs use: `stripe.customers.create(...)`, `stripe.issuing.cards.list()`, `stripe.checkout.sessions.create(...)`.

- **Two layers:** every call works with plain dicts (`stripe.customers.retrieve("cus_123")`), and `.models` takes and returns typed pydantic models (`stripe.customers.models.retrieve("cus_123")`).
- **Sync and async:** add `.aio` to any call for the async version.
- **Lazy loading:** only the sections and models you use are imported. The client covers all 559 operations and about 5,000 models, and importing it takes about a tenth of a second.
- **Typed:** the package ships `py.typed`.

## Installation

```bash
pip install stripe-apiroute    # or: uv add stripe-apiroute
```

It needs Python 3.10 or newer.

## Usage

```python
import os
from stripe_apiroute.api import StripeApi

stripe = StripeApi(api_key=os.environ["STRIPE_SECRET_KEY"])

customer = stripe.customers.create(body={"email": "jenny@example.com"})  # a dict
customer = stripe.customers.models.create(  # Customer
    body={
        "email": "jenny@example.com",
        "metadata": {"order_id": "6735"},
        "address": {"city": "Paris", "line1": "1 rue de Rivoli"},
    }
)
print(customer.id, customer.address.city)

recent = stripe.customers.models.list(created={"gte": 1700000000}, limit=10, expand=["data.tax"])
for customer in stripe.customers.models.list_all(limit=100):  # every page, fetched as you go
    print(customer.email)
session = stripe.checkout.sessions.models.create(
    body={
        "mode": "payment",
        "success_url": "https://example.com/done",
        "line_items": [{"price": "price_123", "quantity": 2}],
    }
)
intent = await stripe.payment_intents.models.aio.retrieve("pi_123")
```

- **Request bodies** are sent the way Stripe expects, as form-encoded data with nested values: `metadata[order_id]=6735`, `line_items[][price]=price_123`. Filters such as `created={"gte": ...}` go out as `created[gte]=...`, and `expand=[...]` as `expand[]=...`.
- **Sections follow Stripe's SDKs:** `stripe.customers`, `stripe.customers.balance_transactions`, `stripe.payment_intents`, `stripe.issuing.cards`, `stripe.billing.meters`, `stripe.test_helpers.test_clocks`, and so on: 75 top-level sections.
- **Pagination:** every list operation has a `_all` twin (`customers.list_all`, `invoices.list_all`, `customers.search_all` …) taking the same arguments and iterating every page's items: it follows `has_more` and `starting_after`, or `next_page` for searches. `async for` works through `.aio`, `.pages()` gives whole pages, and `itertools.islice` or `break` stops early. Which operations get one is set by [`specs/stripe.pagination.yaml`](specs/stripe.pagination.yaml).
- **File uploads** go to `files.stripe.com`, as Stripe requires: `stripe.files.models.create(body={"purpose": "dispute_evidence", "file": ("evidence.png", data, "image/png")})`.
- **Errors** raise `apiroute.UnexpectedResponse`. Its `.response` carries Stripe's error object: `error.response.json()["error"]["code"]`.

### Keys, versions and Connect

| Argument | |
| --- | --- |
| `api_key` | A secret key (`sk_live_…`, `sk_test_…`), a restricted key (`rk_…`), or a function returning the current one. Sent as `Authorization: Bearer …`. See Stripe's [API keys guide](https://docs.stripe.com/keys). |
| `stripe_account` | Acts on behalf of a [connected account](https://docs.stripe.com/connect/authentication), through the `Stripe-Account` header. |
| `stripe_version` | Defaults to the API version of the spec this release was generated from (`stripe_apiroute.spec_info.STRIPE_VERSION`), which the typed models describe. Responses for another version may not match them. |
| `base_url` | Another host, such as [stripe-mock](https://github.com/stripe/stripe-mock) (`http://localhost:12111`). Every operation then goes there, file uploads included. |

### Retries and idempotency

Retries are off unless you turn them on, for example with `stripe.with_options(retries=3)`, or `retries = Retries(...)` in a subclass. Once on, they follow Stripe's SDKs:
- Every `POST` carries an `Idempotency-Key`: a new UUID for each call, the same on every retry of it. A payment can't be created twice.
- Connection failures and timeouts are retried.
- An error response is retried when Stripe's `Stripe-Should-Retry` header says so. Without that header, a 409 (lock timeout), a 429 and server errors are retried.

For transports, timeouts and other client options, see [apiroute's README](https://github.com/dougyouch/apiroute#readme).

## APIs

<!-- apis:start -->
| API | Import | Docs |
| --- | --- | --- |
| Stripe API | `from stripe_apiroute.api import StripeApi` | [docs](https://docs.stripe.com/api) |
<!-- apis:end -->

## How this repository stays up to date

Nothing under `src/stripe_apiroute/` is written by hand except `auth.py` and `__init__.py`. Everything else is generated from the spec listed in [`apis.yaml`](apis.yaml):

1. Every Monday, the **[Build](.github/workflows/build.yml)** workflow does the following:
   - Upgrades apiroute to its newest release.
   - Downloads Stripe's spec into [`specs/`](specs). It uses the SDK variant, whose `x-stripeOperations` extensions name every operation as Stripe's SDKs do.
   - Writes [`specs/stripe.names.json`](specs/stripe.names.json), the map of operation IDs to those names, with [`scripts/stripe_names.py`](scripts/stripe_names.py).
   - Regenerates the client with `apiroute generate --operation-names`.
   - Runs the lint and tests, then the live tests against Stripe's test mode.
2. If anything changed, it commits the result to `main`:
   - `feat(specs): ...` when Stripe changed its spec, which produces a minor release.
   - `fix(codegen): ...` when only a newer apiroute changed the generated code, which produces a patch release.
3. **[Release](.github/workflows/release.yml)** then tests the commit, adds it to [CHANGELOG.md](CHANGELOG.md), tags it, publishes the new version to [PyPI](https://pypi.org/project/stripe-apiroute/) and creates a [GitHub release](https://github.com/dougyouch/stripe-apiroute/releases). No one has to do anything; every merge to main releases the same way.

[CI](.github/workflows/ci.yml) checks every pull request and every release. It lints, runs the tests on Python 3.10 to 3.14, and regenerates from the committed spec to confirm the committed code matches it exactly.

Because `specs/` is committed, `git log -p specs/` shows exactly what Stripe changed and when.

## Development

```bash
uv sync
uv run python scripts/generate.py --fetch   # download the latest spec, regenerate
uv run python scripts/generate.py           # regenerate from the committed spec
uv run pytest
STRIPE_TEST_SECRET_KEY=sk_test_... uv run pytest tests/live   # against Stripe's test mode
uv run ruff check . && uv run ruff format --check .
```

The live tests create a few test-mode objects (a customer, a product and prices, a Checkout session, a small file) and clean up what Stripe lets them. They refuse to run with a key that isn't a test-mode key.

## License

MIT
