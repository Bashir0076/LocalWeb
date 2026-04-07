"""
LocalWeb main crawler orchestration module.
Handles the crawling workflow and URL queue management.
"""
import asyncio
import logging
import time
from typing import Optional

import httpx

from config_loader import CrawlerConfig
import http_client
import html_processor
from state import CrawlerState
import storage
import utils


logger = logging.getLogger(__name__)


#TODO: document all functions in this file and emohasise that crawler() will 
#      reset the state given to it so every state given to crawl() should be
#      seperate from other crawl() calls.

#TODO: use asyncio queue class instead of the current utils.Queue


async def _process_url(
    url_str: str,
    async_http_client: httpx.AsyncClient,
    cfg: CrawlerConfig,
    state: CrawlerState,
    queued_urls: utils.Queue,
    media_queued_urls: utils.Queue,
    semaphore: asyncio.Semaphore,
    ) -> None:
    """Process a single URL (designed for html responses): fetch, save, and extract links."""
    async with semaphore:
        current_url = httpx.URL(url_str)
        
        # Check if URL is already fetched
        if str(current_url) in state.fetched_urls:
            logger.debug(f"URL already fetched, skipping: {current_url}")
            return

        # Check if URL is in scope
        if not html_processor.is_in_scope(
                current_url, cfg.allowed_html_scopes,
                cfg.depth, cfg.depth is not None
                ):
            logger.debug(f"URL outside scope, skipping: {current_url}")
            return
        elif html_processor.is_in_scope(
                current_url, cfg.blocked_html_scopes,
                cfg.depth, cfg.depth is not None
            ):
            logger.debug(f"URL scope blocked, skipping: {current_url}")
            return


        # Fetch response
        try:
            response = await http_client.get_page(
                url= current_url,
                httpx_async_client= async_http_client,
                state= state,
                cookies= dict(state.cookies),
                wait_time= cfg.delay,
                max_tries= cfg.max_tries,
            )

            if response is None:
                return

            # Save the response (this also handles JS/CSS fetching for HTML 
            #   pages, and also extracts links and puts them in the queue and
            #   process them to be relative).
            await storage.save_response(
                response= response,
                async_http_client= async_http_client,
                cfg= cfg,
                state= state,
                queued_urls= queued_urls,
                media_queued_urls= media_queued_urls
            )

            logger.info(f"Successfully saved and processed: {current_url}")

        except Exception as e:
            logger.error(f"Error processing {current_url}: {e}")
            logger.error(f"{e} Traceback: " + ''.join(
                traceback.format_exception(type(e), e, e.__traceback__))
            )

            return


async def _process_media_url(
    media_url_str: str,
    async_http_client: httpx.AsyncClient,
    cfg: CrawlerConfig,
    state: CrawlerState,
    queued_urls: utils.Queue,
    media_queued_urls: utils.Queue,
    semaphore: asyncio.Semaphore,
    ) -> None:
    """Process a single media URL: fetch and save."""
    async with semaphore:
        media_url = httpx.URL(media_url_str)

        if str(media_url) in state.fetched_urls:
            logger.debug(f"Media {media_url} already fetched")
            return
            
        try:
            media_response = await http_client.get_page(
                url= media_url,
                httpx_async_client= async_http_client,
                state= state,
                cookies= dict(state.cookies),
                wait_time= cfg.delay,
                max_tries= cfg.max_tries,
            )
            
            if media_response:
                await storage.save_response(
                    response= media_response,
                    async_http_client= async_http_client,
                    cfg= cfg,
                    state= state,
                    queued_urls= queued_urls,
                    media_queued_urls= media_queued_urls
                )
                logger.debug(f"Successfully fetched media: {media_url}")

        except Exception as e:
            logger.error(f"Error fetching media from {media_url}: {e}")
            logger.error(f"{e} Traceback: " + ''.join(
                traceback.format_exception(type(e), e, e.__traceback__))
            )



async def crawl(
        cfg: CrawlerConfig,
        state: CrawlerState,
        async_http_client: httpx.AsyncClient,
        ) -> None:
    """Crawl a website starting from the URL specified in the config and save all discovered pages locally.

    This is the main function that orchestrates the web crawling process. It uses queues
    to manage URLs to visit, starting with the start_url from cfg and progressively adding
    newly discovered links that are within the specified scope. URLs are fetched
    concurrently up to the max_concurrency limit.
    
    Returns:
        dict: Summary of the crawl results with keys: total_fetched_urls, html_downloaded, 
        media_downloaded, javascript_downloaded, css_downloaded, runtime.
    """

    # Initialize state
    await state.reset()
    state.start_time = time.time()

    # Create queues
    queued_urls = utils.Queue(
        no_repeat=True, 
        load_from_file= cfg.output_directory + "/queued_urls.txt",
        save_file=cfg.output_directory + "/queued_urls.txt"
        )
    media_queued_urls = utils.Queue(
        no_repeat=True,
        load_from_file= cfg.output_directory + "/media_queued_urls.txt",
        save_file=cfg.output_directory + "/media_queued_urls.txt"
        )

    logger.debug(f"Creating semaphore with concurrency limit: {cfg.max_concurrency}")    
    # Use semaphore to limit concurrency
    semaphore = asyncio.Semaphore(cfg.max_concurrency)

    queued_urls.put(str(cfg.start_url))
    logger.info(f"Starting crawl from: {cfg.start_url}")

    # First crawling loop (Fetching HTML/CSS/JS)
    while queued_urls.get_size() > 0:
        tasks = []
        for i in range(cfg.max_concurrency):
            if queued_urls.get_size():
                url_str = queued_urls.get()
            else:
                break
            # Process URL concurrently (semaphore controls concurrency)
            logger.debug(f"Creating task to process url: {url_str}")
            tasks.append(asyncio.create_task(
                _process_url(
                    url_str= url_str,
                    async_http_client= async_http_client,
                    cfg= cfg,
                    state= state,
                    queued_urls= queued_urls,
                    media_queued_urls= media_queued_urls,
                    semaphore= semaphore,
                )
            ))
        # Wait for the tasks to finish
        logger.debug(f"Waiting for tasks to finish processing")
        await asyncio.gather(*tasks)


    logger.info(f"First crawl loop completed. Total URLs saved: {len(state.fetched_urls)}")
    logger.info(f"Second crawling loop (media) started, media left: {media_queued_urls.get_size()}")

    # Second fetching loop (images/videos)
    while media_queued_urls.get_size() > 0:
        tasks = []
        for i in range(cfg.max_concurrency):
            if media_queued_urls.get_size():
                url_str = media_queued_urls.get()
            else:
                break
            # Process URL concurrently (semaphore controls concurrency)
            logger.debug(f"Creating task to process media url: {url_str}")
            tasks.append(asyncio.create_task(
                _process_media_url(
                    media_url_str= url_str,
                    async_http_client= async_http_client,
                    cfg= cfg,
                    state= state,
                    queued_urls= queued_urls,
                    media_queued_urls= media_queued_urls,
                    semaphore= semaphore
                )
            ))
        # Wait for the tasks to finish
        logger.debug(f"Waiting for media tasks to finish processing")
        await asyncio.gather(*tasks)

    logger.info(f"Crawling completed. Total fetched URLs: {len(state.fetched_urls)}")

    # Return summary
    return {
        "total_fetched_urls": len(state.fetched_urls),
        "html_downloaded": state.html_downloaded,
        "media_downloaded": state.media_downloaded,
        "javascript_downloaded": state.javascript_downloaded,
        "css_downloaded": state.css_downloaded,
        "runtime": time.time() - state.start_time
    }

