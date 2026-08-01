# Gold Regime Module

Replaces `goldtrendregressionLONGTERM.py`, `goldtrendregressionSHORTTERM.py`,
and upgrades `macroindicators.py` / `COT.py`.

## Files

| File | What it does | Weight in composite |
|---|---|---|
| `goldregime.py` | Trend regime: 200dma + 12m momentum, regime-shaded chart | 40% |
| `macroindicators.py` | Real yield 12m change, DXY 12m change, breakeven 3y z | 25% |
| `margincycle.py` | AUD gold minus sector median AISC (the miner cycle) | 20% |
| `COT.py` | Managed-money net % of open interest, 3y percentile, cached | 15% |
| `regimescore.py` | Combines all four into a 0-100 score + verdict | — |

## Setup

1. Delete both `goldtrendregression*.py` files from `maincode/`, drop these in.
2. Get a fresh FRED key (the old one is public in your repo history — revoke it):
   set it as an environment variable, never in code:
   ```
   export FRED_API_KEY=yournewkey     # add to ~/.zshrc
   ```
3. Run `python regimescore.py` for the full picture, or any file individually.

## To make it fully yours (important)

- `margincycle.py` ships with PLACEHOLDER sector AISC estimates by FY.
  Replace them with the median AISC of the producers in `golddataset.csv`
  from quarterly reports (or add an `aisc_aud` column and compute the median).
  This is the differentiated part — do not skip it.
- The weights in `regimescore.py` are judgment calls. Change them and be able
  to defend your choice in an interview ("trend heaviest because gold trends
  persist and macro fair-value broke down post-2022" is a good answer).

## Interview talking points baked in

- Why full-sample z-scores on real yields/DXY are wrong (non-stationarity,
  regime breaks) and 12m changes / rolling windows are right.
- Why net COT position must be scaled by open interest.
- Why miners follow the margin cycle, not the gold price.
- Why a quadratic time-trend regression is curve fitting, not signal.
