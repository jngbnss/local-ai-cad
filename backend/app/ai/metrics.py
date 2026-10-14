"""요청 단위 성능 측정.

Mock 결과와 실제 GPU 결과를 같은 구조로 남기되 `provider` 필드로 구분한다.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

_MIB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class InferenceMetrics:
    provider: str
    model_id: str
    device: str
    dtype: str
    load_seconds: float
    inference_seconds: float
    input_tokens: int
    output_tokens: int
    peak_vram_mib: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class Stopwatch:
    """경과 시간을 초 단위로 재는 컨텍스트 매니저."""

    __slots__ = ("_start", "seconds")

    def __init__(self) -> None:
        self._start = 0.0
        self.seconds = 0.0

    def __enter__(self) -> "Stopwatch":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.seconds = time.perf_counter() - self._start


def reset_peak_vram(device: str) -> None:
    """CUDA 최대 할당 통계를 초기화한다. CUDA가 아니면 아무 일도 하지 않는다."""
    if device != "cuda":
        return
    import torch

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def peak_vram_mib(device: str) -> float:
    """측정 구간의 최대 할당 VRAM(MiB). CUDA가 아니면 0.0."""
    if device != "cuda":
        return 0.0
    import torch

    if not torch.cuda.is_available():
        return 0.0
    return round(torch.cuda.max_memory_allocated() / _MIB, 1)
