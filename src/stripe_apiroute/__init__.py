"""A Python client for the Stripe API, generated with apiroute from Stripe's OpenAPI spec.

    from stripe_apiroute.api import StripeApi

    stripe = StripeApi(api_key="sk_test_...")
    customer = stripe.customers.models.create(body={"email": "jenny@example.com"})

Only stripe_apiroute.auth (the hand-written StripeAuth) and this file are written by hand;
everything under stripe_apiroute.api is regenerated from Stripe's spec.
"""
