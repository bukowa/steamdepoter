# Steam Depot Tool

Scrapes SteamDB for depot manifests, downloads game files, and analyzes binaries for debug symbols.

**Problem:** Want to analyze debug info in Steam games? This tool downloads specific depots and tells you which binaries have DWARF/stripped symbols, security features (NX, RELRO, canary), and more.

## Features

- Fetch depot manifests from SteamDB
- Download depot files via DepotDownloader
- Analyze ELF/Mach-O binaries with symwalker
- Analyze PE binaries with pdbwalker
- Interactive HTML report

## Requirements

- Python 3.14+
- [symwalker](https://github.com/19h/symwalker) for ELF/Mach-O analysis
- [pdbwalker](https://github.com/19h/pdbwalker) for PE analysis

### Installing symwalker

**Option 1:** Download pre-built binary from my fork:
https://github.com/bukforks/symwalker/releases/tag/v2.0.0-test4

**Option 2:** Build from source:
```bash
cargo install --git https://github.com/19h/symwalker
```

### Installing pdbwalker

**Option 1:** Download pre-built binary from my fork:
https://github.com/bukforks/pdbwalker/releases/tag/v1.0.0

**Option 2:** Build from source:
```bash
cargo install --git https://github.com/19h/pdbwalker
```

### Installing DepotDownloader

```bash
winget install --exact --id SteamRE.DepotDownloader
```

## Setup

```bash
git clone https://github.com/bukowa/steamdepoter.git
cd steamdepoter
uv venv
uv sync
uv run playwright install chromium
```

Verify installation:
```bash
DepotDownloader --help
symwalker --version
```

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

### symwalker provides (ELF/Mach-O)

- DWARF debug sections detection
- Build ID extraction
- dSYM bundle detection (macOS)
- debuginfod remote symbol lookup
- Security analysis (PIE, NX, RELRO, stack canary, FORTIFY)

### pdbwalker provides (PE)

- PDB debug info detection
- Local PDB file detection
- Microsoft Symbol Server lookup
- PE metadata (architecture, image base, subsystem)

## Ignore Files

Optional: create `ignore.txt` with patterns to skip (one per line, `#` for comments).
