"""
docs-crawler-downloader package.
A web crawler for downloading and saving online documentation for offline viewing.
"""
import logging
import sys

# Configure logging for the entire package
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('crawler.log', mode='a', encoding='utf-8')
    ]
)

# Import main components for easy access
from .crawler import crawl
from .config_loader import config, Config
from .state import state, CrawlerState

__all__ = ['crawl', 'config', 'Config', 'state', 'CrawlerState']
