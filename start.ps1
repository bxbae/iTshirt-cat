# 캣북스 데모를 Windows에서 한 번에 실행합니다.
#   PowerShell:  powershell -ExecutionPolicy Bypass -File .\start.ps1
#   또는 start.bat 더블클릭
# 필요한 것: Python 3.11+ (python 또는 py), Node.js 20+
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { $null }
if (-not $py) { Write-Host "Python 3.11 이상이 필요합니다. https://www.python.org/downloads/ (설치 때 'Add python.exe to PATH' 체크)"; exit 1 }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Write-Host "Node.js 20 이상이 필요합니다. https://nodejs.org/"; exit 1 }

if (-not (Test-Path "backend\.venv")) {
  Write-Host "> 백엔드 패키지 설치 (처음 한 번)"
  & $py -m venv backend\.venv
  & backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
  if ($LASTEXITCODE -ne 0) { Write-Host "백엔드 패키지 설치에 실패했습니다."; exit 1 }
}
if (-not (Test-Path "frontend\node_modules")) {
  Write-Host "> 프런트엔드 패키지 설치 (처음 한 번)"
  Push-Location frontend
  npm.cmd install --no-audit --no-fund --loglevel=error
  if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "프런트엔드 패키지 설치에 실패했습니다."; exit 1 }
  Pop-Location
}

if (-not $env:LLM_PROVIDER) { $env:LLM_PROVIDER = "mock" }

Write-Host "> 백엔드 시작 (http://localhost:8000)"
$api = Start-Process -PassThru -WorkingDirectory "$PSScriptRoot\backend" -FilePath "$PSScriptRoot\backend\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000"
Write-Host "> 프런트엔드 시작 (http://localhost:3000)"
$web = Start-Process -PassThru -WorkingDirectory "$PSScriptRoot\frontend" -FilePath "npm.cmd" -ArgumentList "run", "dev"

Write-Host ""
Write-Host "  쇼핑몰   http://localhost:3000   (로그인: /login 에서 가상 고객 선택)"
Write-Host "  상담원   http://localhost:3000/admin"
Write-Host "  준비되는 데 10~20초 걸립니다. 이 창에서 Enter 를 누르면 종료합니다."
Write-Host "  초기화   종료 후 backend\catbooks.db 를 지우고 다시 실행"
try {
  Start-Sleep -Seconds 12
  Start-Process "http://localhost:3000"
  [void](Read-Host)
} finally {
  foreach ($p in @($api, $web)) { if ($p -and -not $p.HasExited) { taskkill /PID $p.Id /T /F | Out-Null } }
}
