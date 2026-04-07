"""
CLI entry point for the LocalWeb crawler.
"""
import argparse
import asyncio
import logging
import os
import sys
import traceback

import httpx

import crawler
from config_loader import CrawlerConfig
from state import CrawlerState
import storage
from os import path

#TODO: mention in the README that when you encounter wierd Errors or pages are not getting saved, consider retruning config.json to its defaults from config.default.json.
#TODO: mention in the README that you should never touch config.default.json unless you know what you're doing.
#TODO: mention in the README that it is best to use the config.json instead of the regular cli interface for more options, and the cli interface uses the entered url as the html scope.
#TODO: make a simple tkinter GUI inerface with these tabs:
#   - "Log" tab
#   - "New Crawler" tab
#   - "Current Crawler Progress" tab
#   - "Queued Crawlers" tab (not queued_urls but a new queue for the crawlers)


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(
            "localweb.log",
            ),  # Log to file
        logging.StreamHandler(sys.stdout)     # Log to console
    ]
)

logger = logging.getLogger(__name__)



def _get_parsed_args():

    parser = argparse.ArgumentParser(
        description="LocalWeb - Website Downloader for Offline Viewing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s https://example.com                    # Crawl entire site
  %(prog)s https://example.com -d 2               # Crawl with max depth of 2
  %(prog)s https://example.com -v                 # Verbose output
  %(prog)s https://example.com -o my_docs         # Custom output directory
  %(prog)s --from-config                          # Use only config.json settings
        """
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="The starting URL to crawl (overrides config.json unless "
             "--from-config)"
    )
    parser.add_argument(
        "-d", "--depth",
        type=int,
        default=None,
        help="Maximum crawl depth (if provided overrides provided all scopes'"
             "max-depth)(0 = unlimited)"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output directory for downloaded files, default = './output/'"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=None,
        help="verbose (debug) logging mode"
    )
    parser.add_argument(
        "--remove-javascript",
        action="store_true",
        default=None,
        help="removes javascript links permenantly from html"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=None,
        help="Delay between retry attempts in seconds, default: 3"
    )
    parser.add_argument(
        "--max-tries",
        type=int,
        default=None,
        help="Maximum retry attempts per URL, default: 30, 0=unlimited"
    )
    parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=None,
        help="Maximum concurrent requests, default: 10"
    )
    parser.add_argument(
        "-s", "--scope",
        default=None,
        nargs=2,
        action="append",
        metavar=("SCOPE-URL", "MAX-DEPTH"),
        help="add a scope to the allowed html scopes, if no scope is provided"
             " then use the url as the scope depth"
    )
    parser.add_argument(
        "--from-config",
        metavar="JSON-FILE",
        default=None,
        help="Ignore all CLI arguments and use only a provided config.json file"
    )
    
    args = parser.parse_args()

    try:
        if args.scope:
            for s in args.scope:
                scope_url, max_depth = s
                max_depth = int(max_depth)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            "Excpected: <string> <int> for scope"
        )

    return args




async def main() -> int:
    """Main entry point for the CLI interface.

    Returns:
        int: Exit code (0 for success, non-zero for errors)
    """
    args = _get_parsed_args()

    logger.info("setting up config...")
    cfg = CrawlerConfig()

    # Determine effective values: if --from-config, always use provided config 
    #  file; otherwise CLI overrides config
    if args.from_config:
        cfg.load_from_json(args.from_config)
        logger.info(f"Using {args.from_config} settings only (--from-config)")

    # if --from-config is not specified
    else:
        cfg.start_url = args.url if args.url else cfg.start_url
        cfg.output_directory = args.output if args.output else cfg.output_directory
        cfg.delay = args.delay if args.delay else cfg.delay
        cfg.max_tries = args.max_tries if args.max_tries is not None else cfg.max_tries
        cfg.max_concurrency = args.concurrency if args.concurrency else cfg.max_concurrency
        cfg.depth = args.depth if args.depth else cfg.depth


    logger.info("setting up state...")
    state = CrawlerState()

    logger.info("setting up http client...")
    async with httpx.AsyncClient() as async_http_client:
        try:
            logger.info("Starting to crawler...")
            result = await crawler.crawl(
                cfg= cfg,
                state= state,
                async_http_client= async_http_client
            )

            logger.info("Crawl completed successfully!")
            logger.info(f"crawler result: {result}")

            storage.generate_report(cfg, state, "Success")
            return 0

        except KeyboardInterrupt:
            logger.warning("Crawl interrupted by user")
            storage.generate_report(cfg, state, "Interrupted by user")
            return 1

        except Exception as e:
            logger.error(f"Crawl failed with error: {e}")
            logger.error(f"{e} Traceback: " + ''.join(
                traceback.format_exception(type(e), e, e.__traceback__))
            )
            storage.generate_report(cfg, state, f"Error: {e}", e)
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
