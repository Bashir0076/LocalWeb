"""
CLI entry point for the LocalWeb crawler.
"""
import argparse
import asyncio
import logging
import sys

# Configure logging first before importing other modules
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('crawler.log', mode='a', encoding='utf-8')
    ]
)

import crawler
import storage


logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point for the CLI interface.

    Returns:
        int: Exit code (0 for success, non-zero for errors)
    """
    parser = argparse.ArgumentParser(
        description="LocalWeb - Website Downloader for Offline Viewing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://example.com                    # Crawl entire site
  %(prog)s https://example.com -d 2               # Crawl with max depth of 2
  %(prog)s https://example.com -v                 # Verbose output
  %(prog)s https://example.com -o my_docs         # Custom output directory
        """
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="The starting URL to crawl (overrides config.json)"
    )
    parser.add_argument(
        "-d", "--depth",
        type=int,
        default=None,
        help="Maximum crawl depth (overrides config.json, 0 = unlimited)"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output directory for downloaded files (overrides config.json)"
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
        help="Delay between retry attempts in seconds (default: 3)"
    )
    parser.add_argument(
        "--max-tries",
        type=int,
        default=30,
        help="Maximum retry attempts per URL (default: 30)"
    )
    parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=None,
        help="Maximum concurrent requests (overrides config.json, default: 10)"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose >= 1:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # If URL provided, use it; otherwise log info about using config
    if args.url:
        logger.info(f"Starting crawler for: {args.url}")
    else:
        logger.info("No URL provided, using config.json settings")

    try:

        result = asyncio.run(crawler.crawl(
            url=args.url,
            depth=args.depth,
            save_dir=args.output,
            delay=args.delay,
            max_tries=args.max_tries,
            max_concurrency=args.concurrency
        ))
        
        logger.info("Crawl completed successfully!")
        logger.info(f"Summary: {result}")
        
        storage.generate_report("Success")
        return 0
        
    except KeyboardInterrupt:
        logger.warning("Crawl interrupted by user")
        storage.generate_report("Interrupted by user")
        return 1
        
    except Exception as e:
        logger.error(f"Crawl failed with error: {e}")
        storage.generate_report(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
