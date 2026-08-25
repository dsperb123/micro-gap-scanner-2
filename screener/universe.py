"""Build the scannable universe from Nasdaq's public screener API.

One call per exchange returns every listed common stock along with last sale,
market cap, sector and industry. Applying the market-cap floor here — before
any price download — is what keeps the run to a sensible length: it cuts
roughly 6,800 listings down to about 2,700.

Column mapping used throughout the project:
    Nasdaq "sector"    -> dashboard "Industry"      (broad group)
    Nasdaq "industry"  -> dashboard "Sub-Industry"  (detailed group)
"""

from __future__ import annotations

import time

import requests

NASDAQ_SCREENER = "https://api.nasdaq.com/api/screener/stocks"
EXCHANGES = ("nasdaq", "nyse")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _to_float(value) -> float:
    """Parse Nasdaq's money strings ('$12.34', '1,234,000.00', '') to float."""
    if value is None:
        return 0.0
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text in {"NA", "N/A", "--"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _yahoo_symbol(symbol: str) -> str:
    """Nasdaq writes class shares as BRK/B; Yahoo wants BRK-B."""
    return symbol.strip().upper().replace("/", "-").replace("^", "-P")


def fetch_exchange(exchange: str, retries: int = 3) -> list[dict]:
    params = {
        "tableonly": "false",
        "limit": "25000",
        "offset": "0",
        "download": "true",
        "exchange": exchange,
    }
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(
                NASDAQ_SCREENER, params=params, headers=HEADERS, timeout=60
            )
            response.raise_for_status()
            rows = response.json()["data"]["rows"]
            for row in rows:
                row["exchange"] = exchange.upper()
            return rows
        except Exception as exc:  # noqa: BLE001 - retry on any transport error
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Could not fetch {exchange} listings: {last_error}")


def build_universe(min_market_cap: float, min_price: float, max_price: float) -> list[dict]:
    """Return one record per candidate stock, pre-filtered on cap and price.

    The price bounds are applied loosely here using Nasdaq's last sale, purely
    to trim the download. They are re-applied precisely against the weekly
    close in metrics.py, which is the number the screen actually reports.
    """
    raw: list[dict] = []
    for exchange in EXCHANGES:
        raw.extend(fetch_exchange(exchange))

    universe: dict[str, dict] = {}
    for row in raw:
        symbol = _yahoo_symbol(row.get("symbol", ""))
        if not symbol or not symbol.replace("-", "").isalnum():
            continue

        market_cap = _to_float(row.get("marketCap"))
        last_sale = _to_float(row.get("lastsale"))
        if market_cap < min_market_cap:
            continue
        # Generous band: the weekly close can drift from Nasdaq's last sale.
        if not (min_price * 0.7) <= last_sale <= (max_price * 1.3):
            continue

        universe[symbol] = {
            "symbol": symbol,
            "name": (row.get("name") or "").strip(),
            "exchange": row.get("exchange", ""),
            "market_cap": market_cap,
            "industry": (row.get("sector") or "Unclassified").strip() or "Unclassified",
            "sub_industry": (row.get("industry") or "Unclassified").strip() or "Unclassified",
            "country": (row.get("country") or "").strip(),
        }

    return sorted(universe.values(), key=lambda r: r["symbol"])
