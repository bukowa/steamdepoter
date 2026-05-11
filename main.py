#!/usr/bin/env python3
import sys, os, subprocess, shutil, json, argparse, logging, time, yaml, re
from datetime import datetime
from collections import defaultdict

# --- Configuration & Constants ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
MANIFEST_CACHE_DIR = os.path.join(BASE_DIR, "manifest_cache")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "manifest_downloads")
LOG_FILE = os.path.join(BASE_DIR, "steamdepoter.log")
JS_OUTPUT_FILE = os.path.join(BASE_DIR, "scrape.js")
APP_INFO_CACHE = os.path.join(BASE_DIR, "app_info.json")

REQUIRED_BINS = ["DepotDownloader.exe", "pdbwalker.exe", "symwalker.exe"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("steamdepoter")

# --- 1. System Checks ---

def check_dependencies():
    """Ensure all required binaries and config exist."""
    missing_bins = [b for b in REQUIRED_BINS if not (os.path.exists(b) or shutil.which(b) or shutil.which(b.replace('.exe', '')))]
    if missing_bins:
        logger.error(f"Missing required executables: {', '.join(missing_bins)}")
        sys.exit(1)
    
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file not found: {CONFIG_FILE}")
        sys.exit(1)

# --- 2. Data Helpers ---

def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

def load_cache():
    cache = {}
    if not os.path.exists(MANIFEST_CACHE_DIR):
        os.makedirs(MANIFEST_CACHE_DIR, exist_ok=True)
        # Migrate old single file if it exists
        old_file = os.path.join(BASE_DIR, "manifest_cache.json")
        if os.path.exists(old_file):
            shutil.move(old_file, os.path.join(MANIFEST_CACHE_DIR, "migrated_default.json"))
            logger.info("Migrated old manifest_cache.json to manifest_cache/migrated_default.json")
    
    for filename in os.listdir(MANIFEST_CACHE_DIR):
        if filename.endswith(".json"):
            path = os.path.join(MANIFEST_CACHE_DIR, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for depot_id, manifests in data.items():
                        depot_id_str = str(depot_id)
                        if depot_id_str not in cache:
                            cache[depot_id_str] = manifests
                        else:
                            # Merge and deduplicate by manifest_id
                            existing_ids = {m['manifest_id'] for m in cache[depot_id_str]}
                            for m in manifests:
                                if m['manifest_id'] not in existing_ids:
                                    cache[depot_id_str].append(m)
            except Exception as e:
                logger.error(f"Failed to load cache file {filename}: {e}")
    
    if cache:
        logger.info(f"Loaded {len(cache)} depots from {len([f for f in os.listdir(MANIFEST_CACHE_DIR) if f.endswith('.json')])} cache files.")
    return cache

def load_app_info():
    if os.path.exists(APP_INFO_CACHE):
        with open(APP_INFO_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_app_info(info):
    with open(APP_INFO_CACHE, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)

def fetch_app_name(app_id):
    """Fetch app name anonymously using DepotDownloader."""
    logger.info(f"Fetching name for App {app_id}...")
    try:
        res = subprocess.run(["DepotDownloader.exe", "-app", str(app_id)], capture_output=True, text=True, timeout=15)
        match = re.search(fr"App {app_id} \((.*?)\)", res.stdout + res.stderr)
        if match:
            name = match.group(1)
            logger.info(f"  -> Found: {name}")
            return name
    except Exception as e:
        logger.error(f"Failed to fetch app name: {e}")
    return f"App {app_id}"

# --- 3. Step: Scrape (JS Generation) ---

def generate_js_scraper(depots_to_scrape, existing_cache):
    """Generates the JS snippet for manual browser console execution."""
    depots_json = json.dumps(depots_to_scrape, indent=2)
    cache_json = json.dumps(existing_cache, indent=2)

    js_template = f"""// SteamDB Manifest Scraper (Popup Edition)
(async () => {{
    const depots = {depots_json};
    const results = {cache_json};
    const delay = ms => new Promise(r => setTimeout(r, ms));

    console.log("%c[!] Make sure you allowed POPUPS in your browser!", "color: yellow; font-weight: bold; font-size: 14px;");

    let successCount = 0;
    let failCount = 0;

    for (const {{app_id, depot_id}} of depots) {{
        const url = `https://steamdb.info/depot/${{depot_id}}/manifests/`;
        console.log(`[*] Processing ${{depot_id}} (app ${{app_id}})...`);
        
        const popup = window.open(url, '_blank', 'width=800,height=600');
        
        if (!popup) {{ 
            console.error("[-] ERROR: Popup was blocked by the browser!"); 
            break; 
        }}

        let manifests = [];
        try {{
            await new Promise((resolve, reject) => {{
                let attempts = 0;
                const checkInterval = setInterval(() => {{
                    attempts++;
                    
                    const rows = popup.document.querySelectorAll('tr[data-branch]');
                    
                    if (rows.length > 0) {{
                        clearInterval(checkInterval);
                        
                        rows.forEach(row => {{
                            const branch = row.getAttribute('data-branch');
                            const timeTd = row.querySelector('td.timeago');
                            const manifestTd = row.querySelector('td.tabular-nums a');
                            if (timeTd && manifestTd) {{
                                manifests.push({{
                                    branch: branch,
                                    date: timeTd.getAttribute('data-time'),
                                    manifest_id: manifestTd.textContent.trim()
                                }});
                            }}
                        }});
                        resolve();
                    }}

                    if (attempts > 100) {{ // ~20 seconds
                        clearInterval(checkInterval);
                        reject("Timeout: Manifests not found (possible Cloudflare or not logged in).");
                    }}
                }}, 200);
            }});

            console.log(`  -> Success: Found ${{manifests.length}} manifests.`);
            results[depot_id] = manifests;
            successCount++;

        }} catch (err) {{
            console.error(`  -> ERROR for ${{depot_id}}:`, err);
            failCount++;
        }}
        
        popup.close();
        
        const nextDelay = Math.floor(Math.random() * 5000) + 5000;
        console.log(`[*] Waiting ${{nextDelay}}ms before next...`);
        await delay(nextDelay); 
    }}

    const json = JSON.stringify(results, null, 4);
    const blob = new Blob([json], {{type: 'application/json'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'manifest_cache.json';
    a.click();
    
    console.log("%c========================================", "color: white; font-weight: bold;");
    console.log(`%cFINISHED! Success: ${{successCount}}, Errors: ${{failCount}}`, successCount > 0 ? "color: green;" : "color: red;");
    if (failCount > 0) {{
        console.log("%c[!] Some depots could not be scraped (e.g. due to Cloudflare).", "color: yellow;");
        console.log("%cSTRATEGY: Save the downloaded file to your project and run 'uv run main.py scrape' again.", "color: yellow; font-weight: bold;");
    }}
    console.log("%c========================================", "color: white; font-weight: bold;");
}})();
"""
    with open(JS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(js_template)
    
    logger.info(f"Generated {JS_OUTPUT_FILE}")
    print("\n" + "="*60 + "\nMANUAL ACTION REQUIRED:")
    print(f"1. Open https://steamdb.info (logged in)\n2. Paste contents of {JS_OUTPUT_FILE} into Console (F12)")
    print(f"3. Move the downloaded 'manifest_cache.json' to folder: {MANIFEST_CACHE_DIR}")
    print("   (You can rename it to something descriptive like 'app_name.json')")
    print("4. Run: uv run main.py download\n" + "="*60 + "\n")

# --- 4. Step: Download ---

def download_depots(config, cache):
    """Downloads all manifests for the configured branch."""
    username = config.get("username")
    password = config.get("password", "")
    branch = config.get("branch", "public")
    apps_config = config.get("download", {})

    if not username:
        logger.error("Username missing in config.yaml")
        return

    to_download = []
    for app_id, depots in apps_config.items():
        for depot_id in depots:
            manifests = cache.get(str(depot_id), [])
            branch_manifests = [m for m in manifests if m['branch'] == branch]
            for m in branch_manifests:
                to_download.append({'app_id': app_id, 'depot_id': depot_id, 'manifest_id': m['manifest_id']})

    if not to_download:
        logger.warning("No manifests found in cache to download.")
        return

    logger.info(f"Starting download of {len(to_download)} manifests...")
    download_cache_file = os.path.join(DOWNLOAD_DIR, "download_cache.json")
    dl_cache = {}
    if os.path.exists(download_cache_file):
        with open(download_cache_file, 'r') as f: dl_cache = json.load(f)

    app_info = load_app_info()
    for item in to_download:
        app_id_str = str(item['app_id'])
        if app_id_str not in app_info:
            app_info[app_id_str] = fetch_app_name(item['app_id'])
            save_app_info(app_info)

        key = f"{item['app_id']}-{item['depot_id']}-{item['manifest_id']}"
        if key in dl_cache:
            logger.info(f"Skipping cached download: {item['manifest_id']}")
            continue

        dest = os.path.join(DOWNLOAD_DIR, str(item['app_id']), str(item['depot_id']), str(item['manifest_id']))
        cmd = ["DepotDownloader.exe", "-app", str(item['app_id']), "-depot", str(item['depot_id']), 
               "-manifest", str(item['manifest_id']), "-username", username, "-dir", dest, "-remember-password"]
        if password: cmd.extend(["-password", password])

        try:
            subprocess.run(cmd, check=True)
            dl_cache[key] = {"at": datetime.now().isoformat()}
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            with open(download_cache_file, 'w') as f: json.dump(dl_cache, f, indent=2)
        except subprocess.CalledProcessError as e:
            logger.error(f"Download failed for {item['manifest_id']}: {e}")

# --- 5. Step: Analyze ---

def analyze_depots():
    """Runs symwalker and pdbwalker on downloaded files."""
    if not os.path.isdir(DOWNLOAD_DIR): return

    results = []
    logger.info("Analyzing binaries...")
    
    try:
        sym = subprocess.run(['symwalker', DOWNLOAD_DIR, '--show-stripped', '--check-remote', '--security', '--json'], capture_output=True, text=True)
        if sym.returncode == 0: results.extend(json.loads(sym.stdout))
        
        pdb = subprocess.run(['pdbwalker', DOWNLOAD_DIR, '--check-remote', '--json'], capture_output=True, text=True)
        if pdb.returncode == 0: results.extend([json.loads(l) for l in pdb.stdout.strip().split('\n') if l.strip()])
    except Exception as e:
        logger.error(f"Analysis tool error: {e}")

    app_info = load_app_info()
    for entry in results:
        fp = entry.get('file_path', '')
        # Extract AppID from path: manifest_downloads/{app_id}/{depot_id}/...
        rel = os.path.relpath(fp, DOWNLOAD_DIR)
        parts = rel.split(os.sep)
        if len(parts) > 0:
            app_id = parts[0]
            entry['app_name'] = app_info.get(app_id, f"App {app_id}")

    # Process and save results
    dirs = defaultdict(list)
    for entry in results:
        dirs[os.path.relpath(os.path.dirname(entry.get('file_path', '')), DOWNLOAD_DIR)].append(entry)
    
    out = {
        'scan_time': datetime.now().isoformat(),
        'total_files': len(results),
        'directories': {dp: {'total': len(fs), 'files': sorted(fs, key=lambda x: (not has_debug(x), x.get('file_path')))} for dp, fs in dirs.items()}
    }
    
    with open("analysis_results.json", 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    
    generate_html_report("analysis_results.json")
    logger.info(f"Analysis complete. Results in analysis_results.json and .html")

def has_debug(f):
    return f.get('has_debug_info') or f.get('local_pdb', {}).get('available') or f.get('remote_pdb', {}).get('available')

def generate_html_report(json_path):
    html_path = json_path.replace('.json', '.html')
    with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
    
    all_files = []
    for folder, info in data['directories'].items():
        for f in info['files']:
            f['_folder'] = folder
            all_files.append(f)
    all_files.sort(key=lambda x: (not has_debug(x), x.get('file_path', '')))
    
    headers = ['File', 'Game', 'Folder', 'Debug Info', 'Stripped', 'Local PDB', 'Remote PDB', 'Build ID']
    rows = ""
    for f in all_files:
        row_class = "has-debug" if has_debug(f) else "no-debug"
        cells = [
            f'<td class="file-cell">{os.path.basename(f.get("file_path", ""))}</td>',
            f'<td>{f.get("app_name", "-")}</td>',
            f'<td class="folder-cell">{f.get("_folder", "")}</td>',
            f'<td>{"&#10003;" if f.get("has_debug_info") else "-"}</td>',
            f'<td>{"&#10003;" if f.get("is_stripped") else "-"}</td>',
            f'<td>{"&#10003;" if f.get("local_pdb", {}).get("available") else "-"}</td>',
            f'<td>{"&#10003;" if f.get("remote_pdb", {}).get("available") else "-"}</td>',
            f'<td>{f.get("build_id", "-")}</td>'
        ]
        rows += f'<tr class="{row_class}">{"".join(cells)}</tr>'

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Steam Depot Analysis</title><style>
        body {{ font-family: sans-serif; background: #1a1a1a; color: #eee; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; background: #252525; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #333; font-size: 12px; }}
        th {{ background: #333; }}
        .has-debug {{ color: #4caf50; }}
        .no-debug {{ color: #ff9800; }}
        .folder-cell {{ color: #888; font-size: 11px; }}
    </style></head><body>
    <h1>Steam Depot Analysis</h1>
    <div style="margin-bottom: 10px;">{data['total_files']} binaries found</div>
    <table><thead><tr>{"".join(f"<th>{h}</th>" for h in headers)}</tr></thead><tbody>{rows}</tbody></table>
    </body></html>"""
    with open(html_path, 'w', encoding='utf-8') as f: f.write(html)

# --- CLI Subcommands ---

def cmd_scrape(args):
    config = load_config()
    cache = load_cache()
    app_info = load_app_info()
    
    missing = []
    apps_in_config = config.get("download", {})
    
    # Ensure we have names for all apps in config
    for app_id in apps_in_config.keys():
        app_id_str = str(app_id)
        if app_id_str not in app_info:
            app_info[app_id_str] = fetch_app_name(app_id)
            save_app_info(app_info)

    for app_id, depots in apps_in_config.items():
        for depot_id in depots:
            if str(depot_id) not in cache:
                missing.append({"app_id": str(app_id), "depot_id": str(depot_id)})
    
    if missing:
        generate_js_scraper(missing, cache)
    else:
        logger.info("All depots already in cache. No scraping needed.")

def cmd_download(args):
    config = load_config()
    cache = load_cache()
    download_depots(config, cache)

def cmd_analyze(args):
    analyze_depots()

def cmd_all(args):
    cmd_scrape(args)
    # Check if scrape generated a new file, if so, we should probably stop
    if os.path.exists(JS_OUTPUT_FILE) and time.time() - os.path.getmtime(JS_OUTPUT_FILE) < 5:
        return
    cmd_download(args)
    cmd_analyze(args)

# --- Main Entry Point ---

def main():
    check_dependencies()
    
    parser = argparse.ArgumentParser(description="Steam Depot Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    subparsers.add_parser("scrape", help="Generate JS scraper for missing manifests")
    subparsers.add_parser("download", help="Download manifests from Steam")
    subparsers.add_parser("analyze", help="Analyze downloaded binaries")
    subparsers.add_parser("all", help="Run scrape, download, and analyze in sequence")
    
    args = parser.parse_args()
    
    commands = {
        "scrape": cmd_scrape,
        "download": cmd_download,
        "analyze": cmd_analyze,
        "all": cmd_all
    }
    
    commands[args.command](args)

if __name__ == "__main__":
    main()