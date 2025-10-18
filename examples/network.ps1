# network.ps1
param(
  [Parameter(Mandatory=$true)][string]$Action,
  [string]$JsonArgs = "{}"
)

# Ensure errors flow to stderr and non-zero exit codes are set on failure
$ErrorActionPreference = "Stop"

function _OutJson($obj) {
  $obj | ConvertTo-Json -Depth 6 -Compress
}

function Get-Interfaces([string]$Version) {
  $adapters = Get-NetAdapter | Sort-Object -Property ifIndex
  $ipAll = Get-NetIPAddress -AddressFamily ($Version) -ErrorAction SilentlyContinue
  $byIf = $ipAll | Group-Object -Property InterfaceAlias -AsHashTable -AsString

  $rows = @()
  foreach ($a in $adapters) {
    $ips = @()
    if ($byIf.ContainsKey($a.Name)) {
      foreach ($ip in $byIf[$a.Name]) {
        if ($Version -eq "IPv6") {
          $ips += "$($ip.IPAddress)/$($ip.PrefixLength)"
        } else {
          $ips += $ip.IPAddress
        }
      }
    }
    $rows += [pscustomobject]@{
      Name        = $a.Name
      AdminStatus = if ($a.AdminStatus) { $a.AdminStatus } else { if ($a.Enabled) {"Up"} else {"Down"} }
      OperStatus  = $a.Status
      IPv4        = if ($Version -eq "IPv4") { $ips } else { @() }
      IPv6        = if ($Version -eq "IPv6") { $ips } else { @() }
    }
  }
  _OutJson $rows
}

function Set-IP([string]$Name, [string]$Version, [string]$Prefix) {
  # Prefix examples: "192.168.1.10/24" or "2001:db8::1/64"
  if ($Version -eq "IPv4") {
    # Remove existing DHCP/static addresses on this family? Keep simple: add new address.
    New-NetIPAddress -InterfaceAlias $Name -IPAddress ($Prefix.Split("/")[0]) -PrefixLength ([int]$Prefix.Split("/")[1]) -AddressFamily IPv4 -ErrorAction Stop | Out-Null
  } else {
    New-NetIPAddress -InterfaceAlias $Name -IPAddress ($Prefix.Split("/")[0]) -PrefixLength ([int]$Prefix.Split("/")[1]) -AddressFamily IPv6 -ErrorAction Stop | Out-Null
  }
  "OK"
}

function Enable-Interface([string]$Name) {
  Enable-NetAdapter -Name $Name -Confirm:$false | Out-Null
  "up"
}

function Disable-Interface([string]$Name) {
  Disable-NetAdapter -Name $Name -Confirm:$false | Out-Null
  "down"
}

function Get-Routes([string]$Version) {
  $fam = if ($Version -eq "IPv6") { "IPv6" } else { "IPv4" }
  $rts = Get-NetRoute -AddressFamily $fam -ErrorAction SilentlyContinue |
         Sort-Object -Property RouteMetric, DestinationPrefix
  $rows = foreach ($r in $rts) {
    [pscustomobject]@{
      Destination    = $r.DestinationPrefix
      NextHop        = if ($r.NextHop) { $r.NextHop } else { "-" }
      InterfaceAlias = $r.InterfaceAlias
      RouteMetric    = $r.RouteMetric
    }
  }
  _OutJson $rows
}

function Add-Route([string]$Version, [string]$Destination, [string]$NextHop, [string]$InterfaceAlias) {
  $fam = if ($Version -eq "IPv6") { "IPv6" } else { "IPv4" }
  if ([string]::IsNullOrWhiteSpace($InterfaceAlias)) {
    New-NetRoute -AddressFamily $fam -DestinationPrefix $Destination -NextHop $NextHop -ErrorAction Stop | Out-Null
  } else {
    New-NetRoute -AddressFamily $fam -DestinationPrefix $Destination -NextHop $NextHop -InterfaceAlias $InterfaceAlias -ErrorAction Stop | Out-Null
  }
  "OK"
}

function Ping-Host([string]$Target, [int]$Count) {
  # Use Test-Connection for reliability, summarize
  $res = Test-Connection -TargetName $Target -Count $Count -ErrorAction SilentlyContinue
  if (-not $res) { return "No reply" }
  $avg = [math]::Round(($res | Measure-Object -Property ResponseTime -Average).Average,2)
  "$Target: sent=$Count received=$($res.Count) loss=$([int]((1 - ($res.Count / $Count))*100))% avg=${avg}ms"
}

# ----- dispatch -----
try {
  $argsObj = $JsonArgs | ConvertFrom-Json
  switch ($Action) {
    "GetInterfaces" { Get-Interfaces -Version $argsObj.Version; break }
    "SetIP"         { Set-IP -Name $argsObj.Name -Version $argsObj.Version -Prefix $argsObj.Prefix | Write-Output; break }
    "EnableInterface" { Enable-Interface -Name $argsObj.Name | Write-Output; break }
    "DisableInterface" { Disable-Interface -Name $argsObj.Name | Write-Output; break }
    "GetRoutes"     { Get-Routes -Version $argsObj.Version; break }
    "AddRoute"      { Add-Route -Version $argsObj.Version -Destination $argsObj.Destination -NextHop $argsObj.NextHop -InterfaceAlias $argsObj.InterfaceAlias | Write-Output; break }
    "Ping"          { Ping-Host -Target $argsObj.Target -Count $argsObj.Count | Write-Output; break }
    default         { throw "Unknown Action: $Action" }
  }
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
