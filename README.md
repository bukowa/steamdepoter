# Steam Depot Analyzer

A simple tool to download Steam game depots and check them for debug symbols (DWARF, PDB, etc.).

## How it works

1. **Scrape**: It checks SteamDB for manifest IDs of a specific game depot.
2. **Download**: It uses `DepotDownloader` to grab the files.
3. **Analyze**: It scans the binaries (PE, ELF, Mach-O) to see if they contain debug info that tools like Ghidra or IDA Pro can use.

## Setup

1. Make sure you have `DepotDownloader` installed and in your PATH.
2. Install Python dependencies:
   ```bash
   uv sync
   ```
3. Initialize Playwright:
   ```bash
   uv run playwright install chromium
   ```

## Usage

### 1. Configure
Edit `config.yaml` to specify your Steam credentials and which depots you want to download.

```yaml
username: "your_username"
password: "" # Optional
branch: "public"
download:
  "297000": # App ID
    - "297001" # Depot ID
```

### 2. Download
Run the main script to fetch the manifests and download the files.

```bash
uv run main.py
```

### 3. Analyze
Scan the downloaded files for debug symbols.

```bash
uv run analyzer.py
```

## Output

The analyzer will show a summary in the terminal and generate three log files in the `manifest_downloads` directory:

- `symbols_found.log`: Files with full or partial debug symbols.
- `symbols_missing.log`: Files that expect a PDB but it wasn't found, or are fully stripped.
- `analysis_errors.log`: Files that couldn't be parsed.

## Ignoring Files
Add any folder or file names you want to skip to `ignore.txt`.
```
Chromium Embedded Framework.framework
```
