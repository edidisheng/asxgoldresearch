"""
GOLD MACRO DASHBOARD
Replaces the composite score/verdict. Three independent reads — trend,
macro, positioning — presented side by side. No single number, no BUY/SELL:
the indicators describe the environment, the user makes the call.

  TREND        which way is the market going, and how extended is it
  MACRO        are real yields / USD / inflation expectations helping or hurting
  POSITIONING  is the trade crowded (contrarian caution) or washed out
"""

import matplotlib.pyplot as plt
from goldregime import trend_report, plot_regime
from macroindicators import macro_reports
from COT import cot_report


def print_dashboard(trend, macro, cot):
    print("=" * 62)
    print(" GOLD MACRO DASHBOARD")
    print("=" * 62)

    print("\n TREND")
    print(f"   AUD gold ${trend['price']:,.0f} vs 200dma ${trend['ma200']:,.0f} | "
          f"12m mom {trend['mom12m']*100:+.1f}%")
    print(f"   Stretch {trend['stretch']*100:+.1f}% above MA "
          f"({trend['stretch_pctile']*100:.0f}th pctile since 2010)")
    print(f"   Regime: {trend['regime']}")

    print("\n MACRO")
    for r in macro:
        print(f"   {r['name']:<20} {r['detail']:<32} {r['reading']}")

    print("\n POSITIONING")
    print(f"   MM net {cot['net_pct_oi']*100:.1f}% of OI, "
          f"{cot['pctile_3y']*100:.0f}th pctile of 3y — {cot['note']}")
    print("\n" + "=" * 62)


def plot_dashboard(trend, cot):
    fig = plt.figure(figsize=(13, 9))
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 1, 1.4], hspace=0.35)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2])

    plot_regime(trend["df"], ax1=ax1, ax2=ax2)

    cdf = cot["df"]
    ax3.plot(cdf["date"], cdf["net_pct_oi"] * 100, color="darkslateblue", lw=1)
    lo, hi = cdf["net_pct_oi"].quantile([0.10, 0.90]) * 100
    ax3.axhline(hi, color="firebrick", lw=0.8, ls="--", label="crowded (90th pctile)")
    ax3.axhline(lo, color="green", lw=0.8, ls="--", label="washed out (10th pctile)")
    ax3.set_ylabel("MM net % of OI")
    ax3.set_title("COT: managed-money positioning")
    ax3.legend(loc="upper left", fontsize=8)

    plt.savefig("gold_dashboard.png", dpi=150, bbox_inches="tight")
    print("Saved gold_dashboard.png")
    plt.show()


if __name__ == "__main__":
    trend = trend_report()
    macro = macro_reports()
    cot = cot_report()
    print_dashboard(trend, macro, cot)
    plot_dashboard(trend, cot)
