"""
LocalWeb HTML processing functionality.
Handles link extraction, scope checking, and local link conversion.
"""
import logging
from urllib.parse import urljoin
from typing import TYPE_CHECKING
import traceback

import httpx
from bs4 import BeautifulSoup

from . import config_loader
from .config_loader import CrawlerConfig
from .state import CrawlerState
from . import utils
from .http_client import get_page
from .storage import save_response


if TYPE_CHECKING:
    from utils import Queue


logger = logging.getLogger(__name__)

#TODO: document the args of this
def is_in_scope(url: httpx.URL | str, 
                scopes: list[utils.Scope] | None, 
                fallback_depth_limit: int | None = None,
                override_scope_depth: bool = False
                ) -> bool:
    """Check if a URL is within the allowed crawling scope.

    Validates URL against a list of Scope objects, checking:
    - Host matching (with www prefix normalization)
    - Path prefix matching
    - Depth limit enforcement (if max_depth >= 1)

    Args:
        url: The URL to validate (string or httpx.URL).
        scopes: List of Scope objects defining allowed boundaries, or None for any URL.
        fallback_depth_limit: Optional global depth limit to apply if scopes is None or override_scope_depth is True.
        override_scope_depth: If True, uses fallback_depth_limit instead of scope.max_depth.

    Returns:
        True if URL is in scope, False otherwise. Returns True if scopes is None and depth allows.
    """

    logger.debug(f"Checking url {url} in scopes {scopes}")

    url = httpx.URL(url)

    # If scope is None, any URL is valid
    if scopes is None:
        # Check the fallback_depth_limit before proceeding
        if (fallback_depth_limit is not None
                and fallback_depth_limit >= 1
                and get_url_depth(url) > fallback_depth_limit
                ):
            logger.debug(f"fallback depth is provided {fallback_depth_limit}," 
                f" and depth is {get_url_depth(url)}, returning False...")
            return False

        return True

    # Iterating over scopes to find a parent scope
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
            depth = get_relative_url_depth(url, scope.url)
            # Check override
            if override_scope_depth and fallback_depth_limit:
                if depth > fallback_depth_limit:
                    continue
            # If not override_scope_depth then use scope.max_depth
            if depth > scope.max_depth:
                continue
        
        # If all tests are passed successfully return True
        return True
    # If no parent scope was found then return False
    return False



def get_url_depth(url: httpx.URL) -> int:
    """Calculate the absolute depth of a URL path"""
    url_path = url.path.rstrip('/')        
    return url_path.count('/') + 1

def get_relative_url_depth(url: httpx.URL, scope_url: httpx.URL) -> int:
    """Calculate the depth of a URL relative to the scope path.\n
    ### NOTE: this funuction does NOT check if the url is in scope.\n
    ### NOTE: if url is not is scope, this function may result in unexpected 
              output such as number below 1
    """
    url_depth = get_url_depth(url)
    scope_url_depth = get_url_depth(scope_url)
    return (scope_url_depth - url_depth) + 1



def make_links_local(
        response: httpx.Response,
        cfg: CrawlerConfig,
        queued_urls: utils.Queue,
        media_queued_urls: utils.Queue
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
        cfg: CrawlerConfig instance with settings.
        queued_urls: Queue for discovered HTML URLs.
        media_queued_urls: Queue for discovered media URLs.

    Returns:
        Modified HTML string with converted links.
    """
    soup = BeautifulSoup(response.content.decode(), "lxml")

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
        if is_in_scope(
                parsed, cfg.allowed_html_scopes, 
                cfg.depth, cfg.depth is not None
            ):
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

        if is_in_scope(
                parsed, cfg.allowed_iframe_scopes, 
                cfg.depth, cfg.depth is not None
            ):
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
        cfg: CrawlerConfig,
        cookies: dict,
        state: CrawlerState,
        queued_urls: utils.Queue,
        media_queued_urls: utils.Queue,
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
    
    fetched_resources = []

    try:
        soup = BeautifulSoup(response.content, "lxml")

        # Find all script tags with src attribute
        if cfg.remove_javascript or (not cfg.allow_javascript):
            logger.debug("JavaScript is not allowed or should be removed, skipping script fetching.")
            script_urls = []
        else:
            script_elements = soup.find_all("script", src=True)
            script_urls = [e.get("src") for e in script_elements if e.get("src")]

        # Find all link tags for CSS (stylesheet)
        css_elements = soup.find_all("link", rel="stylesheet", href=True)
        css_urls = [e.get("href") for e in css_elements if e.get("href")]

        # Also check for other link types
        other_link_elements = soup.find_all("link", href=True)
        if not cfg.allow_other_link_elements:
            logger.debug("Other link elements are not allowed, skipping.")
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
                    url= parsed_url, 
                    httpx_async_client= async_http_client, 
                    state= state,
                    cookies= cookies,
                )
                
                if resource_response is None:
                    logger.error(f"Couldn't fetch resource {parsed_url}")
                    continue
                    
                fetched_resources.append(parsed_url)
                # Save the resource
                await save_response(
                    response= resource_response, 
                    async_http_client= async_http_client, 
                    cfg= cfg,
                    state= state,
                    queued_urls= queued_urls,
                    media_queued_urls= media_queued_urls,
                    )
                logger.info(f"Fetched resource: {parsed_url}")

            except Exception as e:
                logger.error(f"Failed to fetch resource {url}: {e}")
                logger.error(f"{e} Traceback: " + ''.join(
                    traceback.format_exception(type(e), e, e.__traceback__))
                )
                continue

    except Exception as e:
        logger.error(f"Error parsing JS/CSS from {response.url}: {e}")
        logger.error(f"{e} Traceback: " + ''.join(
            traceback.format_exception(type(e), e, e.__traceback__))
        )

    return fetched_resources
