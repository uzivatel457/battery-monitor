#Requires -Version 5.0
<#
.SYNOPSIS
  Prida cestu do vyjímek Windows Defender (Paths).

.NOTES
  Vyžaduje práva správce. Bez admin práv jen vypíše návod.
  Ekvivalent registru (HKLM, vyžaduje SYSTEM/TrustedInstaller zápis
  přes oficiální API Add-MpPreference, ne ruční hack registru):

    HKLM\SOFTWARE\Microsoft\Windows Defender\Exclusions\Paths
    název hodnoty = plná cesta ke složce, typ DWORD, data = 0

  Ruční zápis do tohoto klíče často nefunguje (chráněný klíč) —
  správná cesta je Add-MpPreference nebo GUI Zabezpečení Windows.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetPath
)

$ErrorActionPreference = "Stop"

try {
    $resolved = (Resolve-Path -LiteralPath $TargetPath).Path
} catch {
    Write-Host "Cesta neexistuje: $TargetPath"
    exit 0
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Add-Exclusion([string]$path) {
    $prefs = Get-MpPreference
    if ($prefs.ExclusionPath -contains $path) {
        Write-Host "Vyjímka Defender již existuje: $path"
        return
    }
    Add-MpPreference -ExclusionPath $path
    Write-Host "Přidána vyjímka Defender: $path"
}

try {
    if (Test-IsAdmin) {
        Add-Exclusion $resolved
        exit 0
    }

    # Zkusit bez elevace (na některých strojích může projít)
    try {
        Add-Exclusion $resolved
        exit 0
    } catch {
        # Elevace přes UAC
        $arg = "-NoProfile -ExecutionPolicy Bypass -Command `"Add-MpPreference -ExclusionPath '$($resolved.Replace("'","''"))'; Write-Host 'OK'`""
        $p = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arg -Wait -PassThru
        if ($p.ExitCode -eq 0) {
            Write-Host "Přidána vyjímka Defender (admin): $resolved"
            exit 0
        }
        throw "UAC / Add-MpPreference selhalo (exit $($p.ExitCode))."
    }
} catch {
    Write-Host "Defender vyjímku se nepodařilo přidat automaticky."
    Write-Host "Bez práv správce je to běžné."
    Write-Host ""
    Write-Host "Ručně:"
    Write-Host "  1) Windows Zabezpečení -> Ochrana před viry a hrozbami"
    Write-Host "  2) Nastavení ochrany -> Vyjímky -> Přidat vyjímku -> Složka"
    Write-Host "  3) Vyberte: $resolved"
    Write-Host ""
    Write-Host "Nebo PowerShell jako správce:"
    Write-Host "  Add-MpPreference -ExclusionPath '$resolved'"
    exit 0
}
