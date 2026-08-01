"""
GOLD TREND REGIME FILTER
Logic: gold is one of the most persistently trending assets, so regime is
defined by trend, not by deviation from a fitted curve:
  1. Price above/below its 200-day moving average
  2. 12-month momentum positive/negative
Both bullish -> BULL (+1) | Both bearish -> BEAR (-1) | Mixed -> NEUTRAL (0)

Also reports STRETCH — how far price sits above the 200dma vs history —
because "bull regime" at +2% above the MA and at +25% are very different
situations. The regime says WHICH WAY; stretch says HOW FAR ALONG.
History starts 2010 so the chart proves the filter goes red when it
should (2013-2015, 2022) rather than being a permanent green light.
"""

import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt


def get_aud_gold(start="2010-01-01"):
    gold = yf.download("GC=F", start=start, auto_adjust=True, progress=False)["Close"].squeeze()
    audusd = yf.download("AUDUSD=X", start=start, auto_adjust=True, progress=False)["Close"].squeeze()
    df = pd.DataFrame({"gp": gold, "audusd": audusd}).dropna()
    df["gp_aud"] = df["gp"] / df["audusd"]
    return df


def build_regime(df):
    df["ma200"] = df["gp_aud"].rolling(200).mean()
    df["mom12m"] = df["gp_aud"].pct_change(252)  # ~252 trading days = 12 months

    df["above_ma"] = df["gp_aud"] > df["ma200"]
    df["mom_pos"] = df["mom12m"] > 0

    def classify(row):
        if row["above_ma"] and row["mom_pos"]:
            return 1
        if (not row["above_ma"]) and (not row["mom_pos"]):
            return -1
        return 0

    df["regime"] = df.apply(classify, axis=1)

    # stretch: % above/below the 200dma, and its percentile vs all history
    df["stretch"] = df["gp_aud"] / df["ma200"] - 1
    df = df.dropna(subset=["ma200", "mom12m"]).copy()
    df["stretch_pctile"] = df["stretch"].rank(pct=True)
    return df


def trend_report():
    """Latest trend reading for the dashboard."""
    df = build_regime(get_aud_gold())
    latest = df.iloc[-1]
    labels = {1: "BULL", 0: "NEUTRAL / transition", -1: "BEAR"}
    stretch_note = ""
    if latest["regime"] == 1 and latest["stretch_pctile"] > 0.90:
        stretch_note = " — but EXTENDED vs history, pullback-prone"
    return {
        "regime": labels[int(latest["regime"])] + stretch_note,
        "price": latest["gp_aud"],
        "ma200": latest["ma200"],
        "mom12m": latest["mom12m"],
        "stretch": latest["stretch"],
        "stretch_pctile": latest["stretch_pctile"],
        "df": df,
    }


def plot_regime(df, ax1=None, ax2=None):
    own_fig = ax1 is None
    if own_fig:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                       gridspec_kw={"height_ratios": [3, 1]})
    ax1.plot(df.index, df["gp_aud"], label="AUD Gold", color="black", lw=1)
    ax1.plot(df.index, df["ma200"], label="200-day MA", color="orange", lw=1.2)

    lo, hi = df["gp_aud"].min(), df["gp_aud"].max()
    ax1.fill_between(df.index, lo, hi, where=df["regime"] == 1,
                     color="green", alpha=0.10, label="Bull regime")
    ax1.fill_between(df.index, lo, hi, where=df["regime"] == -1,
                     color="red", alpha=0.10, label="Bear regime")
    ax1.legend(loc="upper left")
    ax1.set_title("AUD Gold — Trend Regime since 2010 (200dma + 12m momentum)")

    ax2.plot(df.index, df["stretch"] * 100, color="steelblue", lw=1)
    ax2.axhline(0, color="grey", lw=0.8)
    q90 = df["stretch"].quantile(0.90) * 100
    ax2.axhline(q90, color="firebrick", lw=0.8, ls="--", label="90th pctile (extended)")
    ax2.set_ylabel("% above 200dma")
    ax2.legend(loc="upper left")

    if own_fig:
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    r = trend_report()
    print("--- Gold Trend Regime ---")
    print(f" AUD gold      : ${r['price']:,.0f}")
    print(f" 200-day MA    : ${r['ma200']:,.0f}")
    print(f" 12m momentum  : {r['mom12m']*100:+.1f}%")
    print(f" Stretch       : {r['stretch']*100:+.1f}% above MA "
          f"({r['stretch_pctile']*100:.0f}th percentile since 2010)")
    print(f" Regime        : {r['regime']}")
    plot_regime(r["df"])
