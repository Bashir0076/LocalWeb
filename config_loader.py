"""
Configuration loader for the crawler.
Loads user-configurable settings from config.json.
"""
import json
import logging
from pathlib import Path
from typing import Any

from utils import Scope


logger = logging.getLogger(__name__)


class Config:
    """Configuration manager that loads settings from config.json."""
    
    def __init__(self, config_path: str = "config.json"):
        self._config_path = Path(config_path)
        self._data: dict[str, Any] = {}
        self._scopes_cache: dict[str, Scope] = {}
        self.load()
    
    def load(self):
        """Load configuration from JSON file."""
        try:
            with open(self._config_path, 'r') as f:
                self._data = json.load(f)
            logger.info(f"Configuration loaded from {self._config_path}")
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self._config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}")
            raise
    
    def save(self):
        """Save current configuration to JSON file."""
        with open(self._config_path, 'w') as f:
            json.dump(self._data, f, indent=4)
        logger.info(f"Configuration saved to {self._config_path}")
    
    def _get_scope(self, url: str, max_depth: int) -> Scope:
        """Get or create a Scope object, caching for reuse."""
        key = f"{url}:{max_depth}"
        if key not in self._scopes_cache:
            self._scopes_cache[key] = Scope(url, max_depth)
        return self._scopes_cache[key]
    
    # Boolean settings
    @property
    def remove_javascript(self) -> bool:
        return self._data.get("remove_javascript", False)
    
    @property
    def allow_javascript(self) -> bool:
        return self._data.get("allow_javascript", True)
    
    @property
    def allow_videos(self) -> bool:
        return self._data.get("allow_videos", True)
    
    @property
    def allow_images(self) -> bool:
        return self._data.get("allow_images", True)
    
    @property
    def allow_data_protocol(self) -> bool:
        return self._data.get("allow_data_protocol", False)
    
    @property
    def allow_iframe(self) -> bool:
        return self._data.get("allow_iframe", True)
    
    @property
    def allow_other_link_elements(self) -> bool:
        return self._data.get("allow_other_link_elements", False)
    
    # Path settings
    @property
    def save_directory(self) -> str:
        return self._data.get("save_directory", "./output/")
    
    @property
    def report_files_directory(self) -> str:
        return self._data.get("report_files_directory", "./")
    
    @property
    def start_page_url(self) -> str:
        return self._data.get("start_page_url", "")
    
    # Scope settings - returns processed Scope objects
    @property
    def allowed_html_scopes(self) -> list[Scope] | None:
        scopes_data = self._data.get("allowed_html_scopes")
        if scopes_data is None:
            return None
        return [
            self._get_scope(s["url"], s.get("max_depth", 0))
            for s in scopes_data
        ]
    
    @property
    def blocked_scopes(self) -> list[Scope]:
        scopes_data = self._data.get("blocked_scopes", [])
        return [
            self._get_scope(s["url"], s.get("max_depth", 0))
            for s in scopes_data
        ]
    
    @property
    def allowed_iframe_scopes(self) -> list[Scope] | None:
        scopes_data = self._data.get("allowed_iframe_scopes")
        if scopes_data is None:
            return None
        return [
            self._get_scope(s["url"], s.get("max_depth", 0))
            for s in scopes_data
        ]


# Default config instance
config = Config()
