#!/usr/bin/env python3
import os, sys, json, subprocess, argparse, logging, time
from datetime import datetime
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("steamdepoter.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class SteamDBScraper:
    def __init__(self, headless=False):
        self.headless = headless
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
        self.sync_playwright = sync_playwright
        self.BeautifulSoup = BeautifulSoup

    def fetch_manifests(self, depot_id):
        url = f"https://steamdb.info/depot/{depot_id}/manifests/"
        
        with self.sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            
            logger.info(f"Navigating to {url}...")
            page.goto(url, wait_until="domcontentloaded")
            
            logger.info("Waiting for manifests table to load...")
            
            try:
                page.wait_for_selector("tr[data-branch]", timeout=60000)
                logger.info("Table loaded successfully!")
            except Exception as e:
                logger.error(f"Failed to find manifests table: {e}")
                browser.close()
                return []
                
            html_content = page.content()
            browser.close()
            
            return self._parse_html(html_content)
            
    def _parse_html(self, html):
        soup = self.BeautifulSoup(html, 'html.parser')
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


class DepotDownloader:
    def __init__(self, path="DepotDownloader", base_dest_dir="manifest_downloads"):
        self.path = path
        self.base_dest_dir = base_dest_dir

    def download(self, app_id, depot_id, manifest_id, username, password=None):
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
    parser.add_argument("--config", default="config.yaml", help="Config file")
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
    if os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    
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
    
    scraper = SteamDBScraper(headless=headless)
    downloader = DepotDownloader()
    
    if args.mode in ("scrape", "download", "all"):
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
                
                if args.mode in ("download", "all"):
                    for m in branch_manifests:
                        downloader.download(app_id, depot_id, m['manifest_id'], username, password)
    
    if args.mode in ("analyze", "all"):
        analyze()


if __name__ == "__main__":
    main()