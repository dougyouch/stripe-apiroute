"""StripeAuth: the key, the pinned version, Connect, idempotency keys and per-operation hosts."""

import urllib.parse

import httpx
import pytest
from apiroute import Retries, UnexpectedResponse

from stripe_apiroute.api import StripeApi
from stripe_apiroute.spec_info import STRIPE_VERSION


@pytest.fixture
def stripe(transport):
    return StripeApi(api_key="sk_test_123", transport=transport)


def test_the_key_and_the_spec_version_are_sent(stripe, recorder):
    stripe.customers.retrieve("cus_1")
    request = recorder.last
    assert str(request.url) == "https://api.stripe.com/v1/customers/cus_1"
    assert request.headers["Authorization"] == "Bearer sk_test_123"
    assert request.headers["Stripe-Version"] == STRIPE_VERSION
    assert "Stripe-Account" not in request.headers


def test_a_connect_account_a_version_and_a_key_function(transport, recorder):
    keys = iter(["sk_test_a", "sk_test_b"])
    stripe = StripeApi(
        api_key=lambda: next(keys),
        stripe_account="acct_1",
        stripe_version="2025-01-27.acacia",
        transport=transport,
    )
    stripe.balance.retrieve()
    stripe.balance.retrieve()
    assert [r.headers["Authorization"] for r in recorder.requests] == [
        "Bearer sk_test_a",
        "Bearer sk_test_b",
    ]
    assert recorder.last.headers["Stripe-Account"] == "acct_1"
    assert recorder.last.headers["Stripe-Version"] == "2025-01-27.acacia"


def test_nested_form_bodies_and_bracketed_filters(stripe, recorder):
    stripe.checkout.sessions.create(
        body={
            "mode": "payment",
            "metadata": {"order": "6735"},
            "line_items": [{"price": "price_1", "quantity": 2}],
        }
    )
    assert recorder.last.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert urllib.parse.unquote(recorder.last.content.decode()) == (
        "mode=payment&metadata[order]=6735&line_items[][price]=price_1&line_items[][quantity]=2"
    )
    stripe.customers.list(created={"gt": 1700000000}, expand=["data.tax"], limit=3)
    assert urllib.parse.unquote(recorder.last.url.query.decode()) == (
        "created[gt]=1700000000&expand[]=data.tax&limit=3"
    )


def test_posts_carry_one_idempotency_key_across_retries(transport, recorder):
    stripe = StripeApi(api_key="sk_test_1", transport=transport).with_options(
        retries=Retries(attempts=2, sleep=0)
    )
    recorder.respond(httpx.Response(500, json={}), httpx.Response(200, json={"id": "cus_1"}))
    assert stripe.customers.create(body={"email": "a@b.co"}) == {"id": "cus_1"}
    first, second = recorder.requests
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    stripe.customers.create(body={"email": "c@d.co"})
    assert recorder.last.headers["Idempotency-Key"] != first.headers["Idempotency-Key"]
    stripe.customers.retrieve("cus_1")
    assert "Idempotency-Key" not in recorder.last.headers


@pytest.mark.parametrize(
    ("status", "advice", "retried"),
    [
        (500, None, True),
        (429, None, True),
        (409, None, True),
        (400, None, False),
        (500, "false", False),
        (400, "true", True),
    ],
)
def test_retries_follow_stripe_should_retry(transport, recorder, status, advice, retried):
    stripe = StripeApi(api_key="sk_test_1", transport=transport).with_options(
        retries=Retries(attempts=2, sleep=0)
    )
    headers = {"Stripe-Should-Retry": advice} if advice else {}
    recorder.respond(httpx.Response(status, json={}, headers=headers), httpx.Response(200, json={}))
    try:
        stripe.customers.retrieve("cus_1")
    except UnexpectedResponse:
        pass
    assert len(recorder.requests) == (2 if retried else 1)


def test_file_uploads_go_to_the_files_host(stripe, recorder):
    stripe.files.create(body={"purpose": "dispute_evidence", "file": ("a.pdf", b"%PDF")})
    assert str(recorder.last.url) == "https://files.stripe.com/v1/files"
    assert recorder.last.headers["Content-Type"].startswith("multipart/form-data")
    stripe.files.list()
    assert str(recorder.last.url) == "https://api.stripe.com/v1/files"


def test_another_base_url_keeps_every_operation(transport, recorder):
    stripe = StripeApi(api_key="sk_test_1", base_url="http://localhost:12111", transport=transport)
    stripe.files.create(body={"purpose": "dispute_evidence", "file": ("a.pdf", b"%PDF")})
    assert str(recorder.last.url) == "http://localhost:12111/v1/files"
