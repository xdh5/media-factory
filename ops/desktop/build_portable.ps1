param([string]$OutputDirectory = "dist/MediaFactory", [string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "../..")
& $Python ops/desktop/build_portable.py --output $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw "绿色版构建失败，请检查构建日志。" }
