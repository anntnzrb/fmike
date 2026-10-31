# Usage: powershell -ExecutionPolicy Bypass -File install.ps1
# Run as your normal user. Re-run after reboot if Banana was newly installed.
$ErrorActionPreference = 'Stop'
function Fail($Message, $Fix) {
    Write-Host "error: $Message"
    Write-Host "fix: $Fix"
    exit 1
}
try {
    Set-Location $PSScriptRoot
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail 'winget is unavailable.' 'Install App Installer from Microsoft Store, then re-run.'
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host 'Installing uv with winget...'
        winget install -e --id astral-sh.uv --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { Fail 'uv installation failed.' 'Resolve the winget error and re-run.' }
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            Fail 'uv is installed but not on PATH.' 'Open a new PowerShell window and re-run.'
        }
    }
    $BananaKey = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\VB:Voicemeeter {17359A74-1236-5467}'
    if (-not (Test-Path $BananaKey)) {
        Write-Host 'Installing Voicemeeter Banana with winget...'
        winget install -e --id VB-Audio.Voicemeeter.Banana --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { Fail 'Banana installation failed.' 'Resolve the winget error and re-run.' }
        Write-Host 'REBOOT Windows now, then re-run this script to finish driver setup.'
        exit 0
    }
    Write-Host 'Synchronizing the locked Python 3.15 environment...'
    uv sync --locked
    if ($LASTEXITCODE -ne 0) { Fail 'uv sync failed.' 'Check network access and the uv error above; re-run.' }
    Write-Host 'Installing startup, hotkey, and audio routing...'
    & "$PSScriptRoot\.venv\Scripts\fmike.exe" install
    if ($LASTEXITCODE -ne 0) { Fail 'fmike installation checks failed.' 'Follow the printed fix lines, then re-run.' }
    Write-Host 'Ready. Launch .venv\Scripts\fmike-tray.exe or sign out and back in.'
} catch {
    Fail $_.Exception.Message 'Resolve the error above, then re-run install.ps1.'
}
