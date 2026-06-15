"""Adapter registration.

A clone registers its :class:`~assay_engine.contracts.study.StudyDefinition` factory under a
name; the engine looks it up to run. This is the only place adapters and the engine meet by
name, and even here the engine holds only a factory callable — it imports no adapter module
itself (ARCHITECTURE.md §3). The instance repository imports the engine, builds its study,
and registers it.
"""

from __future__ import annotations

import threading
from typing import Callable, Dict

from assay_engine.contracts.study import StudyDefinition

StudyFactory = Callable[[], StudyDefinition]

_REGISTRY: Dict[str, StudyFactory] = {}
# Registration is normally a one-shot import-time op, but the check-then-act duplicate guard
# is a TOCTOU; a lock makes it atomic if studies are ever registered concurrently (issue #13).
_LOCK = threading.Lock()


def register_study(name: str, factory: StudyFactory) -> None:
    """Register a study factory under ``name``. Raises on duplicate names."""
    with _LOCK:
        if name in _REGISTRY:
            raise ValueError(f"a study named {name!r} is already registered")
        _REGISTRY[name] = factory


def get_study(name: str) -> StudyDefinition:
    """Instantiate the registered study ``name``."""
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise KeyError(f"no study registered under {name!r}") from None
    return factory()


def registered_studies() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def clear_registry() -> None:
    """Test helper: drop all registrations."""
    with _LOCK:
        _REGISTRY.clear()
