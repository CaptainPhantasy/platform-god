"""
Platform God Registry Module.

Provides persistent storage for tracked entities and system state.
"""

__all__ = [
    "Registry",
    "EntityOperation",
    "EntityRecord",
    "RegistryIndex",
]

from platform_god.registry.storage import (
    EntityOperation,
    EntityRecord,
    Registry,
    RegistryIndex,
)
