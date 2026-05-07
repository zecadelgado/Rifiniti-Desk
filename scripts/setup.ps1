$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $projectRoot

$pythonCmd = Get-Command py -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $pythonExe = "py"
    $pythonArgs = @("-3")
} else {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        throw "Python nao encontrado. Instale Python 3.11+ e marque a opcao de adicionar ao PATH."
    }
    $pythonExe = "python"
    $pythonArgs = @()
}

& $pythonExe @pythonArgs -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe .\scripts\setup_database.py

Write-Host ""
Write-Host "Ambiente pronto."
Write-Host "Para executar: .\.venv\Scripts\python.exe main.py"
