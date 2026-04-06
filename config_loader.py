"""
LocalWeb configuration loader.
Loads user-configurable settings from config.json.
"""
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

import httpx

from utils import Scope


logger = logging.getLogger(__name__)


@dataclass
class CrawlerConfig:
    """Configuration class for the LocalWeb crawler.

    This dataclass holds all configurable settings for the crawler, including URLs, scopes,
    delays, concurrency limits, and content type allowances. Settings can be loaded from
    a JSON file or set programmatically.
    """
    start_url: str | httpx.URL = "http://example.com"
    output_directory: str = "./output/"
    start_url_as_scope: bool = True
    allowed_html_scopes: list[Scope] | None = None
    blocked_html_scopes: list[Scope] = field(default_factory=list)
    allowed_iframe_scopes: list[Scope] | None = None
    delay: int = 3
    max_tries: int = 30
    max_concurrency: int = 10
    depth: int = None
    allow_javascript: bool = True
    remove_javascript: bool = False
    allow_images: bool = True
    allow_videos: bool = True
    allow_iframe: bool = True
    allow_data_protocol: bool = False
    allow_other_link_elements: bool = False
    report_files_directory: str = "./scraping-reports/"

    def __post_init__(self):
        if self.start_url_as_scope and self.allowed_html_scopes is None:
            self.allowed_html_scopes = [Scope(self.start_url, 0)]

    def load_from_json(self, json_path: str = "./config.json"):
        logger.debug(f"starting to load config from {json_path}")
        data: dict = {}
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                logger.info(f"Configuration loaded from {json_path}")
        except FileNotFoundError as e:
            logger.error(f"Configuration file not found: {json_path}")
            logger.error(f"{e} Traceback: " + ''.join(
                    traceback.format_exception(type(e), e, e.__traceback__))
                )
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}")
            logger.error(f"{e} Traceback: " + ''.join(
                traceback.format_exception(type(e), e, e.__traceback__))
            )
            raise        

        self.start_url = (data.get("start_url") 
            if data.get("start_url") else self.start_url
        )
        self.start_url_as_scope = (data.get("start_url_as_scope") 
            if data.get("start_url_as_scope") else self.start_url_as_scope
        )
        self.output_directory = (data.get("output_directory") 
            if data.get("output_directory") else self.output_directory
        )
        self.delay = (data.get("delay") 
            if data.get("delay") else self.delay
        )
        self.max_tries = (data.get("max_tries") 
            if data.get("max_tries") else self.max_tries
        )
        self.max_concurrency = (data.get("max_concurrency")
            if data.get("max_concurrency") else self.max_concurrency
        )
        self.depth = (data.get("depth")
            if data.get("depth") else self.depth
        )
        self.allow_javascript = (data.get("allow_javascript")
            if data.get("allow_javascript") else self.allow_javascript
        )
        self.remove_javascript = (data.get("remove_javascript")
            if data.get("remove_javascript") else self.remove_javascript
        )
        self.allow_images = (data.get("allow_images")
            if data.get("allow_images") else self.allow_images
        )
        self.allow_videos = (data.get("allow_videos")
            if data.get("allow_videos") else self.allow_videos
        )
        self.allow_iframe = (data.get("allow_iframe")
            if data.get("allow_iframe") else self.allow_iframe
        )
        self.allow_data_protocol = (data.get("allow_data_protocol")
            if data.get("allow_data_protocol") else self.allow_data_protocol
        )
        self.allow_other_link_elements = (
            data.get("allow_other_link_elements")
            if data.get("allow_other_link_elements") 
            else self.allow_other_link_elements
        )
        self.report_files_directory = (data.get("report_files_directory")
            if data.get("report_files_directory") else self.report_files_directory
        )
        self.blocked_html_scopes= (_get_scope_list(data.get("blocked_html_scopes"))
            if data.get("blocked_html_scopes") else self.blocked_html_scopes
        )
        self.allowed_html_scopes = (_get_scope_list(data.get("allowed_html_scopes"))
            if data.get("allowed_html_scopes") else self.allowed_html_scopes
        )
        self.allowed_iframe_scopes = (_get_scope_list(data.get("allowed_iframe_scopes"))
            if data.get("allowed_iframe_scopes") else self.allowed_iframe_scopes
        )

        logger.info(f"loaded from {json_path} successfully")


def _get_scope_list(scope_data: list[dict]):
    scopes : list[Scope] = []
    for data in scope_data:
        try:
            url = data["url"]
            max_depth = data["max_depth"]
        except KeyError as err:
            logger.critical(f"JSON file scope definition wrong, can't get 'url' and 'max_depth' from '{data}'")
            logger.critical(f"{e} Traceback: " + ''.join(
                    traceback.format_exception(type(e), e, e.__traceback__))
                )
            raise err
        scopes.append(Scope(url, max_depth))

    return scopes
