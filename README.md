# Steam Depot Tool

Scrapes SteamDB for depot manifests, downloads game files, and analyzes binaries for debug symbols.

**Problem:** Want to analyze debug info in Steam games? This tool downloads specific depots and tells you which binaries have DWARF/stripped symbols, security features (NX, RELRO, canary), and more.

## Quick Start

1. **Setup dependencies:**
   - **Windows:** `powershell ./setup-deps.ps1`
   - **Linux/macOS:** `chmod +x setup-deps.sh && ./setup-deps.sh`
   
   *This installs `uv`, `DepotDownloader`, `symwalker`, `pdbwalker`, and Playwright browsers.*

2. **Configure:**
   Edit `config.yaml` with your Steam username and desired App/Depot IDs.

3. **Run:**
   ```bash
   uv run main.py
   ```

## Features

- Fetch depot manifests from SteamDB automatically
- Download depot files via DepotDownloader
- Analyze ELF/Mach-O binaries with [symwalker](https://github.com/bukforks/symwalker)
- Analyze PE (Windows) binaries with [pdbwalker](https://github.com/bukforks/pdbwalker)
- Generate an interactive HTML report

## Usage

```bash
# Full pipeline: scrape -> download -> analyze
uv run main.py

# Download only
uv run main.py --mode download

# Analyze only (existing files)
uv run main.py --mode analyze

# Regenerate HTML report from JSON data
uv run main.py --html
```

## Configuration

Edit `config.yaml`:

```yaml
username: "your_steam_username"
password: ""  # recommended to leave empty (prompted at runtime)
branch: "public"
download:
  "712100":  # App ID (e.g., Project Zomboid)
    - "814262"  # Depot ID (only include depots with binaries)
```

**Tip:** Only include depot IDs that contain binary files (like `.exe`, `.dll`, `.so`). Skipping asset-only depots (textures, audio) saves significant time and space.

## Output

- `analysis_results.json`: Raw analysis data.
- `analysis_results.html`: Interactive, sortable, and searchable HTML report.

## Requirements

- Python 3.14+
- [uv](https://github.com/astral-sh/uv) (installed automatically by setup scripts)
- Steam account (for DepotDownloader)
