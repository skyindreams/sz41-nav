import httpx
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse

TITLE_MAX_LENGTH = 100


async def fetch_title(url: str) -> str:
    """Fetch website title from URL with fallback chain."""
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            content_type = resp.headers.get("content-type", "")
            if "html" not in content_type.lower():
                return _fallback_title(url)
            
            soup = BeautifulSoup(resp.text, "lxml")
            
            # Priority 1: <title> tag
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
                if title:
                    return title[:TITLE_MAX_LENGTH]
            
            # Priority 2: og:title
            og = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
            if og and og.get("content"):
                return og["content"].strip()[:TITLE_MAX_LENGTH]
            
            # Priority 3: twitter:title
            tw = soup.find("meta", attrs={"name": "twitter:title"})
            if tw and tw.get("content"):
                return tw["content"].strip()[:TITLE_MAX_LENGTH]
            
            # Priority 4: <h1> tag
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                return h1.get_text(strip=True)[:TITLE_MAX_LENGTH]
            
            return _fallback_title(url)
            
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
        return _fallback_title(url)


def _fallback_title(url: str) -> str:
    """Fallback: extract domain name as title."""
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    # Remove www. prefix
    domain = re.sub(r'^www\.', '', domain)
    return domain if domain else url[:TITLE_MAX_LENGTH]
