#!/usr/bin/env python3
import os, sys, json, struct, argparse, subprocess, time, logging
from datetime import datetime
from collections import defaultdict
from bs4 import BeautifulSoup

try:
    import lief
    lief.logging.disable()
except ImportError:
    print("ERROR: LIEF not installed. Run: uv sync")
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright not installed. Run: uv sync")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("steamdepoter.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

MAGIC_BYTES = {
    b'MZ': 'PE', b'\x7fELF': 'ELF',
    b'\xfe\xed\xfa\xce': 'MachO32', b'\xce\xfa\xed\xfe': 'MachO32RE',
    b'\xfe\xed\xfa\xcf': 'MachO64', b'\xcf\xfa\xed\xfe': 'MachO64RE',
    b'\xca\xfe\xba\xbe': 'FatBinary', b'\xbe\xba\xfe\xca': 'FatBinaryRE',
}


class SteamDBScraper:
    def __init__(self, headless=False):
        self.headless = headless

    def fetch_manifests(self, depot_id):
        url = f"https://steamdb.info/depot/{depot_id}/manifests/"
        
        with sync_playwright() as p:
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
        for m, fmt in MAGIC_BYTES.items():
            if h.startswith(m): return fmt
    except: pass
    return None

def parse_rich_header(data):
    try:
        i = data.find(b'Rich')
        if i == -1: return None
        key = struct.unpack('<I', data[i+4:i+8])[0]
        dans = 0x536e6144 ^ key
        di = data.find(struct.pack('<I', dans))
        if di == -1: return None
        recs = []
        for j in range(di+16, i, 8):
            if j+8 > i: break
            v1 = struct.unpack('<I', data[j:j+4])[0] ^ key
            v2 = struct.unpack('<I', data[j+4:j+8])[0] ^ key
            recs.append({'prod_id': v1>>16, 'build': v1&0xFFFF, 'count': v2})
        return {'xor_key': hex(key), 'records': recs[:5]}
    except: return None

def get_arch(bin):
    try:
        if isinstance(bin, lief.PE.Binary): p = "Win"
        elif isinstance(bin, lief.ELF.Binary): p = "Linux"
        elif isinstance(bin, (lief.MachO.Binary, lief.MachO.FatBinary)): p = "Mac"
        else: return "Unknown"
        obj = bin.at(0) if isinstance(bin, lief.MachO.FatBinary) else bin
        h = obj.abstract.header
        a = str(h.architecture).split('.')[-1].lower()
        b = "64" if h.is_64 else "32"
        am = {"x86_64": "x64", "i386": "x86", "x86": "x86", "aarch64": "arm64", "arm64": "arm64", "arm": "arm"}
        return f"{p}/{am.get(a,a)} ({b}bit)"
    except Exception as e: return f"Error: {type(e).__name__}"

def analyze_pe(bin, data):
    r = {'debug': False, 'debug_type': 'stripped', 'debug_detail': None, 'symtab': False, 'exports': False, 'exports_count': 0, 'extra': {}}
    rich = parse_rich_header(data)
    if rich: r['extra']['rich_header'] = rich
    for dbg in bin.debug:
        if dbg.type == lief.PE.Debug.TYPES.CODEVIEW:
            cv = dbg.code_view if hasattr(dbg, 'code_view') else None
            if cv and cv.filename:
                r['debug'] = True
                r['debug_type'] = 'pdb'
                r['debug_detail'] = cv.filename.split('\\')[-1].split('/')[-1]
                return r
    return r

def analyze_elf(bin):
    r = {'debug': False, 'debug_type': 'stripped', 'debug_detail': None, 'symtab': False, 'exports': False, 'exports_count': 0, 'extra': {}}
    try:
        for n in bin.notes:
            if n.name == "GNU" and "BUILD" in str(n.type).upper():
                r['extra']['build_id'] = bytes(n.description).hex()
                break
    except: pass
    if bin.has_section(".debug_info"):
        r['debug'] = True
        r['debug_type'] = 'dwarf'
        r['debug_detail'] = '.debug_info present'
    if bin.has_section(".symtab"): r['symtab'] = True
    try:
        ds = list(bin.dynamic_symbols)
        if ds: r['exports'], r['exports_count'] = True, len(ds)
    except: pass
    return r

