import requests
import time
from bs4 import BeautifulSoup

def get_latest_quarterly(ticker):
    url = f"https://www.asx.com.au/asx/v2/statistics/announcements.do?by=asxCode&timeframe=D&period=M6&asxCode={ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    
    keywords = ["quarterly results", "quarterly report", "appendix 5b", "quarterly activities"]
    exclusions = ["webcast", "teleconference", "presentation", "details", "webinar"]
    
    for a in soup.find_all("a", href=True):
        if "displayAnnouncement" not in a["href"]:
            continue
        title = a.get_text(strip=True).lower()
        if any(k in title for k in keywords) and not any(e in title for e in exclusions):
            pdf_url = "https://www.asx.com.au" + a["href"]
            print(f"Found quarterly: {a.get_text(strip=True)}")
            print(f"URL: {pdf_url}")
            return pdf_url
    
    print(f"No quarterly found for {ticker}")
    return None
    
def get_resources_report(ticker):
    url = f"https://www.asx.com.au/asx/v2/statistics/announcements.do?by=asxCode&timeframe=D&period=M18&asxCode={ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    
    keywords = [
        "mineral resource", "ore reserve", "resource estimate", "mror",
        "half year financial report", "annual report", "annual financial report"
    ]
    
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True).lower()
        if any(k in title for k in keywords):
            pdf_url = "https://www.asx.com.au" + a["href"]
            print(f"Found resources report: {a.get_text(strip=True)}")
            print(f"URL: {pdf_url}")
            return pdf_url
    
    print(f"No resources report found for {ticker}")
    return None

def list_all_announcements(ticker):
    url = f"https://www.asx.com.au/asx/v2/statistics/announcements.do?by=asxCode&timeframe=D&period=M12&asxCode={ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.5",
        "Referer": "https://www.asx.com.au"
    }
    
    time.sleep(3)
    response = requests.get(url, headers=headers, timeout=10)
    print(f"Status: {response.status_code}, Size: {len(response.text)}")
    soup = BeautifulSoup(response.text, "html.parser")
    
    for a in soup.find_all("a", href=True):
        print(a.get_text(strip=True), "->", a["href"])

if __name__ == "__main__":
    list_all_announcements("WGX")