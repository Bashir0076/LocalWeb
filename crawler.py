"""
online docs crawler/downloader\n
NOTE: only made Sfor static pages
"""
import logging
import os
import sys
import datetime
import time
from urllib.parse import urljoin
import asyncio

import httpx
from bs4 import BeautifulSoup


# Configure logging with a custom format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('crawler.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


"""_____________________________UTILS_________________________________"""
class Queue:
    """Simple classic FIFO queue"""
    def __init__(self, *items, no_repeat: bool = False) -> None:
        self._list = list(items)
        self.no_repeat = no_repeat
        if self.no_repeat:
            # Remove duplicates while preserving order
            seen = set()
            unique_items = []
            for item in self._list:
                if item not in seen:
                    seen.add(item)
                    unique_items.append(item)
            self._list = unique_items

    def __len__(self):
        return len(self._list)

    def put(self, item):
        """add an item to the end of the queue"""
        if self.no_repeat and self._list.count(item):
            return
        self._list.append(item)

    def get(self):
        """returns the first item in the queue, or raises an IndexError if
        list is empty"""
        if not self._list:
            raise IndexError("Queue is empty")
        url = self._list.pop(0)
        return url

    def get_size(self):
        return len(self._list)

    def has(self, item):
        """returns `True` if the `item` is in the queue, else returns `False`"""
        return bool(self._list.count(item))

    def get_depth(self, item):
        """returns the depth of an item in the queue, or 0 if not found"""
        return self._depths.get(item, 0)


class Scope:
    def __init__(
            self,
            url: httpx.URL | str,
            max_depth: int = 0, # 0 means infinite
            ):
        self.url: httpx.URL = httpx.URL(url)
        self.max_depth: int = max_depth


"""____________________________ SETUP_________________________________"""
# Input : (`None` means all urls are valid, `[]` means no url is valid)
remove_javascript: bool = False
allow_javascript: bool = True
allow_videos: bool = True
allow_images: bool = True
allow_data_protocol: bool = False
allow_iframe: bool = True
allow_other_link_elements: bool = False

allowed_html_scopes: list[Scope] | None = [Scope("https://scrapfly.io/academy/", max_depth=2)]
blocked_scopes: list[Scope] = []
allowed_iframe_scopes : list[Scope] | None = None

save_directory: str = "./example-directory/"
report_files_directory: str = "./"
start_page_url: httpx.URL = httpx.URL("https://scrapfly.io/academy")

# top-level variables:
total_requests: int = 0
successful_requests: list[httpx.URL] = []
status_error_requests: list[httpx.URL] = []
request_error_requests: list[httpx.URL] = []
other_error_requests: list[httpx.URL] = []

html_downloaded: int = 0
media_downloaded: int = 0
javascript_downloaded: int = 0
css_dowloaded: int = 0
others_downloaded: int = 0

queued_urls: Queue = Queue(no_repeat=True)
media_queued_urls: Queue = Queue(no_repeat=True)
fetched_urls: dict = {} #{url: url-after-redirects}

start_time: float = time.time()
cookies: dict = {}


def generate_report(title_suffix: str = ""):
    logger.debug("Generating report")
    failed_requests = status_error_requests + request_error_requests + other_error_requests
    total_downloads = (
                    html_downloaded + javascript_downloaded \
                    + css_dowloaded + media_downloaded# + others_downloaded
                    )

    review_message = (
        "____________________________________________________\n"
        f"SCRAPING REPORT {datetime.datetime.now(datetime.UTC).isoformat()}\n"
        f"{title_suffix}\n"
        "____________________________________________________\n"
        f"total fetched urls: {len(fetched_urls.keys())}\n"
        f"total requests: {"total_requests"}\n"
        f"successful requests: {len(successful_requests)}\n"
        f"failed requests: {len(failed_requests)}\n"
        f"status-error: {len(status_error_requests)}\n"
        f"request-error: {len(request_error_requests)}\n"
        f"other-request-errors: {len(other_error_requests)}\n"
        f"cookies: {cookies}\n"
        "____________________________________________________\n"
        f"total saved file: {total_downloads}\n"
        f"media saved: {media_downloaded}\n"
        f"html saved: {html_downloaded}\n"
        f"css saved: {css_dowloaded}\n"
        f"javascript saved: {javascript_downloaded}\n"
        "____________________________________________________\n"
        f"save directory: {save_directory}\n"
        f"total runtime: {int(time.time() - start_time)}\n"
        "____________________________________________________\n"
        )

    report_file_path = os.path.join(
        report_files_directory,
        f"scraping-report.txt {datetime.datetime.now(datetime.UTC).isoformat()}"
        f"{title_suffix}"
        )
    with open(report_file_path, "w") as f:
        f.write(review_message)

    logger.info(f"report generated at {report_file_path}")


