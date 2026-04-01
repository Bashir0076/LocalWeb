"""
HTML processing functionality for the documentation crawler.
Handles link extraction, scope checking, and local link conversion.
"""
import logging
from urllib.parse import urljoin
from typing import TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup

import config_loader
import utils

if TYPE_CHECKING:
    from utils import Queue


logger = logging.getLogger(__name__)


def is_in_scope(url: httpx.URL | str, scopes: list[utils.Scope] | None) -> bool:
    """Check if a URL is within the allowed crawling scope.

    Validates URL against a list of Scope objects, checking:
    - Host matching (with www prefix normalization)
    - Path prefix matching
    - Depth limit enforcement (if max_depth >= 1)

    Args:
        url: The URL to validate (string or httpx.URL).
        scopes: List of Scope objects defining allowed boundaries, or None for any URL.

    Returns:
        True if URL is in scope, False otherwise. Returns True if scopes is None.
    """
    logger.debug(f"Checking url {url} in scopes {scopes}")

    def get_url_depth(url: httpx.URL, scope_path: str) -> int:
        """Calculate the depth of a URL relative to the scope path."""
        url_path = url.path.rstrip('/')
        
        if not url_path.startswith(scope_path):
            return 0
            
        relative = url_path[len(scope_path):]
        if not relative:
            return 1
        return relative.count('/') + 1

    url = httpx.URL(url)

    # If scope is None, any URL is valid
    if scopes is None:
        return True

    for scope in scopes:
        # Parse the scope URL to get host and path
        scope_parsed = httpx.URL(scope.url)
        
        # Handle www prefix variations
        url_host = url.host.replace("www.", "")
        scope_host = scope_parsed.host.replace("www.", "")

        # Check if hosts match
        if url_host != scope_host:
            continue
            
        # Check if path starts with scope path
        url_path = url.path.rstrip('/')
        scope_path = scope_parsed.path.rstrip('/')

        if not url_path.startswith(scope_path) and url_path != scope_path:
            continue
            
        # Check depth limit
        if scope.max_depth >= 1:
            depth = get_url_depth(url, scope_path)
            if depth > scope.max_depth:
                continue
                
        return True

    return False


def make_links_local(
        response: httpx.Response,
        queued_urls: 'Queue',
        media_queued_urls: 'Queue'
) -> str:
    """Convert links in HTML to local relative paths for offline viewing.

    Processes HTML to:
    - Convert anchor hrefs to relative paths (if in scope)
    - Convert img src to relative paths
    - Convert script src to relative paths  
    - Convert link href to relative paths
    - Convert iframe src to relative paths (if allowed)
    - Convert video source src to relative paths

    Uses config settings to determine which content types to include.

    Args:
        response: The HTTP response with HTML content.
        queued_urls: Queue for discovered HTML URLs (can be None).
        media_queued_urls: Queue for discovered media URLs (can be None).

    Returns:
        Modified HTML string with converted links.
    """
    cfg = config_loader.config
    soup = BeautifulSoup(response.content, "lxml")

    # Process <a> tags
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")

        # Check if javascript is allowed
        if href.startswith('javascript:') and not cfg.allow_javascript:
            anchor["href"] = ""
            continue

        # Skip javascript, mailto, tel, and data URLs
        if href.startswith(('javascript:', 'mailto:', 'tel:', 'data:')):
            continue

        # Absolute links
        if href.startswith(('http://', 'https://')):
            parsed = httpx.URL(href)
        # Relative links
        else:
            resolved = urljoin(str(response.url), href)
            parsed = httpx.URL(resolved)

        # Check if it's in scope
        if is_in_scope(parsed, cfg.allowed_html_scopes):
            queued_urls.put(str(parsed))
            rel_path = utils.get_relative_path(
                f"{response.url.host}/{response.url.path}",
                f"{parsed.host}/{parsed.path}"
            )
            anchor["href"] = rel_path
            logger.debug(f"Converted link {href} -> {rel_path}")

    # Process <img> tags
    for img in soup.find_all("img", src=True):
        src = img.get("src")
        if not cfg.allow_images:
            continue
            
        if (
                src.startswith(('http://', 'https://'))
                or (src.startswith("data:") and cfg.allow_data_protocol)
        ):
            parsed = httpx.URL(src)
        else:
            resolved = urljoin(str(response.url), src)
            parsed = httpx.URL(resolved)
        
        media_queued_urls.put(str(parsed))
        rel_path = utils.get_relative_path(
            f"{response.url.host}/{response.url.path}",
            f"{parsed.host}/{parsed.path}"
        )
        img["src"] = rel_path
        logger.debug(f"Converted img src {src} -> {rel_path}")

    # Process <script> tags for JS files
    for script in soup.find_all("script", src=True):
        if cfg.remove_javascript:
            script["src"] = ""
            continue
        if not cfg.allow_javascript:
            continue

        src = script.get("src")
        if (
                src.startswith(('http://', 'https://'))
                or (src.startswith("data:") and cfg.allow_data_protocol)
        ):
            parsed = httpx.URL(src)
        else:
            resolved = urljoin(str(response.url), src)
            parsed = httpx.URL(resolved)
        
        rel_path = utils.get_relative_path(
            f"{response.url.host}/{response.url.path}",
            f"{parsed.host}/{parsed.path}"
        )
        script["src"] = rel_path
        logger.debug(f"Converted script src {src} -> {rel_path}")

    # Process <link> tags for CSS files
    for link in soup.find_all("link", href=True):
        href = link.get("href")
        if (
                href.startswith(('http://', 'https://'))
                or (href.startswith("data:") and cfg.allow_data_protocol)
        ):
            parsed = httpx.URL(href)
        else:
            resolved = urljoin(str(response.url), href)
            parsed = httpx.URL(resolved)
        
        rel_path = utils.get_relative_path(
            f"{response.url.host}/{response.url.path}",
            f"{parsed.host}/{parsed.path}"
        )
        link["href"] = rel_path
        logger.debug(f"Converted link href {href} -> {rel_path}")

    # Process <iframe>
    for iframe in soup.find_all("iframe", src=True):
        if not cfg.allow_iframe:
            continue

        src = iframe.get("src")
        if (
                src.startswith(('http://', 'https://'))
                or (src.startswith("data:") and cfg.allow_data_protocol)
        ):
            parsed = httpx.URL(src)
        else:
            resolved = urljoin(str(response.url), src)
            parsed = httpx.URL(resolved)

        if is_in_scope(parsed, cfg.allowed_iframe_scopes):
            queued_urls.put(str(parsed))
            rel_path = utils.get_relative_path(
                f"{response.url.host}/{response.url.path}",
                f"{parsed.host}/{parsed.path}"
            )
            iframe["src"] = rel_path
            logger.debug(f"Converted iframe src {src} -> {rel_path}")

    # Process <video> tags with <source> tags
    for video in soup.find_all("video"):
        if not cfg.allow_videos:
            continue

        source = video.find("source", src=True)
        if not source:
            continue
        src = source.get("src")
        if src.startswith(('http://', 'https://')):
            parsed = httpx.URL(src)
        else:
            resolved = urljoin(str(response.url), src)
            parsed = httpx.URL(resolved)

        media_queued_urls.put(str(parsed))
        rel_path = utils.get_relative_path(
            f"{response.url.host}/{response.url.path}",
            f"{parsed.host}/{parsed.path}"
        )
        source["src"] = rel_path
        logger.debug(f"Converted video source src {src} -> {rel_path}")

    return str(soup)


