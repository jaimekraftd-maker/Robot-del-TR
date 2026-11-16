<#
preparar_windows.ps1 — Prepara Windows para el cerebro de TR en WSL2
=====================================================================
El cerebro (tr_robot_brain) corre en Ubuntu 22.04 dentro de WSL2 y la cabeza
(Pi Zero 2 W) le habla por Wi-Fi con ROS 2. Este script, una sola vez:

  1. Comprueba que %USERPROFILE%\.wslconfig tiene networkingMode=mirrored
     (Ubuntu comparte la IP de Windows) y lo añade si falta.
  2. Abre en el cortafuegos de Hyper-V, el que protege a WSL, los puertos UDP
     que usa ROS 2 (DDS) con ROS_DOMAIN_ID=42, más el 11811 del Discovery Server.
  3. Mira si el Ollama de Windows tiene gemma2:2b y moondream (los respaldos).

Uso (PowerShell como administrador, después de instalar WSL):
    powershell -ExecutionPolicy Bypass -File scripts\wsl\preparar_windows.ps1
Solo mirar, sin cambiar nada (no hace falta administrador):
    powershell -ExecutionPolicy Bypass -File scripts\wsl\preparar_windows.ps1 -Comprobar
#>
param(
    [int]$DominioRos = 42,
    [switch]$Comprobar
)

# DDS reserva 250 puertos por dominio a partir de 7400 (RTPS: 7400 + 250 * dominio)
$inicio = 7400 + 250 * $DominioRos
$puertos = @("$inicio-$($inicio + 249)", "11811")
$nombreRegla = "TR-ROS2-DDS-$DominioRos"
$wslGuidConocido = "{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}"

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $Comprobar -and -not $esAdmin) {
    Write-Host "Hace falta PowerShell como administrador (o usa -Comprobar para solo mirar)." -ForegroundColor Red
    exit 1
}

# --- 1. .wslconfig ----------------------------------------------------------------
$wslconfig = Join-Path $env:USERPROFILE ".wslconfig"
$texto = if (Test-Path $wslconfig) { Get-Content $wslconfig -Raw } else { "" }
if ($texto -match "(?m)^\s*networkingMode\s*=\s*mirrored\s*$") {
    Write-Host "[1/3] .wslconfig ya tiene networkingMode=mirrored." -ForegroundColor Green
} elseif ($Comprobar) {
    Write-Host "[1/3] .wslconfig NO tiene networkingMode=mirrored." -ForegroundColor Yellow
} elseif ($texto -match "(?m)^\s*networkingMode\s*=") {
    Write-Host "[1/3] .wslconfig ya define otro networkingMode: cámbialo a mano a 'mirrored'." -ForegroundColor Yellow
} else {
    if ($texto) { Copy-Item $wslconfig "$wslconfig.bak" -Force }
    if ($texto -match "(?m)^\s*\[wsl2\]\s*$") {
        $texto = $texto -replace "(?m)^(\s*\[wsl2\]\s*)$", "`$1`r`nnetworkingMode=mirrored"
    } else {
        $texto = $texto.TrimEnd() + "`r`n[wsl2]`r`nnetworkingMode=mirrored`r`n"
    }
    [IO.File]::WriteAllText($wslconfig, $texto.TrimStart())
    Write-Host "[1/3] Añadido networkingMode=mirrored a $wslconfig. Aplica con: wsl --shutdown" -ForegroundColor Green
}

# --- 2. Cortafuegos de Hyper-V para WSL ---------------------------------------------
$creador = Get-NetFirewallHyperVVMCreator -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -eq "WSL" }
$vmCreatorId = if ($creador) { $creador.VMCreatorId } else { $wslGuidConocido }
$regla = Get-NetFirewallHyperVRule -Name $nombreRegla -ErrorAction SilentlyContinue
if ($Comprobar) {
    $estado = if ($regla) { "existe" } else { "NO existe" }
    $color = if ($regla) { "Green" } else { "Yellow" }
    Write-Host "[2/3] Regla $nombreRegla (UDP $($puertos -join ', ')) $estado. WSL VMCreatorId: $vmCreatorId" -ForegroundColor $color
} else {
    if ($regla) { Remove-NetFirewallHyperVRule -Name $nombreRegla }
    New-NetFirewallHyperVRule -Name $nombreRegla -DisplayName "TR: ROS 2 DDS (dominio $DominioRos)" `
        -Direction Inbound -VMCreatorId $vmCreatorId -Protocol UDP -LocalPorts $puertos -Action Allow | Out-Null
    Write-Host "[2/3] Cortafuegos: WSL acepta UDP $($puertos -join ', ') (ROS 2, dominio $DominioRos)." -ForegroundColor Green
}

# --- 3. Ollama de Windows -------------------------------------------------------------
try {
    $modelos = (Invoke-RestMethod http://localhost:11434/api/tags -TimeoutSec 3).models.name
    foreach ($m in "gemma2:2b", "moondream") {
        if ($modelos | Where-Object { $_ -like "$m*" }) {
            Write-Host "[3/3] Ollama de Windows: $m listo." -ForegroundColor Green
        } else {
            Write-Host "[3/3] Ollama de Windows: falta $m (respaldo offline). Descárgalo con:  ollama pull $m" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "[3/3] Ollama de Windows no responde en localhost:11434: ábrelo para tener respaldo offline." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Siguiente paso, en Ubuntu (WSL):  bash ~/ros2_ws/src/tr_robot_ollama/scripts/install_brain.sh"
