"""The client against Stripe's test mode: nested form bodies, bracketed filters, arrays of
objects, the files host, async, and typed models validating real responses."""

import asyncio
import struct
import time
import zlib

import pytest


@pytest.fixture
def customer(stripe):
    created = stripe.customers.models.create(
        body={
            "email": "live@example.com",
            "metadata": {"source": "stripe-apiroute live tests"},
            "address": {"city": "Paris", "line1": "1 rue de Rivoli"},
            "preferred_locales": ["fr", "en"],
        }
    )
    yield created
    stripe.customers.delete(created.id)


@pytest.fixture
def prices(stripe):
    product = stripe.products.models.create(body={"name": "stripe-apiroute live test"})
    created = [
        stripe.prices.models.create(
            body={"product": product.id, "currency": "usd", "unit_amount": amount}
        )
        for amount in (1500, 700)
    ]
    yield created
    for price in created:
        stripe.prices.update(price.id, body={"active": False})
    stripe.products.update(product.id, body={"active": False})


def test_nested_form_values_round_trip(customer):
    assert customer.metadata == {"source": "stripe-apiroute live tests"}
    assert customer.address.city == "Paris"
    assert customer.preferred_locales == ["fr", "en"]


def test_retrieve_update_and_bracketed_filters(stripe, customer):
    assert stripe.customers.models.retrieve(customer.id).email == "live@example.com"
    updated = stripe.customers.models.update(customer.id, body={"metadata": {"step": "2"}})
    assert updated.metadata["step"] == "2"
    recent = stripe.customers.models.list(
        created={"gte": customer.created}, expand=["data.tax"], limit=10
    )
    assert customer.id in [found.id for found in recent.data]


def test_an_array_of_objects_reaches_stripe_as_sent(stripe, prices):
    session = stripe.checkout.sessions.models.create(
        body={
            "mode": "payment",
            "success_url": "https://example.com/done",
            "line_items": [
                {"price": prices[0].id, "quantity": 2},
                {"price": prices[1].id, "quantity": 1},
            ],
        }
    )
    try:
        items = stripe.checkout.sessions.models.list_line_items(session.id).data
        assert [(item.price.id, item.quantity) for item in items] == [
            (prices[0].id, 2),
            (prices[1].id, 1),
        ]
        assert session.amount_total == 2 * 1500 + 700
    finally:
        stripe.checkout.sessions.expire(session.id)


def png() -> bytes:
    """A valid 1x1 PNG: Stripe checks what's uploaded."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )


def test_a_file_upload_goes_to_the_files_host(stripe):
    image = png()
    uploaded = stripe.files.models.create(
        body={"purpose": "dispute_evidence", "file": ("evidence.png", image, "image/png")}
    )
    assert uploaded.purpose == "dispute_evidence" and uploaded.type_ == "png"  # Stripe
    assert uploaded.size > 0  # re-encodes images, so the stored size isn't what was sent
    assert stripe.files.models.retrieve(uploaded.id).id == uploaded.id


def test_reads_across_sections(stripe):
    assert stripe.balance.models.retrieve().livemode is False
    assert len(stripe.events.models.list(limit=3).data) <= 3
    assert stripe.payment_intents.models.list(limit=1).object == "list"


def test_async(stripe, customer):
    found = asyncio.run(stripe.customers.models.aio.retrieve(customer.id))
    assert found.id == customer.id


def test_an_error_is_an_unexpected_response(stripe):
    from apiroute import UnexpectedResponse

    with pytest.raises(UnexpectedResponse) as raised:
        stripe.customers.retrieve(f"cus_does_not_exist_{int(time.time())}")
    assert raised.value.response.status_code == 404
    assert raised.value.response.json()["error"]["code"] == "resource_missing"