def analyze_macho(bin):
    r = {'debug': False, 'debug_type': 'stripped', 'debug_detail': None, 'symtab': False, 'exports': False, 'exports_count': 0, 'extra': {}}
    obj = bin.at(0) if isinstance(bin, lief.MachO.FatBinary) else bin
    if obj.has_uuid: r['extra']['uuid'] = bytes(obj.uuid.uuid).hex()
    if obj.has_section("__debug_info"):
        r['debug'] = True
        r['debug_type'] = 'dwarf'
        r['debug_detail'] = '__debug_info present'
    if obj.has_symbol_command: r['symtab'] = True
    try:
        ex = list(bin.exported_functions) if isinstance(bin, lief.MachO.FatBinary) else list(obj.exported_functions)
        if ex: r['exports'], r['exports_count'] = True, len(ex)
    except: pass
    return r

def analyze_file(path):
    res = {'file': os.path.basename(path), 'path': path, 'arch': 'Unknown', 'debug': False, 'debug_type': 'stripped', 'debug_detail': None, 'symtab': False, 'exports': False, 'exports_count': 0, 'extra': {}}
    try:
        with open(path, 'rb') as f: data = f.read()
        bin = lief.parse(list(data))
        if not bin: res['arch'] = 'Parse failed'; return res
    except Exception as e:
        res['arch'] = f'Error: read/parse - {type(e).__name__}'
        return res
    try:
        res['arch'] = get_arch(bin)
    except Exception as e:
        res['arch'] = f'Error: arch - {type(e).__name__}'
    try:
        if isinstance(bin, lief.PE.Binary): res.update(analyze_pe(bin, data))
        elif isinstance(bin, lief.ELF.Binary): res.update(analyze_elf(bin))
        elif isinstance(bin, (lief.MachO.Binary, lief.MachO.FatBinary)): res.update(analyze_macho(bin))
    except Exception as e:
        res['extra']['analyze_error'] = f'{type(e).__name__}: {e}'
    return res

def ignore_path(path, lst):
    pl = path.lower()
    return any(p.lower() in pl for p in lst)

def analyze(scan_dir="manifest_downloads", output="analysis_results.json", ignore_file="ignore.txt"):
    if not os.path.isdir(scan_dir):
        logger.error(f"Directory not found: {scan_dir}")
        return
    
    ign = []
    if os.path.isfile(ignore_file):
        ign = [l.strip() for l in open(ignore_file, encoding='utf-8') if l.strip() and not l.startswith('#')]
    
    logger.info(f"Scanning: {scan_dir}")
    if ign: logger.info(f"Ignoring: {len(ign)} patterns")
    
    dirs = defaultdict(list)
    total = 0
    for root, ds, fs in os.walk(scan_dir):
        ds[:] = [d for d in ds if not ignore_path(os.path.join(root, d), ign)]
        for f in fs:
            fp = os.path.join(root, f)
            if ignore_path(fp, ign): continue
            if detect_format(fp):
                dirs[os.path.relpath(root, scan_dir)].append(fp)
                total += 1
    
    logger.info(f"Found {total} binaries in {len(dirs)} dirs")
    
    result = {}
    for dp, fls in dirs.items():
        res = [analyze_file(p) for p in fls]
        res.sort(key=lambda x: (-int(x['debug']), -int(x['symtab']), -x['exports_count']))
        result[dp] = {'total': len(res), 'files': res}
    
    out = {'scan_time': datetime.now().isoformat(), 'total_files': total, 'total_directories': len(result), 'directories': result}
    open(output, 'w', encoding='utf-8').write(json.dumps(out, indent=2))
    logger.info(f"Results: {output}")
    
    generate_html(output)
    
    dc = sum(1 for d in result.values() for f in d['files'] if f['debug'])
    sc = sum(1 for d in result.values() for f in d['files'] if f['symtab'])
    ec = sum(1 for d in result.values() for f in d['files'] if f['exports'])
    logger.info(f"Debug: {dc}, Symtab: {sc}, Exports: {ec}")

