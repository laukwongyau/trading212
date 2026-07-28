"""Minimal client for the Trading212 public API (equity accounts).

Docs: https://t212public-api-docs.redoc.ly/
"""

from __future__ import annotations

import time
from urllib.parse import urljoin

import requests

LIVE_BASE_URL = "https://live.trading212.com/api/v0"
DEMO_BASE_URL = "https://demo.trading212.com/api/v0"


class Trading212Error(RuntimeError):
    """Raised for any non-recoverable response from the Trading212 API."""


class Trading212Client:
    def __init__(self, api_key: str, live: bool = True, timeout: float = 15.0):
        if not api_key:
            raise Trading212Error("Missing Trading212 API key.")
        self.base_url = (LIVE_BASE_URL if live else DEMO_BASE_URL) + "/"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": api_key, "Accept": "application/json"})

    def _request(self, path: str, retries: int = 4) -> dict:
        url = urljoin(self.base_url, path.lstrip("/"))
        wait = 2.0
        for attempt in range(retries):
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else wait)
                wait *= 2
                continue
            if resp.status_code == 401:
                raise Trading212Error(
                    "Trading212 rejected the API key (401). Check the key and that it has the "
                    "right scopes enabled."
                )
            if resp.status_code == 403:
                raise Trading212Error(
                    "Trading212 API key is missing the scope needed for this endpoint (403)."
                )
            if not resp.ok:
                raise Trading212Error(f"Trading212 API error {resp.status_code}: {resp.text[:300]}")
            if not resp.content:
                return {}
            return resp.json()
        raise Trading212Error("Trading212 API rate limit hit repeatedly; try again in a minute.")

    def _paginate(self, first_path: str, max_items: int) -> list[dict]:
        items: list[dict] = []
        path: str | None = first_path
        while path and len(items) < max_items:
            data = self._request(path)
            items.extend(data.get("items", []))
            next_path = data.get("nextPagePath")
            if not next_path:
                break
            # nextPagePath may be absolute (includes the base URL) or relative.
            path = next_path.replace(self.base_url.rstrip("/"), "").lstrip("/")
        return items[:max_items]

    def account_info(self) -> dict:
        return self._request("equity/account/info")

    def account_cash(self) -> dict:
        return self._request("equity/account/cash")

    def portfolio(self) -> list[dict]:
        data = self._request("equity/portfolio")
        return data if isinstance(data, list) else data.get("items", [])

    def orders(self, max_items: int = 50) -> list[dict]:
        return self._paginate(f"equity/history/orders?limit={min(max_items, 50)}", max_items)

    def dividends(self, max_items: int = 50) -> list[dict]:
        return self._paginate(f"history/dividends?limit={min(max_items, 50)}", max_items)
