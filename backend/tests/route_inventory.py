"""Every HTTP route of the app with its method, path and dependency tree, whatever the FastAPI version.

FastAPI >= 0.140 wraps included routers (``app.routes`` holds ``_IncludedRouter`` objects): iterating
``app.routes`` then finds no route at all, and a security test written that way passes without
checking anything (found by the security tests of 22/10/2026)."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


@dataclass
class RouteInfo:
    path: str
    methods: set[str]
    dependant: Any


def iter_routes(app) -> Iterator[RouteInfo]:
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is not None:  # FastAPI >= 0.140
            for ctx in contexts():
                yield RouteInfo(ctx.path, set(ctx.methods or ()), ctx.dependant)
        elif getattr(route, "dependant", None) is not None:
            yield RouteInfo(route.path, set(route.methods or ()), route.dependant)


def dependency_calls(dependant) -> set:
    calls, stack = set(), [dependant]
    while stack:
        d = stack.pop()
        calls.add(d.call)
        stack.extend(d.dependencies)
    return calls
