from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import logging

logger = logging.getLogger(__name__)

class SteamDBScraper:
    def __init__(self, headless=False):
        self.headless = headless

    def fetch_manifests(self, depot_id):
        url = f"https://steamdb.info/depot/{depot_id}/manifests/"
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            
            logger.info(f"Navigating to {url}...")
            # Use wait_until="domcontentloaded" to avoid timeout if resources hang
            page.goto(url, wait_until="domcontentloaded")
            
            logger.info("Waiting for manifests table to load... (If Cloudflare challenges you, please solve it manually in the browser window)")
            
            # Wait for either the branch row (success) or a cloudflare indicator
            try:
                # 60 seconds should be enough for a user to click the CF box if needed
                page.wait_for_selector("tr[data-branch]", timeout=60000)
                logger.info("Table loaded successfully!")
            except Exception as e:
                logger.error(f"Failed to find manifests table. It's possible Cloudflare blocked the request or the depot is invalid. Error: {e}")
                browser.close()
                return []
                
            html_content = page.content()
            browser.close()
            
            return self._parse_html(html_content)
            
    def _parse_html(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        manifests = []
        
        for row in soup.find_all('tr'):
            branch = row.get('data-branch')
            if not branch:
                continue
                
            time_td = row.find('td', class_='timeago')
            if not time_td:
                continue
            date_str = time_td.get('data-time')
            
            manifest_td = row.find('td', class_='tabular-nums')
            if not manifest_td:
                continue
                
            a_tag = manifest_td.find('a')
            if not a_tag:
                continue
                
            manifest_id = a_tag.text.strip()
            
            manifests.append({
                'branch': branch,
                'date': date_str,
                'manifest_id': manifest_id
            })
            
        return manifests

if __name__ == "__main__":
    # Quick standalone test
    scraper = SteamDBScraper(headless=False)
    results = scraper.fetch_manifests("325623")
    print(f"Found {len(results)} manifests.")
    for res in results[:5]:
        print(res)
