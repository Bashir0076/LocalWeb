"""
Runtime state management for the crawler.
This module handles all runtime statistics and state that are updated during crawling.
These values are managed internally and not meant to be modified by users.
"""
import time
import threading
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class CrawlerState:
    """Thread-safe runtime state for the crawler."""
    
    # Request tracking
    total_requests: int = 0
    successful_requests: list[httpx.URL] = field(default_factory=list)
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
    fetched_urls: dict = field(default_factory=dict)  # {url: url-after-redirects}
    
    # Cookies
    cookies: dict = field(default_factory=dict)

    # Start time for the crawler (set when crawl begins)
    start_time: float = 0.0

    
    # Lock for thread-safe operations
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def increment_request(self, url: httpx.URL, response_url: httpx.URL | None = None):
        """Thread-safe increment of total requests."""
        with self._lock:
            self.total_requests += 1
            self.successful_requests.append(url)
            self.fetched_urls[str(url)] = str(response_url or url)
    
    def increment_status_error(self, url: httpx.URL):
        """Thread-safe increment of status errors."""
        with self._lock:
            self.status_error_requests.append(url)
    
    def increment_request_error(self, url: httpx.URL):
        """Thread-safe increment of request errors."""
        with self._lock:
            self.request_error_requests.append(url)
    
    def increment_other_error(self, url: httpx.URL):
        """Thread-safe increment of other errors."""
        with self._lock:
            self.other_error_requests.append(url)
    
    def update_cookies(self, new_cookies: dict):
        """Thread-safe cookie update."""
        with self._lock:
            self.cookies.update(new_cookies)
    
    def increment_html(self):
        with self._lock:
            self.html_downloaded += 1
    
    def increment_media(self):
        with self._lock:
            self.media_downloaded += 1
    
    def increment_javascript(self):
        with self._lock:
            self.javascript_downloaded += 1
    
    def increment_css(self):
        with self._lock:
            self.css_downloaded += 1
    
    def increment_others(self):
        with self._lock:
            self.others_downloaded += 1
    
    def reset(self):
        """Reset all state for a new crawl session."""
        with self._lock:
            self.total_requests = 0
            self.successful_requests.clear()
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
    
    @property
    def failed_requests(self) -> list[httpx.URL]:
        """Return all failed requests."""
        with self._lock:
            return (self.status_error_requests + 
                    self.request_error_requests + 
                    self.other_error_requests)
    
    @property
    def total_downloads(self) -> int:
        """Return total number of downloaded files."""
        with self._lock:
            return (self.html_downloaded + self.javascript_downloaded +
                    self.css_downloaded + self.media_downloaded)


# Global state instance
state = CrawlerState()
state.start_time = time.time()

