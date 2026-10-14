"""기하 계층의 오류 경계.

LLM 실패(`app.ai.errors.ProviderError`)와 기하 실패를 절대 섞지 않는다.
"모델이 헛소리를 했다"와 "모델 말은 맞는데 OCP 가 불리언을 못 했다"는
사용자가 취할 행동이 완전히 다르기 때문이다(프롬프트 재시도 vs 치수 수정).
종료 코드도 추론 계층(1,3,4,5)과 겹치지 않게 6번대를 쓴다.
"""

from __future__ import annotations


class GeometryError(Exception):
    """기하 생성·검증·내보내기 계층의 기반 예외."""

    exit_code = 6


class SolidInvalidError(GeometryError):
    """만들어진 솔리드가 닫혀 있지 않거나 부피가 0이다."""

    exit_code = 7


class BooleanFailedError(GeometryError):
    """불리언 연산이 실패했거나 결과가 비었다. 어떤 연산인지 메시지에 담는다."""

    exit_code = 8


class ExportError(GeometryError):
    """STL/STEP 파일을 쓰지 못했거나 빈 파일이 나왔다."""

    exit_code = 9
