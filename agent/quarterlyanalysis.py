import requests
import anthropic
import os
import pdfplumber
import io
import time
import json
import re
import csv
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from asx_fetcher import get_latest_quarterly

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ---- SCREENER INTEGRATION ----
# Importing the screener runs it (it's script-style), giving fresh EV/oz
# valuations at launch. If it fails (no internet, file moved), the agent
# still runs — just without valuation context.
try:
    from ASXgoldscreener import results_df as valuation_df
    print("Screener valuations loaded.")
except Exception as e:
    valuation_df = None
    print(f"WARNING: screener unavailable ({e}) — running without valuation context")


def valuation_context(ticker):
    """One-line valuation summary from the EV/oz screener for the prompt."""
    if valuation_df is None:
        return "No screener valuation available."
    row = valuation_df[valuation_df["ticker"] == ticker]
    if row.empty:
        return "This company is not in the screener universe."
    r = row.iloc[0]
    rel = "discount to" if r["discount_pct"] > 0 else "premium over"
    return (f"EV/oz A${r['ev_oz']:.0f} vs grade/jurisdiction-adjusted peer "
            f"benchmark A${r['adj_peer_ev_oz']:.0f} — a {abs(r['discount_pct']):.0f}% "
            f"{rel} peers (screener signal: {r['signal']})")


def valuation_table():
    """Full screener table for the comparative ranking prompt."""
    if valuation_df is None:
        return "No screener valuations available."
    cols = ["ticker", "stage", "ev_oz", "adj_peer_ev_oz", "discount_pct", "signal"]
    return valuation_df[cols].round(0).to_string(index=False)


def ask_claude(prompt, max_tokens):
    """Single API call with truncation detection + one automatic retry
    with a doubled token budget if the response was cut off."""
    for attempt in range(2):
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if message.stop_reason != "max_tokens":
            return message.content[0].text
        print(f"  WARNING: response truncated at {max_tokens} tokens, retrying with {max_tokens*2}...")
        max_tokens *= 2
    # second attempt still truncated — return what we got, clearly flagged
    return message.content[0].text + "\n\n[TRUNCATED — raise max_tokens]"


# one session for the whole run: keeps ASX cookies from the announcement
# page so the follow-up PDF request is recognised (and is faster)
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_with_retry(url, max_retries=4, timeout=30):
    """GET with exponential backoff. Handles rate limits (429/403/503) by
    waiting — honouring the server's Retry-After header if provided —
    and network errors by retrying with growing delays."""
    for attempt in range(max_retries):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 403, 503):
                wait = int(r.headers.get("Retry-After", 0)) or 30 * (2 ** attempt)
                print(f"  rate limited ({r.status_code}), waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP {r.status_code} for {url} — not retrying")
                return None
        except requests.exceptions.RequestException as e:
            wait = 15 * (attempt + 1)
            print(f"  network error: {e} — retrying in {wait}s...")
            time.sleep(wait)
    print(f"  giving up after {max_retries} attempts: {url}")
    return None


def get_real_pdf_url(asx_url):
    response = fetch_with_retry(asx_url)
    if not response:
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    pdf_input = soup.find("input", {"name": "pdfURL"})
    if pdf_input:
        return pdf_input["value"]
    return None


def is_valid_pdf(data):
    """Every real PDF starts with the magic bytes %PDF. An HTML error or
    terms page (what ASX serves when it blocks you) fails this check."""
    return data is not None and data[:1024].lstrip().startswith(b"%PDF")


def download_pdf(url, ticker):
    """Download with a local cache — reruns make zero ASX requests for
    companies already fetched this month. Only verified PDFs are cached."""
    os.makedirs("pdf_cache", exist_ok=True)
    cache_path = f"pdf_cache/{ticker}_{datetime.now().strftime('%Y%m')}.pdf"

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            data = f.read()
        if is_valid_pdf(data):
            print(f"  using cached PDF for {ticker}")
            return data
        print(f"  cached file for {ticker} is not a real PDF — deleting and refetching")
        os.remove(cache_path)

    response = fetch_with_retry(url)
    if response is None:
        return None
    if not is_valid_pdf(response.content):
        print(f"  {ticker}: server returned HTML instead of a PDF "
              "(likely rate limit or terms page) — not caching")
        return None
    if len(response.content) > 10000:
        with open(cache_path, "wb") as f:
            f.write(response.content)
        return response.content
    return None


def extract_text_from_pdf(pdf_bytes, max_pages=15):
    text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages[:max_pages]):
            page_text = page.extract_text()
            if page_text:
                text += f"\n--- Page {i+1} ---\n{page_text}"
    return text