#TODO: add headers to request
async def get_page(
        url: httpx.URL | str,
        httpx_async_client: httpx.AsyncClient,
        follow_redirects: bool = True,
        cookies: dict = {},
        wait_time: int = 3,
        max_tries: int = 30
        ) -> httpx.Response:
    """Attempt to fetch a web page with specified retries until a successful response is received.
    This function continuously tries to fetch the page, sleeping between attempts on failure.
    It will retry until a successful HTTP 200 response is received or reach max_retries and raise
    either Exception, httpx.HTTPStatusError, or httpx.RequestError.

    Args:
        url: The URL to fetch (can be string or httpx.URL).
        wait_time: Time in seconds to wait between retry attempts. Defaults to 3.

    Returns:
        httpx.Response: The successful HTTP response object with status code 200.

    Raises:
        httpx.HTTPStatusError: Re-raised if response has an error status (after retries stop).
        httpx.RequestError: Re-raised for network-related errors (after retries stop).

    Example:
        >>> response = await get_page("https://example.com", httpx.AsyncClient())\n
        >>> print(response.status_code) # 200\n
    """
    logger.debug(f"Making request to {url}")
    url = httpx.URL(url)

    for tries in range(max_tries):
        try:
            logger.debug(f"Attempting to fetch URL: {url}")
            "total_requests += 1"
            response = await httpx_async_client.get(
                url=url,
                follow_redirects=follow_redirects,
                cookies=cookies
                )

            response.raise_for_status()

            for k, v in response.cookies.items():#storing the SetCookies from response
                cookies[k] = v
            fetched_urls[str(url)] = str(response.url)
            successful_requests.append(url)
            logger.info(f"Successfully fetched {response.url} (status: {response.status_code})")
            return response


        except httpx.HTTPStatusError as err:
            status_error_requests.append(url)
            logger.error(f"HTTP error fetching {url}: {err.response.status_code} - {err.response.reason_phrase}")
            if tries >= max_tries:
                logger.error(f"reached max number of retries for url {err.response.url}, raising an error")
                raise err
            await asyncio.sleep(wait_time)
            continue

        except httpx.RequestError as err:
            request_error_requests.append(url)
            logger.error(f"Request error fetching {url}: {err}")
            if tries >= max_tries:
                logger.error(f"reached max number of retries for url {err.response.url}, raising an error")
                raise err
            await asyncio.sleep(wait_time)
            continue

        except Exception as err:
            other_error_requests.append(url)
            logger.error(f"Unexpected error fetching {url}: {err}")
            await asyncio.sleep(wait_time)
            continue


    logger.error(f"reached max number of retries for url {err.response.url}, ignoring and moving to the next.")
    return None


def is_in_scope(url: httpx.URL, scopes: Scope | list[Scope] | None) -> bool:
    """Check if a URL is within the scope of the crawl.

    Uses proper URL comparison to handle edge cases like www vs non-www,
    trailing slashes, and subdomains.

    Args:
        url: The URL to check (can be string or httpx.URL).
        scope: The base URL scope defining the crawling boundary.

    Returns:
        bool: True if URL is in scope, False otherwise.
    """
    logger.debug(f"checking url {url} in scopes {scopes}")
    def get_url_depth(url: httpx.URL, scope: Scope) -> int:
        """Calculate the depth of a URL relative to the scope.

        Args:
            url: The URL to calculate depth for.
            scope: The base URL scope.

        Returns:
            int: The depth level (1 for scope itself, higher for deeper pages).
        """
        logger.debug(f"checking url depth for {url}")
        url_path = url.path.rstrip('/')
        scope_path = scope.url.path.rstrip('/')

        # Depth is based on path segments
        relative = url_path[len(scope_path):]
        return relative.count('/') + 1

    url = httpx.URL(url)

    # Check if scope is None (which means any url is valid)
    if scopes is None:
        return True

    # If provided single Scope object, then make a tuple out of it
    elif isinstance(scopes, Scope):
        scopes = (scopes,)

    for scope in scopes:
        # Check if hosts match (handle www prefix)
        url_host = url.host
        scope_host = scope.url.host

        # Handle www prefix variations
        url_host_without_www = url_host.replace("www.", "")
        scope_host_without_www = scope_host.replace("www.", "")

        # Check if path starts with scope path
        url_path = url.path.rstrip('/')
        scope_path = scope.url.path.rstrip('/')

        if url_host_without_www != scope_host_without_www:
            continue
        elif not url_path.startswith(scope_path):
            continue
        else:
            #finally check for depth
            if not scope.max_depth >= 1:
                return get_url_depth(url, scope) <= scope.max_depth

            return True

    return False


