"""DesignSpec 생성과 검증 루프.

핵심 원칙: 유효하지 않은 출력은 **조용히 기본값으로 채우지 않는다**.
최대 N회 재시도하고, 그래도 안 되면 시도별 실패 원인을 담아 명시적으로 실패한다.
실패를 숨기면 Phase 3의 산출률 측정이 거짓이 되고 Phase 4가 쓰레기를 받는다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.ai.providers import ModelProvider
from app.design.prompt import build_messages, build_revision_messages, extract_json_object
from app.design.schema import DesignSpec

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3


class SpecGenerationError(Exception):
    """재시도를 모두 쓰고도 유효한 DesignSpec 을 얻지 못했다."""

    exit_code = 8

    def __init__(self, message: str, attempts: list["SpecAttempt"]) -> None:
        super().__init__(message)
        self.attempts = attempts


@dataclass(frozen=True, slots=True)
class SpecAttempt:
    index: int
    failure: str | None  # None 이면 성공
    raw_text: str

    @property
    def ok(self) -> bool:
        return self.failure is None


@dataclass(slots=True)
class SpecResult:
    spec: DesignSpec
    attempts: list[SpecAttempt] = field(default_factory=list)
    metrics: object = None

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)


def parse_spec(text: str) -> DesignSpec:
    """모델 출력 문자열 → DesignSpec. 실패 원인을 구분해 올린다."""
    payload = extract_json_object(text)
    if payload is None:
        raise ValueError("출력에서 JSON 객체를 찾지 못했습니다.")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 파싱 실패: {exc.msg} (pos {exc.pos})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON 최상위가 객체가 아닙니다: {type(data).__name__}")
    try:
        return DesignSpec.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "<root>"
        raise ValueError(f"스키마 위반 ({exc.error_count()}건): {location} — {first['msg']}") from exc


def generate_spec(
    provider: ModelProvider,
    user_prompt: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> SpecResult:
    """프롬프트 → DesignSpec. 검증 실패 시 재시도한다."""
    return _run_loop(provider, build_messages(user_prompt), max_attempts, "생성")


def revise_spec(
    provider: ModelProvider,
    current: DesignSpec,
    instruction: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> SpecResult:
    """기존 명세 + 수정 지시 → 새 DesignSpec."""
    return _run_loop(
        provider, build_revision_messages(current, instruction), max_attempts, "수정"
    )


def _run_loop(
    provider: ModelProvider,
    messages: list[dict[str, str]],
    max_attempts: int,
    label: str,
) -> SpecResult:
    if max_attempts < 1:
        raise ValueError("max_attempts 는 1 이상이어야 합니다.")

    attempts: list[SpecAttempt] = []
    last_metrics = None

    for index in range(1, max_attempts + 1):
        result = provider.generate_chat(messages)
        last_metrics = result.metrics
        try:
            spec = parse_spec(result.text)
        except ValueError as exc:
            attempts.append(SpecAttempt(index=index, failure=str(exc), raw_text=result.text))
            logger.warning("DesignSpec %s 시도 %d 실패: %s", label, index, exc)
            messages = [
                *messages,
                {"role": "assistant", "content": result.text},
                {
                    "role": "user",
                    "content": (
                        f"위 JSON은 검증에 실패했다: {exc}. "
                        "오류가 난 필드만 바로잡되 전체 JSON 객체 하나를 다시 출력해라. "
                        "설명과 코드펜스는 쓰지 마라."
                    ),
                },
            ]
            continue

        attempts.append(SpecAttempt(index=index, failure=None, raw_text=result.text))
        return SpecResult(spec=spec, attempts=attempts, metrics=last_metrics)

    reasons = "; ".join(f"[{a.index}] {a.failure}" for a in attempts)
    raise SpecGenerationError(
        f"{max_attempts}회 시도했지만 유효한 DesignSpec 을 얻지 못했습니다. {reasons}",
        attempts=attempts,
    )
