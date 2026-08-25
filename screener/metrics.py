"""Screen measurements.

Weekly bars drive everything except ADR%, which needs daily bars. The one
subtlety worth knowing: yfinance labels a weekly bar with the Monday that
starts it, and it will happily hand back the current, still-open week. Every
number here is meant to describe a *completed* week, so the in-progress bar is
dropped before anything is measured.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

OHLC = ("Open", "High", "Low", "Close")


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with missing OHLC and coerce to numeric."""
    if df is None or df.empty:
        return pd.DataFrame(columns=list(OHLC))
    frame = df.copy()
    for column in OHLC:
        if column not in frame.columns:
            return pd.DataFrame(columns=list(OHLC))
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=list(OHLC))
    frame = frame[(frame["High"] > 0) & (frame["Low"] > 0) & (frame["Close"] > 0)]
    return frame.sort_index()


def week_ending(stamp) -> dt.date:
    """The Friday that closes the calendar week containing `stamp`.

    yfinance usually labels a weekly bar with its Monday, but not always —
    a handful of tickers come back anchored to other weekdays, which would
    otherwise scatter them into phantom one-stock weeks. Normalising every
    bar onto its week-ending Friday makes the buckets line up.
    """
    return pd.Timestamp(stamp).to_period("W-FRI").end_time.date()


def drop_open_week(weekly: pd.DataFrame, today: dt.date | None = None) -> pd.DataFrame:
    """Remove the final weekly bar if its week has not finished trading."""
    if weekly.empty:
        return weekly
    today = today or dt.date.today()
    if today <= week_ending(weekly.index[-1]):
        return weekly.iloc[:-1]
    return weekly


def weekly_gain_pct(weekly: pd.DataFrame) -> float | None:
    """Percent change of the last completed week's close vs the week before."""
    if len(weekly) < 2:
        return None
    previous, current = weekly["Close"].iloc[-2], weekly["Close"].iloc[-1]
    if previous <= 0:
        return None
    return float((current / previous - 1.0) * 100.0)


def weekly_ema(weekly: pd.DataFrame, length: int = 20) -> float | None:
    """Final value of the weekly EMA of closes."""
    if len(weekly) < length:
        return None
    return float(weekly["Close"].ewm(span=length, adjust=False).mean().iloc[-1])


def adr_percent(daily: pd.DataFrame, length: int = 20) -> float | None:
    """Average Daily Range as a percent, the Qullamaggie/Stockbee formulation:

        ADR% = 100 * (mean(High / Low over the last `length` days) - 1)

    This is a volatility measure, not a volume measure.
    """
    if len(daily) < length:
        return None
    window = daily.iloc[-length:]
    ratio = (window["High"] / window["Low"]).replace([float("inf")], pd.NA).dropna()
    if len(ratio) < length:
        return None
    return float((ratio.mean() - 1.0) * 100.0)


def high_proximity(weekly: pd.DataFrame, lookback_weeks: int = 52) -> dict:
    """Distance from the 52-week high and the all-time high.

    Returned percentages are how far *below* each high the last close sits, so
    0 means sitting at the high and 8.4 means 8.4% under it.
    """
    if weekly.empty:
        return {}
    close = float(weekly["Close"].iloc[-1])
    high_52w = float(weekly["High"].iloc[-lookback_weeks:].max())
    high_all = float(weekly["High"].max())

    def below(high: float) -> float | None:
        if high <= 0:
            return None
        return round((1.0 - close / high) * 100.0, 2)

    return {
        "high_52w": round(high_52w, 4),
        "high_ath": round(high_all, 4),
        "pct_from_52w_high": below(high_52w),
        "pct_from_ath": below(high_all),
    }


def last_three_candles(weekly: pd.DataFrame) -> list[dict]:
    """The W-2 / W-1 / W0 OHLC values that the micro gap glyph draws."""
    if len(weekly) < 3:
        return []
    tail = weekly.iloc[-3:]
    return [
        {
            "o": round(float(row["Open"]), 4),
            "h": round(float(row["High"]), 4),
            "l": round(float(row["Low"]), 4),
            "c": round(float(row["Close"]), 4),
        }
        for _, row in tail.iterrows()
    ]
