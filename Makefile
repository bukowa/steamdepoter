.PHONY: setup clean check help

DEPOT_DL_URL := https://github.com/SteamRE/DepotDownloader/releases/download/DepotDownloader_3.4.0/DepotDownloader-windows-x64.zip
DEPOT_DL_SHA := 41c9e9f0df54b3ad02e67a11726756e5c73283bd7c2e1b04acfa5ae4c2ed3767

BIN_DIR   := .bin
DEPOT_ZIP := $(BIN_DIR)/DepotDownloader.zip
DEPOT_EXE := $(BIN_DIR)/DepotDownloader.exe

help:
	@echo "Available targets:"
	@echo "  make setup   - Download and extract DepotDownloader (if missing)"
	@echo "  make clean   - Remove all binaries"

setup: $(DEPOT_EXE)

$(BIN_DIR):
	@mkdir $(BIN_DIR)

$(DEPOT_EXE): | $(BIN_DIR)
	@echo "Downloading DepotDownloader..."
	@curl -L -o "$(DEPOT_ZIP)" "$(DEPOT_DL_URL)"
	@echo "Verifying SHA256..."
	@powershell -Command "\
		$$expected = '$(DEPOT_DL_SHA)'; \
		$$actual = (certutil -hashfile '$(DEPOT_ZIP)' SHA256 | Select-String -Pattern '^[0-9a-fA-F\s]+$$' | Out-String).Replace(' ','').Trim().ToLower(); \
		if ($$actual -ne $$expected) { \
			Write-Error ('Hash mismatch! Expected: ' + $$expected + ' Got: ' + $$actual); \
			exit 1; \
		}"
	@echo "Extracting DepotDownloader..."
	@powershell -Command "Expand-Archive -Path '$(DEPOT_ZIP)' -DestinationPath '$(BIN_DIR)' -Force"
	@powershell -Command "Remove-Item '$(DEPOT_ZIP)'"
	@echo "DepotDownloader ready at $(DEPOT_EXE)"

clean:
	rm -rf $(BIN_DIR)