<#
  Windows 개발환경 자동 세팅 (VS Code, Git, Miniforge, CUDA 12.6, Python 3.11 conda env + PyTorch)
  사용법: PowerShell에서
      powershell -ExecutionPolicy Bypass -File .\setup-dev-env.ps1
  관리자 권한이 필요하며, 아니면 자동으로 UAC 승격을 요청합니다.
#>
param(
    [string]$EnvName      = "py311",
    [string]$PythonVer    = "3.11",
    [string]$TorchVer     = "2.14.1",
    [string]$TorchIndex   = "https://download.pytorch.org/whl/cu126",
    [string]$CudaVer      = "12.6.3"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# --- 관리자 승격 ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "관리자 권한으로 다시 실행합니다..."
    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -EnvName $EnvName -PythonVer $PythonVer -TorchVer $TorchVer -TorchIndex $TorchIndex -CudaVer $CudaVer"
    Start-Process powershell -Verb RunAs -ArgumentList $argList
    exit
}

$dl = Join-Path $env:TEMP "devsetup"
New-Item -ItemType Directory -Force -Path $dl | Out-Null
$miniforgeDir = Join-Path $env:USERPROFILE "miniforge3"

# --- Git 최신 설치파일 URL 조회 ---
Write-Host "[1/4] Git 최신 릴리스 조회..."
$rel = Invoke-RestMethod "https://api.github.com/repos/git-for-windows/git/releases/latest" -Headers @{ "User-Agent" = "devsetup" }
$gitUrl = ($rel.assets | Where-Object { $_.name -match '^Git-.*-64-bit\.exe$' } | Select-Object -First 1).browser_download_url

$items = @(
    @{ Name = "vscode";    Url = "https://update.code.visualstudio.com/latest/win32-x64/stable"; File = "vscode.exe";
       Args = "/VERYSILENT /NORESTART /MERGETASKS=!runcode,addcontextmenufiles,addcontextmenufolders,addtopath" },
    @{ Name = "git";       Url = $gitUrl; File = "git.exe";
       Args = "/VERYSILENT /NORESTART /NOCANCEL /SP-" },
    @{ Name = "miniforge"; Url = "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe"; File = "miniforge.exe";
       Args = "/InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /S /D=$miniforgeDir" },
    @{ Name = "cuda";      Url = "https://developer.download.nvidia.com/compute/cuda/$CudaVer/network_installers/cuda_${CudaVer}_windows_network.exe"; File = "cuda.exe";
       Args = "-s" }
)

# --- 병렬 다운로드 ---
Write-Host "[2/4] 4개 파일 병렬 다운로드 중..."
$jobs = foreach ($i in $items) {
    $out = Join-Path $dl $i.File
    Start-Job -Name $i.Name -ArgumentList $i.Url, $out -ScriptBlock {
        param($u, $o)
        $ProgressPreference = "SilentlyContinue"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing
    }
}
$jobs | Wait-Job | Out-Null
foreach ($j in $jobs) {
    if ($j.State -ne "Completed") {
        Write-Warning "다운로드 실패: $($j.Name) - $($j.ChildJobs[0].JobStateInfo.Reason.Message)"
    }
    Receive-Job $j -ErrorAction SilentlyContinue | Out-Null
}
$jobs | Remove-Job -Force

# --- 병렬 설치 ---
Write-Host "[3/4] 병렬 설치 중 (CUDA는 시간이 오래 걸립니다)..."
$procs = @{}
foreach ($i in $items) {
    $f = Join-Path $dl $i.File
    if (Test-Path $f) {
        $procs[$i.Name] = Start-Process -FilePath $f -ArgumentList $i.Args -PassThru
    } else {
        Write-Warning "$($i.Name) 설치파일이 없어 건너뜁니다."
    }
}
foreach ($k in $procs.Keys) {
    $procs[$k].WaitForExit()
    # 3010 = 설치 성공, 재부팅 필요
    Write-Host ("  {0}: 종료코드 {1}" -f $k, $procs[$k].ExitCode)
}

# --- conda 가상환경 + PyTorch ---
Write-Host "[4/4] conda 환경($EnvName, Python $PythonVer) 생성 및 PyTorch $TorchVer 설치..."
$conda = Join-Path $miniforgeDir "Scripts\conda.exe"
if (-not (Test-Path $conda)) { throw "conda를 찾을 수 없습니다: $conda (Miniforge 설치 실패)" }

& $conda create -n $EnvName "python=$PythonVer" -y
if ($LASTEXITCODE -ne 0) { throw "conda 환경 생성 실패" }

& $conda run -n $EnvName python -m pip install --upgrade pip
& $conda run -n $EnvName python -m pip install "torch==$TorchVer" --index-url $TorchIndex
if ($LASTEXITCODE -ne 0) {
    Write-Warning "torch==$TorchVer 설치 실패. 설치 가능한 버전 목록:"
    & $conda run -n $EnvName python -m pip index versions torch --index-url $TorchIndex
    exit 1
}

# conda를 PowerShell/cmd에서 쓸 수 있도록 초기화
& $conda init powershell cmd.exe | Out-Null

Write-Host "`n=== 검증 ==="
& $conda run -n $EnvName python -c "import torch; print('torch', torch.__version__, '| cuda', torch.version.cuda, '| available', torch.cuda.is_available())"
Write-Host "`n완료. PATH 반영을 위해 새 터미널을 열고, CUDA 드라이버/설치 반영을 위해 재부팅을 권장합니다."
Write-Host "사용: conda activate $EnvName"
