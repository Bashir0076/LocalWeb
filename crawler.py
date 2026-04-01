"""
Main crawler orchestration module.
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


async def crawl(
        url: str | None = None,
        depth: int | None = None,
        save_dir: str | None = None,
        delay: int = 3,
        max_tries: int = 30
    ) -> dict:
    """Crawl a website starting from a given URL and save all discovered pages locally.

    This is the main function that orchestrates the web crawling process. It uses a queue
    to manage URLs to visit, starting with the provided URL and progressively adding
    newly discovered links that are within the specified scope.

    Args:
        url: The starting URL to crawl. If None, uses config's start_page_url.
        depth: Maximum depth level to crawl. If None, uses config's max_depth.
        save_dir: Output directory for downloaded files.
        delay: Delay between retry attempts in seconds.
        max_tries: Maximum retry attempts per URL.

    Returns:
        dict: Summary of the crawl results.
    """
    cfg = config_loader.config
    st = state_module.state
    
    # Initialize state
    st.reset()
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

    logger.info(f"Creating HTTP client")
    async_http_client = httpx.AsyncClient()

    queued_urls.put(start_url)
    logger.info(f"Starting crawl from: {start_url}")
    logger.info(f"Initial queue size: {queued_urls.get_size()}")

    # First crawling loop (Fetching HTML/CSS/JS)
    while queued_urls.get_size():
        try:
            url_str = queued_urls.get()
        except IndexError:
            break
            
        current_url = httpx.URL(url_str)
        
        # Check if URL is already fetched
        if st.fetched_urls.get(str(current_url)):
            logger.debug(f"URL already fetched, skipping: {current_url}")
            continue

        # Check if URL is in scope
        if not html_processor.is_in_scope(current_url, cfg.allowed_html_scopes):
            logger.debug(f"URL outside scope, skipping: {current_url}")
            continue

        # Fetch response
        try:
            response = await http_client.get_page(
                current_url,
                async_http_client,
                cookies=dict(st.cookies),
                wait_time=delay,
                max_tries=max_tries,
                state=st
            )

            if response is None:
                continue

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
            logger.debug(f"Queue size after processing {current_url}: {queued_urls.get_size()}")

        except Exception as e:
            logger.error(f"Error processing {current_url}: {e}")
            continue

    logger.info(f"First crawl loop completed. Total URLs saved: {len(st.fetched_urls)}")
    logger.info(f"Second crawling loop (media) started, media left: {media_queued_urls.get_size()}")

    # Second fetching loop (images/videos)
    while media_queued_urls.get_size():
        try:
            media_url_str = media_queued_urls.get()
        except IndexError:
            logger.error("Index error: Media Queue empty")
            break
        
        media_url = httpx.URL(media_url_str)
        
        if st.fetched_urls.get(str(media_url)):
            logger.debug(f"Media {media_url} already fetched")
            continue
            
        try:
            media_response = await http_client.get_page(
                media_url,
                async_http_client,
                cookies=dict(st.cookies),
                wait_time=delay,
                max_tries=max_tries,
                state=st
            )
            
            if media_response:
                await storage.save_response(
                    media_response,
                    async_http_client,
                    output_dir,
                    st
                )
                logger.debug(f"Successfully fetched media: {media_url}")

        except Exception as err:
            logger.error(f"Error fetching media from {media_url}: {err}")
            continue

    logger.info(f"Crawling completed. Total fetched URLs: {len(st.fetched_urls)}")
    
    return {
        "total_urls": len(st.fetched_urls),
        "html_downloaded": st.html_downloaded,
        "media_downloaded": st.media_downloaded,
        "javascript_downloaded": st.javascript_downloaded,
        "css_downloaded": st.css_downloaded,
        "runtime": int(time.time() - state_module.start_time)
    }
