# Steam Depot Tool

Download Steam game depots and analyze binaries for debug symbols.

## Requirements

- Python 3.14+
- [.NET SDK](https://dotnet.microsoft.com/download) (for DepotDownloader)
- [symwalker](https://github.com/19h/symwalker) (in PATH)

Install symwalker: `cargo install symwalker` or download from releases.

Install DepotDownloader: `winget install --exact --id SteamRE.DepotDownloader`

## Setup

```bash
git clone https://github.com/bukowa/steamdepoter.git
cd steamdepoter
uv venv
uv sync
uv run playwright install chromium
```

Verify DepotDownloader: `DepotDownloader --help`
Verify symwalker: `symwalker --version`

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

# Regenerate HTML from existing JSON
uv run main.py --html
```

## Output

- `analysis_results.json` - raw analysis data
- `analysis_results.html` - interactive HTML report

### HTML Report Features

- Sortable columns (click header to sort)
- Search/filter by filename
- Green rows = has debug info (DWARF)
- Orange rows = no debug info (stripped)
- Shows: architecture, binary type, security flags (NX, RELRO, canary, etc.)

### symwalker provides

- DWARF debug sections detection
- Build ID extraction
- dSYM bundle detection (macOS)
- debuginfod remote symbol lookup
- Security analysis (PIE, NX, RELRO, stack canary, FORTIFY)

## Ignore Files

Optional: create `ignore.txt` with patterns to skip (one per line, `#` for comments).