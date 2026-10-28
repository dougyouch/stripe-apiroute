"""Every API in apis.yaml is fetched, generated and importable, and every route compiles."""

import importlib
import json
from pathlib import Path

import pytest
import yaml
from apiroute.lazy_attribute import LazyAttribute
from apiroute.route_method import RouteMethod

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "apis.yaml").read_text())
APIS = CONFIG["apis"]


def test_names_and_modules_are_unique():
    assert len({api["name"] for api in APIS}) == len(APIS)
    assert len({api["module"] for api in APIS}) == len(APIS)


@pytest.mark.parametrize("api", APIS, ids=lambda api: api["name"])
def test_each_api(api):
    assert (ROOT / "specs" / f"{api['name']}.json").is_file()
    assert api["docs"].startswith("https://docs.stripe.com/")
    if api.get("operation_names"):
        assert (ROOT / api["operation_names"]).is_file()
    module = importlib.import_module(f"{CONFIG['package']}.{api['module']}")
    client = getattr(module, api["client"])
    base_module, base_name = api["base_class"].split(":")
    assert issubclass(client, getattr(importlib.import_module(base_module), base_name))
    assert client._config.base_url.startswith("https://")
    assert _compile_routes(client) > 0


def test_every_operation_has_stripes_name():
    """Nothing is left on the root client under a generated name: every operation in the spec
    is in the name map, so Stripe adding one without a name shows up here."""
    spec = json.loads((ROOT / "specs" / "stripe.json").read_text())
    names = json.loads((ROOT / "specs" / "stripe.names.json").read_text())
    operation_ids = {
        operation["operationId"]
        for item in spec["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert operation_ids == set(names)
    assert all("." in name for name in names.values())


def _compile_routes(router_class: type) -> int:
    """Compiles every route of a client and its sections; returns how many there were."""
    count = 0
    for name, value in vars(router_class).items():
        if isinstance(value, RouteMethod):
            assert value.definition.name == name
            count += 1
        elif isinstance(value, LazyAttribute) and name != "models":
            count += _compile_routes(value.load())
    return count
