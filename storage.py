"""
LocalWeb storage functionality.
Handles saving responses to disk and generating reports.
"""
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


async def save_response(
        response: httpx.Response,
        async_http_client: httpx.AsyncClient,
        save_directory: str,
        state: 'state.CrawlerState',
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
        state: CrawlerState instance for tracking downloads.

    Returns:
        None. Files are written to the local filesystem.
    """
    host = response.url.host
    path = response.url.path

    # If the URL is a directory (no extension), add index.html
    if '.' not in path.split('/')[-1]:
        path = path + "/index.html"

    # Create the directory structure
    file_path = f"{save_directory.strip(os.sep)}/{host}/{path.strip('/')}".replace("/", os.sep)
    logger.debug(f"Creating directory structure for: {file_path}")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    logger.info(f"Saving response from {response.url} to {file_path}")

    # Determine content type
    content_type = response.headers.get('content-type', '').lower()
    logger.debug(f"Detected content type: {content_type}, for response {response.url}")

    # Save based on content type
    if "image" in content_type or "application" in content_type:
        # Binary content (images/videos)
        state.increment_media()
        logger.debug("Using binary write mode")
        with open(file_path, "wb") as file:
            file.write(response.content)
    else:
        # Text content (HTML/JS/CSS)
        content = response.content.decode(encoding="utf-8", errors="ignore")

        # Convert links to local paths if it's HTML
        if "text/html" in content_type or path.endswith((".html", ".htm")):
            content = html_processor.make_links_local(response, queued_urls, media_queued_urls)
            state.increment_html()
            logger.debug(f"Converted links to local paths for {response.url}")
        else:
            if "javascript" in content_type or path.endswith(".js"):
                state.increment_javascript()
            elif "css" in content_type or path.endswith(".css"):
                state.increment_css()
            else:
                state.increment_others()

        with open(file_path, "w", encoding='utf-8') as file:
            file.write(content)

    logger.info(f"Successfully saved content to {file_path}")

    # Fetch JS and CSS resources if it's HTML
    if "text/html" in content_type or path.endswith((".html", ".htm")):
        await html_processor.fetch_js_css_resources(
            response,
            async_http_client,
            dict(state.cookies),
            state,
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
