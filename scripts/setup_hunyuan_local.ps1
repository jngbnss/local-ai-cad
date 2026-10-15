param(
    [string]$InstallRoot = (Join-Path $PSScriptRoot "..\.local\hunyuan3d")
)

$ErrorActionPreference = "Stop"
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$Repo = Join-Path $InstallRoot "Hunyuan3D-2"
$Venv = Join-Path $InstallRoot ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
if (-not (Test-Path (Join-Path $Repo ".git"))) {
    if (Test-Path $Repo) {
        throw "불완전한 설치 경로가 있습니다: $Repo. 해당 경로를 확인한 뒤 다시 실행하세요."
    }
    git clone --depth 1 --filter=blob:none https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git $Repo
    if ($LASTEXITCODE -ne 0) { throw "Hunyuan3D-2 clone 실패" }
}
if (-not (Test-Path $Python)) {
    python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Python 가상환경 생성 실패" }
}

& $Python -m pip install --upgrade pip
& $Python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
& $Python -m pip install diffusers==0.31.0 transformers==4.46.3 accelerate huggingface_hub einops omegaconf tqdm opencv-python numpy scikit-image trimesh pygltflib pymeshlab
& $Python -c "import torch; assert torch.cuda.is_available(), 'CUDA GPU 없음'; print('GPU:', torch.cuda.get_device_name(0))"
if ($LASTEXITCODE -ne 0) { throw "로컬 Hunyuan 환경 검증 실패" }

Write-Host "설치 완료"
Write-Host "실행:"
Write-Host "& '$Python' '$PSScriptRoot\hunyuan_local_server.py' --repo '$Repo'"
