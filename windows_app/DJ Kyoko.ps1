# DJ Kyoko — Windows launcher (PowerShell core, invoked by "DJ Kyoko.bat")
# Builds automatic beat-matched DJ mixes from free-text requests, with a
# live web UI showing real progress. Closing this window stops it.

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host "========================================"
Write-Host "   DJ Kyoko - Automatic Mix Builder"
Write-Host "========================================"
Write-Host ""

# Bump this — and WINDOWS_APP_VERSION in djbot-gallery/app.py — every time a
# new build ships.
$LocalAppVersion = "2026-09-05-harmonic-and-hardcut-fix-v1"
$GalleryUrl = "https://djbot-gallery-production.up.railway.app"

# ── Auto-update ──────────────────────────────────────────────────────────
# Extracts into a NEW sibling folder rather than replacing the currently-
# running script's own folder in place — Windows can hold a lock on a .ps1
# file while it's executing, unlike Mac/Linux, so an in-place swap risks a
# file-in-use error mid-update. The old folder is left behind (harmless,
# friend can delete it) rather than risk a broken update. Never blocks a
# normal launch on any failure (offline, etc.).
try {
    $latestVersion = (Invoke-RestMethod -Uri "$GalleryUrl/api/app-version" -TimeoutSec 5).windows_version
} catch { $latestVersion = $null }

if ($latestVersion -and $latestVersion -ne $LocalAppVersion) {
    Write-Host "A new version of DJ Kyoko is available ($latestVersion) - updating..."
    $updateZip = Join-Path $env:TEMP "djkyoko-update-$([guid]::NewGuid()).zip"
    $parentDir = Split-Path $PSScriptRoot -Parent
    $newDir = Join-Path $parentDir "DJ Kyoko ($latestVersion)"
    try {
        Invoke-WebRequest -Uri "$GalleryUrl/download/windows" -OutFile $updateZip
        Expand-Archive -Path $updateZip -DestinationPath $newDir -Force
        $newLauncher = Join-Path $newDir 'DJ Kyoko.bat'
        if (Test-Path $newLauncher) {
            Remove-Item $updateZip -ErrorAction SilentlyContinue
            Write-Host "Updated - launching the new version..."
            Start-Process -FilePath $newLauncher
            exit 0
        } else {
            Write-Host "Update didn't extract as expected - continuing with the current version."
        }
    } catch {
        Write-Host "Update download failed - continuing with the current version."
    }
    Remove-Item $updateZip -ErrorAction SilentlyContinue
}

$Src = Join-Path $PSScriptRoot 'djbot_src'
$AppDataDir = Join-Path $env:LOCALAPPDATA 'DJ Kyoko'
$Venv = Join-Path $AppDataDir 'venv'
$RbDir = Join-Path $AppDataDir 'rubberband'
$ReqHashFile = Join-Path $AppDataDir '.reqs_installed_hash'
$Port = 8934

New-Item -ItemType Directory -Force -Path $AppDataDir | Out-Null

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Refresh-Path {
    $machine = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Find-AndAddToPath($exeName, $searchRoot) {
    if (-not (Test-Path $searchRoot)) { return $false }
    $found = Get-ChildItem -Path $searchRoot -Filter $exeName -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $env:Path = "$($found.DirectoryName);$env:Path"
        return $true
    }
    return $false
}

function Fail($msg) {
    Write-Host ""
    Write-Host $msg
    Read-Host "Press Enter to close"
    exit 1
}

# 1. winget must exist (ships with Windows 10/11 by default)
if (-not (Test-Cmd 'winget')) {
    Fail "DJ Kyoko needs 'winget' (the Windows Package Manager) to install ffmpeg and deno.`nIt ships with Windows 10/11 by default. If it's missing, install 'App Installer' from the Microsoft Store, then re-run this file."
}