def get_relative_path(from_path: str, to_path: str) -> str:
    """Calculate relative path from one path to another.

    Args:
        from_path: The source path (e.g., '/docs/guide/index.html')
        to_path: The target path (e.g., '/docs/api/reference')

    Returns:
        str: The relative path (e.g., '../../api/reference')
    """

    return os.path.relpath(to_path, from_path)


def make_links_local(response: httpx.Response) -> str:
    """Convert all links in HTML content to local relative paths.
    AND processes the response to get other URLs

    Args:
        html_content: The HTML content to modify.


    Returns:
        str: The modified HTML content with local links.
    """
    soup = BeautifulSoup(response.content, "lxml")
    current_dpath = response.url.path

    # Process <a> tags
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")

        #check if javascript is allowed
        if href.startswith('javascript:') and not allow_javascript:
            anchor["href"] = ""
            continue

        # Skip javascript, and data URLs
        if href.startswith(('javascript:', 'mailto:', 'tel:', 'data:')):
            continue

        # absolute links
        if href.startswith(('http://', 'https://')):
            # Check if it's an internal anchor (in scope)
            parsed = httpx.URL(href)
        # relative links
        else:
            # Resolve relative URL
            resolved = urljoin(str(response.url), href)
            parsed = httpx.URL(resolved)

        # Check if it's an internal anchor (in scope)
        if is_in_scope(parsed, allowed_html_scopes):
            queued_urls.put(str(parsed))
            rel_path = get_relative_path(f"{response.url.host}/{response.url.path}",
                                            f"{parsed.host}/{parsed.path}")
            # FIX: Use bracket notation instead of .get() for assignment
            anchor["href"] = rel_path
            logger.debug(f"Converted link {href} -> {rel_path}")


    # Process <img> tags
    for img in soup.find_all("img", src=True):
        src = img.get("src")
        # check if images are allowed
        if not allow_images:
            continue
        # If url is external
        if (
                src.startswith(('http://', 'https://'))
                or (src.startswith("data:") and allow_data_protocol)
            ):
            parsed = httpx.URL(src)
        # If url is relative
        else:
            resolved = urljoin(str(response.url), src)
            parsed = httpx.URL(resolved)
        media_queued_urls.put(str(parsed))
        #getting the relative path
        rel_path = get_relative_path(f"{response.url.host}/{response.url.path}",
                                     f"{parsed.host}/{parsed.path}")
        img["src"] = rel_path
        logger.debug(f"Converted img src {src} -> {rel_path}")

    # Process <script> tags for JS files
    for script in soup.find_all("script", src=True):
        #check if javascript is allowed or should be removed
        if remove_javascript:
            script["src"] = ""
            continue
        if not allow_javascript:
            continue

        src = script.get("src")
        # if link is external
        if (
                src.startswith(('http://', 'https://'))
                or src.startswith(('data:')) and allow_data_protocol
            ):
            parsed = httpx.URL(src)
        # if link is relative
        else:
            resolved = urljoin(str(response.url), src)
            parsed = httpx.URL(resolved)
        #NOTE: javascript and css fetching is handled via ``fetch_js_css_resources(...)``
        #       so no need to put their links in global queue
        rel_path = get_relative_path(f"{response.url.host}/{response.url.path}",
                                     f"{parsed.host}/{parsed.path}")
        script["src"] = rel_path
        logger.debug(f"Converted script src {src} -> {rel_path}")

    # Process <link> tags for CSS files
    for link in soup.find_all("link", href=True):
        href = link.get("href")
        # if link is external
        if (
                src.startswith(('http://', 'https://'))
                or (src.startswith("data:") and allow_data_protocol)
            ):
            parsed = httpx.URL(href)
        # if link is relative
        else:
            resolved = urljoin(str(response.url), href)
            parsed = httpx.URL(resolved)

            resolved = urljoin(str(response.url), src)
            parsed = httpx.URL(resolved)
        #NOTE: javascript and css fetching is handled via ``fetch_js_css_resources(...)``
        #       so no need to put their links in global queue
        rel_path = get_relative_path(f"{response.url.host}/{response.url.path}",
                                     f"{parsed.host}/{parsed.path}")
        link["href"] = rel_path
        logger.debug(f"Converted link href {href} -> {rel_path}")

    # Process <iframe>
    for iframe in soup.find_all("iframe", src=True):
        # check if iframes are allowed
        if not allow_iframe:
            continue

        src = iframe.get("src")
        # if link is external
        if (
                src.startswith(('http://', 'https://'))
                or (src.startswith("data:") and allow_data_protocol)
            ):
            parsed = httpx.URL(src)
        # if link is relative
        else:
            resolved = urljoin(str(response.url), src)
            parsed = httpx.URL(resolved)

        # check if iframe scope is allowed
        if is_in_scope(parsed, allowed_iframe_scopes):
            queued_urls.put(str(parsed))
            rel_path = get_relative_path(f"{response.url.host}/{response.url.path}",
                                         f"{parsed.host}/{parsed.path}")
            iframe["src"] = rel_path
            logger.debug(f"Converted iframe src {src} -> {rel_path}")

    # Process <video> tags with <source> tags
    for video in soup.find_all("video"):
        # check if videos are allowed
        if not allow_videos:
            continue

        source = video.find("source", src=True)
        src = source.get("src")
        # if link is external
        if src.startswith(('http://', 'https://')):
            parsed = httpx.URL(src)
        # if link is relative
        else:
            resolved = urljoin(str(response.url), src)
            parsed = httpx.URL(resolved)

        media_queued_urls.put(str(parsed))
        rel_path = get_relative_path(f"{response.url.host}/{response.url.path}",
                                     f"{parsed.host}/{parsed.path}")
        iframe["src"] = rel_path
        logger.debug(f"Converted iframe src {src} -> {rel_path}")


    return str(soup)


