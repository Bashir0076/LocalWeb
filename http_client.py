"""
LocalWeb HTTP client functionality.
Handles fetching pages with retry logic.
"""
import asyncio
import logging
from typing import Optional

import httpx


logger = logging.getLogger(__name__)


async def get_page(
        url: httpx.URL | str,
        httpx_async_client: httpx.AsyncClient,
        follow_redirects: bool = True,
        cookies: dict | None = None,
        wait_time: int = 3,
        max_tries: int = 30,
        state=None
) -> Optional[httpx.Response]:
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

    Raises:
        httpx.HTTPStatusError: Re-raised after final retry if HTTP error occurs.
        httpx.RequestError: Re-raised after final retry on network error.
    """
    if cookies is None:
        cookies = {}
        
    logger.debug(f"Making request to {url}")
    url = httpx.URL(url)
    last_error = None

    for tries in range(max_tries):
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
            
            # Update state if provided
            if state is not None:
                state.increment_request(url, response.url)
                state.update_cookies(dict(response.cookies))
            else:
                # Fallback to global state
                import state as state_module
                state_module.state.increment_request(url, response.url)
                state_module.state.update_cookies(dict(response.cookies))
            
            logger.info(f"Successfully fetched {response.url} (status: {response.status_code})")
            return response

        except httpx.HTTPStatusError as err:
            last_error = err
            logger.error(f"HTTP error fetching {url}: {err.response.status_code} - {err.response.reason_phrase}")
            if state is not None:
                state.increment_status_error(url)
            else:
                import state as state_module
                state_module.state.increment_status_error(url)
            
            if tries >= max_tries - 1:
                logger.error(f"Max retries ({max_tries}) reached for {url}, raising error")
                raise
            
            logger.debug(f"Retrying in {wait_time} seconds...")
            await asyncio.sleep(wait_time)
            continue

        except httpx.RequestError as err:
            last_error = err
            logger.error(f"Request error fetching {url}: {err}")
            if state is not None:
                state.increment_request_error(url)
            else:
                import state as state_module
                state_module.state.increment_request_error(url)
            
            if tries >= max_tries - 1:
                logger.error(f"Max retries ({max_tries}) reached for {url}, raising error")
                raise
            
            logger.debug(f"Retrying in {wait_time} seconds...")
            await asyncio.sleep(wait_time)
            continue

        except Exception as err:
            last_error = err
            logger.error(f"Unexpected error fetching {url}: {err}")
            if state is not None:
                state.increment_other_error(url)
            else:
                import state as state_module
                state_module.state.increment_other_error(url)
            
            if tries >= max_tries - 1:
                logger.error(f"Max retries ({max_tries}) reached for {url}, raising error")
                raise
            
            logger.debug(f"Retrying in {wait_time} seconds...")
            await asyncio.sleep(wait_time)
            continue

    logger.error(f"Failed to fetch {url} after {max_tries} attempts")
    return None
