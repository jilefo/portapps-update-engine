# build-portable.ps1 —— 通用包装（主逻辑在 Python）
param()
$ErrorActionPreference = "Stop"
$python = if ($env:PAF_PYTHON) { $env:PAF_PYTHON } else { "python" }
& $python "$PSScriptRoot\build-portable.py" @args
exit $LASTEXITCODE
