Param(
  [string]$OutDir = "$PWD\cookies_export",
  [switch]$All,
  [string]$Service = ""
)

$ErrorActionPreference = "Stop"

Write-Host "[1/3] Installing/Updating browser-cookie3..."
py -m pip install --upgrade browser-cookie3 | Out-Host

Write-Host "[2/3] Exporting cookies from local Chrome profile..."
if ($All) {
  py scripts\export_chrome_cookies.py --all --out-dir $OutDir | Out-Host
} elseif ($Service -ne "") {
  py scripts\export_chrome_cookies.py --service $Service --out-dir $OutDir | Out-Host
} else {
  throw "Specify -All or -Service <name>"
}

Write-Host "[3/3] Done. Files are in: $OutDir"
Write-Host "Next: upload *.cookies.json to server and run /auth_cookie <service> <path> verify"

