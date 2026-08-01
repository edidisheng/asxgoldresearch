"""
BUILD SITE DATA
Runs the screener, margin fit, and gold dashboard, then writes everything
the static site needs into docs/ :
  docs/data/site_data.json   - tables, readings, quarterly report text
  docs/assets/*.png          - dashboard + margin scatter charts

Run from the project root:  python build_site.py
GitHub Actions runs this daily; the Claude agent stays manual — this
script only READS aisc_history.csv and the latest quarterly_analysis_*.md.

Expected layout (adjust the paths below if yours differs):
  asx-scraper/
    agent/ASXgoldscreener.py     agent/marginscatter.py (not needed here)
    regime/goldregime.py  regime/macroindicators.py  regime/COT.py
    golddataset.csv  aisc_history.csv  quarterly_analysis_*.md
    build_site.py  docs/
"""

import json
import re
import sys
import glob
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "regime"))

DOCS = ROOT / "docs"
(DOCS / "data").mkdir(parents=True, exist_ok=True)
(DOCS / "assets").mkdir(parents=True, exist_ok=True)

site = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "errors": []}


# ---------- 1. SCREENER ----------
try:
    from ASXgoldscreener import results_df

    cols = ["ticker", "name", "stage", "price", "ev_oz", "adj_peer_ev_oz",
            "discount_pct", "signal"]
    screener = results_df[[c for c in cols if c in results_df.columns]].copy()
    screener = screener.sort_values("discount_pct", ascending=False)
    site["screener"] = json.loads(screener.round(1).to_json(orient="records"))
except (Exception, SystemExit) as e:
    site["errors"].append(f"screener: {e}")
    site["screener"] = []
    results_df = None


# ---------- 2. MARGIN ANALYSIS ----------
try:
    import statsmodels.api as sm
    import yfinance as yf

    hist = pd.read_csv(ROOT / "aisc_history.csv").dropna(subset=["aisc_aud_oz"])
    latest = hist.sort_values("run_date").groupby("ticker").tail(1)

    gold = yf.download("GC=F", period="5d", auto_adjust=True, progress=False)["Close"].squeeze()
    aud = yf.download("AUDUSD=X", period="5d", auto_adjust=True, progress=False)["Close"].squeeze()
    spot = float(gold.iloc[-1] / aud.iloc[-1])

    mdf = latest.merge(results_df[["ticker", "ev_oz", "stage"]], on="ticker")
    mdf = mdf[mdf["stage"] == "producer"].copy()
    mdf["margin"] = spot - mdf["aisc_aud_oz"]

    X = sm.add_constant(mdf["margin"])
    model = sm.OLS(mdf["ev_oz"], X).fit()
    mdf["fair_ev_oz"] = model.fittedvalues
    mdf["mispricing_pct"] = (mdf["fair_ev_oz"] - mdf["ev_oz"]) / mdf["fair_ev_oz"] * 100

    site["margin"] = {
        "spot_aud": round(spot),
        "slope_per_100": round(model.params["margin"] * 100),
        "r2": round(model.rsquared, 2),
        "rows": json.loads(mdf[["ticker", "aisc_aud_oz", "margin", "ev_oz",
                                "fair_ev_oz", "mispricing_pct"]]
                           .sort_values("mispricing_pct", ascending=False)
                           .round(1).to_json(orient="records")),
    }

    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.scatter(mdf["margin"], mdf["ev_oz"], s=90, color="darkgoldenrod", zorder=3)
    xs = np.linspace(mdf["margin"].min() * 0.9, mdf["margin"].max() * 1.1, 50)
    ax.plot(xs, model.params["const"] + model.params["margin"] * xs,
            color="grey", ls="--", lw=1.2, label="Market-implied fair value")
    for _, r in mdf.iterrows():
        ax.annotate(f"{r['ticker']} {r['mispricing_pct']:+.0f}%",
                    (r["margin"], r["ev_oz"]), textcoords="offset points",
                    xytext=(8, 6), fontsize=9,
                    color="green" if r["mispricing_pct"] > 0 else "firebrick")
    ax.set_xlabel("AISC margin (A$/oz)")
    ax.set_ylabel("EV per resource oz (A$/oz)")
    ax.set_title(f"EV/oz vs Margin — spot A${spot:,.0f}/oz  |  below line = cheap for its cost quality",
                 fontsize=11)
    ax.legend()
    plt.tight_layout()
    plt.savefig(DOCS / "assets" / "margin_scatter.png", dpi=150)
    plt.close()