# 2/3/4. ffmpeg, deno, python via winget — with a fallback PATH search since
# some winget "portable" packages don't register on PATH until a fresh shell
$wingetPkgs = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
function Ensure-WingetTool($cmdName, $exeName, $wingetId) {
    if (Test-Cmd $cmdName) { return }
    Write-Host "Installing $cmdName (first run only)..."
    winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
    if (Test-Cmd $cmdName) { return }
    if (Find-AndAddToPath $exeName $wingetPkgs) { return }
    Fail "$cmdName installed but DJ Kyoko couldn't find it automatically. Close this window and re-run 'DJ Kyoko.bat' — Windows sometimes needs a fresh window to pick up new PATH entries. If it still fails, ask Louis for help."
}
Ensure-WingetTool 'ffmpeg' 'ffmpeg.exe' 'Gyan.FFmpeg'
Ensure-WingetTool 'deno' 'deno.exe' 'DenoLand.Deno'
Ensure-WingetTool 'python' 'python.exe' 'Python.Python.3.11'

# 5. rubberband — no winget package; download Rubber Band's own prebuilt zip
if (-not (Test-Cmd 'rubberband')) {
    $rbExe = Get-ChildItem -Path $RbDir -Filter 'rubberband.exe' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $rbExe) {
        Write-Host "Installing rubberband (first run only)..."
        $zipPath = Join-Path $env:TEMP 'rubberband.zip'
        try {
            Invoke-WebRequest -Uri 'https://breakfastquay.com/files/releases/rubberband-4.0.0-gpl-executable-windows.zip' -OutFile $zipPath
            Expand-Archive -Path $zipPath -DestinationPath $RbDir -Force
            $rbExe = Get-ChildItem -Path $RbDir -Filter 'rubberband.exe' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        } catch {
            Fail "Rubberband download failed: $_`nCheck your internet connection and re-run this file."
        }
    }
    if ($rbExe) {
        $env:Path = "$($rbExe.DirectoryName);$env:Path"
    } else {
        Fail "Rubberband downloaded but 'rubberband.exe' wasn't found inside the zip — the download may have changed shape. Ask Louis for help."
    }
}

# 6. venv + deps
if (-not (Test-Path $Venv)) {
    Write-Host "Setting up DJ Kyoko (first run only, a few minutes)..."
    python -m venv $Venv
}
& (Join-Path $Venv 'Scripts\Activate.ps1')

$reqHash = (Get-FileHash -Algorithm SHA256 (Join-Path $Src 'requirements.txt')).Hash
$oldHash = if (Test-Path $ReqHashFile) { (Get-Content $ReqHashFile -Raw).Trim() } else { '' }

if ($reqHash -ne $oldHash) {
    Write-Host "Installing dependencies (first run only, this can take several minutes)..."
    python -m pip install --quiet --upgrade pip
    $installOk = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        python -m pip install --quiet --retries 10 --timeout 60 -r (Join-Path $Src 'requirements.txt')
        if ($LASTEXITCODE -eq 0) { $installOk = $true; break }
        Write-Host "Dependency install attempt $attempt failed (likely a network hiccup) - retrying in 15s..."
        Start-Sleep -Seconds 15
    }
    if (-not $installOk) {
        Fail "Dependency install failed after 3 attempts, likely a network problem. Check your internet connection and re-run this file."
    }
    Set-Content -Path $ReqHashFile -Value $reqHash -NoNewline
}

# 7. Launch
Write-Host ""
Write-Host "Starting DJ Kyoko..."
$env:DJBOT_APP_SUPPORT = $AppDataDir

Start-Job -ScriptBlock {
    param($Port)
    $chromePaths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
    )
    $chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 1
            if ($r.StatusCode -eq 200) {
                if ($chrome) {
                    # --app= opens a chromeless window (no tabs/address bar) —
                    # reads as a real application instead of a browser tab.
                    Start-Process -FilePath $chrome -ArgumentList "--app=http://127.0.0.1:$Port"
                } else {
                    Start-Process "http://127.0.0.1:$Port"
                }
                return
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
} -ArgumentList $Port | Out-Null

Write-Host "Opening in your browser at http://127.0.0.1:$Port ..."
Write-Host "(Leave this window open while you use DJ Kyoko - closing it stops the app.)"
Write-Host "(Also reachable from your phone/iPad over Tailscale - see CROSS_PLATFORM_PLAN.md.)"
Write-Host ""

Set-Location (Join-Path $Src 'webapp')
python -m uvicorn server:app --host 0.0.0.0 --port $Port --log-level warning
