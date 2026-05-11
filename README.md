# steamdepoter

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Steam account

## Setup

```powershell
./setup-deps.ps1
```

## Usage

### 1. Generate Scraper
Configure your App/Depot IDs in `config.yaml`, then run:
```bash
uv run main.py scrape
```

### 2. Manual Scrape
1. Open [steamdb.info](https://steamdb.info) in your browser (make sure you are logged in).
2. Open Browser Console (F12).
3. Paste contents of `scrape.js` and press Enter.
4. Move the downloaded `manifest_cache.json` to the `manifest_cache/` folder.

### 3. Download
```bash
uv run main.py download
```

### 4. Analyze
```bash
uv run main.py analyze
```

*Or run everything in sequence (after step 2):*
```bash
uv run main.py all
```

## Configuration

Edit `config.yaml`:

```yaml
username: "your_steam_username"
branch: "public"
download:
  "712100":   # App ID
    - "814262" # Depot ID
```
