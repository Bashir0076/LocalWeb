"""
LocalWeb utility classes and functions.
"""
import os
from dataclasses import dataclass


@dataclass
class Scope:
    """Defines a URL scope for crawling with depth limits."""
    
    url: str
    max_depth: int = 0  # 0 means infinite
    
    @property
    def normalized_url(self) -> str:
        """Return URL without trailing slash for consistent comparison."""
        return self.url.rstrip('/')


class Queue:
    """Simple classic FIFO queue with optional duplicate prevention."""
    
    def __init__(self, *items, no_repeat: bool = False) -> None:
        self._list = list(items)
        self.no_repeat = no_repeat
        if self.no_repeat:
            # Remove duplicates while preserving order
            seen = set()
            unique_items = []
            for item in self._list:
                if item not in seen:
                    seen.add(item)
                    unique_items.append(item)
            self._list = unique_items

    def __len__(self):
        return len(self._list)

    def put(self, item):
        """Add an item to the end of the queue."""
        if self.no_repeat and item in self._list:
            return
        self._list.append(item)

    def get(self):
        """Returns the first item in the queue, or raises IndexError if empty."""
        if not self._list:
            raise IndexError("Queue is empty")
        return self._list.pop(0)

    def get_size(self):
        return len(self._list)

    def has(self, item):
        """Returns True if the item is in the queue."""
        return item in self._list

    def clear(self):
        """Clear all items from the queue."""
        self._list.clear()


def get_relative_path(from_path: str, to_path: str) -> str:
    """Calculate relative path from one path to another.

    Args:
        from_path: The source path (e.g., '/docs/guide/index.html')
        to_path: The target path (e.g., '/docs/api/reference')

    Returns:
        str: The relative path (e.g., '../../api/reference')
    """
    return os.path.relpath(to_path, from_path)
