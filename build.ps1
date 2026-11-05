$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
$savedPath = $env:PATH
try {
    $buildPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $buildPython)) {
        throw 'BUILD.mdの手順でPython 3.12.0の専用.venvを作成してください。'
    }
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    & $buildPython -I tools\check_build_environment.py
    if ($LASTEXITCODE -ne 0) { throw '固定したビルド環境と一致しません。' }
    & $buildPython -I -m pip check
    if ($LASTEXITCODE -ne 0) { throw '依存関係の整合性チェックに失敗しました。' }
    & $buildPython -I -m PyInstaller --noconfirm --clean `
        --distpath dist --workpath work\pyinstaller public-release.spec
    if ($LASTEXITCODE -ne 0) { throw 'exeのビルドに失敗しました。' }
    & $buildPython -I tools\audit_distribution.py dist\Simple-PSD-Mascot-v1.0.1
    if ($LASTEXITCODE -ne 0) { throw '配布物の監査に失敗しました。' }
}
finally {
    $env:PATH = $savedPath
    Pop-Location
}
