import requests
from bs4 import BeautifulSoup

def get_real_pdf_url(asx_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(asx_url, headers=headers, timeout=30)
    soup = BeautifulSoup(response.text, "html.parser")
    
    pdf_input = soup.find("input", {"name": "pdfURL"})
    if pdf_input:
        return pdf_input["value"]
    return None

url = "https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03087291"
real_url = get_real_pdf_url(url)
print(f"Real PDF URL: {real_url}")