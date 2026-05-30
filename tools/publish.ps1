param(
  [string]$Message = "Publish blog updates"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python tools/build.py
git status --short
git add .
git commit -m $Message
git push origin main
