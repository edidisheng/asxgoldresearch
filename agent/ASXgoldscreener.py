import pandas as pd
import yfinance as yf

#Peer benchmarks 
peer_ev_per_oz_producer = 542
peer_ev_per_oz_developer = 139
peer_ev_per_oz_explorer = 40 

#Grade adjustments 
GRADE_ADJUSTMENTS = [
    {"max_gt" : 0.6 , "adjustment" : -0.40},
    {"max_gt" : 1 , "adjustment" : -0.20},
    {"max_gt" : 2 , "adjustment" : -0},
    {"max_gt" : 3.5 , "adjustment" : +0.2},
    {"max_gt" : 6 , "adjustment" : +0.40},
    {"max_gt" : 9999 , "adjustment" : +0.60},

]

#jurisdiction discounts
jurisdiction_discounts = {
    1:0,
    2:0.15,
    3:0.35,
    4:0.55,
}


#LOADING CSV

def load_companies(filepath):
    df = pd.read_csv("golddataset.csv")
    print = (f" Loaded {len(df)} companies from {filepath}")
    return df

df = load_companies("golddataset.csv")
print(df)

##df = dataframe


## LIVE PRICES FROM YAHOO FINANCE

def get_price(ticker):
 try:
    stock = yf.Ticker(ticker + ".AX") 
    price = stock.fast_info["last_price"]
    return price
 except Exception as e:
        print(f"  WARNING: Could not fetch price for {ticker} — {e}")
        return None

for i, row in df.iterrows():
    price = get_price(row["ticker"])
    if price is None:
        print(f"  {row['ticker']}:    price unavailable")
    else:
        print(f"  {row['ticker']}:    A${price:.2f}")


## CALCULATIONS For each company:

##Market cap  =  price  ×  shares
##EV          =  market cap  -  cash + debt
##EV/oz       =  EV  /  (resource_moz × 1,000,000)

def calculation_metrics(df):
    results = []

    for i, row in df.iterrows():
        price = get_price(row["ticker"])
        if price is None: 
            print(f"    Skipping {row['ticker']} - no price availible")
            continue

        market_cap = price * row["shares_total"]
        ev = market_cap - row["cash_aud"] + row["debt_total"]
        ev_oz = ev / (row["resource_moz"] * 1000000)

        results.append({
            "ticker" : row["ticker"],
            "name" : row["name"],
            "stage" : row["stage"],
            "price" : price,
            "market_cap" : market_cap,
            "ev" :  ev,
            "resource_moz" : row["resource_moz"],
            "grade_gt":    row["grade_gt"],
            "jurisdiction_tier": row["jurisdiction_tier"],
            "ev_oz":       ev_oz,


        })

        print(f"  {row['ticker']}:  "
              f"price A${price:.2f}  "
              f"mktcap A${market_cap/1e6:.0f}M  "
              f"EV A${ev/1e6:.0f}M  "
              f"EV/oz A${ev_oz:.0f}/oz")

    return pd.DataFrame(results)

results_df = calculation_metrics(df)


##grade and jurisdiction adjustments
## This is very unclear code that should be optimised
def get_grade_adjustment(grade_gt):
    for band in GRADE_ADJUSTMENTS:
        if grade_gt <= band["max_gt"]:
            return band["adjustment"]
    return GRADE_ADJUSTMENTS[-1]["adjustment"]

def get_peer_benchmark(stage):
    if stage == "producer":
        return peer_ev_per_oz_producer
    elif stage == "developer":
        return peer_ev_per_oz_developer
    else:
        return peer_ev_per_oz_explorer

## EXCLUDING THE MEASURED 


##MAKING PEER BENCHMARKS AN AVERAGE  INSTEAD OF HARDCODED NUMBER
def apply_adjustments(results_df):
    for i, row in results_df.iterrows():
        jur_discount = jurisdiction_discounts[row["jurisdiction_tier"]]

        # exclude self from peer average
        peers = results_df[
            (results_df["stage"] == row["stage"]) &
            (results_df["ticker"] != row["ticker"])
        ]["ev_oz"]
        
        base_peer = peers.mean() if len(peers) > 0 else get_peer_benchmark(row["stage"])

        if row["stage"] == "producer":
            grade_adj = 0.0
        else:
            grade_adj = get_grade_adjustment(row["grade_gt"])

        adj_peer = base_peer * (1 + grade_adj) * (1 - jur_discount)

        results_df.at[i, "grade_adj"]      = grade_adj
        results_df.at[i, "jur_discount"]   = jur_discount
        results_df.at[i, "adj_peer_ev_oz"] = adj_peer

    return results_df

results_df = apply_adjustments(results_df)




##discount to peers and buy signal

def calculate_signals(results_df):
    for i, row in results_df.iterrows():
        discount_pct = ((row["adj_peer_ev_oz"] - row["ev_oz"])
                       / row["adj_peer_ev_oz"]) * 100

        if discount_pct > 20:
            signal = "CHEAP ✅"
        elif discount_pct < -20:
            signal = "RICH  🚩"
        else:
            signal = "FAIR  ⚠️"

        results_df.at[i, "discount_pct"] = discount_pct
        results_df.at[i, "signal"]       = signal

    return results_df

results_df = calculate_signals(results_df)

##rank and print table


def print_table(results_df):
    ranked = results_df.sort_values("discount_pct", ascending=False)
    ranked = ranked.reset_index(drop=True)

    print("\n" + "=" * 78)
    print("  ASX GOLD SCREENER — RANKED BY DISCOUNT TO PEERS")
    print("=" * 78)
    print(f"  {'Rank':<5} {'Ticker':<6} {'Name':<25} {'Stage':<10} "
          f"{'EV/oz':>8} {'Peer':>8} {'Discount':>10} {'Signal':<12}")
    print("-" * 78)

    for i, row in ranked.iterrows():
        print(f"  {i+1:<5} "
              f"{row['ticker']:<6} "
              f"{row['name']:<25} "
              f"{row['stage']:<10} "
              f"A${row['ev_oz']:>6.0f}/oz "
              f"A${row['adj_peer_ev_oz']:>6.0f}/oz "
              f"{row['discount_pct']:>+8.1f}%  "
              f"{row['signal']}")

    print("=" * 78)
    print(f"  Prices fetched live from Yahoo Finance")
    print(f"  Peer benchmarks: "
          f"Producer A${peer_ev_per_oz_producer}/oz  "
          f"Developer A${peer_ev_per_oz_developer}/oz  "
          f"Explorer A${peer_ev_per_oz_explorer}/oz")
    print("=" * 78)

print_table(results_df)