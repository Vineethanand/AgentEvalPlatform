"""Harness registry. Adding a harness = one adapter class + one line here + a Dockerfile."""
from .base import HarnessAdapter


def get_adapter(name: str) -> HarnessAdapter:
    if name == "baseline":
        from .baseline import BaselineAdapter
        return BaselineAdapter()
    if name == "hermes":
        from .hermes import HermesAdapter
        return HermesAdapter()
    raise KeyError(f"unknown harness {name!r}")
