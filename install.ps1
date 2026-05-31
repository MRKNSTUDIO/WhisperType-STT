# WhisperType Installer
# Sets up a virtual environment, installs PyTorch (GPU or CPU) and all
# dependencies, and optionally pre-downloads Whisper models.
#
# Run from a PowerShell window:
#     powershell -ExecutionPolicy Bypass -File install.ps1
# or right-click this file and choose "Run with PowerShell".

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $PSScriptRoot

# Remove the Windows "Mark-of-the-Web" from every file in this folder, so the
# scripts (run.ps1, etc.) are no longer flagged as "downloaded from another
# computer". This is why launching via install.bat needs no manual unblocking.
try { Get-ChildItem -Path $PSScriptRoot -Recurse -File | Unblock-File -ErrorAction SilentlyContinue } catch { }

function Write-Header($text) {
    Write-Host ""
    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step($text) {
    Write-Host ""
    Write-Host "--- $text ---" -ForegroundColor Yellow
    Write-Host ""
}

function Pause-Continue {
    Write-Host ""
    Read-Host "Press Enter to continue"
}

# This whole script is wrapped so the window never closes silently on an error
# (this replaces the old debug_install.bat).
try {
    Write-Header "Welcome to the WhisperType Installer"
    Write-Host "This script analyzes your system and guides you through a"
    Write-Host "fully compatible installation."
    Pause-Continue

    # ------------------------------------------------------------------
    # Step 1 of 5: Select Python
    # ------------------------------------------------------------------
    Write-Step "Step 1 of 5: Select Python Installation"

    # Collect Python interpreters from several sources so none are missed.
    $found = New-Object System.Collections.Generic.List[string]

    # 1) The "py" launcher knows about every registered install. Parse the WHOLE
    #    output with Matches (not a per-line singular Match), because PowerShell
    #    sometimes returns this as one multi-line string, which would otherwise
    #    yield only the first interpreter.
    try {
        $rawList = (& py --list-paths 2>&1 | Out-String)
        foreach ($m in [regex]::Matches($rawList, '([A-Za-z]:\\[^\r\n]*?python\.exe)')) {
            $found.Add($m.Groups[1].Value)
        }
    } catch { }

    # 2) Anything named "python" on PATH (skip the Microsoft Store alias stub).
    foreach ($c in (Get-Command python -All -ErrorAction SilentlyContinue)) {
        if ($c.Source -and $c.Source -notmatch '\\WindowsApps\\') { $found.Add($c.Source) }
    }

    # 3) Common install locations the launcher might not list (e.g. conda).
    $searchRoots = @(
        "C:\Python*\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
        "$env:ProgramData\miniconda3\python.exe",
        "$env:ProgramData\anaconda3\python.exe",
        "$env:LOCALAPPDATA\miniconda3\python.exe",
        "$env:USERPROFILE\miniconda3\python.exe",
        "$env:USERPROFILE\anaconda3\python.exe"
    )
    foreach ($pattern in $searchRoots) {
        foreach ($f in (Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue)) {
            $found.Add($f.FullName)
        }
    }

    # De-duplicate (case-insensitive) and keep only paths that actually exist.
    $pythonPaths = @()
    $seen = @{}
    foreach ($p in $found) {
        if (-not $p) { continue }
        try { $full = [System.IO.Path]::GetFullPath($p) } catch { $full = $p }
        $key = $full.ToLowerInvariant()
        if ((Test-Path $full) -and -not $seen.ContainsKey($key)) {
            $seen[$key] = $true
            $pythonPaths += $full
        }
    }

    if ($pythonPaths.Count -eq 0) {
        Write-Host "[CRITICAL ERROR] No Python installation found." -ForegroundColor Red
        Write-Host "Please install 64-bit Python 3.11+ from https://www.python.org/downloads/ and re-run."
        Pause-Continue
        exit 1
    }

    Write-Host "Available Python installations:"
    for ($i = 0; $i -lt $pythonPaths.Count; $i++) {
        $ver = ""
        try {
            $ver = (& $pythonPaths[$i] -c "import sys;print('.'.join(map(str,sys.version_info[:3])), '64-bit' if sys.maxsize>2**32 else '32-bit')" 2>$null) -join ''
        } catch { }
        if ($ver) {
            Write-Host ("  [{0}] Python {1,-16} {2}" -f ($i + 1), $ver, $pythonPaths[$i])
        } else {
            Write-Host ("  [{0}] {1}" -f ($i + 1), $pythonPaths[$i])
        }
    }
    Write-Host ""

    $pyExe = $pythonPaths[0]
    if ($pythonPaths.Count -gt 1) {
        $choice = Read-Host "Enter the number of the Python version to use (default 1)"
        if ($choice -match '^\d+$' -and [int]$choice -ge 1 -and [int]$choice -le $pythonPaths.Count) {
            $pyExe = $pythonPaths[[int]$choice - 1]
        }
    }
    Write-Host "[OK] Using Python: $pyExe" -ForegroundColor Green
    Pause-Continue

    # ------------------------------------------------------------------
    # Step 2 of 5: Virtual environment
    # ------------------------------------------------------------------
    Write-Step "Step 2 of 5: Creating Virtual Environment"

    if (Test-Path "venv") {
        Write-Host "[INFO] Removing existing venv for a clean install..."
        Remove-Item -Recurse -Force "venv"
    }

    Write-Host "Creating Python environment..."
    & $pyExe -m venv venv
    $venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "[CRITICAL ERROR] Failed to create the virtual environment." -ForegroundColor Red
        Pause-Continue
        exit 1
    }
    Write-Host "[OK] Virtual environment is ready." -ForegroundColor Green

    Write-Host "Upgrading pip..."
    & $venvPython -m pip install --upgrade pip | Out-Null
    Pause-Continue

    # ------------------------------------------------------------------
    # Step 3 of 5: PyTorch
    # ------------------------------------------------------------------
    Write-Step "Step 3 of 5: Installing PyTorch"

    $driverCuda = $null
    $hasNvidia = $null -ne (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
    if ($hasNvidia) {
        try {
            $smi = & nvidia-smi 2>$null | Out-String
            $m = [regex]::Match($smi, 'CUDA Version:\s*([\d.]+)')
            if ($m.Success) { $driverCuda = $m.Groups[1].Value }
        } catch { }
    }

    if ($driverCuda) {
        Write-Host "[OK] NVIDIA GPU detected. Driver supports up to CUDA $driverCuda." -ForegroundColor Green
    } elseif ($hasNvidia) {
        Write-Host "[INFO] NVIDIA GPU detected, but the CUDA version could not be read."
    } else {
        Write-Host "[INFO] No NVIDIA GPU detected. CPU mode is recommended."
    }

    # Pick the best PyTorch wheel index. The pip wheels bundle their own CUDA
    # runtime, so the requirements are: (a) a driver new enough for that CUDA
    # version, and (b) a wheel actually built for the selected Python ON WINDOWS.
    # (This is why a hardcoded cu121 failed on Python 3.13 - cu121 ships no
    #  win_amd64 cp313 wheels.)
    $pyTag = ""
    try { $pyTag = (& $venvPython -c "import sys;print(f'cp{sys.version_info.major}{sys.version_info.minor}')" 2>$null).Trim() } catch { }

    # Parse the driver CUDA version in a locale-independent way (e.g. "13.1").
    $driverNum = 0.0
    if ($driverCuda) {
        [void][double]::TryParse($driverCuda, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$driverNum)
    }

    function Find-TorchIndex([string[]]$names, [string]$cpTag) {
        foreach ($n in $names) {
            $url = "https://download.pytorch.org/whl/$n"
            try {
                $html = (Invoke-WebRequest -UseBasicParsing "$url/torch/" -TimeoutSec 25).Content
                if ($cpTag) {
                    if ($html -match "$cpTag-$cpTag-win_amd64") { return $url }
                } elseif ($html -match 'win_amd64') { return $url }
            } catch { }
        }
        return $null
    }

    # CUDA runtime version shipped by each wheel index. We only consider builds
    # whose CUDA version is <= what the driver supports, newest first, then probe
    # the index for a wheel matching this Python on Windows.
    $wheelCuda = [ordered]@{ 'cu130' = 13.0; 'cu128' = 12.8; 'cu126' = 12.6; 'cu124' = 12.4; 'cu121' = 12.1; 'cu118' = 11.8 }
    $recommended = $null
    if ($driverNum -gt 0) {
        $candidates = @()
        foreach ($k in $wheelCuda.Keys) { if ($wheelCuda[$k] -le $driverNum) { $candidates += $k } }
        if ($candidates.Count -gt 0) {
            Write-Host "Checking which CUDA build has a wheel for Python ($pyTag) on Windows..." -ForegroundColor DarkGray
            $recommended = Find-TorchIndex $candidates $pyTag
        }
        if (-not $recommended) {
            Write-Host "[INFO] No prebuilt CUDA wheel matches this Python version yet." -ForegroundColor Yellow
            Write-Host "       Very new Python releases sometimes lack a GPU build for a while." -ForegroundColor Yellow
            Write-Host "       You can pick an older Python (re-run) or use a CPU build below." -ForegroundColor Yellow
        }
    }

    Write-Host ""
    Write-Host "How would you like to install PyTorch?"
    if ($recommended) {
        Write-Host "  [1] Recommended GPU build for your driver  ($recommended)"
    } else {
        Write-Host "  [1] CPU build (no NVIDIA GPU detected)"
    }
    Write-Host "  [2] Custom - paste the command from https://pytorch.org/ (most reliable)"
    Write-Host "  [3] CPU-only build"
    Write-Host ""
    Write-Host "  TIP: For the perfect match, open https://pytorch.org/, pick" -ForegroundColor DarkGray
    Write-Host "       Stable / Windows / Pip / Python and a CUDA version <= $driverCuda," -ForegroundColor DarkGray
    Write-Host "       then copy the generated command and use option [2]." -ForegroundColor DarkGray
    Write-Host ""

    $ptChoice = Read-Host "Enter your choice (default 1)"
    if (-not $ptChoice) { $ptChoice = "1" }

    $installOk = $false
    switch ($ptChoice) {
        "2" {
            Write-Host ""
            Write-Host "Paste the full command from pytorch.org and press Enter."
            Write-Host "Example: pip3 install torch torchaudio --index-url https://download.pytorch.org/whl/cu126"
            $custom = Read-Host "Command"
            # Strip a leading "pip install" / "pip3 install" if the user pasted it.
            $pipArgs = $custom -replace '^\s*pip3?\s+install\s+', ''
            if (-not ($pipArgs -match 'torch')) { $pipArgs = "torch torchaudio $pipArgs" }
            Write-Host "Running: pip install $pipArgs"
            & $venvPython -m pip install @($pipArgs -split '\s+' | Where-Object { $_ })
            $installOk = ($LASTEXITCODE -eq 0)
        }
        "3" {
            Write-Host "Installing CPU build of PyTorch..."
            & $venvPython -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
            $installOk = ($LASTEXITCODE -eq 0)
        }
        default {
            if ($recommended) {
                Write-Host "Installing GPU build from $recommended ..."
                & $venvPython -m pip install torch torchaudio --index-url $recommended
            } else {
                Write-Host "Installing CPU build of PyTorch..."
                & $venvPython -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
            }
            $installOk = ($LASTEXITCODE -eq 0)
        }
    }

    if (-not $installOk) {
        Write-Host ""
        Write-Host "[CRITICAL ERROR] Failed to install PyTorch." -ForegroundColor Red
        Write-Host "Tip: try option [2] with the exact command from https://pytorch.org/."
        Pause-Continue
        exit 1
    }
    Write-Host "[OK] PyTorch installed successfully." -ForegroundColor Green
    Pause-Continue

    # ------------------------------------------------------------------
    # Step 4 of 5: Other dependencies
    # ------------------------------------------------------------------
    Write-Step "Step 4 of 5: Installing Other Dependencies"

    Write-Host "Installing libraries from requirements.txt..."
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[CRITICAL ERROR] Failed to install required libraries." -ForegroundColor Red
        Pause-Continue
        exit 1
    }
    Write-Host "[OK] All other libraries installed successfully." -ForegroundColor Green
    Pause-Continue

    # ------------------------------------------------------------------
    # Step 5 of 5: Optional model download
    # ------------------------------------------------------------------
    Write-Step "Step 5 of 5: Download Whisper Models (Optional)"

    Write-Host "You can download Whisper models now, or skip and download them"
    Write-Host "later from inside the application."
    Write-Host ""
    $dl = Read-Host "Download models now? (y/N)"
    if ($dl -match '^[Yy]') {
        Write-Host "Launching model download wizard..."
        & $venvPython "src\predownload_models.py"
    }

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    Write-Header "Installation Complete!"
    Write-Host "Start the app by right-clicking 'run.ps1' and choosing 'Run with PowerShell',"
    Write-Host "or run:  powershell -ExecutionPolicy Bypass -File run.ps1"
    Pause-Continue
}
catch {
    Write-Host ""
    Write-Host "[CRITICAL ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
    Pause-Continue
    exit 1
}
