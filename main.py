#!/usr/bin/env python3
import os, sys, json, subprocess, argparse, logging, time
from datetime import datetime
from collections import defaultdict

# --- Paths Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(BASE_DIR, "steamdb_profile")
MANIFEST_CACHE = os.path.join(BASE_DIR, "manifest_cache.json")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "manifest_downloads")
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
LOG_FILE = os.path.join(BASE_DIR, "steamdepoter.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class SteamDBScraper:
    """
    Scrapes SteamDB manifests using a persistent browser profile.
    """

    # Simple detection: If 'Sign out' text is on the page, we are logged in.
    LOGGED_IN_SELECTOR = "text='Sign out'"
    LOGIN_TIMEOUT_MS = 300_000

    def __init__(self):
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
        self.sync_playwright = sync_playwright
        self.BeautifulSoup = BeautifulSoup
        os.makedirs(PROFILE_DIR, exist_ok=True)
        self._playwright = None
        self._context = None
        self._page = None
        self._logged_in_verified = False
        self._cache = self._load_cache()

    def _load_cache(self):
        if os.path.exists(MANIFEST_CACHE):
            try:
                with open(MANIFEST_CACHE, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load manifest cache: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(MANIFEST_CACHE, "w") as f:
                json.dump(self._cache, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save manifest cache: {e}")

    def __enter__(self):
        return self

    def _ensure_browser(self):
        if self._page:
            return

        import random
        self._playwright = self.sync_playwright().start()
        
        # Randomize viewport slightly to avoid static fingerprints
        random_width = 1280 + random.randint(0, 100)
        random_height = 800 + random.randint(0, 100)
        
        logger.info("Starting local scraper instance...")
        try:
            # Try connection first
            logger.info("Attempting to connect to a real Chrome instance on 127.0.0.1:9222...")
            self._browser = self._playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            self._context = self._browser.contexts[0]
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            logger.info("SUCCESS: Connected to your real Chrome browser!")
            self._is_connected_to_real = True
        except Exception:
            logger.info("Starting isolated browser context...")
            self._context = self._playwright.chromium.launch_persistent_context(
                PROFILE_DIR,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized"
                ],
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": random_width, "height": random_height},
                locale="en-US",
                timezone_id="America/New_York"
            )
            self._page = self._context.new_page()
            self._is_connected_to_real = False
        
        self._page.set_default_timeout(60000)

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if hasattr(self, "_is_connected_to_real") and self._is_connected_to_real:
                if self._playwright:
                    self._playwright.stop()
            else:
                if self._context:
                    self._context.close()
                if self._playwright:
                    self._playwright.stop()
        except Exception:
            pass

    def _is_logged_in(self) -> bool:
        if self._page.is_closed():
            return False
        try:
            return self._page.locator(self.LOGGED_IN_SELECTOR).count() > 0
        except Exception:
            return False

    def _ensure_logged_in(self) -> bool:
        if self._logged_in_verified:
            return True

        if self._page.is_closed():
            return False

        # Check current page first
        if self._is_logged_in():
            self._logged_in_verified = True
            return True

        # Go to homepage to check
        logger.info("Checking SteamDB login status...")
        try:
            self._page.goto("https://steamdb.info/", wait_until="domcontentloaded")
            if self._is_logged_in():
                logger.info("SteamDB: already logged in via saved profile.")
                self._logged_in_verified = True
                return True
        except Exception:
            pass

        logger.warning(
            "SteamDB: NOT logged in. Please log in manually in the browser window now."
        )
        
        # Wait for any of the logged-in selectors to appear
        start_time = time.time()
        while time.time() - start_time < (self.LOGIN_TIMEOUT_MS / 1000):
            if self._page.is_closed():
                logger.error("Browser was closed during login.")
                return False
            if self._is_logged_in():
                logger.info("SteamDB: login detected!")
                self._logged_in_verified = True
                return True
            time.sleep(1)

        logger.error("SteamDB: login timeout.")
        return False

    def fetch_manifests(self, depot_id):
        # Check cache first
        depot_id_str = str(depot_id)
        if depot_id_str in self._cache:
            logger.info(f"Using cached manifests for Depot {depot_id}")
            return self._cache[depot_id_str]

        # Cache miss - we need the browser now
        self._ensure_browser()

        if self._page.is_closed():
            return []

        url = f"https://steamdb.info/depot/{depot_id}/manifests/"

        self._ensure_logged_in()
        
        if self._page.is_closed():
            return []

        logger.info(f"Navigating to {url}...")
        # Random delay to seem more human
        time.sleep(2)
        
        self._page.goto(url, wait_until="domcontentloaded")
        
        # Give Cloudflare background checks a chance to settle (from BQL guide)
        logger.info("Waiting 5s for background challenges to settle...")
        time.sleep(5)

        logger.info("Waiting for manifests table to load...")
        try:
            self._page.wait_for_selector("tr[data-branch]", timeout=60_000)
            logger.info("Table loaded successfully!")
        except Exception as e:
            logger.error(f"Failed to find manifests table: {e}")
            return []

        # Small delay before grabbing content to allow any JS to settle
        time.sleep(1)
        html_content = self._page.content()

        manifests = self._parse_html(html_content)
        
        if manifests:
            self._cache[depot_id_str] = manifests
            self._save_cache()
            
        return manifests

    def _parse_html(self, html):
        soup = self.BeautifulSoup(html, "html.parser")
        manifests = []

        for row in soup.find_all("tr"):
            branch = row.get("data-branch")
            if not branch:
                continue

            time_td = row.find("td", class_="timeago")
            if not time_td:
                continue
            date_str = time_td.get("data-time")

            manifest_td = row.find("td", class_="tabular-nums")
            if not manifest_td:
                continue

            a_tag = manifest_td.find("a")
            if not a_tag:
                continue

            manifest_id = a_tag.text.strip()

            manifests.append({
                "branch": branch,
                "date": date_str,
                "manifest_id": manifest_id,
            })

        return manifests


class DepotDownloader:
    def __init__(self, path=DUMPER_EXE):
        self.path = path
        self.base_dest_dir = DOWNLOAD_DIR
        self.cache_file = os.path.join(self.base_dest_dir, "download_cache.json")
        self.cache = self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_cache(self):
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, indent=2)

    def _cache_key(self, app_id, depot_id, manifest_id):
        return f"{app_id}-{depot_id}-{manifest_id}"

    def download(self, app_id, depot_id, manifest_id, username, password=None):
        key = self._cache_key(app_id, depot_id, manifest_id)
        if key in self.cache:
            logger.info(f"Skipping (cached): {manifest_id}")
            return True

        logger.info(f"Downloading manifest: {manifest_id}")

        dest_dir = os.path.join(self.base_dest_dir, str(app_id), str(depot_id), str(manifest_id))

        cmd = [
            self.path,
            "-app", str(app_id),
            "-depot", str(depot_id),
            "-manifest", str(manifest_id),
            "-username", username,
            "-dir", dest_dir,
            "-remember-password"
        ]

        if password:
            cmd.extend(["-password", password])

        for attempt in range(1, 6):
            try:
                subprocess.run(cmd, check=True)
                logger.info(f"Downloaded: {manifest_id}")
                self.cache[key] = {"downloaded_at": datetime.now().isoformat()}
                self._save_cache()
                return True
            except subprocess.CalledProcessError as e:
                logger.warning(f"Attempt {attempt}/5 failed: {e}")
                if attempt == 5:
                    return False
                time.sleep(3)
            except FileNotFoundError:
                logger.error(f"DepotDownloader not found in PATH")
                return False
        return False


def detect_format(path):
    try:
        with open(path, 'rb') as f:
            h = f.read(4)
        for m, fmt in [(b'MZ', 'PE'), (b'\x7fELF', 'ELF'), (b'\xfe\xed\xfa\xce', 'MachO32'), (b'\xce\xfa\xed\xfe', 'MachO32RE'), (b'\xfe\xed\xfa\xcf', 'MachO64'), (b'\xcf\xfa\xed\xfe', 'MachO64RE'), (b'\xca\xfe\xba\xbe', 'FatBinary'), (b'\xbe\xba\xfe\xca', 'FatBinaryRE')]:
            if h.startswith(m): return fmt
    except: pass
    return None


def run_symwalker(directory):
    try:
        result = subprocess.run(
            ['symwalker', directory, '--show-stripped', '--check-remote', '--security', '--json'],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        logger.warning(f"symwalker error: {e}")
    return []

def run_pdbwalker(directory):
    try:
        result = subprocess.run(
            ['pdbwalker', directory, '--check-remote', '--json'],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode == 0:
            lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
            return [json.loads(l) for l in lines]
    except Exception as e:
        logger.warning(f"pdbwalker error: {e}")
    return []


def analyze(scan_dir="manifest_downloads", output="analysis_results.json"):
    if not os.path.isdir(scan_dir):
        logger.error(f"Directory not found: {scan_dir}")
        return

    logger.info(f"Scanning: {scan_dir}")

    all_results = []
    logger.info("Running symwalker (ELF/Mach-O)...")
    all_results.extend(run_symwalker(scan_dir))
    
    logger.info("Running pdbwalker (PE)...")
    all_results.extend(run_pdbwalker(scan_dir))
    
    dirs = defaultdict(list)
    total = 0
    for entry in all_results:
        fp = entry.get('file_path', '')
        parent = os.path.dirname(fp)
        dirs[os.path.relpath(parent, scan_dir)].append(entry)
        total += 1
    
    logger.info(f"Found {total} binaries in {len(dirs)} dirs")
    
    result = {}
    for dp, files in dirs.items():
        files.sort(key=lambda x: (
            -int(has_debug(x)),
            x.get('file_path', '')
        ))
        result[dp] = {'total': len(files), 'files': files}
    
    out = {'scan_time': datetime.now().isoformat(), 'total_files': total, 'total_directories': len(result), 'directories': result}
    open(output, 'w', encoding='utf-8').write(json.dumps(out, indent=2))
    logger.info(f"Results: {output}")
    
    generate_html(output)
    
    dc = sum(1 for d in result.values() for f in d['files'] if f.get('has_debug_info') or f.get('local_pdb', {}).get('available') or f.get('remote_pdb', {}).get('available'))
    logger.info(f"With debug info: {dc}")

def has_debug(f):
    return (f.get('has_debug_info') == True or 
            f.get('local_pdb', {}).get('available') == True or 
            f.get('remote_pdb', {}).get('available') == True)

def generate_html(json_path):
    html_path = json_path.replace('.json', '.html')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_files = []
    for folder, info in data['directories'].items():
        for f in info['files']:
            f['_folder'] = folder
            all_files.append(f)
    
    all_files.sort(key=lambda x: (-int(has_debug(x)), x.get('file_path', '')))
    
    all_keys = set()
    for f in all_files:
        all_keys.update(f.keys())
    excluded = {'_folder', 'file_path', 'debug_sections', 'debuginfod_url', 'debug_file_path', 'file_modified'}
    left_cols = ['has_debug_info', 'is_stripped', 'dsym_bundle', 'local_pdb', 'remote_pdb']
    right_cols = ['build_id', 'uuid']
    middle_cols = sorted(all_keys - excluded - set(left_cols) - set(right_cols))
    all_keys = left_cols + middle_cols + right_cols
    
    def flag(v, k):
        if v is None: return '-'
        if isinstance(v, bool): return '&#10003;' if v else '-'
        if isinstance(v, list): return ', '.join(str(x) for x in v[:5]) + ('...' if len(v) > 5 else '')
        if isinstance(v, dict):
            if k in ('local_pdb', 'remote_pdb'):
                return '&#10003;' if v.get('available') else '-'
            return str(v)
        return str(v)
    
    headers = ['File', 'Folder'] + all_keys
    rows = ''
    for f in all_files:
        cells = [f'<td class="file-cell">{os.path.basename(f.get("file_path", ""))}</td>', f'<td class="folder-cell">{f.get("_folder", "")}</td>']
        for k in all_keys:
            v = f.get(k)
            cells.append(f'<td>{flag(v, k)}</td>')
        rows += f'<tr class="{"has-debug" if has_debug(f) else "no-debug"}">{"".join(cells)}</tr>'
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Steam Depot Analysis</title>
    <style>
        body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; margin: 20px; background: #1a1a1a; color: #eee; }}
        h1 {{ color: #fff; margin-bottom: 5px; }}
        .stats {{ color: #888; margin-bottom: 15px; }}
        .search-box {{ margin-bottom: 15px; }}
        .search-box input {{ padding: 8px 12px; width: 300px; background: #333; border: 1px solid #444; color: #fff; border-radius: 4px; font-size: 13px; }}
        .search-box input:focus {{ outline: none; border-color: #4caf50; }}
        table {{ border-collapse: collapse; width: 100%; background: #252525; }}
        th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #333; font-size: 12px; white-space: nowrap; }}
        th {{ background: #333; cursor: pointer; user-select: none; position: sticky; top: 0; }}
        th:hover {{ background: #444; }}
        tr:hover {{ background: #2a2a2a; }}
        .file-cell {{ color: #4caf50; }}
        .no-debug .file-cell {{ color: #ff9800; }}
        tr.hidden {{ display: none; }}
        .folder-cell {{ color: #666; font-size: 11px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; }}
    </style>
</head>
<body>
    <h1>Steam Depot Analysis</h1>
    <div class="stats">{data['total_files']} binaries in {data['total_directories']} folders</div>
    <div class="search-box">
        <input type="text" id="searchInput" placeholder="Search..." oninput="filterTable()">
    </div>
    <table id="table">
        <thead>
            <tr>
                {"".join(f'<th onclick="sortTable(this.cellIndex)">{h}</th>' for h in headers)}
            </tr>
        </thead>
        <tbody id="tbody">{rows}</tbody>
    </table>
    <script>
        let sortAsc = true;
        let sortCol = 0;

        function filterTable() {{
            const search = document.getElementById('searchInput').value.toLowerCase();
            document.querySelectorAll('#tbody tr').forEach(row => {{
                row.style.display = row.textContent.toLowerCase().includes(search) ? '' : 'none';
            }});
        }}

        function sortTable(col) {{
            if (sortCol === col) sortAsc = !sortAsc;
            else {{ sortAsc = true; sortCol = col; }}
            const tbody = document.getElementById('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            rows.sort((a, b) => {{
                const A = a.cells[col].textContent.trim();
                const B = b.cells[col].textContent.trim();
                const aNum = parseFloat(A), bNum = parseFloat(B);
                if (!isNaN(aNum) && !isNaN(bNum) && aNum === bNum) return sortAsc ? A.localeCompare(B) : B.localeCompare(A);
                if (!isNaN(aNum) && !isNaN(bNum)) return sortAsc ? aNum - bNum : bNum - aNum;
                return sortAsc ? A.localeCompare(B, undefined, {{numeric: true}}) : B.localeCompare(A, undefined, {{numeric: true}});
            }});
            rows.forEach(r => tbody.appendChild(r));
        }}
    </script>
</body>
</html>'''
    
    open(html_path, 'w', encoding='utf-8').write(html)
    logger.info(f"HTML: {html_path}")


def main():
    parser = argparse.ArgumentParser(description="Steam Depot Tool")
    parser.add_argument("--config", default=CONFIG_FILE, help="Config file")
    parser.add_argument("--app", help="App ID")
    parser.add_argument("--depot", help="Depot ID")
    parser.add_argument("--username", help="Steam username")
    parser.add_argument("--password", help="Steam password")
    parser.add_argument("--branch", default="public", help="Branch name")
    parser.add_argument("--headless", action="store_true", help="Headless browser")
    parser.add_argument("--mode", choices=["scrape", "download", "analyze", "all"], default="all", help="Mode")
    parser.add_argument("--html", action="store_true", help="Generate HTML from existing JSON")
    args = parser.parse_args()
    
    if args.html:
        generate_html("analysis_results.json")
        return
    
    import yaml
    
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    else:
        logger.warning(f"Config file not found: {CONFIG_FILE}")
    
    username = args.username or config.get("username", "")
    password = args.password or config.get("password", "")
    branch = args.branch or config.get("branch", "public")
    headless = args.headless or config.get("headless", False)
    
    downloads = {}
    if args.app and args.depot:
        downloads = {args.app: [args.depot]}
    else:
        downloads = config.get("download", {})
    
    logger.info("=" * 40)
    logger.info("      Steam Depot Tool")
    logger.info("=" * 40)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Apps: {len(downloads)}")
    logger.info("=" * 40)
    
    downloader = DepotDownloader()
    
    all_manifests_to_download = []
    
    if args.mode in ("scrape", "download", "all"):
        with SteamDBScraper() as scraper:
            for app_id, depots in downloads.items():
                for depot_id in depots:
                    logger.info(f">>> App: {app_id} | Depot: {depot_id}")
                    
                    manifests = scraper.fetch_manifests(depot_id)
                    if not manifests:
                        logger.error(f"No manifests for Depot {depot_id}")
                        continue
                    
                    branch_manifests = [m for m in manifests if m['branch'] == branch]
                    if not branch_manifests:
                        logger.error(f"No manifests for branch '{branch}'")
                        continue
                    
                    logger.info(f"Found {len(branch_manifests)} manifests")
                    for m in branch_manifests:
                        all_manifests_to_download.append({
                            'app_id': app_id,
                            'depot_id': depot_id,
                            'manifest_id': m['manifest_id']
                        })

    # Now that the browser is closed, start the downloads
    if args.mode in ("download", "all") and all_manifests_to_download:
        logger.info("=" * 40)
        logger.info(f"Starting batch download of {len(all_manifests_to_download)} manifests...")
        logger.info("=" * 40)
        
        for item in all_manifests_to_download:
            downloader.download(
                item['app_id'], 
                item['depot_id'], 
                item['manifest_id'], 
                username, 
                password
            )
    
    if args.mode in ("analyze", "all"):
        analyze()


if __name__ == "__main__":
    main()