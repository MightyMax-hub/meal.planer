```powershell
param(
    [string]$Source,
    [string]$RemoteHost,
    [string]$RemoteRoot,
    [string]$ServiceName,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
if (-not $Source) { $Source = $PSScriptRoot }
if (-not $RemoteHost) { $RemoteHost = "mightymax@192.168.178.81" }
if (-not $RemoteRoot) { $RemoteRoot = "/home/mightymax/meal.planer" }
if (-not $ServiceName) { $ServiceName = $env:MEAL_PLANER_SERVICE }

function ConvertTo-ShellQuotedString {
    param([string]$Value)

    $escapedValue = $Value.Replace("'", ("'" + [char]92 + "''"))
    return "'" + $escapedValue + "'"
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "       meal.planer - Update" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    throw "Source directory not found: $Source"
}

$Source = (Resolve-Path -LiteralPath $Source).Path.TrimEnd('\', '/')
if (-not $RemoteRoot.StartsWith('/')) {
    throw "RemoteRoot must be an absolute Linux path: $RemoteRoot"
}
if ($ServiceName -and $ServiceName -notmatch '^[A-Za-z0-9_.@-]+$') {
    throw "Invalid systemd service name: $ServiceName"
}

if (-not $WhatIf) {
    foreach ($commandName in @("ssh", "scp")) {
        if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
            throw "Required command not found: $commandName"
        }
    }
}

$ExcludedSegments = @("data", ".git", ".venv", "venv", "__pycache__", ".pytest_cache")
$Files = @(
    Get-ChildItem -LiteralPath $Source -Recurse -File -Force |
        ForEach-Object {
            $relativePath = $_.FullName.Substring($Source.Length).TrimStart('\', '/')
            $linuxRelativePath = $relativePath -replace '\\', '/'
            $pathSegments = $linuxRelativePath -split '/'
            $excluded = $pathSegments | Where-Object { $_ -in $ExcludedSegments }

            if (-not $excluded -and $_.Extension -notin @(".pyc", ".pyo")) {
                [PSCustomObject]@{
                    File = $_
                    RelativePath = $linuxRelativePath
                }
            }
        }
)

Write-Host "Source: $Source"
Write-Host "Target: $RemoteHost`:$RemoteRoot"
Write-Host "Files considered: $($Files.Count)"
Write-Host "Excluded: data/, virtual environments, caches, and bytecode."
Write-Host ""

$FilesToUpload = @()
foreach ($Entry in $Files) {
    if ($WhatIf) {
        $FilesToUpload += $Entry
        continue
    }

    $remoteFile = "$RemoteRoot/$($Entry.RelativePath)"
    $quotedRemoteFile = ConvertTo-ShellQuotedString $remoteFile
    $remoteInfo = & ssh $RemoteHost "if [ -f $quotedRemoteFile ]; then sha256sum -- $quotedRemoteFile; fi"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not check remote file: $remoteFile"
    }

    $remoteHash = ""
    $remoteOutput = ($remoteInfo | Out-String).Trim()
    if ($remoteOutput) {
        $remoteHash = ($remoteOutput -split '\s+')[0]
    }

    $localHash = (Get-FileHash -LiteralPath $Entry.File.FullName -Algorithm SHA256).Hash
    if ($localHash -ne $remoteHash) {
        $FilesToUpload += $Entry
        Write-Host "CHANGED: $($Entry.RelativePath)" -ForegroundColor Yellow
    }
}

if ($FilesToUpload.Count -eq 0) {
    Write-Host "Everything is up to date. No files need uploading." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "Files to upload: $($FilesToUpload.Count)" -ForegroundColor Cyan

$UploadedCount = 0
foreach ($Entry in $FilesToUpload) {
    $remoteFile = "$RemoteRoot/$($Entry.RelativePath)"
    $remoteDirectory = $remoteFile.Substring(0, $remoteFile.LastIndexOf('/'))
    $quotedRemoteDirectory = ConvertTo-ShellQuotedString $remoteDirectory

    if ($WhatIf) {
        Write-Host "What if: upload $($Entry.RelativePath) to $RemoteHost`:$remoteFile"
        continue
    }

    & ssh $RemoteHost "mkdir -p -- $quotedRemoteDirectory"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create remote directory: $remoteDirectory"
    }

    Write-Host "Uploading: $($Entry.RelativePath)" -ForegroundColor Cyan
    & scp -- $Entry.File.FullName "$RemoteHost`:$remoteFile"
    if ($LASTEXITCODE -ne 0) {
        throw "Upload failed: $($Entry.RelativePath)"
    }
    $UploadedCount++
}

if ($UploadedCount -gt 0 -and $ServiceName) {
    if ($WhatIf) {
        Write-Host "What if: restart systemd service $ServiceName on $RemoteHost"
    }
    else {
        & ssh $RemoteHost "sudo -n systemctl restart $ServiceName"
        if ($LASTEXITCODE -ne 0) {
            throw "Files were uploaded, but restarting '$ServiceName' failed. Check the service name and passwordless sudo permissions."
        }
    }
}
elseif ($UploadedCount -gt 0) {
    Write-Host "No service restart requested. Set MEAL_PLANER_SERVICE or pass -ServiceName if the app needs restarting." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Update complete. Uploaded: $UploadedCount file(s)." -ForegroundColor Green
Write-Host "data/ was not scanned or modified."
Write-Host ""
```
