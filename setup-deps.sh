#!/usr/bin/env bash
# setup-deps.sh - Automated dependency setup for Linux/macOS
set -eo pipefail

# Colors
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
GRAY='\033[0;90m'
NC='\033[0m'

echo -e "\n${YELLOW}--- Linux/macOS Dependency Setup ---${NC}"

# 1. DepotDownloader - Extract ONLY the binary to avoid overwriting LICENSE
echo -e "${CYAN}[*] Downloading DepotDownloader...${NC}"
curl -L -# -f -o "DepotDownloader.zip" "https://github.com/SteamRE/DepotDownloader/releases/download/DepotDownloader_3.4.0/DepotDownloader-linux-x64.zip"
echo -e "${GRAY}    Extracting binary only...${NC}"
unzip -q -o "DepotDownloader.zip" "DepotDownloader"
chmod +x DepotDownloader
rm "DepotDownloader.zip"

# 2. pdbwalker
echo -e "${CYAN}[*] Downloading pdbwalker...${NC}"
curl -L -# -f -o "pdbwalker" "https://github.com/bukforks/pdbwalker/releases/download/v1.0.0/pdbwalker-x86_64-unknown-linux-gnu"
chmod +x pdbwalker

# 3. symwalker
echo -e "${CYAN}[*] Downloading symwalker...${NC}"
curl -L -# -f -o "symwalker" "https://github.com/bukforks/symwalker/releases/download/v2.0.0-test4/symwalker-x86_64-unknown-linux-gnu"
chmod +x symwalker

# 4. UV
echo -e "${CYAN}[*] Creating venv & installing Python deps...${NC}"
uv sync --frozen
uv run playwright install chromium

# 5. Verify
echo -e "\n${YELLOW}--- Verification ---${NC}"
for bin in "./DepotDownloader" "./pdbwalker" "./symwalker"; do
    if [ -f "$bin" ]; then
        echo -e "    ${GREEN}[OK] $bin${NC}"
    else
        echo -e "    ${RED}[FAIL] $bin missing${NC}"
        exit 1
    fi
done

echo -e "\n${GREEN}Setup complete!${NC}\n"
