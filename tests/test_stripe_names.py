"""scripts/stripe_names.py: Stripe's SDK names from x-stripeOperations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import stripe_names  # noqa: E402


def resource(*operations):
    return {
        "x-stripeOperations": [
            {"method_name": name, "method_type": kind, "operation": method, "path": path}
            for name, kind, method, path in operations
        ]
    }


def spec(**schemas):
    paths: dict = {}
    for schema in schemas.values():
        for op in schema["x-stripeOperations"]:
            operation_id = op["operation"].title() + op["path"].replace("/", "_")
            paths.setdefault(op["path"], {})[op["operation"]] = {"operationId": operation_id}
    return {"paths": paths, "components": {"schemas": schemas}}


def named(**schemas):
    return set(stripe_names.operation_names(spec(**schemas)).values())


def test_standard_and_custom_methods_share_the_resources_service():
    customer = resource(
        ("list", "list", "get", "/v1/customers"),
        ("retrieve", "retrieve", "get", "/v1/customers/{customer}"),
        ("search", "search", "get", "/v1/customers/search"),
        ("delete_discount", "custom", "delete", "/v1/customers/{customer}/discount"),
    )
    assert named(customer=customer) == {
        "customers.list",
        "customers.retrieve",
        "customers.search",
        "customers.delete_discount",
    }


def test_sub_resources_and_namespaces_nest():
    balance = resource(("list", "list", "get", "/v1/customers/{customer}/balance_transactions"))
    card = resource(("create", "create", "post", "/v1/issuing/cards"))
    assert named(balance=balance, card=card) == {
        "customers.balance_transactions.list",
        "issuing.cards.create",
    }


def test_test_helpers_and_resources_without_standard_methods():
    card = resource(
        ("list", "list", "get", "/v1/issuing/cards"),
        (
            "deliver_card",
            "custom",
            "post",
            "/v1/test_helpers/issuing/cards/{card}/shipping/deliver",
        ),
    )
    login_link = resource(("create", "custom", "post", "/v1/accounts/{account}/login_links"))
    assert named(card=card, login_link=login_link) == {
        "issuing.cards.list",
        "test_helpers.issuing.cards.deliver_card",
        "accounts.login_links.create",
    }


def test_a_standard_method_on_its_own_service_wins_a_shared_operation():
    customer = resource(
        ("list", "list", "get", "/v1/customers"),
        ("balance_transactions", "custom", "get", "/v1/customers/{customer}/balance_transactions"),
    )
    balance = resource(("list", "list", "get", "/v1/customers/{customer}/balance_transactions"))
    names = stripe_names.operation_names(spec(customer=customer, balance=balance))
    assert names["Get_v1_customers_{customer}_balance_transactions"] == (
        "customers.balance_transactions.list"
    )


def test_write(tmp_path):
    spec_path, names_path = tmp_path / "spec.json", tmp_path / "names.json"
    import json

    spec_path.write_text(json.dumps(spec(c=resource(("list", "list", "get", "/v1/charges")))))
    stripe_names.write(spec_path, names_path)
    assert json.loads(names_path.read_text()) == {"Get_v1_charges": "charges.list"}
