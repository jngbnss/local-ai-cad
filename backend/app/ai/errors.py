"""오류 경계.

환경 오류·다운로드 오류·OOM·구성 오류를 각각 다른 타입으로 분리한다.
하나로 뭉치면 "GPU가 없어서 실패한 건지 모델이 없어서 실패한 건지"를
사용자가 구분할 수 없다. 종료 코드도 타입별로 다르게 매핑한다.
"""

from __future__ import annotations


class ProviderError(Exception):
    """추론 계층의 기반 예외."""

    exit_code = 1


class CudaUnavailableError(ProviderError):
    """CUDA를 요구했지만 PyTorch가 사용할 수 없다."""

    exit_code = 3


class TorchNotInstalledError(ProviderError):
    """PyTorch가 설치되지 않았다."""

    exit_code = 3


class ModelDownloadError(ProviderError):
    """모델 가중치/토크나이저를 받아오지 못했다. 추론 실패와 구분한다."""

    exit_code = 4


class GpuOutOfMemoryError(ProviderError):
    """생성 중 VRAM이 부족했다. 캐시를 비워 성공을 가장하지 않는다."""

    exit_code = 5

    def __init__(self, message: str, peak_vram_mib: float, max_new_tokens: int) -> None:
        super().__init__(message)
        self.peak_vram_mib = peak_vram_mib
        self.max_new_tokens = max_new_tokens
