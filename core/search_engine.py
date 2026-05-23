from __future__ import annotations

from datetime import datetime

from core.models import LauncherItem


class SearchEngine:
    def search(self, items: list[LauncherItem], query: str) -> list[LauncherItem]:
        normalized = query.strip().lower()
        if not normalized:
            return self._sort_usage(items)

        scored: list[tuple[tuple[int, int, int], LauncherItem]] = []
        for item in items:
            score = self._score_item(item, normalized)
            if score is not None:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0])
        return [item for _, item in scored]

    def find_exact(self, items: list[LauncherItem], query: str) -> LauncherItem | None:
        normalized = query.strip().lower()
        for item in items:
            if item.command_name.lower() == normalized:
                return item
        return None

    def _score_item(self, item: LauncherItem, query: str) -> tuple[int, int, int] | None:
        aliases = [alias.lower() for alias in item.aliases]
        name = item.name.lower()
        command_name = item.command_name.lower()

        if command_name == query:
            rank = 0
        elif command_name.startswith(query):
            rank = 1
        elif any(alias.startswith(query) for alias in aliases):
            rank = 2
        elif name.startswith(query):
            rank = 3
        elif query in command_name or query in name or any(query in alias for alias in aliases):
            rank = 4
        else:
            return None

        return (rank, -item.usage_count, -self._last_used_value(item.last_used))

    def _sort_usage(self, items: list[LauncherItem]) -> list[LauncherItem]:
        return sorted(items, key=lambda item: (-item.usage_count, -self._last_used_value(item.last_used), item.name.lower()))

    def _last_used_value(self, value: str) -> int:
        if not value:
            return 0
        try:
            return int(datetime.fromisoformat(value).timestamp())
        except ValueError:
            return 0
