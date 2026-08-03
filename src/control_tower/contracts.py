"""Durable contracts for the Phase 8 Control Tower refresh pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.control_tower.relation_extractor import MODEL_SPECS


@dataclass(frozen=True)
class ParentChildContract:
    parent_model: str
    child_model: str
    parent_field: str
    strategy: str = "PARENT_CURRENT_CHILD_SET"


@dataclass(frozen=True)
class DomainContract:
    key: str
    label: str
    model_keys: tuple[str, ...]
    dependency_domains: tuple[str, ...] = ()
    parent_children: tuple[ParentChildContract, ...] = ()
    downstream_stages: tuple[str, ...] = (
        "RECONCILING", "VALIDATING", "REFRESHING_DERIVED_DATA",
    )


@dataclass(frozen=True)
class ModelExecutionContract:
    model_key: str
    domain_keys: tuple[str, ...]
    parent_children: tuple[ParentChildContract, ...]
    downstream_stages: tuple[str, ...]
    supports_write_date: bool = True


MODEL_SPEC_KEYS = frozenset(spec.model for spec in MODEL_SPECS)

DOMAIN_REGISTRY: tuple[DomainContract, ...] = (
    DomainContract("commercial", "Commercial", ("sale.order", "sale.order.line"), parent_children=(ParentChildContract("sale.order", "sale.order.line", "order_id"),)),
    DomainContract("internal_order", "Internal Order", ("approval.request", "approval.product.line"), parent_children=(ParentChildContract("approval.request", "approval.product.line", "approval_request_id"),)),
    DomainContract("manufacturing", "Manufacturing", ("mrp.production", "stock.move"), ("internal_order",), (ParentChildContract("mrp.production", "stock.move", "production_id"),)),
    DomainContract("procurement", "Procurement", ("purchase.order", "purchase.order.line"), ("internal_order",), (ParentChildContract("purchase.order", "purchase.order.line", "order_id"),)),
    DomainContract("warehouse", "Warehouse", ("stock.picking", "stock.move"), ("commercial", "manufacturing", "procurement"), (ParentChildContract("stock.picking", "stock.move", "picking_id"),)),
    DomainContract("finance", "Finance", ("account.move", "account.move.line", "account.partial.reconcile"), ("commercial", "procurement"), (ParentChildContract("account.move", "account.move.line", "move_id"),)),
)

DOMAIN_BY_KEY = {domain.key: domain for domain in DOMAIN_REGISTRY}


def validate_domain_registry() -> None:
    if len(DOMAIN_BY_KEY) != len(DOMAIN_REGISTRY):
        raise ValueError("Control Tower domain keys must be unique.")
    for domain in DOMAIN_REGISTRY:
        unknown_models = set(domain.model_keys) - MODEL_SPEC_KEYS
        if unknown_models:
            raise ValueError(f"Domain {domain.key} references unknown MODEL_SPECS: {sorted(unknown_models)}")
        unknown_dependencies = set(domain.dependency_domains) - set(DOMAIN_BY_KEY)
        if unknown_dependencies:
            raise ValueError(f"Domain {domain.key} references unknown dependencies: {sorted(unknown_dependencies)}")
        for relation in domain.parent_children:
            if relation.parent_model not in domain.model_keys or relation.child_model not in MODEL_SPEC_KEYS:
                raise ValueError(f"Invalid parent-child contract in domain {domain.key}: {relation}")


def resolve_domain_selection(selected: Iterable[str] | None) -> tuple[DomainContract, ...]:
    validate_domain_registry()
    requested = tuple(selected or ("all",))
    if "all" in requested and len(requested) != 1:
        raise ValueError("The 'all' selector cannot be combined with domain keys.")
    if requested == ("all",):
        return DOMAIN_REGISTRY
    unknown = set(requested) - set(DOMAIN_BY_KEY)
    if unknown:
        raise ValueError(f"Unknown Control Tower domain(s): {sorted(unknown)}")
    resolved: list[DomainContract] = []
    seen: set[str] = set()
    def add(key: str) -> None:
        if key in seen:
            return
        seen.add(key)
        for dependency in DOMAIN_BY_KEY[key].dependency_domains:
            add(dependency)
        resolved.append(DOMAIN_BY_KEY[key])
    for key in requested:
        add(key)
    return tuple(resolved)


def resolve_model_keys(selected: Iterable[str] | None) -> tuple[str, ...]:
    models: list[str] = []
    seen: set[str] = set()
    for domain in resolve_domain_selection(selected):
        for model in domain.model_keys:
            if model not in seen:
                seen.add(model)
                models.append(model)
    return tuple(models)


def resolve_execution_entries(selected: Iterable[str] | None) -> tuple[ModelExecutionContract, ...]:
    """Return one deterministic execution entry per model with merged metadata."""
    entries: dict[str, dict[str, list[object]]] = {}
    for domain in resolve_domain_selection(selected):
        for model in domain.model_keys:
            data = entries.setdefault(model, {"domains": [], "parents": [], "stages": []})
            if domain.key not in data["domains"]:
                data["domains"].append(domain.key)
            for relation in domain.parent_children:
                if relation not in data["parents"]:
                    data["parents"].append(relation)
            for stage in domain.downstream_stages:
                if stage not in data["stages"]:
                    data["stages"].append(stage)
    return tuple(ModelExecutionContract(
        model_key=model,
        domain_keys=tuple(data["domains"]),
        parent_children=tuple(data["parents"]),
        downstream_stages=tuple(data["stages"]),
    ) for model, data in entries.items())


validate_domain_registry()