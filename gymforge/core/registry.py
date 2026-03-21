"""Environment registry with versioning support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from gymforge.core.environment import BaseEnvironment
    from gymforge.core.task import TaskSpec


class _RegistryEntry:
    __slots__ = ("cls", "version")

    def __init__(self, cls: Type["BaseEnvironment"], version: str) -> None:
        self.cls = cls
        self.version = version


class EnvironmentRegistry:
    """Registry that maps string names to environment classes.

    Supports multiple versions of the same environment name. The latest
    registered version is returned by default.
    """

    def __init__(self) -> None:
        self._entries: dict[str, list[_RegistryEntry]] = {}

    def register(
        self,
        name: str,
        cls: Type["BaseEnvironment"],
        version: str = "v1",
    ) -> None:
        """Register an environment class under *name* with *version*.

        Raises ``ValueError`` if the same (name, version) pair is already
        registered.
        """
        if name not in self._entries:
            self._entries[name] = []
        for entry in self._entries[name]:
            if entry.version == version:
                raise ValueError(
                    f"Environment '{name}' version '{version}' is already registered."
                )
        self._entries[name].append(_RegistryEntry(cls=cls, version=version))

    def make(
        self,
        name: str,
        task_spec: "TaskSpec",
        version: str | None = None,
        **kwargs,
    ) -> "BaseEnvironment":
        """Instantiate an environment by *name*.

        If *version* is ``None``, the most recently registered version is used.
        Passes extra *kwargs* to the environment constructor.
        """
        if name not in self._entries or not self._entries[name]:
            raise KeyError(f"No environment registered under name '{name}'.")

        entries = self._entries[name]
        if version is None:
            entry = entries[-1]
        else:
            matches = [e for e in entries if e.version == version]
            if not matches:
                raise KeyError(
                    f"Environment '{name}' version '{version}' not found. "
                    f"Available: {[e.version for e in entries]}"
                )
            entry = matches[0]

        return entry.cls(task_spec, **kwargs)

    def list(self) -> list[dict]:
        """Return all registered (name, version, cls) triples as dicts."""
        result = []
        for name, entries in self._entries.items():
            for e in entries:
                result.append({"name": name, "version": e.version, "cls": e.cls.__name__})
        return result


# Global default registry
registry = EnvironmentRegistry()


def register(name: str, cls: Type["BaseEnvironment"], version: str = "v1") -> None:
    """Register an environment in the global registry."""
    registry.register(name, cls, version)


def make(name: str, task_spec: "TaskSpec", version: str | None = None, **kwargs) -> "BaseEnvironment":
    """Instantiate an environment from the global registry."""
    return registry.make(name, task_spec, version, **kwargs)
