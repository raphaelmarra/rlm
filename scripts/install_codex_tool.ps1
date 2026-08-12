[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$SkillRoot = (Join-Path ([Environment]::GetFolderPath("UserProfile")) ".agents\skills"),
    [switch]$SkipToolInstall,
    [switch]$SkipVerification
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceSkill = Join-Path $repoRoot ".agents\skills\usar-rlm"
$skillRootPath = [IO.Path]::GetFullPath($SkillRoot)
$destination = Join-Path $skillRootPath "usar-rlm"
$manifestName = ".rlm-codex-origin.json"
$utf8NoBom = [Text.UTF8Encoding]::new($false)

if (-not (Test-Path -LiteralPath (Join-Path $sourceSkill "SKILL.md") -PathType Leaf)) {
    throw "Versioned usar-rlm skill was not found under the repository root"
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command '$Command' failed with exit code $LASTEXITCODE"
    }
}

function Install-VersionedSkill {
    $stage = Join-Path $skillRootPath (".usar-rlm.stage." + [Guid]::NewGuid().ToString("N"))
    $backup = Join-Path $skillRootPath (".usar-rlm.backup." + [Guid]::NewGuid().ToString("N"))
    $destinationMoved = $false

    try {
        New-Item -ItemType Directory -Path $skillRootPath -Force | Out-Null
        Copy-Item -LiteralPath $sourceSkill -Destination $stage -Recurse -Force

        $sourceCommit = (& git -C $repoRoot rev-parse HEAD).Trim().ToLowerInvariant()
        if ($LASTEXITCODE -ne 0 -or $sourceCommit -notmatch "^[0-9a-f]{40}$") {
            throw "Could not resolve the repository source commit"
        }

        $fileHashes = [ordered]@{}
        $stagePrefix = $stage.TrimEnd("\") + "\"
        Get-ChildItem -LiteralPath $stage -Recurse -File |
            Sort-Object FullName |
            ForEach-Object {
                if (-not $_.FullName.StartsWith($stagePrefix, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Skill file escaped the staging directory"
                }
                $relativePath = $_.FullName.Substring($stagePrefix.Length).Replace("\", "/")
                $fileHashes[$relativePath] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        if ($fileHashes.Count -eq 0) {
            throw "The versioned skill contains no files"
        }

        $manifest = [ordered]@{
            schema_version = "1"
            source_commit = $sourceCommit
            files = $fileHashes
        }
        $manifestJson = ($manifest | ConvertTo-Json -Depth 4) + [Environment]::NewLine
        [IO.File]::WriteAllText((Join-Path $stage $manifestName), $manifestJson, $utf8NoBom)

        if (Test-Path -LiteralPath $destination) {
            Move-Item -LiteralPath $destination -Destination $backup
            $destinationMoved = $true
        }
        Move-Item -LiteralPath $stage -Destination $destination
        if ($destinationMoved) {
            Remove-Item -LiteralPath $backup -Recurse -Force
            $destinationMoved = $false
        }
    }
    catch {
        if ($destinationMoved -and -not (Test-Path -LiteralPath $destination)) {
            Move-Item -LiteralPath $backup -Destination $destination
            $destinationMoved = $false
        }
        throw
    }
    finally {
        if (Test-Path -LiteralPath $stage) {
            Remove-Item -LiteralPath $stage -Recurse -Force
        }
        if ($destinationMoved -and (Test-Path -LiteralPath $backup)) {
            Remove-Item -LiteralPath $backup -Recurse -Force
        }
    }
}

if (-not $SkipToolInstall) {
    if ($PSCmdlet.ShouldProcess($repoRoot, "Synchronize uv environment and install rlm-codex")) {
        Invoke-CheckedCommand -Command "uv" -Arguments @(
            "sync",
            "--extra",
            "codex",
            "--group",
            "dev",
            "--group",
            "test"
        )
        Invoke-CheckedCommand -Command "uv" -Arguments @(
            "tool",
            "install",
            "--editable",
            "${repoRoot}[codex]",
            "--force"
        )
        Invoke-CheckedCommand -Command "uv" -Arguments @("tool", "update-shell")
    }
}

if ($PSCmdlet.ShouldProcess($destination, "Install versioned usar-rlm skill")) {
    Install-VersionedSkill
    Write-Output "Installed usar-rlm skill at $destination"
}

if (-not $SkipVerification -and -not $WhatIfPreference) {
    $toolBin = (& uv tool dir --bin).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $toolBin) {
        throw "Could not resolve the uv tool bin directory"
    }
    if (($env:PATH -split [IO.Path]::PathSeparator) -notcontains $toolBin) {
        $env:PATH = $toolBin + [IO.Path]::PathSeparator + $env:PATH
    }

    $rlmCodex = Get-Command "rlm-codex" -ErrorAction Stop
    Push-Location ([IO.Path]::GetTempPath())
    try {
        $doctorOutput = (& $rlmCodex.Source doctor | Out-String).Trim()
        $doctorExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($doctorExitCode -ne 0) {
        throw "rlm-codex doctor failed with exit code $doctorExitCode"
    }
    $doctor = $doctorOutput | ConvertFrom-Json
    $failedChecks = @($doctor.checks | Where-Object { -not $_.ok })
    if ($failedChecks.Count -gt 0) {
        $failedNames = ($failedChecks | ForEach-Object name) -join ", "
        throw "rlm-codex doctor reported failures: $failedNames"
    }
    Write-Output $doctorOutput
}