def generate_html(json_path):
    html_path = json_path.replace('.json', '.html')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    folders = sorted(data['directories'].keys())
    all_files = []
    for folder, info in data['directories'].items():
        for f in info['files']:
            f['_folder'] = folder
            all_files.append(f)
    
    all_files.sort(key=lambda x: (-int(x['debug']), -int(x['symtab']), -x['exports_count']))
    
    rows = ''
    for f in all_files:
        debug_color = '#4caf50' if f['debug'] else '#666'
        debug_label = f['debug_type'].upper() if f['debug_type'] else '-'
        sym = '✓' if f['symtab'] else '-'
        exp = f['exports_count'] if f['exports_count'] else '-'
        rows += f'''<tr>
            <td>{f['file']}</td>
            <td>{f['arch']}</td>
            <td style="color:{debug_color};font-weight:bold">{debug_label}</td>
            <td>{sym}</td>
            <td>{exp}</td>
            <td style="color:#888;font-size:85%">{f['_folder']}</td>
        </tr>'''
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Steam Depot Analysis</title>
    <style>
        body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; margin: 20px; background: #1a1a1a; color: #eee; }}
        h1 {{ color: #fff; }}
        .controls {{ margin: 15px 0; }}
        select {{ padding: 8px; background: #333; color: #fff; border: 1px solid #555; border-radius: 4px; }}
        table {{ border-collapse: collapse; width: 100%; background: #252525; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ background: #333; cursor: pointer; user-select: none; }}
        th:hover {{ background: #444; }}
        tr:hover {{ background: #2a2a2a; }}
        .stats {{ margin: 20px 0; color: #888; }}
    </style>
</head>
<body>
    <h1>Steam Depot Analysis</h1>
    <div class="stats">
        {data['total_files']} binaries in {data['total_directories']} folders | 
        Scanned: {data['scan_time']}
    </div>
    <div class="controls">
        <label>Folder: </label>
        <select id="folderFilter" onchange="filterFolder()">
            <option value="">All</option>
            {"".join(f'<option value="{f}">{f}</option>' for f in folders)}
        </select>
    </div>
    <table id="table">
        <thead>
            <tr>
                <th onclick="sort(0)">File</th>
                <th onclick="sort(1)">Arch</th>
                <th onclick="sort(2)">Debug</th>
                <th onclick="sort(3)">Sym</th>
                <th onclick="sort(4)">Exp</th>
                <th onclick="sort(5)">Folder</th>
            </tr>
        </thead>
        <tbody id="tbody">{rows}</tbody>
    </table>
    <script>
        let asc = true;
        function sort(col) {{
            const tbody = document.getElementById('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const idx = col === 0 ? 0 : col === 1 ? 1 : col === 2 ? 2 : col === 3 ? 3 : col === 4 ? 4 : 5;
            rows.sort((a, b) => {{
                const A = a.cells[idx].textContent.trim().toLowerCase();
                const B = b.cells[idx].textContent.trim().toLowerCase();
                if (col === 2) {{
                    const order = {{'dwarf':3, 'pdb':2, 'stripped':0}};
                    const va = order[a.cells[2].textContent.toLowerCase()] ?? 0;
                    const vb = order[b.cells[2].textContent.toLowerCase()] ?? 0;
                    return asc ? vb - va : va - vb;
                }}
                if (col === 3) {{ return asc ? (a.cells[3].textContent === '✓' ? 1 : 0) - (b.cells[3].textContent === '✓' ? 1 : 0) : (b.cells[3].textContent === '✓' ? 1 : 0) - (a.cells[3].textContent === '✓' ? 1 : 0); }}
                if (col === 4) {{ return asc ? parseInt(b.cells[4].textContent) - parseInt(a.cells[4].textContent) : parseInt(a.cells[4].textContent) - parseInt(b.cells[4].textContent); }}
                return asc ? A.localeCompare(B) : B.localeCompare(A);
            }});
            rows.forEach(r => tbody.appendChild(r));
            asc = !asc;
        }}
        function filterFolder() {{
            const f = document.getElementById('folderFilter').value;
            document.querySelectorAll('#tbody tr').forEach(r => r.style.display = f && !r.cells[5].textContent.includes(f) ? 'none' : '');
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