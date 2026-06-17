"""Guards the load-bearing safety invariant: the orchestrator never touches the
send module. Generation and sending are decoupled, so running a batch can never
mail anyone — this test fails the moment someone wires `send` into the
orchestrator (directly or transitively). NO API calls, no DB, no network.
"""

from __future__ import annotations

import importlib
import sys


def test_orchestrator_does_not_reference_send():
    import orchestrator

    # `send` must not be an attribute of the orchestrator module namespace
    # (i.e. it was never imported there).
    assert not hasattr(orchestrator, "send"), "orchestrator must not import send"


def test_importing_orchestrator_does_not_pull_in_send():
    # Re-import orchestrator with `send` evicted from the module cache; if the
    # orchestrator (or anything it imports) pulled send in, it would reappear.
    # Save/restore so the rest of the suite's module state is untouched.
    saved = {name: sys.modules.get(name) for name in ("send", "orchestrator")}
    try:
        for name in ("send", "orchestrator"):
            sys.modules.pop(name, None)
        importlib.import_module("orchestrator")
        assert "send" not in sys.modules, (
            "importing orchestrator must not import send, directly or transitively"
        )
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)
