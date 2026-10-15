"""DesignSpec 생성용 프롬프트.

1.5B 모델은 스키마 준수가 약하다. "프롬프트를 잘 쓴다"에 기대지 않고
(1) 출력 형식을 극단적으로 좁히고 (2) few-shot 예제를 주고
(3) validator.py 의 재시도 루프로 받친다. 세 개가 한 세트다.

템플릿을 코드 상수가 아니라 이 모듈에 모아 둔 이유는 Phase 3 평가에서
프롬프트만 바꿔가며 산출률을 비교하기 위함이다.
"""

from __future__ import annotations

import json
import re

from app.design.schema import DesignSpec

SYSTEM_PROMPT = """너는 CAD 설계 명세를 JSON으로 만드는 도구다.
반드시 JSON 객체 하나만 출력한다. 설명, 인사, 코드펜스, 주석을 쓰지 않는다.

규칙:
- 모든 길이 단위는 밀리미터(mm) 정수다. cm 입력은 10을 곱하고, m 입력은 1000을 곱한다.
- position 은 부품의 바닥면 중심이다. x,y 는 중심 좌표, z 는 바닥 높이다.
- primitive 는 "box" 또는 "cylinder" 만 쓴다.
- 단순 직육면체·판·기둥은 면으로 분해하지 말고 parts 원소 하나로 만든다.
- box 는 dimensions 에 x,y,z 를 쓴다. cylinder 는 radius,height 를 쓴다. 섞지 않는다.
- id 는 영문 소문자와 밑줄만 쓴다.
- operations 는 부품을 합치는 union 또는 빼는 cut 이다. targets 는 2개 이상이다.
- part는 반드시 {"id","primitive","dimensions","position"} 네 필드를 가진다. radius나 height를 part 바로 아래 쓰지 않는다.
- 부품이 하나면 operations는 반드시 []다. 여러 부품 결합은 {"type":"union","targets":["id1","id2"]} 형식만 쓴다. target, shape, offset 필드는 금지한다.
- 모든 part id는 서로 달라야 한다. 다리가 여러 개면 leg_fl, leg_fr처럼 각각 이름을 붙인다.
- 치수를 모르면 가구 표준값을 쓴다. 책상 높이 750, 상판 두께 25, 다리 두께 50.
- JSON은 공백과 줄바꿈을 최소화해 짧게 출력한다.

출력 형식:
{"schema_version":"2.0","unit":"mm","name":"<영문 소문자 이름>","parts":[...],"operations":[...]}"""

FEW_SHOT_USER = "가로 80cm 세로 40cm 높이 75cm 사이드 테이블 만들어줘"

FEW_SHOT_ASSISTANT = json.dumps(
    {
        "schema_version": "2.0",
        "unit": "mm",
        "name": "side_table",
        "parts": [
            {
                "id": "top",
                "primitive": "box",
                "dimensions": {"x": 800, "y": 400, "z": 25},
                "position": {"x": 0, "y": 0, "z": 725},
            },
            {
                "id": "leg_fl",
                "primitive": "box",
                "dimensions": {"x": 50, "y": 50, "z": 725},
                "position": {"x": -350, "y": -150, "z": 0},
            },
            {
                "id": "leg_fr",
                "primitive": "box",
                "dimensions": {"x": 50, "y": 50, "z": 725},
                "position": {"x": 350, "y": -150, "z": 0},
            },
            {
                "id": "leg_bl",
                "primitive": "box",
                "dimensions": {"x": 50, "y": 50, "z": 725},
                "position": {"x": -350, "y": 150, "z": 0},
            },
            {
                "id": "leg_br",
                "primitive": "box",
                "dimensions": {"x": 50, "y": 50, "z": 725},
                "position": {"x": 350, "y": 150, "z": 0},
            },
        ],
        "operations": [
            {"type": "union", "targets": ["top", "leg_fl", "leg_fr", "leg_bl", "leg_br"]}
        ],
    },
    ensure_ascii=False,
)


def build_messages(user_prompt: str) -> list[dict[str, str]]:
    """chat template 에 넣을 메시지 목록."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FEW_SHOT_USER},
        {"role": "assistant", "content": FEW_SHOT_ASSISTANT},
        {"role": "user", "content": user_prompt},
    ]


def build_revision_messages(current: DesignSpec, instruction: str) -> list[dict[str, str]]:
    """기존 명세를 보존하면서 일부만 고치게 한다.

    매번 전체를 다시 쓰게 하면 1.5B 모델은 언급하지 않은 필드를 날린다.
    그래서 현재 명세를 그대로 주고 "바꾸라고 한 것만 바꿔라"를 못 박는다.
    """
    current_json = current.model_dump_json()
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "아래는 현재 설계 명세다.\n"
                f"{current_json}\n\n"
                f"수정 지시: {instruction}\n\n"
                "지시에 해당하는 값만 바꾸고 나머지 부품, id, 치수, 위치, operations 는 "
                "그대로 유지한 전체 JSON 을 출력한다."
            ),
        },
    ]


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json_object(text: str) -> str | None:
    """모델 출력에서 JSON 객체 하나를 떼어낸다.

    1.5B 모델은 지시해도 코드펜스나 서론을 붙인다. 파싱 단계에서 관대하게 받고,
    스키마 검증은 엄격하게 한다. 둘을 섞으면 "형식 때문에 실패"와
    "내용 때문에 실패"를 구분할 수 없다.
    """
    fenced = _FENCE.search(text)
    candidate = fenced.group(1) if fenced else text

    start = candidate.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(candidate)):
        char = candidate[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return candidate[start : index + 1]
    return None
