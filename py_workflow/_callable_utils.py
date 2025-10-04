from __future__ import annotations

import inspect
from typing import Any, Callable, Iterable, Optional, Sequence


def call_with_optional_helper(
    func: Callable[..., Any],
    args: Sequence[Any],
    helper: Optional[Any],
    base_arg_count: int,
) -> Any:
    if helper is None:
        return func(*args)

    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):  # pragma: no cover - builtins or C funcs
        return func(*args, helper)

    params = sig.parameters.values()
    if any(
        p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for p in params
    ):
        return func(*args, helper)

    positional = [
        p
        for p in params
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]

    if len(positional) >= base_arg_count + 1:
        return func(*args, helper)

    return func(*args)