async def fetch_js_css_resources(response: httpx.Response, async_http_client: httpx.AsyncClient) -> list:
    """Fetch and save JavaScript and CSS resources from a page.

    Args:
        response: The HTTP response containing the page content.
        scope: The base URL scope.

    Returns:
        list: List of fetched resource URLs.
    """
    fetched_resources = []

    try:
        soup = BeautifulSoup(response.content, "lxml")

        # Find all script tags with src attribute
        script_elements = soup.find_all("script", src=True)
        if remove_javascript or not allow_javascript:
            script_urls = []
        else:
            script_urls = [e.get("src") for e in script_elements if e.get("src")]

        # Find all link tags for CSS (stylesheet)
        css_elements = soup.find_all("link", rel="stylesheet", href=True)
        css_urls = [e.get("href") for e in css_elements if e.get("href")]

        # Also check for other link types
        other_link_elements = soup.find_all("link", href=True)
        if not allow_other_link_elements:
            other_urls = []
        else:
            other_urls = [e.get("href") for e in other_link_elements if e.get("href") and e.get("href") not in css_urls]

        all_urls = script_urls + css_urls + other_urls
        logger.debug(f"Found {len(script_urls)} JS files, {len(css_urls)} CSS files in {response.url}")

        for url in all_urls:
            # Skip data URLs
            if url.startswith('data:') and not allow_data_protocol:
                continue

            try:
                # if absolute url
                if url.startswith(("http://", "https://", "data:")):
                    parsed_url = httpx.URL(url)
                # if relative url
                else:
                    resolved_url = urljoin(str(response.url), url)
                    parsed_url = httpx.URL(resolved_url)

                # Fetch the resource and validate it
                resource_response = await get_page(parsed_url, async_http_client, cookies=cookies)
                # Check if request failed or not
                if resource_response is None:
                    logger.error(f"Couldn't to fetch resource {parsed_url}: {resource_response}")
                    continue
                else:
                    fetched_resources.append(parsed_url)
                    # Save the resource
                    await save_response(resource_response, async_http_client, save_directory)
                    logger.info(f"Fetched resource: {parsed_url}")

            except Exception as e:
                logger.error(f"Failed to fetch resource {url}: {e}")
                continue

    except Exception as e:
        logger.error(f"Error parsing JS/CSS from {response.url}: {e}")

    return fetched_resources


