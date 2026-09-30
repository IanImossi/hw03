# Sets up the Python virtual environment for hw03.
# Run from the hw03 folder:  powershell -ExecutionPolicy Bypass -File .\setup_env.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Find a Python launcher
if (Get-Command py -ErrorAction SilentlyContinue) { $py = "py"; $pyArgs = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = "python"; $pyArgs = @() }
else { Write-Error "Python not found. Install Python 3.10+ from https://www.python.org/downloads/ (check 'Add to PATH')."; exit 1 }

& $py @pyArgs --version

# Create venv if missing
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv ..."
    & $py @pyArgs -m venv .venv
}

$venvPy = ".\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt

# Register a Jupyter kernel for this project
& $venvPy -m ipykernel install --user --name hw03 --display-name "Python (hw03)"

# Verify the install with the project's check script
& $venvPy verify_setup.py
if ($LASTEXITCODE -ne 0) { Write-Error "verify_setup.py reported missing libraries."; exit 1 }

Write-Host ""
Write-Host "Done. Activate with:  .\.venv\Scripts\Activate.ps1"
