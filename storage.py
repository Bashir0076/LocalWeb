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
from typing import TYPE_CHECKING

import httpx

import config_loader
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
            or path.endswith(media_extensions)
            ):
        return True

    return False


def _is_html(response: httpx.Response):
    if "text/html" in content_type or path.endswith((".html", ".htm")):
        return True

    return False


def _is_css(response: httpx.Response):
    if "css" in content_type or path.endswith(".css"):
        return True

    return False


def _is_javascript(response: httpx.Response):
    if "javascript" in content_type or path.endswith(".js"):
        return True

    return False


def _write_binary_file(path: str, content: bytes) -> None:
    """Write binary content to a file (blocking I/O, run in executor)."""
    with open(path, "wb") as f:
        f.write(content)
    

async def save_response(
        response: httpx.Response,
        async_http_client: httpx.AsyncClient,
        save_directory: str,
        state_obj: 'state.CrawlerState',
        queued_urls: utils.Queue,
        media_queued_urls: utils.Queue
    ) -> None:
    """Save an HTTP response to the local filesystem, organizing files by domain and path.

    This function saves the response content to a directory structure that mirrors
    the URL structure (e.g., example.com/path/to/page).

    Args:
        response: The httpx.Response object containing the page content to save.
        async_http_client: The async HTTP client to use.
        save_directory: The base directory to save files to.
        state_obj: CrawlerState instance for tracking downloads.
        queued_urls: Queue for discovered URLs.
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
    file_path = f"{save_directory.strip(os.sep)}/{host}/{path.strip('/')}".replace("/", os.sep)
    logger.debug(f"Creating directory structure for: {file_path}")
    await asyncio.to_thread(os.makedirs, os.path.dirname(file_path), exist_ok=True)

    logger.info(f"Saving response from {response.url} to {file_path}")

    content = response.content

    
    # Convert links to local paths if it's HTML
    if _is_html(response):
        content = html_processor.make_links_local(response, queued_urls, media_queued_urls)
        await state_obj.increment_html()
        logger.debug(f"Converted links to local paths for {response.url}")

    elif _is_javascript(response):
        await state_obj.increment_javascript()

    elif _is_css(response):
        await state_obj.increment_css()

    elif _is_media(response):
        await state_obj.increment_media()

    else:
        await state_obj.increment_others()

    await asyncio.to_thread(_write_binary_file, file_path, response.content)

    logger.info(f"Successfully saved content to {file_path}")

    # Fetch JS and CSS resources if it's HTML
    if _is_html(response):
        await html_processor.fetch_js_css_resources(
            response,
            async_http_client,
            dict(state_obj.cookies),
            state_obj,
            queued_urls,
            media_queued_urls
        )


def generate_report(title_suffix: str = ""):
    """Generate a scraping report with statistics.

    Args:
        title_suffix: Optional suffix to add to the report title.
    """
    logger.debug("Generating report")

    import state as state_module
    st = state_module.state

    cfg = config_loader.config

    with open(cfg.config_path) as cfg_file:
        cfg_json = cfg_file.read()

    review_message = (
        "____________________________________________________\n"
        f"# Scraping Report {datetime.datetime.now(datetime.UTC).isoformat()}\n"
        f"{title_suffix}\n"
        "____________________________________________________\n"
        "## Requests report:\n"
        f"- total fetched urls: {len(st.fetched_urls)}\n"
        f"- total requests: {st.total_requests}\n"
        f"- successful requests: {len(st.successful_requests)}\n"
        f"- failed requests: {len(st.failed_requests)}\n"
        f"- status-error: {len(st.status_error_requests)}\n"
        f"- request-error: {len(st.request_error_requests)}\n"
        f"- other-request-errors: {len(st.other_error_requests)}\n"
        f"- cookies: {st.cookies}\n"
        "____________________________________________________\n"
        "## Storage Report:\n"
        f"- total saved file: {st.total_downloads}\n"
        f"- media saved: {st.media_downloaded}\n"
        f"- html saved: {st.html_downloaded}\n"
        f"- css saved: {st.css_downloaded}\n"
        f"- javascript saved: {st.javascript_downloaded}\n"
        "____________________________________________________\n"
        f"### save directory: {cfg.save_directory}\n"
        f"### total runtime: {int(time.time() - st.start_time)}\n"
        "____________________________________________________\n"
        f"## config.json:\n"
        f"{cfg_json}\n"
    )

    # Create ISO-safe filename
    timestamp = datetime.datetime.now(datetime.UTC).isoformat().replace(':', '-')
    title_suffix_clean = title_suffix.replace(' ', '_').replace(':', '-')
    report_filename = f"scraping-report_{timestamp}{title_suffix_clean}.md"

    report_file_path = os.path.join(cfg.report_files_directory, report_filename)

    with open(report_file_path, "w") as f:
        f.write(review_message)

    logger.info(f"Report generated at {report_file_path}")