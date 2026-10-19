"""Harness registry. Adding a harness = one adapter class + one line here + a Dockerfile."""
from .base import HarnessAdapter


def get_adapter(name: str) -> HarnessAdapter:
    """Return a new adapter for the harness called ``name``; raises KeyError for an unknown name.

    Adapters are imported inside the branches on purpose: each one may need a package that only exists in its
    own harness image (for example Hermes), so importing them all up front would break the other images.
    """
    # pylint: disable=import-outside-toplevel
    if name == "baseline":
        from .baseline import BaselineAdapter
        return BaselineAdapter()
    if name == "hermes":
        from .hermes import HermesAdapter
        return HermesAdapter()
    if name == "claude-code":
        from .claude_code import ClaudeCodeAdapter
        return ClaudeCodeAdapter()
    raise KeyError(f"unknown harness {name!r}")
