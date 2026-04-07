# LocalWeb

A powerful Python web crawler designed to download and save websites for offline viewing. It crawls websites, converts links to local relative paths, and downloads all associated assets (HTML, CSS, JavaScript, images, videos) to create a fully navigable offline site.

## Features

- **Async HTTP Crawling** - Fast, efficient crawling using httpx with concurrent requests
- **Scope-Based Crawling** - Limit crawling by domain, path, and depth
- **Offline-Ready Output** - Converts all links to local relative paths for offline navigation
- **Asset Downloading** - Downloads CSS, JavaScript, images, and videos
- **Configurable Retry Logic** - Automatic retries with customizable delay and max attempts
- **Detailed Reporting** - Generates comprehensive scraping reports after each run
- **Thread-Safe State Management** - Handles concurrent operations safely

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/Bashir0076/LocalWeb.git
cd LocalWeb
```

2. **Create a virtual environment (recommended):**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install the package and dependencies:**
```bash
pip install -r requirements.txt
pip install .
```

4. **(Optional) Install in editable mode while developing:**
```bash
pip install -e .
```

## How to Use

### Quick Start

The simplest way to start crawling is to provide a URL directly from the repository:

```bash
python main.py https://example.com
```

After installing the package, use the installed command:

```bash
localweb https://example.com
```

You can also run the package as a module:

```bash
python -m localweb https://example.com
```

### CLI Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `url` | - | Starting URL to crawl (overrides config.json) | Uses config.json |
| `--depth` | `-d` | Maximum crawl depth (0 = unlimited) | Uses config.json |
| `--output` | `-o` | Output directory for downloaded files | Uses config.json |
| `--verbose` | `-v` | Verbose (debug) logging mode | Uses config.json |
| `--remove-javascript` | - | Removes JavaScript links permanently from HTML | Uses config.json |
| `--delay` | - | Delay between retry attempts in seconds | 3 |
| `--max-tries` | - | Maximum retry attempts per URL (0 = unlimited) | 30 |
| `--concurrency` | `-c` | Maximum concurrent requests | 10 |
| `--scope` | `-s` | Add a scope: SCOPE-URL MAX-DEPTH (can be used multiple times) | Uses config.json |
| `--from-config` | - | Ignore all CLI args and use only the specified config.json file | - |

### Usage Examples

**1. Crawl an entire website:**
```bash
python main.py https://example.com
```

**2. Crawl with a specific depth:**
```bash
python main.py https://example.com -d 2
```

**3. Crawl with verbose output:**
```bash
python main.py https://example.com -v
```

**4. Crawl with custom output directory:**
```bash
python main.py https://example.com -o my_docs
```

**5. Combine multiple options:**
```bash
localweb https://example.com -d 3 -v -o ./output --delay 2
```

**6. Use only config.json settings (ignore all CLI arguments):**
```bash
localweb --from-config config.json
```

**7. Crawl with custom scope and remove JavaScript:**
```bash
localweb https://example.com -s https://example.com/docs 2 --remove-javascript
```

### Configuration File

The crawler can be configured via `config.json`. Copy `config.example.json` to get started:

```bash
cp config.example.json config.json
```

Then edit `config.json` with your desired settings:

#### Configuration Options

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `remove_javascript` | boolean | Remove JavaScript from HTML | `false` |
| `allow_javascript` | boolean | Download JavaScript files | `true` |
| `allow_videos` | boolean | Download video content | `true` |
| `allow_images` | boolean | Download images | `true` |
| `allow_data_protocol` | boolean | Allow data: URLs | `false` |
| `allow_iframe` | boolean | Process iframes | `true` |
| `allow_other_link_elements` | boolean | Download other link elements | `false` |
| `allowed_html_scopes` | array | Allowed URL scopes with max depth | Required |
| `blocked_scopes` | array | Blocked URL scopes | `[]` |
| `allowed_iframe_scopes` | array | Allowed iframe scopes | `null` |
| `save_directory` | string | Output directory | `./output/` |
| `report_files_directory` | string | Report output directory | `./` |
| `start_page_url` | string | Default start URL | Required |
| `delay` | int | Delay between retry attempts (seconds) | `3` |
| `max_tries` | int | Maximum retry attempts per URL | `30` |
| `max_concurrency` | int | Maximum concurrent requests | `10` |
| `verbose` | boolean | Enable debug logging | `false` |

#### Scope Configuration

Scopes define where the crawler is allowed to go:

```json
{
    "allowed_html_scopes": [
        {
            "url": "https://example.com",
            "max_depth": 3
        }
    ],
    "blocked_scopes": [
        {
            "url": "https://example.com/admin",
            "max_depth": 0
        }
    ]
}
```

- `url`: The base URL for the scope
- `max_depth`: Maximum crawl depth (0 = unlimited)

### Programmatic Usage

You can also use the crawler in your Python code:

```python
import asyncio
import httpx
from localweb import crawl, CrawlerConfig, CrawlerState

async def main():
    cfg = CrawlerConfig(
        start_url="https://example.com",
        depth=3,
        output_directory="./output",
        delay=3,
        max_tries=30,
        max_concurrency=10
    )
    state = CrawlerState()
    async with httpx.AsyncClient() as client:
        result = await crawl(cfg, state, client)
    
    print(resu)

asyncio.run(main())
```

The `crawl()` function returns a dictionary with crawl statistics:
```python
{
    "total_urls": 100,
    "html_downloaded": 50,
    "media_downloaded": 30,
    "javascript_downloaded": 10,
    "css_downloaded": 10,
    "runtime": 120.0  # seconds
}
```

### Import from Package

```python
from localweb import crawl, CrawlerConfig, CrawlerState

# Create config
cfg = CrawlerConfig(start_url="https://example.com")

# Create state
state = CrawlerState()
```

## Project Structure

```
LocalWeb/
├── __init__.py          # Package initialization and exports
├── main.py          # CLI entry point
├── crawler.py           # Main crawler orchestration
├── config_loader.py     # Configuration management
├── http_client.py       # HTTP client with retry logic
├── html_processor.py    # HTML parsing and link conversion
├── storage.py           # File storage and report generation
├── state.py             # Runtime state management
├── utils.py             # Utility classes (Queue, Scope)
├── config.json          # User configuration
├── config.example.json  # Example configuration template
├── requirements.txt     # Python dependencies
└── LICENSE              # MIT License
```

## Output

After crawling, the downloaded files will be organized by domain:

```
output/
└── example.com/
    ├── index.html
    ├── docs/
    │   └── guide/
    │       └── index.html
    ├── css/
    │   └── style.css
    ├── js/
    │   └── main.js
    └── images/
        └── logo.png
```

A scraping report will also be generated in the report directory with details about the crawl.

## Requirements

- Python 3.10+
- httpx >= 0.27.0
- beautifulsoup4 >= 4.12.0
- lxml >= 4.9.0

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

Bashir

## Acknowledgments

- Built with [httpx](https://www.python-httpx.org/) for async HTTP
- Uses [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) for HTML parsing
- Uses [lxml](https://lxml.de/) for XML/HTML processing
