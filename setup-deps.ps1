# setup-deps.ps1 - Automated dependency setup for Windows
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Download-Bin {
    param([string]$Url, [string]$Out)
    Write-Host "[*] Downloading $Out..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Url -OutFile $Out -UseBasicParsing
}

Write-Host "`n--- Windows Dependency Setup ---" -ForegroundColor Yellow

# 1. DepotDownloader (Zip) - Extracting ONLY the executable
Download-Bin "https://github.com/SteamRE/DepotDownloader/releases/download/DepotDownloader_3.4.0/DepotDownloader-windows-x64.zip" "DepotDownloader.zip"
Write-Host "    Extracting DepotDownloader.exe..." -ForegroundColor Gray

$shell = New-Object -ComObject Shell.Application
$zip = $shell.NameSpace((Get-Item "DepotDownloader.zip").FullName)
$dest = $shell.NameSpace((Get-Item ".").FullName)
$file = $zip.Items() | Where-Object { $_.Name -eq "DepotDownloader.exe" }

if ($file) {
    $dest.CopyHere($file, 16) # 16 = Respond "Yes to All" to any dialogs
} else {
    throw "Could not find DepotDownloader.exe in zip"
}

Remove-Item "DepotDownloader.zip" -Force

# 2. pdbwalker (Exe)
Download-Bin "https://github.com/bukforks/pdbwalker/releases/download/v1.0.0/pdbwalker-x86_64-pc-windows-msvc.exe" "pdbwalker.exe"

# 3. symwalker (Exe)
Download-Bin "https://github.com/bukforks/symwalker/releases/download/v2.0.0-test4/symwalker-x86_64-pc-windows-msvc.exe" "symwalker.exe"

# 4. UV
Write-Host "[*] Creating venv & installing Python deps..." -ForegroundColor Cyan
uv sync --frozen # --frozen ensures it uses the lockfile exactly
uv run playwright install chromium

# 5. Verify
Write-Host "`n--- Verification ---" -ForegroundColor Yellow
$bins = @("DepotDownloader.exe", "pdbwalker.exe", "symwalker.exe")
$failed = $false
foreach ($bin in $bins) {
    if (Test-Path $bin) {
        Write-Host "    [OK] $bin" -ForegroundColor Green
    } else {
        Write-Host "    [FAIL] $bin" -ForegroundColor Red
        $failed = $true
    }
}

if ($failed) { exit 1 }
Write-Host "`nSetup complete!`n" -ForegroundColor Green
