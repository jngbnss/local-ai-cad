"""읽기 전용 GPU/런타임 진단.

추론을 시도하지 않고 환경만 보고한다. CUDA가 없어도 예외 없이 사실을 반환해야
사용자가 원인을 볼 수 있다. 단 PyTorch 자체가 없으면 진단이 불가능하므로 실패한다.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys

from app.ai.errors import TorchNotInstalledError

_MIB = 1024 * 1024


def collect_diagnostics() -> dict[str, object]:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - 설치된 환경에서는 발생하지 않는다
        raise TorchNotInstalledError(
            "PyTorch가 설치되지 않았습니다. `.venv` 활성화 후 "
            "`python -m pip install torch --index-url https://download.pytorch.org/whl/cu130` "
            "를 실행하세요."
        ) from exc

    cuda_available = torch.cuda.is_available()
    report: dict[str, object] = {
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": cuda_available,
        "device_name": None,
        "device_capability": None,
        "total_vram_mib": None,
        "driver_version": _driver_version(),
    }

    if cuda_available:
        props = torch.cuda.get_device_properties(0)
        report["device_name"] = props.name
        report["device_capability"] = f"{props.major}.{props.minor}"
        report["total_vram_mib"] = round(props.total_memory / _MIB)
    else:
        report["cuda_unavailable_hint"] = (
            "torch.cuda.is_available() 가 False 입니다. CPU 전용 휠이 설치됐거나 "
            "드라이버가 인식되지 않았습니다. torch_version 의 `+cuXXX` 접미사와 "
            "driver_version 을 함께 확인하세요."
        )

    return report


def _driver_version() -> str | None:
    """nvidia-smi 로 드라이버 버전을 읽는다. 없으면 None."""
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    first = result.stdout.strip().splitlines()
    return first[0].strip() if first else None
