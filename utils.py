"""
LocalWeb utility classes and functions.
"""
import os
from collections import deque
from dataclasses import dataclass
import httpx


@dataclass
class Scope:
    """Defines a URL scope for crawling with depth limits.
    Args:
        url: the scope url that we should only scrape urls under it (NOTE: the
            url must include the protocol like "https://" or "http://")
        max_depth: the max depth of the url path to limit crawling too far;
            if `max_depth <= 0` then there is no depth limit.
    """

    url: httpx.URL
    max_depth: int = 0  # 0 means infinite
    def __post_init__(self):
        if isinstance(self.url, str):
            self.url = httpx.URL(self.url)

class Queue:
    """FIFO queue with optional duplicate prevention.
    
    When no_repeat=True, items that have ever been added to the queue
    cannot be added again, even after being dequeued. This is essential
    for crawlers to avoid visiting the same URL twice.
    
    Uses a deque internally for O(1) popleft instead of list.pop(0) which is O(n).
    Uses a set for O(1) membership checks instead of list.__contains__ which is O(n).
    """
    
    def __init__(self, *items, no_repeat: bool = False, load_from_file: str | None = None, save_file: str | None = None) -> None:
        self.no_repeat = no_repeat
        self._seen: set = set()
        self._deque: deque = deque()
        self._save_file = None

        if save_file:
            os.makedirs(os.path.dirname(save_file), exist_ok=True)
            self._save_file = open(save_file, 'a')
        
        for item in items:
            self.put(item)

        # If load_from_file is provided, load items from the file. The file can contain lines of the form:
        # - "item_value" to add an item to the queue
        # - "DEQUEUED: item_value" to indicate that an item was dequeued (and should be removed from the queue and seen set)
        if load_from_file:
            os.makedirs(os.path.dirname(load_from_file), exist_ok=True)
            try:
                with open(load_from_file, 'r') as f:
                    data = f.readlines()
            except FileNotFoundError:
                logger.warning(f"Load file not found: {load_from_file}. Starting with an empty queue.")
                pass
            for item in data:
                if item.startswith("DEQUEUED: "):
                    dequeued_item = item[len("DEQUEUED: "):].strip()
                    if self._deque.count(dequeued_item) > 0:
                        self._deque.remove(dequeued_item)
                        self._seen.discard(dequeued_item)
                        self._save_file.write(f"DEQUEUED: {dequeued_item}\n")
                    continue
                self.put(item)


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
        if self._save_file:
            self._save_file.write(f"{item}\n")

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
        item = self._deque.popleft()
        if self._save_file:
            self._save_file.write(f"DEQUEUED: {item}\n")
        return item
    
    def close_save_file(self):        
        """Close the save file if it was opened."""
        if self._save_file:
            self._save_file.flush() 
            self._save_file.close()

    def __del__(self):
        """Ensure the save file is closed when the Queue is garbage collected."""
        self.close_save_file()

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
