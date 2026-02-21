"""Base HTTP client for Binance API with retry and rate limiting."""

import logging
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)


def to_milliseconds(dt) -> int:
    """Convert various datetime representations to millisecond timestamp.

    Accepts:
        int/float: treated as millisecond timestamp directly
        str: 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' (interpreted as UTC)
        datetime: converted to ms timestamp (naive datetimes treated as UTC)
    """
    if isinstance(dt, (int, float)):
        return int(dt)
    if isinstance(dt, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(dt, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        else:
            raise ValueError(
                f"Unsupported datetime format: {dt!r}. "
                "Use 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'"
            )
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    raise TypeError(f"Cannot convert {type(dt).__name__} to timestamp")


class BinanceBaseClient:
    """Base HTTP client with retry logic and rate limiting for Binance API."""

    FUTURES_BASE_URL = "https://fapi.binance.com"

    def __init__(self, max_retries: int = 3, rate_limit_sleep: float = 0.1):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.max_retries = max_retries
        self.rate_limit_sleep = rate_limit_sleep

    def _request(self, url: str, params: dict | None = None) -> list | dict:
        """Make GET request with retry and rate limiting.

        Raises RuntimeError on persistent failure or non-retryable errors.
        """
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 200:
                    time.sleep(self.rate_limit_sleep)
                    return resp.json()

                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning("Rate limited (429). Waiting %ds...", wait)
                    time.sleep(wait)
                    continue

                if resp.status_code == 418:
                    raise RuntimeError(f"IP banned by Binance: {resp.text}")

                raise RuntimeError(
                    f"HTTP {resp.status_code}: {resp.text}"
                )

            except requests.exceptions.RequestException as exc:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"Request failed after {self.max_retries} retries: {exc}"
                    ) from exc
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Request error: %s. Retry in %ds (%d/%d)",
                    exc, wait, attempt + 1, self.max_retries,
                )
                time.sleep(wait)

        raise RuntimeError(f"Max retries ({self.max_retries}) exceeded for {url}")

    def close(self):
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
