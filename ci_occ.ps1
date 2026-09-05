# ci_occ.ps1 - occ 运行时 CI (pythonocc-core OCC 一等公民)
# 在 conda env "occ" 下运行 OCC 专项: occ 可用性 + test_occ + lt_parity --gate(OCC 语料) [+CAD 交换].
# 用法: powershell -File ci_occ.ps1   ;  ci_occ.ps1 -Full
param([switch]$Full)
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PATH = "C:\Users\sdcll\.conda\envs\occ\Library\bin;" + $env:PATH
$py = "C:\Users\sdcll\.conda\envs\occ\python.exe"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== OCC CI (occ runtime) =="
& $py -c "import lts_occ as lo; print('engine:', lo.engine_name(), 'gprop:', lo.cad_features()['gprop'])"
if ($LASTEXITCODE -ne 0) { throw "OCC import failed in occ env" }
& $py -c "import lts_occ as lo; assert lo.occ_available(), 'OCC not available'"
if ($LASTEXITCODE -ne 0) { throw "OCC not available in occ env" }

Write-Host "== test_occ (OCC-gated) =="
& $py -m pytest "$root\tests\test_occ.py" -q
if ($LASTEXITCODE -ne 0) { throw "test_occ failed" }

Write-Host "== lt_parity --gate (with OCC geometry corpus) =="
& $py "$root\lt_parity.py" --gate
if ($LASTEXITCODE -ne 0) { throw "lt_parity --gate failed" }

if ($Full) {
    Write-Host "== verify_cad_exchange (OCC CAD exchange) =="
    & $py "$root\verify_cad_exchange.py"
    if ($LASTEXITCODE -ne 0) { throw "verify_cad_exchange failed" }
}
Write-Host "== OCC CI OK =="
