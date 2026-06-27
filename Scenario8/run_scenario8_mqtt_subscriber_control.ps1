param(
    [ValidateSet("realtime", "50", "150")]
    [string]$Scenario = "realtime",

    [ValidateSet("gui", "headless")]
    [string]$Mode = "gui",

    [ValidateSet("visual", "protect")]
    [string]$ControlMode = "visual",

    [ValidateRange(20, 500)]
    [int]$VehicleCount = 150,

    [int]$Duration = 0,

    [int]$ConflictGroups = 0,

    [int]$Seed = 8408,

    [switch]$NoRegenerateRealtime,

    [switch]$Fast,

    [int]$TraciPort = 8873,

    [string]$SumoBinary = "",

    [int]$MaxSteps = 0,

    [switch]$ShowSubscriber,

    [switch]$HideSubscriber,

    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$sumoConfig = switch ($Scenario) {
    "150" { "osm_150.sumocfg" }
    "realtime" { "osm_realtime.sumocfg" }
    default { "osm.sumocfg" }
}

if ($Scenario -eq "realtime" -and -not $NoRegenerateRealtime) {
    if ($Duration -le 0) {
        $Duration = [Math]::Max(240, [Math]::Min(1200, $VehicleCount * 4))
    }
    if ($ConflictGroups -le 0) {
        $ConflictGroups = [Math]::Max(4, [Math]::Min(30, [Math]::Floor($VehicleCount / 6)))
    }
    $maxConflictGroups = [Math]::Floor($VehicleCount / 2)
    if ($ConflictGroups -gt $maxConflictGroups) {
        $ConflictGroups = $maxConflictGroups
    }

    Write-Host "Generating realtime route: vehicles=$VehicleCount duration=${Duration}s conflict_groups=$ConflictGroups seed=$Seed"
    & $Python @(
        "scripts\create_scenario8_routes.py",
        "--vehicle-count", "$VehicleCount",
        "--conflict-groups", "$ConflictGroups",
        "--end-time", "$Duration",
        "--seed", "$Seed",
        "--safe-behavior",
        "--output-route", "scenario8_realtime.routes.xml",
        "--output-conflict-groups", "data\scenario8_realtime_conflict_groups.csv"
    )
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if (-not $SumoBinary) {
    $SumoBinary = if ($Mode -eq "headless") { "sumo" } else { "sumo-gui" }
}

if ($Mode -eq "headless") {
    $Fast = $true
}

$realTimeArgs = if ($Fast) {
    @("--no-real-time")
} else {
    @("--real-time", "--realtime-factor", "1")
}

$controllerArgs = @(
    "scripts\mqtt_alert_subscriber_traci_controller.py",
    "--traci-port", "$TraciPort",
    "--traci-client-order", "2",
    "--control-mode", $ControlMode
)

$engineArgs = @(
    "scripts\mqtt_alert_engine_multiclient.py",
    "--sumo-binary", $SumoBinary,
    "--sumo-config", $sumoConfig,
    "--vehicle-groups", "targeted",
    "--min-risk", "LOW",
    "--prediction-interval-steps", "10",
    "--max-alerts-per-cycle", "5",
    "--alert-mode", "episode",
    "--episode-reset-s", "3600"
) + $realTimeArgs + @(
    "--traci-num-clients", "2",
    "--traci-client-order", "1"
)

if ($MaxSteps -gt 0) {
    $controllerArgs += @("--max-steps", "$MaxSteps")
    $engineArgs += @("--max-steps", "$MaxSteps")
}

$env:SCENARIO8_TRACI_PORT = "$TraciPort"
$env:PYTHONUNBUFFERED = "1"
$showSubscriberWindow = [bool]($ShowSubscriber -or (($Mode -eq "gui") -and -not $HideSubscriber))

$controllerOut = Join-Path $env:TEMP "scenario8-controller.out.log"
$controllerErr = Join-Path $env:TEMP "scenario8-controller.err.log"
Remove-Item -LiteralPath $controllerOut, $controllerErr -ErrorAction SilentlyContinue

Write-Host "Scenario8 run: scenario=$Scenario mode=$Mode control_mode=$ControlMode vehicles=$VehicleCount sumo_config=$sumoConfig sumo_binary=$SumoBinary port=$TraciPort"
if ($showSubscriberWindow) {
    Write-Host "Subscriber output: visible PowerShell window"
    $quotedControllerArgs = ($controllerArgs | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ","
    $subscriberCommand = @"
Set-Location '$($PSScriptRoot -replace "'", "''")'
`$env:SCENARIO8_TRACI_PORT='$TraciPort'
`$env:PYTHONUNBUFFERED='1'
Write-Host 'Scenario8 MQTT subscriber-controller'
Write-Host 'Received LOW/HIGH alerts will appear here.'
& '$($Python -replace "'", "''")' @($quotedControllerArgs)
Write-Host ''
Write-Host 'Subscriber finished. Press Enter to close this window.'
Read-Host
"@
    $controller = Start-Process `
        -FilePath "powershell" `
        -ArgumentList @("-NoExit", "-Command", $subscriberCommand) `
        -WorkingDirectory $PSScriptRoot `
        -PassThru
} else {
    Write-Host "Controller output: $controllerOut"
    Write-Host "Controller errors: $controllerErr"

    $controller = Start-Process `
        -FilePath $Python `
        -ArgumentList $controllerArgs `
        -WorkingDirectory $PSScriptRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $controllerOut `
        -RedirectStandardError $controllerErr `
        -PassThru
}

try {
    Start-Sleep -Seconds 1
    & $Python @engineArgs
    $engineExit = $LASTEXITCODE

    $controllerWaitTimeout = if ($showSubscriberWindow) { 3 } else { 30 }
    Wait-Process -Id $controller.Id -Timeout $controllerWaitTimeout -ErrorAction SilentlyContinue
    if (-not $controller.HasExited) {
        Stop-Process -Id $controller.Id -Force
    }
    $controller.Refresh()
    $controllerExit = if ($null -eq $controller.ExitCode) { 0 } else { $controller.ExitCode }

    if (-not $showSubscriberWindow) {
        Write-Host "Controller output tail:"
        Get-Content -LiteralPath $controllerOut -Tail 20 -ErrorAction SilentlyContinue
    }

    if ($engineExit -ne 0) {
        exit $engineExit
    }
    exit $controllerExit
}
finally {
    if ($controller -and -not $controller.HasExited) {
        Stop-Process -Id $controller.Id -Force
    }
}
