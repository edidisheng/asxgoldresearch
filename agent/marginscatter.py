"""
EV/oz vs AISC MARGIN — market-implied producer valuation
Replaces arbitrary producer adjustments with the line the market draws.

Logic: EV is roughly the PV of (margin x future ounces), so across a peer
group EV/oz should scale with margin per ounce. Fit a line through
EV/oz vs (AUD spot - AISC); the residual is the mispricing signal
ADJUSTED FOR COST QUALITY. Below the line = cheap for its margin;
above = expensive.

Inputs: aisc_history.csv (from quarterly_agent) + EV/oz from the screener.
"""

import pandas as pd
import numpy as np
import statsmodels.api as sm
import matplotlib.pyplot as plt
import yfinance as yf

from ASXgoldscreener import results_df


def get_spot_aud():
    gold = yf.download("GC=F", period="5d", auto_adjust=True, progress=False)["Close"].squeeze()
    aud = yf.download("AUDUSD=X", period="5d", auto_adjust=True, progress=False)["Close"].squeeze()
    return float(gold.iloc[-1] / aud.iloc[-1])


def build_dataset():
    hist = pd.read_csv("aisc_history.csv").dropna(subset=["aisc_aud_oz"])
    # most recent quarter per ticker
    latest = hist.sort_values("run_date").groupby("ticker").tail(1)

    spot = get_spot_aud()
    df = latest.merge(results_df[["ticker", "ev_oz", "stage"]], on="ticker", how="inner")
    # producers only: a developer's "AISC" is a study projection, not a real cost
    df = df[df["stage"] == "producer"]
    df["margin"] = spot - df["aisc_aud_oz"]
    return df.reset_index(drop=True), spot


def fit_and_rank(df):
    if len(df) < 4:
        raise SystemExit(f"Only {len(df)} producers with AISC data — need at least 4. "
                         "Rerun quarterly_agent to fill aisc_history.csv")
    if len(df) < 6:
        print(f"NOTE: only {len(df)} data points — the fitted line is indicative, "
              "not statistical. Add more producers for a robust fit.")

    X = sm.add_constant(df["margin"])
    model = sm.OLS(df["ev_oz"], X).fit()
    df["fair_ev_oz"] = model.fittedvalues
    df["mispricing_pct"] = (df["fair_ev_oz"] - df["ev_oz"]) / df["fair_ev_oz"] * 100

    slope = model.params["margin"]
    print(f"\nMarket-implied relationship: each extra A$100/oz of margin adds "
          f"~A${slope*100:.0f}/oz of EV  (R² {model.rsquared:.2f}, n={len(df)})")

    ranked = df.sort_values("mispricing_pct", ascending=False).reset_index(drop=True)
    print("\n--- RANKED BY MARGIN-ADJUSTED MISPRICING ---")
    print(f"  {'Ticker':<8}{'AISC':>8}{'Margin':>9}{'EV/oz':>8}{'Fair':>8}{'Mispricing':>12}")
    print("  " + "-" * 55)
    for _, r in ranked.iterrows():
        print(f"  {r['ticker']:<8}{r['aisc_aud_oz']:>8.0f}{r['margin']:>9.0f}"
              f"{r['ev_oz']:>8.0f}{r['fair_ev_oz']:>8.0f}{r['mispricing_pct']:>+11.1f}%")
    return ranked, model


def plot_scatter(df, model, spot):
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.scatter(df["margin"], df["ev_oz"], s=80, color="darkgoldenrod", zorder=3)

    xs = np.linspace(df["margin"].min() * 0.9, df["margin"].max() * 1.1, 50)
    ax.plot(xs, model.params["const"] + model.params["margin"] * xs,
            color="grey", ls="--", lw=1.2, label="Market-implied fair value")

    for _, r in df.iterrows():
        cheap = r["mispricing_pct"] > 0
        ax.annotate(f"{r['ticker']}\n{r['mispricing_pct']:+.0f}%",
                    (r["margin"], r["ev_oz"]),
                    textcoords="offset points", xytext=(8, 6), fontsize=9,
                    color="green" if cheap else "firebrick")

    ax.set_xlabel("AISC margin (A$/oz)  =  spot AUD gold − quarterly AISC")
    ax.set_ylabel("EV per resource ounce (A$/oz)")
    ax.set_title(f"ASX Gold Producers — EV/oz vs Margin  (spot A${spot:,.0f}/oz)\n"
                 "Below the line = cheap for its cost quality")
    ax.legend()
    plt.tight_layout()
    plt.savefig("margin_scatter.png", dpi=150)
    print("\nSaved margin_scatter.png")
    plt.show()


if __name__ == "__main__":
    df, spot = build_dataset()
    ranked, model = fit_and_rank(df)
    plot_scatter(df, model, spot)
    ranked.to_csv("margin_adjusted_valuations.csv", index=False)
    print("Saved margin_adjusted_valuations.csv")