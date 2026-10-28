"""Live tests: calls to Stripe's test mode, run only when STRIPE_TEST_SECRET_KEY is set.

    STRIPE_TEST_SECRET_KEY=sk_test_... uv run pytest tests/live

They check requests and typed models against what Stripe actually accepts and sends. Test
mode moves no money; the tests still clean up the objects they create where Stripe allows
it. A key that isn't a test-mode key is refused, never used.
"""

import os

import pytest

from stripe_apiroute.api import StripeApi

KEY = os.environ.get("STRIPE_TEST_SECRET_KEY", "")
TEST_MODE = KEY.startswith(("sk_test_", "rk_test_"))


def pytest_collection_modifyitems(items):
    if TEST_MODE:
        return
    reason = "live tests need STRIPE_TEST_SECRET_KEY, a test-mode key (sk_test_ or rk_test_)"
    for item in items:
        if "tests/live/" in item.nodeid:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(scope="session")
def stripe() -> StripeApi:
    assert TEST_MODE, "refusing to run live tests without a test-mode key"
    return StripeApi(api_key=KEY)