#TODO: recognize videos as binary
async def save_response(response: httpx.Response, async_http_client: httpx.AsyncClient, save_directory: str = ".", make_local: bool = True) -> None:
    """Save an HTTP response to the local filesystem, organizing files by domain and path.

    This function saves the response content to a directory structure that mirrors
    the URL structure (e.g., example.com/path/to/page). It also extracts and
    processes links found in HTML content for later crawling.

    The function handles:
    - Creating appropriate directory structures
    - Extracting href links from anchor tags
    - Extracting src links from img tags
    - Saving HTML content as index.html
    - Converting links to local paths (when make_local=True)

    Args:
        response: The httpx.Response object containing the page content to save.
        scope: The base URL scope (domain) that defines the crawling boundary.
               Used to determine if links are within the target site.
        make_local: Whether to convert links to local relative paths. Default True.

    Returns:
        None. Files are written to the local filesystem.

    Raises:
        OSError: If there are issues creating directories or writing files.

    Example:
        # Creates: example.com/docs/index.html
    """
    host = response.url.host
    path = response.url.path

    # If the url is a direcetory
    if path.find('.') < 0:
        path = path + "/index.html"

    # Handling the creation of the directory
    file_path = f"{save_directory.strip(os.sep)}/{host}/{path.strip("/")}".replace("/", os.sep)
    logger.debug(f"Creating directory structure for: {file_path}")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    logger.info(f"Saving response from {response.url} to {file_path}")

    # Determine if response is HTML or binary (image)
    content_type = response.headers.get('content-type', '').lower()

    logger.debug(f"Detected content type: {content_type}, for response {response.url}")
    # Save the content
    if "image" in content_type or "application" in content_type:
        # For binary content (images/videos), use binary write mode
        global media_downloaded
        media_downloaded += 1
        logger.debug("using binary write mode")
        with open(file_path, "wb") as file:
            file.write(response.content)
    else:
        # For text/HTML/JS/CSS content, use text write mode
        content = response.content.decode(encoding="utf-8",errors="ignore")
        # Convert links to local paths if it's HTML
        if "text/html" in content_type or path.endswith((".html", ".htm")):
            # Make links local before saving
            content = make_links_local(response)
            logger.debug(f"Converted links to local paths for {response.url}")

            global html_downloaded
            html_downloaded += 1
        else:
            content = response.content
            if "javascript" in content_type or path.endswith(".js"):
                global javascript_downloaded
                javascript_downloaded += 1
            elif "css" in content_type or path.endswith(".css"):
                global css_dowloaded
                css_dowloaded += 1
            else:
                global others_downloaded
                others_downloaded += 1

        with open(file_path, "w", encoding='utf-8') as file:
            file.write(content)

    logger.info(f"Successfully saved content to {file_path}")

    # Fetch JS and CSS resources if it's HTML
    if content_type == "text/html" or content_type.endswith((".html", ".htm")):
        await fetch_js_css_resources(response, async_http_client)


