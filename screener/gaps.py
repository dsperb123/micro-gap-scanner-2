"""Micro gap detection.

MICRO GAP DEFINITION — matches microGapBull / microGapBear in the
`Open Micro Gaps with Patterns` Pine indicator. Three consecutive weekly
candles W-2, W-1, W0, where W0 is the bar being evaluated:

  Bullish:
      low[W0]  >  high[W-2]     clean gap up, zero overlap with W-2
      low[W-1] >= low[W-2]      rising staircase of lows
      low[W0]  >= low[W-1]

  Bearish (mirror):
      high[W0]  <  low[W-2]
      high[W-1] <= high[W-2]
      high[W0]  <= high[W-1]

Every function here evaluates the condition at *every* bar index, not just
the newest one. That is what lets the dashboard rebuild a full trend history
of weekly gap counts from a single price download, rather than waiting weeks
to accumulate it.
"""

from __future__ import annotations

import pandas as pd


def micro_gap_series(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorised bull/bear micro gap flags for every bar in df.

    Expects columns High and Low. Returns a DataFrame indexed like df with
    boolean 'bull' and 'bear' columns. The first two bars are always False
    (not enough history to form a three-candle pattern).
    """
    high, low = df["High"], df["Low"]

    bull = (
        (low > high.shift(2))
        & (low.shift(1) >= low.shift(2))
        & (low >= low.shift(1))
    )
    bear = (
        (high < low.shift(2))
        & (high.shift(1) <= high.shift(2))
        & (high <= high.shift(1))
    )

    return pd.DataFrame(
        {
            "bull": bull.fillna(False).astype(bool),
            "bear": bear.fillna(False).astype(bool),
        },
        index=df.index,
    )


def gap_label(bull: bool, bear: bool) -> str:
    """Human-readable label for the Micro Gap column."""
    if bull:
        return "Bull"
    if bear:
        return "Bear"
    return "None"
