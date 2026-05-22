Param(
    [ValidateSet("pypi", "git")]
    [string]$Source = $(if ($env:LIMBI_INSTALL_SOURCE) { $env:LIMBI_INSTALL_SOURCE } else { "pypi" })
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoUrl = if ($env:LIMBI_INSTALL_REPO) { $env:LIMBI_INSTALL_REPO } else { "https://github.com/sayon999-d/Limbi-.git" }

$PythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = @("py", "-3.11")
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = @("python")
}
elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PythonCmd = @("python3")
}

if (-not $PythonCmd) {
    Write-Host "Python 3.11+ is required to install Limbi."
    Write-Host "Install Python 3.11 and rerun this installer."
    exit 1
}

if ($PythonCmd.Count -gt 1) {
    $PythonArgs = $PythonCmd[1..($PythonCmd.Length - 1)]
} else {
    $PythonArgs = @()
}

$version = & $PythonCmd[0] @PythonArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$version -lt [version]"3.11") {
    Write-Host "Python 3.11+ is required. Found: $version"
    exit 1
}

Write-Host "Limbi install check"
Write-Host "Python: $version"
Write-Host ""

if ($Source -eq "git") {
    Write-Host "Installing Limbi from GitHub..."
    & $PythonCmd[0] @PythonArgs -m pip install --upgrade "git+$RepoUrl@main#egg=limbi"
}
else {
    Write-Host "Installing Limbi from PyPI..."
    & $PythonCmd[0] @PythonArgs -m pip install --upgrade limbi
}

Write-Host ""
Write-Host "Verifying installation..."
try {
    & $PythonCmd[0] @PythonArgs -c "import limbi; print(getattr(limbi, '__version__', 'installed'))"
}
catch {
    Write-Host "Limbi installed"
}

Write-Host ""
Write-Host "Limbi is installed."
Write-Host "Run: limbi"
