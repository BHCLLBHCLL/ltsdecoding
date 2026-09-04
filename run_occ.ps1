# run_occ.ps1 - 用 OCC 环境 (occ) 运行项目脚本 (pythonocc-core 一等公民)
# 用法: .\run_occ.ps1 <script.py> [args...]
# 环境: conda env "occ" + Library\bin 入 PATH (OpenBLAS/OCC DLL) + UTF-8 控制台
$env:PYTHONIOENCODING = "utf-8"
$env:PATH = "C:\Users\sdcll\.conda\envs\occ\Library\bin;" + $env:PATH
$py = "C:\Users\sdcll\.conda\envs\occ\python.exe"
& $py @args
exit $LASTEXITCODE
