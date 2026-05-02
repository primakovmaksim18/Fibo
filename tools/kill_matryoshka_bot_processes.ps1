# Stops processes whose command line contains matryoshka_bot (Windows).
# Run: powershell -ExecutionPolicy Bypass -File tools/kill_matryoshka_bot_processes.ps1

# Only Python (py/pythonw): match `-m matryoshka_bot` or path ...\matryoshka_bot\...
$targets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and
        ($_.Name -match '^(python|py)(w)?(\d+)?\.exe$') -and
        (
            $_.CommandLine -match '(?:^|\s)(-m|--module)\s+matryoshka_bot\b' -or
            $_.CommandLine -match '\\matryoshka_bot(\\|\.|")'
        )
    }

if (-not $targets) {
    Write-Host "No processes with matryoshka_bot in command line."
    exit 0
}

foreach ($p in $targets) {
    $snippet = $p.CommandLine.Substring(0, [Math]::Min(120, $p.CommandLine.Length))
    Write-Host "Stopping PID $($p.ProcessId): $snippet"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Done."
