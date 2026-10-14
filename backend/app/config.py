"""환경변수 기반 구성.

구성 오류는 추론 실패와 구분되어야 하므로 전용 예외로 즉시 보고한다.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_DEVICE = "cuda"
DEFAULT_DTYPE = "float16"
DEFAULT_MAX_NEW_TOKENS = 512
DEFAULT_LOG_LEVEL = "INFO"

SUPPORTED_DEVICES = ("cuda", "cpu")
SUPPORTED_DTYPES = ("float16", "bfloat16", "float32")
SUPPORTED_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# Hugging Face 저장소 ID는 `owner/name` 형태다. 공백이나 경로 구분자가 섞이면
# 다운로드 단계에서야 실패하므로 구성 단계에서 먼저 거른다.
_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


class ConfigError(Exception):
    """환경변수 값이 유효하지 않다."""


@dataclass(frozen=True, slots=True)
class Settings:
    model_id: str = DEFAULT_MODEL_ID
    device: str = DEFAULT_DEVICE
    dtype: str = DEFAULT_DTYPE
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS
    hf_home: str | None = None
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env

        model_id = _text(source, "LOCAL_AI_CAD_MODEL_ID", DEFAULT_MODEL_ID)
        if not _MODEL_ID_PATTERN.match(model_id):
            raise ConfigError(
                f"LOCAL_AI_CAD_MODEL_ID 형식이 올바르지 않습니다: {model_id!r}. "
                "`owner/name` 형태여야 합니다. 예: Qwen/Qwen2.5-1.5B-Instruct"
            )

        device = _choice(source, "LOCAL_AI_CAD_DEVICE", DEFAULT_DEVICE, SUPPORTED_DEVICES)
        dtype = _choice(source, "LOCAL_AI_CAD_DTYPE", DEFAULT_DTYPE, SUPPORTED_DTYPES)
        log_level = _choice(
            source, "LOCAL_AI_CAD_LOG_LEVEL", DEFAULT_LOG_LEVEL, SUPPORTED_LOG_LEVELS, upper=True
        )

        raw_tokens = _text(source, "LOCAL_AI_CAD_MAX_NEW_TOKENS", str(DEFAULT_MAX_NEW_TOKENS))
        try:
            max_new_tokens = int(raw_tokens)
        except ValueError as exc:
            raise ConfigError(
                f"LOCAL_AI_CAD_MAX_NEW_TOKENS 는 정수여야 합니다: {raw_tokens!r}"
            ) from exc
        if max_new_tokens < 1:
            raise ConfigError(
                f"LOCAL_AI_CAD_MAX_NEW_TOKENS 는 1 이상이어야 합니다: {max_new_tokens}"
            )

        hf_home = _text(source, "LOCAL_AI_CAD_HF_HOME", "") or None

        return cls(
            model_id=model_id,
            device=device,
            dtype=dtype,
            max_new_tokens=max_new_tokens,
            hf_home=hf_home,
            log_level=log_level,
        )


def _text(source: Mapping[str, str], key: str, default: str) -> str:
    value = source.get(key)
    if value is None:
        return default
    return value.strip()


def _choice(
    source: Mapping[str, str],
    key: str,
    default: str,
    allowed: tuple[str, ...],
    *,
    upper: bool = False,
) -> str:
    value = _text(source, key, default)
    value = value.upper() if upper else value.lower()
    if value not in allowed:
        raise ConfigError(f"{key} 는 {allowed} 중 하나여야 합니다: {value!r}")
    return value
