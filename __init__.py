"""
localweb package.
A web crawler for downloading and saving websites for offline viewing.
"""
import logging
import sys


# Import main components for easy access
from .crawler import crawl
from .config_loader import config, Config
from .state import state, CrawlerState

__all__ = ['crawl', 'config', 'Config', 'state', 'CrawlerState']
