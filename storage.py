"""
LocalWeb storage functionality.
Handles saving responses to disk and generating reports.
"""
import asyncio
import datetime
import logging
import os
import time
import json
import pprint
import traceback
from typing import TYPE_CHECKING

import httpx

from config_loader import CrawlerConfig
from state import CrawlerState
import html_processor
import utils

if TYPE_CHECKING:
    import state


logger = logging.getLogger(__name__)


def _is_media(response: httpx.Response):
    media_extensions = {
        '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.mp4', 
        '.webm', '.ogg', '.mp3', '.wav', '.pdf','.zip', '.tar', '.gz', '.rar',
        '.exe', '.dmg', '.pkg', '.deb', '.rpm'
        }
    content_type = response.headers.get("content-type").strip().lower()

    if ("image" in content_type or "video" in content_type 
            or response.url.path.endswith(media_extensions)
            ):
        return True

    return False


def _is_html(response: httpx.Response):
    content_type = response.headers["content-type"].lower().strip()
    if "text/html" in content_type or response.url.path.endswith((".html", ".htm")):
        return True

    return False


def _is_css(response: httpx.Response):
    content_type = response.headers["content-type"].lower().strip()
    if "css" in content_type or response.url.path.endswith(".css"):
        return True

    return False


def _is_javascript(response: httpx.Response):
    content_type = response.headers["content-type"].lower().strip()
    if "javascript" in content_type or response.url.path.endswith(".js"):
        return True

    return False


def _write_binary_file(path: str, content: bytes) -> None:
    """Write binary content to a file (blocking I/O, run in executor)."""
    with open(path, "wb") as f:
        f.write(content)
    
async def save_response(
        response: httpx.Response,
        async_http_client: httpx.AsyncClient,
        cfg: CrawlerConfig,
        state: CrawlerState,
        queued_urls: utils.Queue,
        media_queued_urls: utils.Queue
    ) -> None:
    """Save an HTTP response to the local filesystem, organizing files by domain and path.

    This function saves the response content to a directory structure that mirrors
    the URL structure (e.g., example.com/path/to/page). For HTML pages, it processes
    the content to convert links to local relative paths and extracts new URLs to
    add to the crawl queues. It also fetches and saves associated JS and CSS resources.

    Args:
        response: The httpx.Response object containing the page content to save.
        async_http_client: The async HTTP client to use.
        cfg: CrawlerConfig instance with settings.
        state: CrawlerState instance for tracking downloads.
        queued_urls: Queue for discovered HTML URLs.
        media_queued_urls: Queue for discovered media URLs.

    Returns:
        None. Files are written to the local filesystem.
    """
    host = response.url.host
    path = response.url.path

    # If the URL is a directory (no extension), add index.html
    if '.' not in path.split('/')[-1]:
        path = path + "/index.html"

    # Create the directory structure (async-safe)
    file_path = (f"{cfg.output_directory.strip(os.sep)}"
                 f"{os.sep}{host}{os.sep}{path.strip('/')}"
                )
    logger.debug(f"Creating directory structure for: {file_path}")
    await asyncio.to_thread(os.makedirs, os.path.dirname(file_path), exist_ok=True)

    logger.info(f"Saving response from {response.url} to {file_path}")

    content = response.content
    
    # Convert links to local paths if it's HTML
    if _is_html(response):
        content = html_processor.make_links_local(response, cfg, queued_urls, media_queued_urls)
        await state.increment_html()
        logger.debug(f"Converted links to local paths for {response.url}")

    elif _is_javascript(response):
        await state.increment_javascript()

    elif _is_css(response):
        await state.increment_css()

    elif _is_media(response):
        await state.increment_media()

    else:
        await state.increment_others()

    await asyncio.to_thread(_write_binary_file, file_path, response.content)

    logger.info(f"Successfully saved content to {file_path}")

    # Fetch JS and CSS resources if it's HTML
    if _is_html(response):
        await html_processor.fetch_js_css_resources(
            response= response,
            async_http_client= async_http_client,
            cfg= cfg,
            state= state,
            cookies= dict(state.cookies),
            queued_urls= queued_urls,
            media_queued_urls= media_queued_urls
        )


def generate_report(
        cfg: CrawlerConfig, state: CrawlerState, 
        title_suffix: str = "", exception: Exception | None = None
    ):
    """Generate a scraping report with statistics.

    Args:
        title_suffix: Optional suffix to add to the report title.
    """
    logger.debug("Generating report")

    utc_iso_time = datetime.datetime.now(datetime.UTC).isoformat()

    report_message = (
        "____________________________________________________\n"
        f"# Scraping Report {utc_iso_time}\n"
        f"{title_suffix}\n"
        "____________________________________________________\n"
        "## Requests report:\n"
        f"- total successful requests: {state.total_successful_requests}\n"
        f"- failed requests: {len(state.failed_requests)}\n"
        f"- status-error: {len(state.status_error_requests)}\n"
        f"- request-error: {len(state.request_error_requests)}\n"
        f"- other-request-errors: {len(state.other_error_requests)}\n"
        f"- cookies: {state.cookies}\n"
        "____________________________________________________\n"
        "## Storage Report:\n"
        f"- total saved file: {state.total_downloads}\n"
        f"- media saved: {state.media_downloaded}\n"
        f"- html saved: {state.html_downloaded}\n"
        f"- css saved: {state.css_downloaded}\n"
        f"- javascript saved: {state.javascript_downloaded}\n"
        "____________________________________________________\n"
        f"### output directory: {cfg.output_directory}\n"
        f"### total runtime: {int(time.time() - state.start_time)} seconds\n"
        "____________________________________________________\n"
        f"## configurations in dictionary format:\n"
        f"```python\n{pprint.pformat(cfg.__dict__)}\n```\n"
        "____________________________________________________\n"
        f"### Error Traceback:\n"
        f"{exception} Traceback: " + "".join(traceback.format_exception(type(exception), exception, exception.__traceback__)) + "\n" if exception is not None else "None\n"
        "____________________________________________________\n"        
    )

    # Create ISO-safe filename
    timestamp = utc_iso_time.replace(':', '-')
    title_suffix_clean = title_suffix.replace(' ', '_').replace(':', '-')
    report_filename = f"scraping-report_{timestamp} {title_suffix_clean}.md"

    report_file_path = os.path.join(cfg.report_files_directory, report_filename)

    os.makedirs(cfg.report_files_directory, exist_ok=True)
    with open(report_file_path, "w") as f:
        f.write(report_message)

    logger.info(f"Report generated at {report_file_path}")
