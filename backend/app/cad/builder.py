"""DesignSpec → 실제 3D 솔리드.

LLM 이 만든 Python 코드를 실행하지 않는다는 원칙의 실행부다. 여기서 소비하는 것은
검증을 통과한 선언적 `DesignSpec` 뿐이고, CadQuery 호출은 전부 이 모듈이 직접 쓴다.

좌표 규약은 스키마와 동일하게 **바닥면 중심**이다. `Part.position` 의 x·y 는 부품
중심, z 는 바닥 높이다. CadQuery 2.8 의 `centered=(True, True, False)` 가 정확히 이
규약과 일치한다(실측: `box(10, 20, 30, centered=(True, True, False))` 의 바운딩 박스는
x -5~5, y -10~10, z 0~30). 그래서 추가 보정 없이 `translate(position)` 만 하면 된다.

불리언 결과가 비는 경우(예: 큰 부품으로 작은 부품을 통째로 cut)를 그대로 흘려보내지
않는다. OCP 는 이때 예외 대신 빈 Compound 를 돌려주므로, 어느 연산이 솔리드를
없앴는지 아는 이 지점에서 `BooleanFailedError` 로 끊는다.
"""

from __future__ import annotations

import cadquery as cq

from app.cad.errors import BooleanFailedError
from app.design.schema import BooleanOp, DesignSpec, Operation, Part, Primitive


def build_solid(spec: DesignSpec) -> cq.Workplane:
    """명세를 솔리드 하나로 만든다.

    부품을 모두 만든 뒤 `operations` 를 순서대로 적용하고, 어느 연산에도 소비되지
    않고 남은 솔리드를 마지막에 union 한다. `operations` 가 비어 있으면 모든 부품을
    union 한 결과가 되고, 부품이 하나면 그 부품이 그대로 나온다.
    """
    solids: dict[str, cq.Workplane] = {}
    for part in spec.parts:
        solids[part.id] = _build_part(part)

    for index, operation in enumerate(spec.operations):
        _apply_operation(solids, index, operation)

    return _merge_remaining(solids)


def _build_part(part: Part) -> cq.Workplane:
    """부품 하나를 바닥면 중심 규약으로 만든다."""
    dims = part.dimensions
    position = (part.position.x, part.position.y, part.position.z)
    try:
        if part.primitive is Primitive.BOX:
            shape = cq.Workplane("XY").box(
                float(dims.x), float(dims.y), float(dims.z), centered=(True, True, False)
            )
        else:
            shape = cq.Workplane("XY").cylinder(
                float(dims.height), float(dims.radius), centered=(True, True, False)
            )
        return shape.translate(position)
    except Exception as exc:  # noqa: BLE001 - OCP 예외 타입이 공개 계약이 아니다.
        raise BooleanFailedError(
            f"부품 '{part.id}'({part.primitive.value}) 를 만들지 못했습니다: {exc}"
        ) from exc


def _apply_operation(solids: dict[str, cq.Workplane], index: int, operation: Operation) -> None:
    """연산 하나를 적용하고 결과를 첫 target id 에 다시 바인딩한다."""
    head, *rest = operation.targets
    label = f"operations[{index}] {operation.type.value}{operation.targets}"

    consumed = [target for target in operation.targets if target not in solids]
    if consumed:
        raise BooleanFailedError(
            f"{label}: 부품 {consumed} 는 앞선 연산에 이미 소비되어 참조할 수 없습니다."
        )

    result = solids[head]
    for target in rest:
        try:
            if operation.type is BooleanOp.UNION:
                result = result.union(solids[target])
            else:
                result = result.cut(solids[target])
        except Exception as exc:  # noqa: BLE001 - OCP 예외 타입이 공개 계약이 아니다.
            raise BooleanFailedError(
                f"{label}: '{head}' 와 '{target}' 의 "
                f"{operation.type.value} 연산이 실패했습니다: {exc}"
            ) from exc

        if not _solid_count(result, label):
            raise BooleanFailedError(
                f"{label}: '{target}' 를 {operation.type.value} 한 뒤 솔리드가 남지 않았습니다."
            )

    solids[head] = result
    for target in rest:
        del solids[target]


def _merge_remaining(solids: dict[str, cq.Workplane]) -> cq.Workplane:
    """연산에 소비되지 않고 남은 솔리드를 하나로 합친다."""
    remaining = list(solids.items())
    merged_id, merged = remaining[0]
    for target, solid in remaining[1:]:
        try:
            merged = merged.union(solid)
        except Exception as exc:  # noqa: BLE001 - OCP 예외 타입이 공개 계약이 아니다.
            raise BooleanFailedError(
                f"남은 부품 '{merged_id}' 와 '{target}' 의 최종 결합이 실패했습니다: {exc}"
            ) from exc
        merged_id = f"{merged_id}+{target}"
    return merged


def _solid_count(solid: cq.Workplane, label: str) -> int:
    """결과에 들어 있는 솔리드 개수. 빈 결과를 조용히 넘기지 않기 위한 확인용."""
    try:
        return len(solid.val().Solids())
    except Exception as exc:  # noqa: BLE001 - OCP 예외 타입이 공개 계약이 아니다.
        raise BooleanFailedError(f"{label}: 연산 결과를 읽지 못했습니다: {exc}") from exc
