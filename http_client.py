"""
LocalWeb HTTP client functionality.
Handles fetching pages with retry logic.
"""
import asyncio
import logging

import httpx

import state


logger = logging.getLogger(__name__)


async def get_page(
        url: httpx.URL | str,
        httpx_async_client: httpx.AsyncClient,
        state: state.CrawlerState,
        follow_redirects: bool = True,
        cookies: dict = {},
        wait_time: int = 3,
        max_tries: int = 30,
    ) -> httpx.Response | None:
    """Fetch a web page with automatic retries on failure.
    
    Attempts to fetch the page up to `max_tries` times, sleeping `wait_time`
    seconds between each attempt. Updates the provided CrawlerState with
    request statistics and cookies.

    Args:
        url: The URL to fetch (string or httpx.URL).
        httpx_async_client: The httpx async client for making requests.
        follow_redirects: Whether to follow HTTP redirects. Default True.
        cookies: Optional dict of cookies to send with the request. Modified in-place.
        wait_time: Seconds to wait between retry attempts. Default 3.
        max_tries: Maximum number of attempts. Default 30.
        state: Optional CrawlerState to track request statistics and cookies.

    Returns:
        httpx.Response on success, or None if all retries exhausted.
    """
        
    logger.debug(f"Making request to {url}")
    url = httpx.URL(url)
    last_error = None

    #setting the max tries to 'inf' so that it is always greater that `tries`
    if max_tries <= 0:
        max_tries = float("inf")

    tries = 0
    while True:
        tries += 1
        try:
            logger.debug(f"Attempting to fetch URL: {url} (attempt {tries + 1}/{max_tries})")
            response = await httpx_async_client.get(
                url=url,
                follow_redirects=follow_redirects,
                cookies=cookies
            )

            response.raise_for_status()

            # Store cookies from response
            for k, v in response.cookies.items():
                cookies[k] = v
            
            # Update state
            await state.increment_request(url, response.url)
            await state.update_cookies(dict(response.cookies))
            
            logger.info(f"Successfully fetched {response.url} (status: {response.status_code})")
            return response

        except httpx.HTTPStatusError as err:
            last_error = err
            logger.error(f"HTTP error fetching {url}: {err.response.status_code} - {err.response.reason_phrase}")
            await state.increment_status_error(url)
            
            if tries >= max_tries - 1:
                logger.error(f"Max retries ({max_tries}) reached for {url}, raising error")
                return None
            
            logger.debug(f"Retrying in {wait_time} seconds...")
            await asyncio.sleep(wait_time)
            continue

        except httpx.RequestError as err:
            last_error = err
            logger.error(f"Request error fetching {url}: {err}")
            await state.increment_request_error(url)
            
            if tries >= max_tries - 1:
                logger.error(f"Max retries ({max_tries}) reached for {url}, returning None")
                return None
            
            logger.debug(f"Retrying in {wait_time} seconds...")
            await asyncio.sleep(wait_time)
            continue

        except Exception as err:
            last_error = err
            logger.error(f"Unexpected error fetching {url}: {err}")
            await state.increment_other_error(url)
            
            if tries >= max_tries - 1:
                logger.error(f"Max retries ({max_tries}) reached for {url}, returning None")
                return None
            
            logger.debug(f"Retrying in {wait_time} seconds...")
            await asyncio.sleep(wait_time)
            continue
