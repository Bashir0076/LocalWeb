"""
LocalWeb main crawler orchestration module.
Handles the crawling workflow and URL queue management.
"""
import asyncio
import logging
import time
from typing import Optional

import httpx

import config_loader
import http_client
import html_processor
import state as state_module
import storage
import utils


logger = logging.getLogger(__name__)

# Default concurrency limit
DEFAULT_MAX_CONCURRENCY = 10


async def _process_url(
    url_str: str,
    async_http_client: httpx.AsyncClient,
    cfg,
    st,
    output_dir: str,
    queued_urls: utils.Queue,
    media_queued_urls: utils.Queue,
    delay: int,
    max_tries: int,
    semaphore: asyncio.Semaphore,
) -> None:
    """Process a single URL: fetch, save, and extract links."""
    async with semaphore:
        current_url = httpx.URL(url_str)
        
        # Check if URL is already fetched
        if st.fetched_urls.get(str(current_url)):
            logger.debug(f"URL already fetched, skipping: {current_url}")
            return

        # Check if URL is in scope
        if not html_processor.is_in_scope(current_url, cfg.allowed_html_scopes):
            logger.debug(f"URL outside scope, skipping: {current_url}")
            return

        # Fetch response
        try:
            response = await http_client.get_page(
                current_url,
                async_http_client,
                state=st,
                cookies=dict(st.cookies),
                wait_time=delay,
                max_tries=max_tries,
            )

            if response is None:
                return

            # Save the response (this also handles JS/CSS fetching for HTML pages)
            await storage.save_response(
                response,
                async_http_client,
                output_dir,
                st,
                queued_urls,
                media_queued_urls
            )

            logger.info(f"Successfully saved and processed: {current_url}")

        except Exception as e:
            logger.error(f"Error processing {current_url}: {e}")
            return


async def _process_media_url(
    media_url_str: str,
    async_http_client: httpx.AsyncClient,
    cfg,
    st,
    output_dir: str,
    queued_urls: utils.Queue,
    media_queued_urls: utils.Queue,
    delay: int,
    max_tries: int,
    semaphore: asyncio.Semaphore,
) -> None:
    """Process a single media URL: fetch and save."""
    async with semaphore:
        media_url = httpx.URL(media_url_str)
        
        if st.fetched_urls.get(str(media_url)):
            logger.debug(f"Media {media_url} already fetched")
            return
            
        try:
            media_response = await http_client.get_page(
                media_url,
                async_http_client,
                state=st,
                cookies=dict(st.cookies),
                wait_time=delay,
                max_tries=max_tries,
            )
            
            if media_response:
                await storage.save_response(
                    media_response,
                    async_http_client,
                    output_dir,
                    st,
                    queued_urls,
                    media_queued_urls
                )
                logger.debug(f"Successfully fetched media: {media_url}")

        except Exception as err:
            logger.error(f"Error fetching media from {media_url}: {err}")


async def crawl(
        url: str | None = None,
        depth: int | None = None,
        save_dir: str | None = None,
        delay: int = 3,
        max_tries: int = 30,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> dict:
    """Crawl a website starting from a given URL and save all discovered pages locally.

    This is the main function that orchestrates the web crawling process. It uses a queue
    to manage URLs to visit, starting with the provided URL and progressively adding
    newly discovered links that are within the specified scope. URLs are fetched
    concurrently up to the max_concurrency limit.

    Args:
        url: The starting URL to crawl. If None, uses config's start_page_url.
        depth: Maximum depth level to crawl. If None, uses config's max_depth.
        save_dir: Output directory for downloaded files.
        delay: Delay between retry attempts in seconds.
        max_tries: Maximum retry attempts per URL.
        max_concurrency: Maximum number of concurrent HTTP requests.

    Returns:
        dict: Summary of the crawl results.
    """
    cfg = config_loader.config
    st = state_module.state
    
    # Initialize state
    await st.reset()
    state_module.start_time = time.time()
    
    # Override config with function parameters if provided
    start_url = url or cfg.start_page_url
    max_depth = depth if depth is not None else (
        cfg.allowed_html_scopes[0].max_depth if cfg.allowed_html_scopes else 0
    )
    output_dir = save_dir or cfg.save_directory
    
    # Create queues
    queued_urls = utils.Queue(no_repeat=True)
    media_queued_urls = utils.Queue(no_repeat=True)
    
    # Set up scopes if depth is specified
    if depth is not None and cfg.allowed_html_scopes:
        for scope in cfg.allowed_html_scopes:
            scope.max_depth = depth

    logger.info(f"Creating HTTP client with concurrency limit: {max_concurrency}")
    
    # Use semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrency)

    queued_urls.put(start_url)
    logger.info(f"Starting crawl from: {start_url}")
    logger.info(f"Initial queue size: {queued_urls.get_size()}")

    # Use async context manager for proper cleanup
    async with httpx.AsyncClient() as async_http_client:
        # First crawling loop (Fetching HTML/CSS/JS)
        while queued_urls.get_size():
            try:
                url_str = queued_urls.get()
            except IndexError:
                break
            
            # Process URL concurrently (semaphore controls concurrency)
            asyncio.create_task(
                _process_url(
                    url_str,
                    async_http_client,
                    cfg,
                    st,
                    output_dir,
                    queued_urls,
                    media_queued_urls,
                    delay,
                    max_tries,
                    semaphore,
                )
            )
            
            # Small delay to avoid overwhelming the queue
            await asyncio.sleep(0.01)
        
        # Wait for all pending URL tasks to complete
        await asyncio.sleep(0.5)  # Give tasks time to complete
        
        # Second loop: process any remaining URLs that were added during processing
        # This is a simple approach - for true concurrency we'd use a more sophisticated
        # task management system, but this works for the current architecture
        while queued_urls.get_size():
            try:
                url_str = queued_urls.get()
            except IndexError:
                break
            
            await _process_url(
                url_str,
                async_http_client,
                cfg,
                st,
                output_dir,
                queued_urls,
                media_queued_urls,
                delay,
                max_tries,
                semaphore,
            )

        logger.info(f"First crawl loop completed. Total URLs saved: {len(st.fetched_urls)}")
        logger.info(f"Second crawling loop (media) started, media left: {media_queued_urls.get_size()}")

        # Second fetching loop (images/videos)
        while media_queued_urls.get_size():
            try:
                media_url_str = media_queued_urls.get()
            except IndexError:
                logger.error("Index error: Media Queue empty")
                break
            
            await _process_media_url(
                media_url_str,
                async_http_client,
                cfg,
                st,
                output_dir,
                queued_urls,
                media_queued_urls,
                delay,
                max_tries,
                semaphore,
            )

        logger.info(f"Crawling completed. Total fetched URLs: {len(st.fetched_urls)}")
    
    # AsyncClient is automatically closed here
    
    return {
        "total_urls": len(st.fetched_urls),
        "html_downloaded": st.html_downloaded,
        "media_downloaded": st.media_downloaded,
        "javascript_downloaded": st.javascript_downloaded,
        "css_downloaded": st.css_downloaded,
        "runtime": int(time.time() - state_module.state.start_time)
    }