param(
  [string]$Serial = "",
  [string]$TargetDir = "/data/local/tmp",
  [int]$TimeoutSec = 30
)

$ErrorActionPreference = "Stop"

function Invoke-Adb {
  param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
  if ([string]::IsNullOrWhiteSpace($Serial)) {
    & adb @Args
  } else {
    & adb -s $Serial @Args
  }
}

function Get-TrimmedLine([string]$s) {
  if ($null -eq $s) { return "" }
  return $s.Trim()
}

function Download-File([string]$Url, [string]$OutPath) {
  Write-Host "Downloading: $Url"
  Invoke-WebRequest -Uri $Url -OutFile $OutPath -UseBasicParsing -TimeoutSec $TimeoutSec | Out-Null
}

function Get-DeviceProp([string]$Key) {
  $v = (Invoke-Adb shell getprop $Key | Out-String)
  return (Get-TrimmedLine $v)
}

function Resolve-MinicapSoSdkCandidates([int]$Sdk) {
  # Use device SDK first; if not found, fallback to lower SDKs.
  $candidates = @()
  $candidates += $Sdk
  for ($i = 1; $i -le 10; $i++) {
    $candidates += ($Sdk - $i)
  }
  # 去重并过滤 <=0
  $uniq = New-Object System.Collections.Generic.HashSet[int]
  $out = @()
  foreach ($x in $candidates) {
    if ($x -gt 0 -and $uniq.Add($x)) { $out += $x }
  }
  return $out
}

Write-Host "== Minicap installer =="
Write-Host ("Serial    : " + ($(if ([string]::IsNullOrWhiteSpace($Serial)) {"(default)"} else {$Serial})))
Write-Host ("TargetDir : " + $TargetDir)

# quick check
try {
  $null = (Invoke-Adb version | Out-String)
} catch {
  throw "adb not found or not working. Make sure adb is in PATH and device is connected."
}

$ABI = Get-DeviceProp "ro.product.cpu.abi"
$SDKStr = Get-DeviceProp "ro.build.version.sdk"
if (-not $ABI) { throw "Failed to read device ABI (ro.product.cpu.abi)." }
if (-not $SDKStr) { throw "Failed to read device SDK (ro.build.version.sdk)." }

$SDK = 0
if (-not [int]::TryParse($SDKStr, [ref]$SDK)) {
  throw ("Device SDK is not a number: " + $SDKStr)
}

Write-Host ("ABI=" + $ABI + " SDK=" + $SDK)

# Use DeviceFarmer prebuilt package on UNPKG (stable downloadable binaries)
# Package: @devicefarmer/minicap-prebuilt
# You may change @2.7.3 to @latest if you prefer.
$RepoBase = "https://unpkg.com/@devicefarmer/minicap-prebuilt@2.7.3"
$MinicapName = $(if ($SDK -lt 16) { "minicap-nopie" } else { "minicap" })

$Tmp = Join-Path $env:TEMP ("minicap_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Tmp | Out-Null

$MinicapLocal = Join-Path $Tmp "minicap"
$SoLocal = Join-Path $Tmp "minicap.so"

$MinicapUrl = "$RepoBase/prebuilt/$ABI/bin/$MinicapName"
Download-File $MinicapUrl $MinicapLocal

# minicap.so may not exist for the latest SDK; try fallbacks.
$SoDownloaded = $false
$Tried = @()
foreach ($sdkTry in (Resolve-MinicapSoSdkCandidates $SDK)) {
  $SoUrl = "$RepoBase/prebuilt/$ABI/lib/android-$sdkTry/minicap.so"
  $Tried += $sdkTry
  try {
    Download-File $SoUrl $SoLocal
    $SoDownloaded = $true
    Write-Host ("minicap.so matched android-" + $sdkTry)
    break
  } catch {
    # continue
  }
}
if (-not $SoDownloaded) {
  throw ("Failed to download minicap.so. Tried SDKs: " + ($Tried -join ", ") + ". The repo may not ship a prebuilt .so for this ABI/SDK.")
}

Write-Host "Pushing to device..."
Invoke-Adb shell sh -c "mkdir -p '$TargetDir' >/dev/null 2>&1 || true" | Out-Null

Invoke-Adb push $MinicapLocal "$TargetDir/minicap" | Out-Null
Invoke-Adb push $SoLocal "$TargetDir/minicap.so" | Out-Null

Invoke-Adb shell chmod 755 "$TargetDir/minicap" | Out-Null
Invoke-Adb shell ls -l "$TargetDir/minicap" "$TargetDir/minicap.so"

Write-Host "Self-check: minicap -h"
Invoke-Adb shell sh -c "LD_LIBRARY_PATH=$TargetDir $TargetDir/minicap -h"

Write-Host ("OK: minicap installed in " + $TargetDir)

