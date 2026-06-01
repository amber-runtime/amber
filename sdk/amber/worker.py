from __future__ import annotations

import importlib
import sys
from typing import Any


def _load_target(target: str) -> Any:
    module_name, separator, object_name = target.partition(":")
    if not separator or not module_name or not object_name:
        raise ValueError("Worker target must use the format 'module:object'.")

    module = importlib.import_module(module_name)
    try:
        return getattr(module, object_name)
    except AttributeError:
        raise ValueError(
            f"Worker target {target!r} does not exist. "
            f"Could not find {object_name!r} in {module_name!r}."
        ) from None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        raise SystemExit("Usage: python -m amber.worker module:agent_runtime")

    agent_runtime = _load_target(args[0])
    run_worker = getattr(agent_runtime, "run_worker", None)
    if not callable(run_worker):
        raise SystemExit(
            f"Worker target {args[0]!r} must expose a callable run_worker() method."
        )

    run_worker()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
