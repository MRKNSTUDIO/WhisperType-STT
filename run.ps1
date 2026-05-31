# WhisperType Launcher
# Set console encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Change to script directory
Set-Location $PSScriptRoot

# Check for virtual environment
$venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
	Write-Host "[ERROR] Virtual environment not found." -ForegroundColor Red
	Write-Host "Please run 'install.ps1' first to set up the application." -ForegroundColor Yellow
	Read-Host "Press Enter to exit"
	exit
}

# Create ready file path
$readyFile = Join-Path $env:TEMP "whisper_type_ready_$(Get-Random).flag"
$env:WHISPER_TYPE_READY_FILE = $readyFile

# Start title bar spinner
$spinnerJob = Start-Job -ScriptBlock {
	param($readyFile)
	$chars = @('|', '/', '-', '\')
	$i = 0
	while (-not (Test-Path $readyFile)) {
		$Host.UI.RawUI.WindowTitle = "Starting WhisperType... $($chars[$i])"
		$i = ($i + 1) % 4
		Start-Sleep -Milliseconds 200
	}
	$Host.UI.RawUI.WindowTitle = "WhisperType"
} -ArgumentList $readyFile

# Just show a simple message and start Python directly
Write-Host "Starting WhisperType..."

# Start Python process and wait (sources live in src/)
& $venvPython "src\main.py"

# Clean up
Stop-Job $spinnerJob -ErrorAction SilentlyContinue
Remove-Job $spinnerJob -ErrorAction SilentlyContinue
if (Test-Path $readyFile) {
	Remove-Item $readyFile -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "The application has been closed."
Read-Host "Press Enter to exit"