$ErrorActionPreference = "Stop"

$statePath = Join-Path $PSScriptRoot ".toggle-suspend-state.json"

function Get-ActiveSchemeGuid {
    $output = powercfg /getactivescheme
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read the active power scheme."
    }

    $match = [regex]::Match($output, "([A-Fa-f0-9-]{36})")
    if (-not $match.Success) {
        throw "Could not parse the active power scheme GUID."
    }

    return $match.Groups[1].Value
}

function Get-StandbyTimeoutMinutes {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Mode
    )

    $schemeGuid = Get-ActiveSchemeGuid
    $output = powercfg /query $schemeGuid SUB_SLEEP STANDBYIDLE
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to query the sleep timeout for mode '$Mode'."
    }

    $pattern = if ($Mode -eq "AC") {
        "Current AC Power Setting Index:\s+0x([0-9A-Fa-f]+)"
    }
    elseif ($Mode -eq "DC") {
        "Current DC Power Setting Index:\s+0x([0-9A-Fa-f]+)"
    }
    else {
        throw "Unsupported power mode '$Mode'. Use AC or DC."
    }

    $match = [regex]::Match($output, $pattern)
    if (-not $match.Success) {
        throw "Could not parse the sleep timeout for mode '$Mode'."
    }

    return [Convert]::ToInt32($match.Groups[1].Value, 16)
}

function Get-HibernateTimeoutMinutes {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Mode
    )

    $schemeGuid = Get-ActiveSchemeGuid
    $output = powercfg /query $schemeGuid SUB_SLEEP HIBERNATEIDLE
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to query the hibernate timeout for mode '$Mode'."
    }

    $pattern = if ($Mode -eq "AC") {
        "Current AC Power Setting Index:\s+0x([0-9A-Fa-f]+)"
    }
    elseif ($Mode -eq "DC") {
        "Current DC Power Setting Index:\s+0x([0-9A-Fa-f]+)"
    }
    else {
        throw "Unsupported power mode '$Mode'. Use AC or DC."
    }

    $match = [regex]::Match($output, $pattern)
    if (-not $match.Success) {
        throw "Could not parse the hibernate timeout for mode '$Mode'."
    }

    return [Convert]::ToInt32($match.Groups[1].Value, 16)
}

function Set-StandbyTimeoutMinutes {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Mode,
        [Parameter(Mandatory = $true)]
        [int]$Minutes
    )

    $command = if ($Mode -eq "AC") { "/change standby-timeout-ac $Minutes" } else { "/change standby-timeout-dc $Minutes" }
    $null = & powercfg.exe $command.Split(" ")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set the sleep timeout for mode '$Mode'."
    }
}

function Set-HibernateTimeoutMinutes {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Mode,
        [Parameter(Mandatory = $true)]
        [int]$Minutes
    )

    $command = if ($Mode -eq "AC") { "/change hibernate-timeout-ac $Minutes" } else { "/change hibernate-timeout-dc $Minutes" }
    $null = & powercfg.exe $command.Split(" ")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set the hibernate timeout for mode '$Mode'."
    }
}

function Get-HibernationEnabled {
    $output = powercfg /a
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to query hibernation support."
    }

    if ($output -match "The following sleep states are available") {
        if ($output -match "Hibernate") {
            return $true
        }
    }

    if ($output -match "Hibernation has not been enabled") {
        return $false
    }

    return $true
}

function Set-HibernationEnabled {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Enabled
    )

    $action = if ($Enabled) { "on" } else { "off" }
    $null = & powercfg.exe "/hibernate" $action
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to turn hibernation $action."
    }
}

function Save-State {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$State
    )

    $State | ConvertTo-Json | Set-Content -Path $statePath -Encoding ascii
}

function Load-State {
    if (-not (Test-Path -LiteralPath $statePath)) {
        return $null
    }

    return Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
}

function Remove-State {
    if (Test-Path -LiteralPath $statePath) {
        Remove-Item -LiteralPath $statePath -Force
    }
}

$savedState = Load-State
$activeSchemeGuid = Get-ActiveSchemeGuid

if ($savedState -and $savedState.activeSchemeGuid -eq $activeSchemeGuid) {
    Set-StandbyTimeoutMinutes -Mode "AC" -Minutes ([int]$savedState.acMinutes)
    Set-StandbyTimeoutMinutes -Mode "DC" -Minutes ([int]$savedState.dcMinutes)
    if ($null -ne $savedState.hibernateEnabled -and [bool]$savedState.hibernateEnabled) {
        Set-HibernationEnabled -Enabled $true
    }
    Set-HibernateTimeoutMinutes -Mode "AC" -Minutes ([int]$savedState.hibernateAcMinutes)
    Set-HibernateTimeoutMinutes -Mode "DC" -Minutes ([int]$savedState.hibernateDcMinutes)
    if ($null -ne $savedState.hibernateEnabled -and -not [bool]$savedState.hibernateEnabled) {
        Set-HibernationEnabled -Enabled $false
    }
    Remove-State

    Write-Host "Sleep and hibernation restored."
    Write-Host "AC: $($savedState.acMinutes) minute(s)"
    Write-Host "DC: $($savedState.dcMinutes) minute(s)"
    Write-Host "Hibernate AC: $($savedState.hibernateAcMinutes) minute(s)"
    Write-Host "Hibernate DC: $($savedState.hibernateDcMinutes) minute(s)"
    Write-Host "Hibernation enabled: $([bool]$savedState.hibernateEnabled)"
    exit 0
}

$acMinutes = Get-StandbyTimeoutMinutes -Mode "AC"
$dcMinutes = Get-StandbyTimeoutMinutes -Mode "DC"
$hibernateAcMinutes = Get-HibernateTimeoutMinutes -Mode "AC"
$hibernateDcMinutes = Get-HibernateTimeoutMinutes -Mode "DC"
$hibernateEnabled = Get-HibernationEnabled

$state = @{
    activeSchemeGuid = $activeSchemeGuid
    acMinutes = $acMinutes
    dcMinutes = $dcMinutes
    hibernateAcMinutes = $hibernateAcMinutes
    hibernateDcMinutes = $hibernateDcMinutes
    hibernateEnabled = $hibernateEnabled
}

Save-State -State $state

Set-StandbyTimeoutMinutes -Mode "AC" -Minutes 0
Set-StandbyTimeoutMinutes -Mode "DC" -Minutes 0
Set-HibernateTimeoutMinutes -Mode "AC" -Minutes 0
Set-HibernateTimeoutMinutes -Mode "DC" -Minutes 0
Set-HibernationEnabled -Enabled $false

Write-Host "Sleep timeout disabled and hibernation turned off for the active power plan."
Write-Host "Run this script again to restore:"
Write-Host "AC: $acMinutes minute(s)"
Write-Host "DC: $dcMinutes minute(s)"
Write-Host "Hibernate AC: $hibernateAcMinutes minute(s)"
Write-Host "Hibernate DC: $hibernateDcMinutes minute(s)"