async def crawl() -> None:
    """Crawl a website starting from a given scope URL and save all discovered pages locally.
    Description:
        This is the main function that orchestrates the web crawling process. It uses a queue
        to manage URLs to visit, starting with the scope URL and progressively adding newly
        discovered links that are within the specified scope.

        The crawler:
        1. Starts with a scope URL and adds it to the queue
        2. Continuously processes URLs from the queue until empty
        3. Fetches each URL using get_page()
        4. Saves the response using save_response()
        5. Parses the HTML to find new links (<a> tags), images (<img> tags), scripts, and CSS
        6. Adds valid in-scope links to the queue for processing (respecting max_depth)

    Args:
        scope: The base URL defining the crawling boundary. Only URLs starting with
               this scope will be crawled. Example: "https://scrapefly.io/academy"
               won't crawl links like "https://scrapefly.io/blog".
        max_depth: Maximum depth level to crawl. Depth 1 is the scope itself.
                   Default is 0 (unlimited/infinite depth).

    Returns:
        None. All crawled pages are saved to the local filesystem.

    Raises:
        Exception: Any exceptions from get_page() or save_response() are logged
                   but may cause the crawler to continue or stop depending on implementation.

    Example:
        >>> crawl(httpx.URL("https://example.com/docs"), max_depth=2)
        # Crawls example.com/docs and all links within 2 levels of depth

    Note:
        - The function uses httpx.URL for better URL manipulation
        - Links are checked to ensure they are within scope using proper URL comparison
        - JavaScript and CSS files are fetched and saved locally
        - Local link conversion is implemented
    """
    logger.info(f"Creating http client")
    async_http_client = httpx.AsyncClient()

    queued_urls.put(start_page_url)
    logger.info(f"Initial queue size: {queued_urls.get_size()}")

    # First crawling loop (Fetching html/css/js)
    while queued_urls.get_size():
        # Getting the url from the queue
        logger.debug("Getting url from queue")
        try:
            url = httpx.URL(queued_urls.get())
        except IndexError:
            break
        # Checking if url is already fetched
        if  fetched_urls.get(str(url)):
            logger.debug(f"URL already fetched, skipping: {url}")
            continue

        # Fetching response
        try:
            # Convert to httpx.URL for proper handling
            response = await get_page(url, async_http_client, cookies=cookies)

            if response is None:
                continue

            # Check if response URL is still in scope (handles redirects)
            #if not is_in_scope(response.url, ):
            #    logger.warning(f"Redirected URL {response.url} is outside scope, skipping")
            #    continue

            #NOTE: ``save_response(...)`` also handles fetching js/css/resources
            await save_response(response, async_http_client, save_directory)

            logger.info(f"Successfully saved and processed: {url}")
            logger.debug(f"Queue size after processing {url}: {len(queued_urls)}")

        except Exception as e:
            logger.error(f"Error parsing links from {url}: {e}")
            continue

    logger.info(f"First crawl loop completed. Total URLs saved: {len(fetched_urls.keys())}")
    logger.info(f"Second crawling loop (media) started, media left: {media_queued_urls.get_size()}")

    # Second Fetching loop (images/videos)
    while media_queued_urls.get_size():
        logger.debug("getting media url from queue...")
        try:
            media_url = httpx.URL(media_queued_urls.get())
        except IndexError:
            logger.error("index error: Media Queue empty")
            break
        
        if fetched_urls.get(str(media_url)):
            logger.debug(f"media {media_url} already fetched")
            continue
        try:
            logger.debug(f"getting media from {media_url}")
            media_response = await get_page(media_url, async_http_client, cookies=cookies)
            logger.debug(f"image response from {media_response.url}: {media_response.status_code}")

            logger.debug("saving image...")
            save_response(media_response, async_http_client, save_directory)
            fetched_urls[str(media_url)] = str(media_response.url)

        except Exception as err:
            logger.error(f"An error occured getting media from {media_url}")
            logger.error(f"Error: {err}")
            continue

    logger.info(f"Crawling images done, total fetched urls: {len(fetched_urls.keys())}")


def main():
    """Main entry point for the CLI interface.

    This function sets up argument parsing and initiates the crawling process
    based on command-line arguments.

    Returns:
        int: Exit code (0 for success, non-zero for errors)
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Online Documentation Crawler-Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=
        """Examples:
  %(prog)s https://example.com                    # Crawl entire site
  %(prog)s https://example.com -d 2               # Crawl with max depth of 2
  %(prog)s https://example.com -v                 # Verbose output
  %(prog)s https://example.com -o my_docs         # Custom output directory
        """
    )

    parser.add_argument(
        "url",
        help="The starting URL to crawl"
    )
    parser.add_argument(
        "-d", "--depth",
        type=int,
        default=0,
        help="Maximum crawl depth (0 = unlimited, default: 0)"
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory for downloaded files (default: output)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=3,
        help="Delay between requests in seconds (default: 3)"
    )

    args = parser.parse_args()
    print(f"VERBOSE MODE {args.verbose}")

    logger.setLevel(args.verbose)

    logger.info(f"Starting crawler for: {args.url}")

    try:
        asyncio.run(crawl())
        logger.info("Crawl completed successfully!")
        generate_report("Success")
        return 0
    except KeyboardInterrupt:
        logger.warning("Crawl interrupted by user")
        generate_report("Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Crawl failed with error: {e}")
        generate_report(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
