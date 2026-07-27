from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any


ActionCallback = Callable[..., None]
FilterCallback = Callable[..., Any]


class HookRegistry:
    """WordPress-style actions and filters for plugins."""

    def __init__(self) -> None:
        self._actions: dict[str, list[tuple[int, ActionCallback]]] = defaultdict(list)
        self._filters: dict[str, list[tuple[int, FilterCallback]]] = defaultdict(list)

    def clear(self) -> None:
        self._actions.clear()
        self._filters.clear()

    def add_action(self, hook: str, callback: ActionCallback, priority: int = 10) -> None:
        self._actions[hook].append((priority, callback))
        self._actions[hook].sort(key=lambda item: item[0])

    def do_action(self, hook: str, *args: Any, **kwargs: Any) -> None:
        for _, callback in self._actions.get(hook, []):
            callback(*args, **kwargs)

    def add_filter(self, hook: str, callback: FilterCallback, priority: int = 10) -> None:
        self._filters[hook].append((priority, callback))
        self._filters[hook].sort(key=lambda item: item[0])

    def apply_filters(self, hook: str, value: Any, *args: Any, **kwargs: Any) -> Any:
        result = value
        for _, callback in self._filters.get(hook, []):
            result = callback(result, *args, **kwargs)
        return result
