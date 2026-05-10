# Steam Depot Tool

Download Steam game depots and analyze binaries for debug symbols.

## Requirements

- Python 3.14+
- [DepotDownloader](https://github.com/SteamRE/DepotDownloader)

Install via: `winget install --exact --id SteamRE.DepotDownloader`

## Setup

```bash
git clone https://github.com/bukowa/steamdepoter.git
cd steamdepoter
uv venv
uv sync
uv run playwright install chromium
```

Verify DepotDownloader: `DepotDownloader --help`

## Config

Edit `config.yaml`:

```yaml
username: "your_steam_username"
password: ""  # optional
branch: "public"
download:
  "712100":  # App ID
    - "814262"  # Depot ID (only include depots with binaries)
```

**Tip:** Only include depot IDs that contain binary files (like `.exe`, `.dll`, `.so`). Empty depots (textures, audio, etc.) will just waste time.

## Usage

```bash
# Full pipeline (download + analyze)
uv run main.py

# Download only
uv run main.py --mode download

# Analyze only
uv run main.py --mode analyze
```

## Output

Results in `analysis_results.json` - debug/symbol info for each binary.

HTML report: `analysis_results.html` - sortable table with folder filter.

## Ignore Files

Optional: create `ignore.txt` with patterns to skip (one per line, `#` for comments).