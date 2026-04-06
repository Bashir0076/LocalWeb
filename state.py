"""
LocalWeb runtime state management.
This module handles all runtime statistics and state that are updated during crawling.
These values are managed internally and not meant to be modified by users.
"""
import time
import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class CrawlerState:
    """Async-safe runtime state for the crawler."""
    
    # Request tracking
    total_successful_requests: int = 0
    status_error_requests: list[httpx.URL] = field(default_factory=list)
    request_error_requests: list[httpx.URL] = field(default_factory=list)
    other_error_requests: list[httpx.URL] = field(default_factory=list)
    
    # Download tracking
    html_downloaded: int = 0
    media_downloaded: int = 0
    javascript_downloaded: int = 0
    css_downloaded: int = 0
    others_downloaded: int = 0
    
    # URL tracking
    fetched_urls: set = field(default_factory=set)
    
    # Cookies
    cookies: dict = field(default_factory=dict)

    # Start time for the crawler (set when crawl begins)
    start_time: float = 0.0

    # Lock for async-safe operations
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    
    async def increment_request(self, url: httpx.URL, response_url: httpx.URL | None = None):
        """Async-safe increment of total requests."""
        async with self._lock:
            self.total_successful_requests += 1
            self.fetched_urls.add(str(url))
            if response_url:
                self.fetched_urls.add(str(response_url))
    
    async def increment_status_error(self, url: httpx.URL):
        """Async-safe increment of status errors."""
        async with self._lock:
            self.status_error_requests.append(url)
    
    async def increment_request_error(self, url: httpx.URL):
        """Async-safe increment of request errors."""
        async with self._lock:
            self.request_error_requests.append(url)
    
    async def increment_other_error(self, url: httpx.URL):
        """Async-safe increment of other errors."""
        async with self._lock:
            self.other_error_requests.append(url)
    
    async def update_cookies(self, new_cookies: dict):
        """Async-safe cookie update."""
        async with self._lock:
            self.cookies.update(new_cookies)
    
    async def increment_html(self):
        async with self._lock:
            self.html_downloaded += 1
    
    async def increment_media(self):
        async with self._lock:
            self.media_downloaded += 1
    
    async def increment_javascript(self):
        async with self._lock:
            self.javascript_downloaded += 1
    
    async def increment_css(self):
        async with self._lock:
            self.css_downloaded += 1
    
    async def increment_others(self):
        async with self._lock:
            self.others_downloaded += 1
    
    async def reset(self):
        """Reset all state for a new crawl session."""
        async with self._lock:
            self.total_successful_requests = 0
            self.status_error_requests.clear()
            self.request_error_requests.clear()
            self.other_error_requests.clear()
            self.html_downloaded = 0
            self.media_downloaded = 0
            self.javascript_downloaded = 0
            self.css_downloaded = 0
            self.others_downloaded = 0
            self.fetched_urls.clear()
            self.cookies.clear()
    
    async def get_failed_requests(self) -> list[httpx.URL]:
        """Return all failed requests."""
        async with self._lock:
            return (self.status_error_requests + 
                    self.request_error_requests + 
                    self.other_error_requests)
    
    async def get_total_downloads(self) -> int:
        """Return total number of downloaded files."""
        async with self._lock:
            return (self.html_downloaded + self.javascript_downloaded +
                    self.css_downloaded + self.media_downloaded)

    # Synchronous properties for backward compatibility (read-only, no lock needed)
    @property
    def failed_requests(self) -> list[httpx.URL]:
        """Return all failed requests (synchronous, use with caution in async context)."""
        return (self.status_error_requests + 
                self.request_error_requests + 
                self.other_error_requests)
    
    @property
    def total_downloads(self) -> int:
        """Return total number of downloaded files (synchronous, use with caution)."""
        return (self.html_downloaded + self.javascript_downloaded +
                self.css_downloaded + self.media_downloaded)


# Global state instance
state = CrawlerState()
state.start_time = time.time()