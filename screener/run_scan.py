"""Run the weekly micro gap scan and write the dashboard's data files.

Pipeline
--------
1. Build the NASDAQ + NYSE universe, pre-filtered on market cap.
2. Download full weekly history for that universe in chunks.
3. Measure every stock, and flag micro gaps on the last completed week.
4. Rebuild the bull-gap-per-week trend from the same weekly history, so the
   chart is populated on the very first run instead of taking two months to
   fill in.
5. Download daily bars for the surviving candidates only, and apply ADR%.
6. Write docs/results.json and docs/history.json.

Run it with `python -m screener.run_scan`. Add `--limit 300` for a fast
smoke test against a slice of the universe.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from screener.gaps import gap_label, micro_gap_series
from screener.metrics import (
    adr_percent,
    clean_frame,
    drop_open_week,
    high_proximity,
    last_three_candles,
    week_ending,
    weekly_ema,
    weekly_gain_pct,
)
from screener.universe import build_universe

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    "min_weekly_gain_pct": 4.0,
    "min_price": 5.0,
    "max_price": 900.0,
    "ema_length": 20,
    "min_adr_pct": 1.5,
    "adr_length": 20,
    "min_market_cap": 1_000_000_000,
    "near_high_threshold_pct": 10.0,
    "history_weeks": 104,
    "chunk_size": 180,
    "chunk_pause_seconds": 1.0,
}


def load_config() -> dict:
    config = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        config.update(json.loads(CONFIG_PATH.read_text()))
    return config


def log(message: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {message}", flush=True)


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

def _extract(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Pull one symbol's OHLC out of a yfinance multi-ticker download."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    if isinstance(frame.columns, pd.MultiIndex):
        if symbol not in frame.columns.get_level_values(0):
            return pd.DataFrame()
        return frame[symbol]
    return frame


def download_chunked(
    symbols: list[str], period: str, interval: str, chunk_size: int, pause: float
) -> dict[str, pd.DataFrame]:
    """Download in chunks and return {symbol: cleaned OHLC frame}."""
    out: dict[str, pd.DataFrame] = {}
    total = len(symbols)
    for start in range(0, total, chunk_size):
        chunk = symbols[start : start + chunk_size]
        try:
            raw = yf.download(
                chunk,
                period=period,
                interval=interval,
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=False,
            )
        except Exception as exc:  # noqa: BLE001 - one bad chunk must not kill the run
            log(f"  chunk {start}-{start + len(chunk)} failed: {exc}")
            continue

        for symbol in chunk:
            frame = clean_frame(_extract(raw, symbol))
            if not frame.empty:
                out[symbol] = frame

        done = min(start + chunk_size, total)
        log(f"  {interval} {done}/{total} ({len(out)} with data)")
        if done < total:
            time.sleep(pause)
    return out


# ---------------------------------------------------------------------------
# Trend history
# ---------------------------------------------------------------------------

def build_history(
    weekly_data: dict[str, pd.DataFrame], meta: dict[str, dict], config: dict
) -> list[dict]:
    """Count bull micro gaps per week-ending across the whole universe.

    Two series are produced:
      universe_bull  every stock in the universe with a bull gap that week
      screened_bull  the subset that also cleared the gain / price / EMA
                     filters as at that week

    Each week also carries a per-industry tally of its bull gaps, which is what
    lets the dashboard's industry panel follow the chart's date range instead of
    being stuck on the latest week.

    Market cap and ADR% are measured as of today and are deliberately not
    applied retrospectively, so the counts describe gap activity in the
    current universe rather than a true point-in-time screen.
    """
    weeks = int(config["history_weeks"])
    universe_counts: dict[dt.date, int] = {}
    screened_counts: dict[dt.date, int] = {}
    span_counts: dict[dt.date, int] = {}
    industry_counts: dict[dt.date, dict[str, int]] = {}

    ema_length = int(config["ema_length"])
    min_gain = float(config["min_weekly_gain_pct"])
    min_price, max_price = float(config["min_price"]), float(config["max_price"])

    for symbol, weekly in weekly_data.items():
        if len(weekly) < 3:
            continue
        industry = meta.get(symbol, {}).get("industry", "Unclassified")

        flags = micro_gap_series(weekly)
        close = weekly["Close"]
        gain = (close / close.shift(1) - 1.0) * 100.0
        ema = close.ewm(span=ema_length, adjust=False).mean()

        qualifies = (
            (gain > min_gain)
            & (close >= min_price)
            & (close <= max_price)
            & (close > ema)
        )

        for stamp in flags.index[-weeks:]:
            friday = week_ending(stamp)
            span_counts[friday] = span_counts.get(friday, 0) + 1
            if bool(flags.at[stamp, "bull"]):
                universe_counts[friday] = universe_counts.get(friday, 0) + 1
                bucket = industry_counts.setdefault(friday, {})
                bucket[industry] = bucket.get(industry, 0) + 1
                if bool(qualifies.get(stamp, False)):
                    screened_counts[friday] = screened_counts.get(friday, 0) + 1

    ordered = sorted(span_counts.keys())[-weeks:]
    history = []
    for friday in ordered:
        covered = span_counts.get(friday, 0)
        bull = universe_counts.get(friday, 0)
        history.append(
            {
                "week_ending": friday.isoformat(),
                "universe_bull": bull,
                "screened_bull": screened_counts.get(friday, 0),
                "stocks_covered": covered,
                "bull_pct": round(bull / covered * 100.0, 2) if covered else 0.0,
                "industries": dict(
                    sorted(
                        industry_counts.get(friday, {}).items(),
                        key=lambda kv: -kv[1],
                    )
                ),
            }
        )
    return history


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly micro gap scan")
    parser.add_argument("--limit", type=int, default=0, help="cap universe size for testing")
    args = parser.parse_args()

    config = load_config()
    started = time.time()

    log("Building universe from Nasdaq listings")
    universe = build_universe(
        min_market_cap=float(config["min_market_cap"]),
        min_price=float(config["min_price"]),
        max_price=float(config["max_price"]),
    )
    if args.limit:
        universe = universe[: args.limit]
    log(f"  {len(universe)} stocks above ${config['min_market_cap'] / 1e9:.1f}B")

    meta = {row["symbol"]: row for row in universe}
    symbols = list(meta.keys())

    log("Downloading weekly history")
    weekly_data = download_chunked(
        symbols,
        period="max",
        interval="1wk",
        chunk_size=int(config["chunk_size"]),
        pause=float(config["chunk_pause_seconds"]),
    )
    weekly_data = {
        symbol: dropped
        for symbol, frame in weekly_data.items()
        if len(dropped := drop_open_week(frame)) >= 3
    }
    log(f"  usable weekly history for {len(weekly_data)} stocks")

    log("Rebuilding bull gap trend history")
    history = build_history(weekly_data, meta, config)

    log("Applying weekly filters")
    min_gain = float(config["min_weekly_gain_pct"])
    min_price, max_price = float(config["min_price"]), float(config["max_price"])
    ema_length = int(config["ema_length"])

    candidates: list[dict] = []
    for symbol, weekly in weekly_data.items():
        gain = weekly_gain_pct(weekly)
        if gain is None or gain <= min_gain:
            continue
        close = float(weekly["Close"].iloc[-1])
        if not (min_price <= close <= max_price):
            continue
        ema = weekly_ema(weekly, ema_length)
        if ema is None or close <= ema:
            continue

        flags = micro_gap_series(weekly)
        bull = bool(flags["bull"].iloc[-1])
        bear = bool(flags["bear"].iloc[-1])

        record = dict(meta[symbol])
        record.update(
            {
                "price": round(close, 2),
                "weekly_gain_pct": round(gain, 2),
                "ema20w": round(ema, 2),
                "pct_above_ema": round((close / ema - 1.0) * 100.0, 2),
                "micro_gap": gap_label(bull, bear),
                "candles": last_three_candles(weekly),
                "week_ending": week_ending(weekly.index[-1]).isoformat(),
            }
        )
        record.update(high_proximity(weekly))
        candidates.append(record)

    log(f"  {len(candidates)} passed gain / price / EMA")

    if not candidates:
        log("Nothing passed the weekly filters — writing an empty result set")
        results: list[dict] = []
    else:
        log("Downloading daily bars for ADR%")
        daily_data = download_chunked(
            [r["symbol"] for r in candidates],
            period="6mo",
            interval="1d",
            chunk_size=int(config["chunk_size"]),
            pause=float(config["chunk_pause_seconds"]),
        )

        min_adr = float(config["min_adr_pct"])
        adr_length = int(config["adr_length"])
        near = float(config["near_high_threshold_pct"])

        results = []
        for record in candidates:
            daily = daily_data.get(record["symbol"])
            if daily is None:
                continue
            adr = adr_percent(daily, adr_length)
            if adr is None or adr <= min_adr:
                continue

            pct_52w = record.get("pct_from_52w_high")
            pct_ath = record.get("pct_from_ath")
            record["adr_pct"] = round(adr, 2)
            record["near_52w_high"] = pct_52w is not None and pct_52w <= near
            record["near_ath"] = pct_ath is not None and pct_ath <= near
            record.pop("high_52w", None)
            record.pop("high_ath", None)
            results.append(record)

        log(f"  {len(results)} passed ADR% >= {min_adr}")

    results.sort(key=lambda r: r["weekly_gain_pct"], reverse=True)

    snapshot = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "week_ending": results[0]["week_ending"] if results else (
            history[-1]["week_ending"] if history else None
        ),
        "universe_size": len(weekly_data),
        "match_count": len(results),
        "bull_gap_count": sum(1 for r in results if r["micro_gap"] == "Bull"),
        "bear_gap_count": sum(1 for r in results if r["micro_gap"] == "Bear"),
        "filters": {
            "min_weekly_gain_pct": config["min_weekly_gain_pct"],
            "price_range": [config["min_price"], config["max_price"]],
            "above_weekly_ema": config["ema_length"],
            "min_adr_pct": config["min_adr_pct"],
            "min_market_cap": config["min_market_cap"],
            "near_high_threshold_pct": config["near_high_threshold_pct"],
        },
        "results": results,
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "results.json").write_text(json.dumps(snapshot, indent=1))
    (DOCS / "history.json").write_text(json.dumps(history, indent=1))

    log(
        f"Wrote {len(results)} matches and {len(history)} weeks of history "
        f"in {time.time() - started:.0f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
