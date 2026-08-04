"""Stateful Odoo search_read fake that models hidden second precision.

The fake emulates the Odoo 18 XML-RPC boundary: search domains are evaluated
against internal (hidden-precision) timestamps, while every returned
``write_date`` is the displayed second string ``YYYY-MM-DD HH:MM:SS`` without
microseconds.  Only ``search_read`` is available; complete-record reads are
forbidden.

Domain fidelity matches Odoo 18: flat implicit-AND lists and flat prefix
domains are accepted, while nested sublists are rejected the same way the real
server rejects them (``Invalid field <model>.& in leaf``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


_PREFIX_OPERATORS = frozenset({"&", "|"})


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _freeze(item: Any) -> Any:
    """Deep-convert domain lists to tuples so recorded calls are hashable."""
    if isinstance(item, list):
        return tuple(_freeze(part) for part in item)
    return item


class FakeOdoo:
    """Read-only Odoo client fake with server-side filtering and ordering."""

    def __init__(self, rows, *, fail_model=None, live=False):
        self._store = {model: [dict(row) for row in model_rows] for model, model_rows in rows.items()}
        self.fail_model = fail_model
        self.live = live
        self.calls = []

    def _true_ts(self, row):
        return _aware(row.get("_true_write_date") or row["write_date"])

    def _wire(self, row):
        out = {key: value for key, value in row.items() if key != "_true_write_date"}
        out["write_date"] = self._true_ts(row).strftime("%Y-%m-%d %H:%M:%S")
        return out

    def _validate_leaf(self, model, leaf):
        """Reject nested or malformed domain leaves like real Odoo 18."""
        if not isinstance(leaf, (tuple, list)) or len(leaf) != 3:
            raise ValueError(f"Invalid field {model} in leaf {leaf!r}")
        field, operator, value = leaf
        if isinstance(field, str) and field in _PREFIX_OPERATORS:
            raise ValueError(f"Invalid field {model}.{field} in leaf {tuple(leaf)!r}")
        if not isinstance(field, str) or not isinstance(operator, str):
            name = field if isinstance(field, str) else type(field).__name__
            raise ValueError(f"Invalid field {model}.{name} in leaf {tuple(leaf)!r}")

    def _validate_domain(self, model, domain):
        """Validate the domain shape before evaluating it, like the server."""
        if not isinstance(domain, list):
            raise ValueError(f"Invalid domain for {model}: {domain!r}")
        if not domain:
            return
        if isinstance(domain[0], str) and domain[0] in _PREFIX_OPERATORS:
            if len(domain) < 3:
                raise ValueError(f"Malformed flat prefix domain for {model}: {domain!r}")
            for operand in domain[1:]:
                self._validate_leaf(model, operand)
            return
        for leaf in domain:
            if isinstance(leaf, (dict, str)):
                raise ValueError(f"Invalid leaf for {model}: {leaf!r}")
            self._validate_leaf(model, leaf)

    def _eval(self, expr, row):
        field, operator, value = expr
        if field == "write_date":
            actual = self._true_ts(row)
            value = _aware(value)
        elif field == "company_id":
            actual = row.get("company_id")
            actual = actual[0] if isinstance(actual, list) else actual
        else:
            actual = row.get(field)
        if operator == "=":
            return actual == value
        if operator == ">":
            return actual > value
        if operator == ">=":
            return actual >= value
        if operator == "<":
            return actual < value
        if operator == "<=":
            return actual <= value
        raise AssertionError(f"unsupported domain operator: {operator}")

    def _matches(self, row, domain):
        if not domain:
            return True
        if isinstance(domain[0], str) and domain[0] in _PREFIX_OPERATORS:
            operator = domain[0]
            results = [self._eval(operand, row) for operand in domain[1:]]
            return all(results) if operator == "&" else any(results)
        return all(self._eval(leaf, row) for leaf in domain)

    def _sorted(self, rows, order):
        result = list(rows)
        if not order:
            return result
        keys = []
        for part in order.split(","):
            name, direction = part.strip().split()
            keys.append((name, direction == "desc"))
        for name, descending in reversed(keys):
            result = sorted(
                result,
                key=lambda row: self._true_ts(row) if name == "write_date" else row.get(name),
                reverse=descending,
            )
        return result

    def _match(self, model, domain):
        return [row for row in self._store[model] if self._matches(row, domain)]

    def _finish(self, model, rows, order, limit):
        rows = self._sorted(rows, order)
        if limit is not None:
            rows = rows[:limit]
        if self.live:
            self._append_newer(model)
        return [self._wire(row) for row in rows]

    def search_read(self, model, domain, *, fields=None, order=None, limit=None):
        self._validate_domain(model, domain)
        self.calls.append({
            "model": model,
            "domain": _freeze(domain),
            "fields": list(fields or []),
            "order": order,
            "limit": limit,
        })
        if model == self.fail_model:
            raise RuntimeError("injected Odoo read failure")
        return self._finish(model, self._match(model, domain), order, limit)

    def _append_newer(self, model):
        existing = self._store[model]
        if not existing:
            return
        latest = max(self._true_ts(row) for row in existing)
        next_id = max(row["id"] for row in existing) + 1
        template = dict(existing[-1])
        template["id"] = next_id
        template["_true_write_date"] = latest + timedelta(seconds=2)
        template["write_date"] = template["_true_write_date"].strftime("%Y-%m-%d %H:%M:%S")
        self._store[model].append(template)

    def read(self, *args, **kwargs):
        raise AssertionError("complete Odoo reads are outside detection")

    def read_batched(self, *args, **kwargs):
        raise AssertionError("complete Odoo reads are outside detection")


class UnfilteredOdoo(FakeOdoo):
    """Rogue client that ignores the domain so the scanner must fail closed."""

    def _match(self, model, domain):
        return list(self._store[model])
