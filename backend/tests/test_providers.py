import threading

import pytest
import torch

from app.ai.metrics import InferenceMetrics
from app.ai.providers import (
    GenerationResult,
    HuggingFaceModelProvider,
    MockModelProvider,
    ModelProvider,
    build_provider,
)
from app.config import Settings

CPU_SETTINGS = Settings(device="cpu", max_new_tokens=8)


def test_mock_is_labelled_and_reports_no_gpu_usage():
    """Mock 결과가 GPU 성능 보고로 오인되면 Phase 1 완료 판정이 거짓이 된다."""
    result = MockModelProvider(CPU_SETTINGS).generate("책상 치수 알려줘")

    assert result.metrics.provider == "mock"
    assert result.metrics.peak_vram_mib == 0.0
    assert "mock" in result.text.lower()


def test_real_provider_uses_a_different_provider_label():
    assert HuggingFaceModelProvider(CPU_SETTINGS).name == "huggingface"
    assert MockModelProvider(CPU_SETTINGS).name != HuggingFaceModelProvider(CPU_SETTINGS).name


def test_build_provider_selects_implementation():
    assert isinstance(build_provider(CPU_SETTINGS, mock=True), MockModelProvider)
    assert isinstance(build_provider(CPU_SETTINGS, mock=False), HuggingFaceModelProvider)


def test_blank_prompt_is_rejected():
    with pytest.raises(ValueError):
        MockModelProvider(CPU_SETTINGS).generate("   ")


class _ConcurrencyProbe(ModelProvider):
    """동시 실행 수를 관측하는 provider."""

    name = "probe"

    def __init__(self, settings):
        super().__init__(settings)
        self.active = 0
        self.max_active = 0
        self._guard = threading.Lock()

    def _generate(self, prompt):
        with self._guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            threading.Event().wait(0.02)
        finally:
            with self._guard:
                self.active -= 1
        metrics = InferenceMetrics(
            provider=self.name,
            model_id=self.settings.model_id,
            device=self.settings.device,
            dtype=self.settings.dtype,
            load_seconds=0.0,
            inference_seconds=0.0,
            input_tokens=0,
            output_tokens=0,
            peak_vram_mib=0.0,
        )
        return GenerationResult(text="", metrics=metrics)


def test_inference_lock_serialises_concurrent_requests():
    """6~8GB VRAM에서 동시 생성 2개는 OOM 경로다. 불변식으로 막는다."""
    provider = _ConcurrencyProbe(CPU_SETTINGS)
    threads = [threading.Thread(target=provider.generate, args=("prompt",)) for _ in range(6)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert provider.max_active == 1


class _StubTokenizer:
    """chat template 과 토크나이즈를 흉내내는 최소 구현."""

    pad_token_id = 0
    eos_token_id = 0

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        return f"<|user|>{messages[0]['content']}<|assistant|>"

    def __call__(self, text, return_tensors):
        return _Batch({"input_ids": torch.tensor([[11, 12, 13, 14]])})

    def decode(self, token_ids, skip_special_tokens):
        return " ".join(str(int(t)) for t in token_ids)


class _Batch(dict):
    def to(self, device):
        return self


class _StubModel:
    def generate(self, input_ids, max_new_tokens, do_sample, pad_token_id):
        # 입력 4토큰 뒤에 새 토큰 3개를 이어붙인 형태를 반환한다.
        new_tokens = torch.tensor([[91, 92, 93]])
        return torch.cat([input_ids, new_tokens], dim=-1)


def test_output_excludes_input_tokens():
    """입력 토큰을 자르지 않으면 프롬프트가 응답에 그대로 섞여 나온다."""
    provider = HuggingFaceModelProvider(CPU_SETTINGS)
    provider._tokenizer = _StubTokenizer()
    provider._model = _StubModel()
    provider.load_count = 1

    result = provider.generate("책상")

    assert result.text == "91 92 93"
    assert result.metrics.input_tokens == 4
    assert result.metrics.output_tokens == 3


def test_second_request_does_not_reload_the_model():
    provider = HuggingFaceModelProvider(CPU_SETTINGS)
    provider._tokenizer = _StubTokenizer()
    provider._model = _StubModel()
    provider.load_count = 1

    provider.generate("첫 번째")
    second = provider.generate("두 번째")

    assert provider.load_count == 1
    assert second.metrics.load_seconds == 0.0
