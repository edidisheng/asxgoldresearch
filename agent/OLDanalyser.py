import requests
import anthropic
import os
import pdfplumber
import io
import time
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from asx_fetcher import get_latest_quarterly

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def get_real_pdf_url(asx_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(asx_url, headers=headers, timeout=30)
    soup = BeautifulSoup(response.text, "html.parser")
    pdf_input = soup.find("input", {"name": "pdfURL"})
    if pdf_input:
        return pdf_input["value"]
    return None

def download_pdf(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code == 200 and len(response.content) > 10000:
        return response.content
    return None

def extract_text_from_pdf(pdf_bytes, max_pages=10):
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
        return None
    
    pdf_url = get_real_pdf_url(asx_url)
    if not pdf_url:
        return None
    
    pdf_bytes = download_pdf(pdf_url)
    if not pdf_bytes:
        return None
    
    text = extract_text_from_pdf(pdf_bytes)
    if not text.strip():
        return None
    
    message = client.messages.create(
        
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""You are an equity analyst reviewing a gold mining quarterly report for {company_name} ({ticker}).

Analyse the following quarterly report text and return a concise investment-focused summary under these exact headings:

**GUIDANCE:** Any changes to production or cost guidance. Upgraded, downgraded, or reaffirmed?

**OPERATIONS:** Key operational developments, mine performance, any issues or improvements.

**COSTS:** AISC trend, cost pressures, any one-off items affecting costs.

**BALANCE SHEET:** Cash position, debt, any capital raises or buybacks.

**CATALYSTS:** What to watch next quarter. Upcoming milestones or decisions.

**RED FLAGS:** Anything concerning for the investment thesis. Be direct.

**TONE:** One word — Bullish, Neutral, or Cautious. Then one sentence explaining why.

Keep each section to 2-3 sentences maximum. Be direct and analytical, not promotional.

Report text:
{text[:15000]}"""
        }]
    )
    
    return message.content[0].text


def compare_all(summaries):
    combined = "\n\n".join([f"{ticker}:\n{summary}" for ticker, summary in summaries.items()])
    
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        messages=[{
            "role": "user",
            "content": f"""You are a gold equity analyst. Based on these quarterly report summaries for ASX gold producers, produce a comparative investment ranking assuming a macro environment that is bullish for gold (strong real asset demand, central bank buying, USD weakness).

Rank all companies from most to least attractive for a new long position entry right now. For each company provide:

**Rank #X — TICKER (Company Name)**
- **Why buy:** 1-2 sentences on the bull case
- **Key risk:** Single biggest risk to the thesis
- **Profitability:** AISC margin quality and cost trajectory
- **Verdict:** One line — Strong Buy, Buy, Hold, or Avoid

End with a 3-sentence portfolio construction note on how you would size these positions relative to each other.

Summaries:
{combined}"""
        }]
    )
    
    return message.content[0].text

if __name__ == "__main__":
    companies = {
        "WGX": "Westgold Resources",
        "NST": "Northern Star Resources",
        "CMM": "Capricorn Metals",
        "RRL": "Regis Resources",
        "RMS": "Ramelius Resources",
        "BGL": "Bellevue Gold",
        "GMD": "Genesis Minerals",
        "HRN": "Horizon Minerals",
    }
    
    date = datetime.now().strftime("%Y-%m-%d")
    output_file = f"quarterly_analysis_{date}.md"
    summaries = {}

    with open(output_file, "w") as f:
        f.write(f"# ASX Gold Producer Quarterly Analysis\n")
        f.write(f"Generated: {date}\n\n")
        
        for ticker, name in companies.items():
            result = analyse_quarterly(ticker, name)
            if result:
                summaries[ticker] = result
                f.write(f"\n{'='*50}\n")
                f.write(f"## {name} ({ticker})\n")
                f.write(f"{'='*50}\n\n")
                f.write(result)
                f.write("\n\n")
                print(f"Done: {ticker}")
            else:
                print(f"Skipped: {ticker}")
            
            time.sleep(15)

        print("\nGenerating comparative analysis...")
        comparison = compare_all(summaries)
        f.write(f"\n{'='*50}\n")
        f.write(f"## COMPARATIVE RANKING & PORTFOLIO CONSTRUCTION\n")
        f.write(f"{'='*50}\n\n")
        f.write(comparison)
        print("Done.")

    print(f"\nSaved to {output_file}")