async def fetch_js_css_resources(
        response: httpx.Response,
        async_http_client: httpx.AsyncClient,
        cookies: dict,
        state
) -> list:
    """Fetch and save JavaScript and CSS resources linked from an HTML page.

    Extracts resource URLs from <script>, <link>, and other elements in the
    HTML, fetches each resource, and saves them locally. Respects config
    settings for which resource types to include.

    Args:
        response: The HTTP response containing the HTML page.
        async_http_client: The httpx async client for fetching.
        cookies: Dict of cookies to send with resource requests.
        state: CrawlerState to track fetches and update cookies.

    Returns:
        List of successfully fetched resource URLs.
    """
    from http_client import get_page
    from storage import save_response
    
    cfg = config_loader.config
    fetched_resources = []

    try:
        soup = BeautifulSoup(response.content, "lxml")

        # Find all script tags with src attribute
        script_elements = soup.find_all("script", src=True)
        if cfg.remove_javascript or not cfg.allow_javascript:
            script_urls = []
        else:
            script_urls = [e.get("src") for e in script_elements if e.get("src")]

        # Find all link tags for CSS (stylesheet)
        css_elements = soup.find_all("link", rel="stylesheet", href=True)
        css_urls = [e.get("href") for e in css_elements if e.get("href")]

        # Also check for other link types
        other_link_elements = soup.find_all("link", href=True)
        if not cfg.allow_other_link_elements:
            other_urls = []
        else:
            other_urls = [
                e.get("href") for e in other_link_elements
                if e.get("href") and e.get("href") not in css_urls
            ]

        all_urls = script_urls + css_urls + other_urls
        logger.debug(f"Found {len(script_urls)} JS files, {len(css_urls)} CSS files in {response.url}")

        for url in all_urls:
            # Skip data URLs
            if url.startswith('data:') and not cfg.allow_data_protocol:
                continue

            try:
                # If absolute url
                if url.startswith(("http://", "https://", "data:")):
                    parsed_url = httpx.URL(url)
                # If relative url
                else:
                    resolved_url = urljoin(str(response.url), url)
                    parsed_url = httpx.URL(resolved_url)

                # Fetch the resource
                resource_response = await get_page(
                    parsed_url, 
                    async_http_client, 
                    cookies=cookies,
                    state=state
                )
                
                if resource_response is None:
                    logger.error(f"Couldn't fetch resource {parsed_url}")
                    continue
                    
                fetched_resources.append(parsed_url)
                # Save the resource
                await save_response(resource_response, async_http_client, cfg.save_directory, state)
                logger.info(f"Fetched resource: {parsed_url}")

            except Exception as e:
                logger.error(f"Failed to fetch resource {url}: {e}")
                continue

    except Exception as e:
        logger.error(f"Error parsing JS/CSS from {response.url}: {e}")

    return fetched_resources
