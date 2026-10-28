"""The _all methods page as Stripe does (over a mock transport)."""

import httpx
import pytest
from apiroute.testing import MockTransport

from stripe_apiroute.api import StripeApi


@pytest.fixture
def mock():
    return MockTransport()


@pytest.fixture
def stripe(mock):
    return StripeApi(api_key="sk_test_123", transport=mock)


def page(ids, has_more, **extra):
    data = [{"id": i, "object": "customer"} for i in ids]
    return httpx.Response(200, json={"object": "list", "data": data, "has_more": has_more, **extra})


def test_lists_start_after_the_last_item(stripe, mock):
    mock.respond(page(["cus_1", "cus_2"], True), page(["cus_3"], False))
    ids = [c["id"] for c in stripe.customers.list_all(limit=2, email="a@example.com")]
    assert ids == ["cus_1", "cus_2", "cus_3"]
    assert [call.params.get("starting_after") for call in mock.calls] == [None, "cus_2"]
    assert all(call.params["email"] == "a@example.com" for call in mock.calls)
    assert all(call.operation == "GetCustomers" for call in mock.calls)


def test_searches_follow_next_page(stripe, mock):
    mock.respond(
        page(["cus_1"], True, next_page="tok_2"),
        page(["cus_2"], False, next_page=None),
    )
    assert [c["id"] for c in stripe.customers.search_all(query="email:'a@example.com'")] == [
        "cus_1",
        "cus_2",
    ]
    assert [call.params.get("page") for call in mock.calls] == [None, "tok_2"]


def test_the_one_page_method_is_unchanged(stripe, mock):
    mock.respond(page(["cus_1"], True))
    assert stripe.customers.list(limit=1)["has_more"] is True
    assert len(mock.calls) == 1