except (Exception, SystemExit) as e:
    site["errors"].append(f"margin: {e}")
    site["margin"] = None


# ---------- 3. GOLD DASHBOARD ----------
try:
    from goldregime import trend_report, plot_regime
    from macroindicators import macro_reports
    from COT import cot_report

    trend = trend_report()
    macro = macro_reports()
    cot = cot_report()

    site["dashboard"] = {
        "regime": trend["regime"],
        "price": round(trend["price"]),
        "ma200": round(trend["ma200"]),
        "mom12m_pct": round(trend["mom12m"] * 100, 1),
        "stretch_pct": round(trend["stretch"] * 100, 1),
        "stretch_pctile": round(trend["stretch_pctile"] * 100),
        "macro": [{k: r[k] for k in ("name", "detail", "reading")} for r in macro],
        "cot_net_pct_oi": round(cot["net_pct_oi"] * 100, 1),
        "cot_pctile_3y": round(cot["pctile_3y"] * 100),
        "cot_note": cot["note"],
    }

    fig = plt.figure(figsize=(12, 9))
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 1, 1.4], hspace=0.4)
    ax1 = fig.add_subplot(gs[0]); ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2])
    plot_regime(trend["df"], ax1=ax1, ax2=ax2)
    cdf = cot["df"]
    ax3.plot(cdf["date"], cdf["net_pct_oi"] * 100, color="darkslateblue", lw=1)
    lo, hi = cdf["net_pct_oi"].quantile([0.10, 0.90]) * 100
    ax3.axhline(hi, color="firebrick", lw=0.8, ls="--", label="crowded (90th pctile)")
    ax3.axhline(lo, color="green", lw=0.8, ls="--", label="washed out (10th pctile)")
    ax3.set_title("COT: managed-money net % of open interest", fontsize=10)
    ax3.legend(loc="upper left", fontsize=8)
    plt.savefig(DOCS / "assets" / "gold_dashboard.png", dpi=150, bbox_inches="tight")
    plt.close()
except (Exception, SystemExit) as e:
    site["errors"].append(f"dashboard: {e}")
    site["dashboard"] = None


# ---------- 4. QUARTERLY REPORT (latest md, split into sections) ----------
try:
    md_files = sorted(glob.glob(str(ROOT / "quarterly_analysis_*.md")))
    if not md_files:
        raise FileNotFoundError("no quarterly_analysis_*.md found")
    text = Path(md_files[-1]).read_text()
    site["quarterly_date"] = re.search(r"(\d{4}-\d{2}-\d{2})", md_files[-1]).group(1)

    text = re.sub(r"^=+\s*$", "", text, flags=re.MULTILINE)  # strip ==== rules

    # Split at the comparative heading FIRST — the AI uses ## headings inside
    # the ranking itself, so splitting the whole file on ## would shred it.
    m = re.search(r"^#+ *COMPARATIVE.*$", text, flags=re.MULTILINE)
    before = text[:m.start()] if m else text
    comparison = text[m.start():].strip() if m else ""

    companies = {}
    for p in re.split(r"^## ", before, flags=re.MULTILINE)[1:]:
        title = p.split("\n", 1)[0].strip()
        t = re.search(r"\((\w+)\)", title)
        companies[t.group(1) if t else title] = "## " + p.strip()
    site["quarterly"] = {"comparison": comparison, "companies": companies}
except (Exception, SystemExit) as e:
    site["errors"].append(f"quarterly: {e}")
    site["quarterly"] = None


# ---------- WRITE ----------
out = DOCS / "data" / "site_data.json"
out.write_text(json.dumps(site, indent=1))
print(f"Wrote {out}")
if site["errors"]:
    print("Completed WITH ERRORS:")
    for e in site["errors"]:
        print("  -", e)
else:
    print("All sections built cleanly.")