def analyse_quarterly(ticker, company_name):
    print(f"\nAnalysing {ticker}...")

    asx_url = get_latest_quarterly(ticker)
    if not asx_url:
        print(f"  no quarterly found for {ticker}")
        return None

    time.sleep(5)  # space out consecutive ASX hits — don't look bursty
    pdf_url = get_real_pdf_url(asx_url)
    if not pdf_url:
        print(f"  could not resolve PDF URL for {ticker}")
        return None

    time.sleep(5)
    pdf_bytes = download_pdf(pdf_url, ticker)
    if not pdf_bytes:
        print(f"  PDF download failed for {ticker}")
        return None

    text = extract_text_from_pdf(pdf_bytes)
    if not text.strip():
        print(f"  no extractable text for {ticker}")
        return None

    prompt = f"""You are an equity analyst reviewing a gold mining quarterly report for {company_name} ({ticker}).

My quantitative EV/oz screener currently values this company as follows:
{valuation_context(ticker)}

Analyse the following quarterly report text and return a concise investment-focused summary under these exact headings:

**GUIDANCE:** Any changes to production or cost guidance. Upgraded, downgraded, or reaffirmed?

**OPERATIONS:** Key operational developments, mine performance, any issues or improvements.

**COSTS:** AISC trend, cost pressures, any one-off items affecting costs.

**BALANCE SHEET:** Cash position, debt, any capital raises or buybacks.

**VALUATION:** Reconcile the screener's EV/oz discount or premium with what this report shows. Is the cheapness justified by fundamental problems (a value trap), or does the market appear to be lagging genuine improvement (an opportunity)? If the company trades at a premium, does the quality in this report earn it?

**CATALYSTS:** What to watch next quarter. Upcoming milestones or decisions.

**RED FLAGS:** Anything concerning for the investment thesis. Be direct.

**TONE:** One word — Bullish, Neutral, or Cautious. Then one sentence explaining why.

**DATA:** This section is mandatory. Output a single line of valid JSON in exactly this format — plain raw JSON (no code fences), plain numbers (no commas, no units, no currency symbols), and null for anything the report does not state:
{{"quarter": "Q4 FY26", "aisc_aud_oz": 2841, "production_oz": 98854, "cash_aud_m": 939, "debt_aud_m": 0}}
Definitions: quarter = the reporting quarter as labelled in the report; aisc_aud_oz = the ACTUAL group AISC achieved this quarter in AUD per ounce — never a guidance figure, study projection, or life-of-mine estimate, and null if the company is pre-production or reports AISC only in USD; production_oz = gold produced this quarter in ounces; cash_aud_m = cash, bullion and liquid investments in millions of AUD; debt_aud_m = total debt in millions of AUD.

Keep each section to 2-3 sentences maximum. Be direct and analytical, not promotional.

Report text:
{text[:30000]}"""

    return ask_claude(prompt, max_tokens=2000)


DATA_FIELDS = ["quarter", "aisc_aud_oz", "production_oz", "cash_aud_m", "debt_aud_m"]
DATA_CSV = "aisc_history.csv"


def extract_data_block(summary):
    """Pull the DATA JSON out of a summary. Returns (clean_summary, dict|None).
    Robust to code fences, missing **DATA:** label, and thousands commas.
    The block is removed from the markdown — it lives in the CSV instead."""
    # find any JSON object that contains our key, fenced or not
    m = re.search(r"\{[^{}]*\"aisc_aud_oz\"[^{}]*\}", summary, re.DOTALL)
    if not m:
        print("  WARNING: no DATA block found in summary — nothing extracted")
        return summary, None

    raw = re.sub(r"(?<=\d),(?=\d{3})", "", m.group(0))  # strip 2,841 -> 2841
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  WARNING: DATA block was not valid JSON ({e}) — skipping extraction")
        data = None

    # remove the whole DATA section (label, fences, json) from the display copy
    clean = re.sub(r"(\*\*DATA:\*\*\s*)?(```(json)?\s*)?" + re.escape(m.group(0)) + r"(\s*```)?",
                   "", summary).rstrip()
    return clean, data


def save_data_row(ticker, data):
    """Append one row per (ticker, quarter) to the AISC history CSV.
    Skips duplicates so reruns don't double-count."""
    fields = ["run_date", "ticker"] + DATA_FIELDS
    existing = set()
    if os.path.exists(DATA_CSV):
        with open(DATA_CSV, newline="") as cf:
            for r in csv.DictReader(cf):
                existing.add((r["ticker"], r["quarter"]))
    if (ticker, str(data.get("quarter"))) in existing:
        print(f"  {ticker} {data.get('quarter')} already in {DATA_CSV}")
        return
    write_header = not os.path.exists(DATA_CSV)
    with open(DATA_CSV, "a", newline="") as cf:
        w = csv.DictWriter(cf, fieldnames=fields)
        if write_header:
            w.writeheader()
        row = {"run_date": datetime.now().strftime("%Y-%m-%d"), "ticker": ticker}
        row.update({k: data.get(k) for k in DATA_FIELDS})
        w.writerow(row)
    print(f"  saved {ticker} {data.get('quarter')}: AISC A${data.get('aisc_aud_oz')}/oz")


