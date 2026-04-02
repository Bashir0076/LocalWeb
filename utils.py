"""
LocalWeb utility classes and functions.
"""
import os
from collections import deque
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
    """FIFO queue with optional duplicate prevention.
    
    When no_repeat=True, items that have ever been added to the queue
    cannot be added again, even after being dequeued. This is essential
    for crawlers to avoid visiting the same URL twice.
    
    Uses a deque internally for O(1) popleft instead of list.pop(0) which is O(n).
    Uses a set for O(1) membership checks instead of list.__contains__ which is O(n).
    """
    
    def __init__(self, *items, no_repeat: bool = False) -> None:
        self.no_repeat = no_repeat
        self._seen: set = set()
        self._deque: deque = deque()

        for item in items:
            if self.no_repeat:
                if item not in self._seen:
                    self._seen.add(item)
                    self._deque.append(item)
            else:
                self._deque.append(item)

    def __len__(self) -> int:
        return len(self._deque)

    def put(self, item) -> None:
        """Add an item to the end of the queue.
        
        If no_repeat=True, silently skips items that have ever been seen.
        """
        if self.no_repeat and item in self._seen:
            return
        self._deque.append(item)
        self._seen.add(item)

    def get(self):
        """Remove and return the first item in the queue.
        
        Note: With no_repeat=True, dequeued items remain in the _seen set,
        preventing them from being re-added. This is by design for crawler
        use cases where each URL should only be visited once.
        
        Raises:
            IndexError: If the queue is empty.
        """
        if not self._deque:
            raise IndexError("Queue is empty")
        return self._deque.popleft()

    def get_size(self) -> int:
        """Return the number of items currently in the queue."""
        return len(self._deque)

    def has(self, item) -> bool:
        """Return True if the item has ever been added (when no_repeat=True)
        or is currently in the queue."""
        return item in self._seen

    def clear(self) -> None:
        """Clear all items from the queue and the seen set."""
        self._deque.clear()
        self._seen.clear()


def get_relative_path(from_path: str, to_path: str) -> str:
    """Calculate relative path from one path to another.

    Args:
        from_path: The source path (e.g., '/docs/guide/index.html')
        to_path: The target path (e.g., '/docs/api/reference')

    Returns:
        str: The relative path (e.g., '../../api/reference')
    """
    return os.path.relpath(to_path, from_path)
