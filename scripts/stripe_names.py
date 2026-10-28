"""Stripe's own names for its operations, from the SDK spec's x-stripeOperations, as the
JSON map apiroute's --operation-names takes ({"PostCustomers": "customers.create", ...}).

Each resource schema lists its operations with the method name Stripe's SDKs use. The section
is the resource's service, named by its path the way Stripe's SDKs name services:

    GET /v1/customers                                  customers.list
    GET /v1/customers/{customer}/balance_transactions  customers.balance_transactions.list
    GET /v1/issuing/cards                              issuing.cards.list

A resource's services are the paths of its standard methods (list, create, retrieve, update,
delete, search), and each of its operations goes to the longest one its path starts with: a
custom method such as DELETE /v1/customers/{customer}/discount lands on customers. An
operation outside them (a test helper) goes to its own path up to the first {param}; a resource
with no standard methods (LoginLink) to the path its operations share. When two resources list
one operation, a standard method on its own service wins.
"""

import json
from pathlib import Path

STANDARD = frozenset({"list", "create", "retrieve", "update", "delete", "search"})


def operation_names(spec: dict) -> dict[str, str]:
    """Operation ID -> dotted name, sorted by operation ID."""
    operation_ids = {
        (method, path): operation["operationId"]
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if isinstance(operation, dict) and "operationId" in operation
    }
    chosen: dict[str, tuple[tuple[int, int], str]] = {}
    for schema in spec["components"]["schemas"].values():
        operations = schema.get("x-stripeOperations") or []
        services = [
            _service_path(op["path"], op["method_type"])
            for op in operations
            if op.get("method_type") in STANDARD
        ]
        for operation in operations:
            operation_id = operation_ids.get((operation["operation"], operation["path"]))
            if operation_id is None:
                continue
            candidate = _candidate(operation, operations, services)
            if operation_id not in chosen or candidate < chosen[operation_id]:
                chosen[operation_id] = candidate
    return {operation_id: chosen[operation_id][1] for operation_id in sorted(chosen)}


def write(spec_path: Path, names_path: Path) -> None:
    names = operation_names(json.loads(spec_path.read_text()))
    names_path.write_text(json.dumps(names, indent=2) + "\n")


def _candidate(operation: dict, operations: list[dict], services: list[list[str]]):
    """((how loosely it was placed, whether it's a custom method), dotted name)."""
    parts = _segments(operation["path"])
    matches = [service for service in services if parts[: len(service)] == service]
    if matches:
        section, loose = _section(max(matches, key=len)), 0
    elif not services:
        section, loose = _section(_shared([_segments(op["path"]) for op in operations])), 1
    else:
        first_param = next((i for i, part in enumerate(parts) if part.startswith("{")), None)
        section, loose = _section(parts[:first_param]), 1
    custom = 0 if operation.get("method_type") in STANDARD else 1
    method = operation["method_name"]
    return (loose, custom), f"{section}.{method}" if section else method


def _segments(path: str) -> list[str]:
    return path.strip("/").split("/")


def _service_path(path: str, method_type: str) -> list[str]:
    """A standard method's service: its path without a trailing {id} or /search."""
    parts = _segments(path)
    if parts[-1].startswith("{") or (method_type == "search" and parts[-1] == "search"):
        parts = parts[:-1]
    return parts


def _shared(paths: list[list[str]]) -> list[str]:
    shared = []
    for parts in zip(*paths, strict=False):
        if len(set(parts)) != 1:
            break
        shared.append(parts[0])
    return shared


def _section(parts: list[str]) -> str:
    """Path segments as a dotted section: v1 and {params} dropped (other versions kept)."""
    version, rest = parts[0], parts[1:]
    named = [part for part in rest if not part.startswith("{")]
    return ".".join(([version] if version != "v1" else []) + named)
