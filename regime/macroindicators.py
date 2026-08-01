"""
MACRO INDICATORS
- FRED key from environment variable / .env (never commit keys)
- Signals based on CHANGES / rolling windows, not full-sample z-scores:
  real yields and DXY are non-stationary, so the 2003-2026 mean mixes
  regimes and misleads. What moves gold is the DIRECTION of real yields.
- Real yield = nominal - breakeven, so breakeven partly double-counts;
  it is kept as a dashboard item, real yield is the headline.
"""

import os
import pandas as pd
import yfinance as yf
from fredapi import Fred
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.environ.get("FRED_API_KEY")
if not FRED_API_KEY:
    raise SystemExit("Set FRED_API_KEY in your .env (free at fred.stlouisfed.org)")

fred = Fred(api_key=FRED_API_KEY)

ROLL = 756  # 3-year rolling window in trading days


def real_yield_report():
    """12-month change in 10yr TIPS yield. Falling real yields = tailwind."""
    y = fred.get_series("DFII10", observation_start="2010-01-01").dropna()
    change_12m = float(y.iloc[-1] - y.iloc[-252])
    reading = "tailwind (falling)" if change_12m < -0.15 else \
              "headwind (rising)" if change_12m > 0.15 else "neutral"
    return {"name": "Real 10y yield", "value": float(y.iloc[-1]),
            "detail": f"{y.iloc[-1]:.2f}%, {change_12m:+.2f}pp over 12m", "reading": reading}


def dollar_report():
    """12-month % change in DXY. Rising USD = headwind for gold."""
    dxy = yf.download("DX-Y.NYB", start="2010-01-01", auto_adjust=True,
                      progress=False)["Close"].squeeze().dropna()
    pct_12m = float(dxy.iloc[-1] / dxy.iloc[-252] - 1)
    reading = "tailwind (USD falling)" if pct_12m < -0.03 else \
              "headwind (USD rising)" if pct_12m > 0.03 else "neutral"
    return {"name": "US Dollar (DXY)", "value": float(dxy.iloc[-1]),
            "detail": f"{dxy.iloc[-1]:.1f}, {pct_12m*100:+.1f}% over 12m", "reading": reading}


def breakeven_report():
    """5yr breakeven inflation vs its 3-year rolling mean."""
    be = fred.get_series("T5YIE", observation_start="2010-01-01").dropna()
    z = float((be.iloc[-1] - be.rolling(ROLL).mean().iloc[-1]) / be.rolling(ROLL).std().iloc[-1])
    reading = "tailwind (infl. expectations elevated)" if z > 0.5 else \
              "headwind (infl. expectations depressed)" if z < -0.5 else "neutral"
    return {"name": "5y breakeven infl.", "value": float(be.iloc[-1]),
            "detail": f"{be.iloc[-1]:.2f}%, 3y z-score {z:+.2f}", "reading": reading}


def macro_reports():
    return [real_yield_report(), dollar_report(), breakeven_report()]


if __name__ == "__main__":
    print("--- Macro Indicators ---")
    for r in macro_reports():
        print(f" {r['name']:<20} {r['detail']:<32} {r['reading']}")