def macro_context():
    """Current gold regime readings from the site's daily data build, so the
    ranking reflects the ACTUAL macro environment instead of a hard-coded
    bullish assumption. Falls back to neutral wording if unavailable."""
    path = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "site_data.json")
    try:
        with open(path) as f:
            db = json.load(f)["dashboard"]
        lines = [f"- Trend regime: {db['regime']}. AUD gold ${db['price']:,} vs 200-day "
                 f"average ${db['ma200']:,}; 12m momentum {db['mom12m_pct']:+}%; "
                 f"stretch {db['stretch_pct']:+}% vs MA ({db['stretch_pctile']}th pctile since 2010)."]
        for m in db["macro"]:
            lines.append(f"- {m['name']}: {m['detail']} — {m['reading']}.")
        lines.append(f"- COT positioning: managed-money net {db['cot_net_pct_oi']}% of OI, "
                     f"{db['cot_pctile_3y']}th pctile of 3y — {db['cot_note']}.")
        return "\n".join(lines)
    except Exception as e:
        print(f"  NOTE: no macro readings available ({e}) — using neutral framing")
        return "- No current readings available. Take no view on the gold price direction."


def compare_all(summaries):
    combined = "\n\n".join(f"{ticker}:\n{summary}" for ticker, summary in summaries.items())

    prompt = f"""You are a gold equity analyst. Based on these quarterly report summaries for ASX gold producers, produce a comparative investment ranking.

Ground your ranking in the CURRENT macro environment for gold, as measured by my regime dashboard:
{macro_context()}

Let these readings inform the ranking: in a weaker or neutral regime, favour balance sheet strength, low AISC, and self-funded growth over gold-price torque; in a strong bull regime, operational leverage and unhedged production matter more. State briefly at the top how the current regime shaped your ranking.

Current EV/oz screener valuations (grade and jurisdiction adjusted; positive discount_pct = cheap vs peers):
{valuation_table()}

Rank all companies from most to least attractive for a new long position entry right now. The ranking must balance fundamental quality against price paid: a well-run company at a large premium can rank below a decent company at a deep discount. Explicitly call out any value traps (cheap on EV/oz but deservedly so) and any quality names worth paying up for. For each company provide:

**Rank #X — TICKER (Company Name)**
- **Why buy:** 1-2 sentences on the bull case
- **Valuation:** EV/oz vs peers, and whether this quarter justifies the discount/premium
- **Key risk:** Single biggest risk to the thesis
- **Profitability:** AISC margin quality and cost trajectory
- **Verdict:** One line — Strong Buy, Buy, Hold, or Avoid

End with a 3-sentence portfolio construction note on how you would size these positions relative to each other.

Summaries:
{combined}"""

    return ask_claude(prompt, max_tokens=8000)


if __name__ == "__main__":
    companies = {
        "WGX": "Westgold Resources",
        "NST": "Northern Star Resources",
        "CMM": "Capricorn Metals",
        "RRL": "Regis Resources",
        "RMS": "Ramelius Resources",
        "BGL": "Bellevue Gold",
        "GMD": "Genesis Minerals",
    }

    date = datetime.now().strftime("%Y-%m-%d")
    output_file = f"quarterly_analysis_{date}.md"
    summaries = {}
    failed = []

    with open(output_file, "w") as f:
        f.write("# ASX Gold Producer Quarterly Analysis\n")
        f.write(f"Generated: {date}\n\n")
        f.flush()

        for ticker, name in companies.items():
            # one bad company must never kill the whole run
            try:
                result = analyse_quarterly(ticker, name)
            except Exception as e:
                print(f"  ERROR on {ticker}: {e}")
                result = None

            if result:
                clean_summary, data = extract_data_block(result)
                if data:
                    save_data_row(ticker, data)
                summaries[ticker] = clean_summary
                f.write(f"\n{'='*50}\n")
                f.write(f"## {name} ({ticker})\n")
                f.write(f"{'='*50}\n\n")
                f.write(clean_summary)
                f.write("\n\n")
                f.flush()  # section is safely on disk before moving on
                print(f"Done: {ticker}")
            else:
                failed.append(ticker)
                print(f"Skipped: {ticker}")

            time.sleep(15)

        if summaries:
            print("\nGenerating comparative analysis...")
            try:
                comparison = compare_all(summaries)
                f.write(f"\n{'='*50}\n")
                f.write("## COMPARATIVE RANKING & PORTFOLIO CONSTRUCTION\n")
                f.write(f"{'='*50}\n\n")
                f.write(comparison)
            except Exception as e:
                print(f"  ERROR in comparison: {e}")
                f.write("\n\n[Comparative analysis failed — rerun compare_all]\n")

        if failed:
            f.write(f"\n\n---\nNot analysed this run: {', '.join(failed)}\n")
        f.flush()

    print(f"\nSaved to {output_file}")
    if failed:
        print(f"Failed/skipped: {', '.join(failed)}")