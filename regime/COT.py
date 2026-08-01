"""
COT POSITIONING
- Net managed-money position divided by OPEN INTEREST (the futures market
  has grown since 2010, raw contract counts overstate today's positioning)
- Percentile over trailing 3 years, not a full-sample z-score
- Local cache so you don't re-download 17 zip files every run
"""

import io
import os
import zipfile
import requests
import pandas as pd
from datetime import date

CACHE = os.path.join(os.path.dirname(__file__), "cot_cache.csv")
MARKET = "GOLD - COMMODITY EXCHANGE INC."


def fetch_year(year):
    url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
    r = requests.get(url, timeout=30)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), encoding="latin1", low_memory=False)
    gold = df[df["Market_and_Exchange_Names"] == MARKET]
    gold = gold[["Report_Date_as_YYYY-MM-DD", "M_Money_Positions_Long_All",
                 "M_Money_Positions_Short_All", "Open_Interest_All"]].copy()
    gold.columns = ["date", "long", "short", "oi"]
    return gold


def load_cot(start_year=2010):
    this_year = date.today().year
    if os.path.exists(CACHE):
        cached = pd.read_csv(CACHE, parse_dates=["date"])
        last_cached_year = cached["date"].max().year
        fresh = [fetch_year(y) for y in range(last_cached_year, this_year + 1)]
        df = pd.concat([cached[cached["date"].dt.year < last_cached_year], *fresh])
    else:
        parts = []
        for y in range(start_year, this_year + 1):
            try:
                parts.append(fetch_year(y))
                print(f"  fetched {y}")
            except Exception as e:
                print(f"  skipped {y}: {e}")
        df = pd.concat(parts)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    df.to_csv(CACHE, index=False)
    return df


def positioning_series():
    """Full weekly history of managed-money net position as % of OI."""
    df = load_cot()
    df["net_pct_oi"] = (df["long"] - df["short"]) / df["oi"]
    return df


def cot_report():
    """Latest positioning reading for the dashboard."""
    df = positioning_series()
    window = df["net_pct_oi"].tail(156)  # ~3 years of weekly reports
    pctile = float((window < window.iloc[-1]).mean())
    if pctile > 0.90:
        note = "crowded long — contrarian caution"
    elif pctile < 0.10:
        note = "washed out — contrarian support"
    else:
        note = "not extreme"
    return {"net_pct_oi": float(df["net_pct_oi"].iloc[-1]),
            "pctile_3y": pctile, "note": note, "df": df}


if __name__ == "__main__":
    r = cot_report()
    print("--- COT Positioning ---")
    print(f" MM net position : {r['net_pct_oi']*100:.1f}% of open interest")
    print(f" 3y percentile   : {r['pctile_3y']*100:.0f}th")
    print(f" Reading         : {r['note']}")
