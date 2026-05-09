# Bale Gold Price Bot

A production-ready Telegram bot that scrapes live gold, coin, and cryptocurrency prices from Persian financial sources and broadcasts them to multiple channels on a user-defined schedule.

## What It Does

- Scrapes real-time gold and currency prices from tala.ir using multiple fallback selectors
- Supports over a dozen assets: gold, various coins, Bitcoin, USDT, oil, and more
- Broadcasts formatted price updates to an unlimited number of Telegram channels
- Offers a full Persian-language admin panel via private chat, with inline keyboard controls
- Schedules daily automatic broadcasts at a configurable time (24-hour format)
- Manages channels with enable/disable toggling, add/remove, and access testing
- Persists all configuration and channel lists in local JSON files — no database required
- Runs asynchronously for non-blocking performance

## Built With

- Python 3.10+
- python-bale-bot (Bale Bot API wrapper)
- BeautifulSoup4 for HTML scraping
- Requests for HTTP calls
- Asyncio for concurrent scheduling

## Project Status

Actively maintained by a two-person team. Used in real-world scenarios under restrictive network conditions, demonstrating resilient design and practical utility.
