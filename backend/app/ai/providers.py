"""ModelProvider 계약과 구현.

계약 규칙:
- `generate()` 는 기반 클래스가 소유하고 추론 lock을 건다. 구현체는 `_generate()` 만 쓴다.
  단일 프로세스에서 동시 생성이 2개가 되면 6~8GB VRAM에서 OOM이 나므로 불변식으로 강제한다.
- 모델 로드는 provider 인스턴스당 1회다. `load_count` 로 관찰 가능하게 둔다.
- Mock 은 `provider: "mock"` 을 남기며 GPU 성능 보고에 쓰지 않는다.
"""

from __future__ import annotations

import logging
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.ai.errors import (
    CudaUnavailableError,
    GpuOutOfMemoryError,
    ModelDownloadError,
    TorchNotInstalledError,
)
from app.ai.metrics import InferenceMetrics, Stopwatch, peak_vram_mib, reset_peak_vram
from app.config import Settings

logger = logging.getLogger(__name__)

_MOCK_REPLY = (
    "[mock] 이 응답은 모델을 로드하지 않고 생성한 고정 문자열입니다. "
    "애플리케이션 경로 점검 전용이며 GPU 성능 지표가 아닙니다."
)


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    metrics: InferenceMetrics


class ModelProvider(ABC):
    """추론 계약. 동시 실행 1개 불변식을 기반 클래스가 보장한다."""

    name: str

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.load_count = 0
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self.load_count > 0

    def generate(self, prompt: str) -> GenerationResult:
        if not prompt.strip():
            raise ValueError("prompt 가 비어 있습니다.")
        with self._lock:
            return self._generate(prompt)

    @abstractmethod
    def _generate(self, prompt: str) -> GenerationResult:
        """lock 을 획득한 상태에서 호출된다."""


class MockModelProvider(ModelProvider):
    """모델 다운로드 없이 CLI·측정·로그 경로를 점검한다."""

    name = "mock"

    def _generate(self, prompt: str) -> GenerationResult:
        with Stopwatch() as load_timer:
            if self.load_count == 0:
                self.load_count = 1

        with Stopwatch() as infer_timer:
            text = _MOCK_REPLY

        metrics = InferenceMetrics(
            provider=self.name,
            model_id=self.settings.model_id,
            device=self.settings.device,
            dtype=self.settings.dtype,
            load_seconds=round(load_timer.seconds, 4),
            inference_seconds=round(infer_timer.seconds, 4),
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            peak_vram_mib=0.0,
        )
        return GenerationResult(text=text, metrics=metrics)


class HuggingFaceModelProvider(ModelProvider):
    """tokenizer/model 을 1회 로드하고 이후 요청에서 재사용한다."""

    name = "huggingface"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._tokenizer = None
        self._model = None
        self._load_seconds = 0.0

    def _generate(self, prompt: str) -> GenerationResult:
        import torch

        load_seconds = self._ensure_loaded()
        settings = self.settings
        device = settings.device

        messages = [{"role": "user", "content": prompt}]
        rendered = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(rendered, return_tensors="pt").to(device)
        input_tokens = int(inputs["input_ids"].shape[-1])

        reset_peak_vram(device)
        try:
            with Stopwatch() as timer, torch.inference_mode():
                generated = self._model.generate(
                    **inputs,
                    max_new_tokens=settings.max_new_tokens,
                    do_sample=False,
                    pad_token_id=self._tokenizer.pad_token_id
                    or self._tokenizer.eos_token_id,
                )
        except torch.cuda.OutOfMemoryError as exc:
            peak = peak_vram_mib(device)
            raise GpuOutOfMemoryError(
                "생성 중 VRAM이 부족했습니다. 캐시를 비워 성공을 가장하지 않고 요청을 실패 처리합니다. "
                f"peak_vram_mib={peak}, max_new_tokens={settings.max_new_tokens}. "
                "LOCAL_AI_CAD_MAX_NEW_TOKENS 를 줄이거나 다른 GPU 프로세스를 종료하세요.",
                peak_vram_mib=peak,
                max_new_tokens=settings.max_new_tokens,
            ) from exc

        # 입력 토큰을 제외하고 새로 생성된 토큰만 디코딩한다.
        new_token_ids = generated[0][input_tokens:]
        text = self._tokenizer.decode(new_token_ids, skip_special_tokens=True)

        metrics = InferenceMetrics(
            provider=self.name,
            model_id=settings.model_id,
            device=device,
            dtype=settings.dtype,
            load_seconds=round(load_seconds, 3),
            inference_seconds=round(timer.seconds, 3),
            input_tokens=input_tokens,
            output_tokens=int(new_token_ids.shape[-1]),
            peak_vram_mib=peak_vram_mib(device),
        )
        return GenerationResult(text=text.strip(), metrics=metrics)

    def _ensure_loaded(self) -> float:
        """최초 1회만 실제 로드한다. 반환값은 이번 호출에서 쓴 로드 시간."""
        if self._model is not None:
            return 0.0

        settings = self.settings
        if settings.hf_home:
            os.environ["HF_HOME"] = settings.hf_home

        torch = _import_torch()
        if settings.device == "cuda" and not torch.cuda.is_available():
            raise CudaUnavailableError(
                "LOCAL_AI_CAD_DEVICE=cuda 인데 torch.cuda.is_available() 가 False 입니다. "
                f"설치된 torch={torch.__version__}, torch.version.cuda={torch.version.cuda}. "
                "CPU로 자동 전환하지 않습니다. `local-ai-cad diagnose` 로 환경을 먼저 확인하세요."
            )

        from transformers import AutoModelForCausalLM, AutoTokenizer

        dtype = getattr(torch, settings.dtype)
        logger.info(
            "모델 로드 시작: model_id=%s device=%s dtype=%s",
            settings.model_id,
            settings.device,
            settings.dtype,
        )
        try:
            with Stopwatch() as timer:
                tokenizer = AutoTokenizer.from_pretrained(
                    settings.model_id, trust_remote_code=False
                )
                model = AutoModelForCausalLM.from_pretrained(
                    settings.model_id,
                    dtype=dtype,
                    trust_remote_code=False,
                )
                model.to(settings.device)
                model.eval()
        except torch.cuda.OutOfMemoryError as exc:
            peak = peak_vram_mib(settings.device)
            raise GpuOutOfMemoryError(
                f"모델 로드 중 VRAM이 부족했습니다. peak_vram_mib={peak}. "
                "다른 GPU 프로세스를 종료하거나 더 작은 모델을 사용하세요.",
                peak_vram_mib=peak,
                max_new_tokens=settings.max_new_tokens,
            ) from exc
        except (OSError, ValueError) as exc:
            raise ModelDownloadError(
                f"모델 '{settings.model_id}' 를 가져오지 못했습니다. "
                "네트워크, 디스크 여유 공간, 모델 ID를 확인하세요. 추론 실패와는 다른 원인입니다. "
                f"원인: {exc}"
            ) from exc

        self._tokenizer = tokenizer
        self._model = model
        self._load_seconds = timer.seconds
        self.load_count += 1
        logger.info("모델 로드 완료: %.3f초", timer.seconds)
        return timer.seconds


def _import_torch():
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - 설치된 환경에서는 발생하지 않는다
        raise TorchNotInstalledError(
            "PyTorch가 설치되지 않았습니다. `.venv` 활성화 후 공식 CUDA 휠을 설치하세요."
        ) from exc
    return torch


def build_provider(settings: Settings, *, mock: bool) -> ModelProvider:
    return MockModelProvider(settings) if mock else HuggingFaceModelProvider(settings)
