"""생성된 솔리드가 명세대로인지 측정한다.

"파일이 나왔다"는 성공의 증거가 아니다. 닫힌 솔리드인지, 부피가 실제로 있는지,
바운딩 박스가 명세와 맞는지를 숫자로 확인한다.

역할 분리: 솔리드 자체가 망가진 경우(열린 형상·부피 0)는 더 진행할 의미가 없으므로
`SolidInvalidError` 로 끊는다. 반면 치수가 어긋난 것은 "틀렸다"가 아니라 "측정 결과"다.
재생성할지 사용자에게 보여줄지는 호출자가 정하므로 `within_tolerance: False` 로
보고만 하고 예외를 던지지 않는다.
"""

from __future__ import annotations

from typing import Any

import cadquery as cq

from app.cad.errors import SolidInvalidError
from app.design.schema import BooleanOp, DesignSpec

# 0.5mm. 가구 규모(수백~수천 mm)에서 OCP 의 수치 오차보다 훨씬 크고,
# 사람이 알아챌 수 있는 설계 오류보다는 훨씬 작은 값이다.
TOLERANCE_MM = 0.5


def validate_solid(solid: cq.Workplane, spec: DesignSpec) -> dict[str, Any]:
    """솔리드를 실측해 검증 결과 dict 를 돌려준다.

    반환 키: `is_valid`, `volume_mm3`, `bounding_box_mm`, `expected_bounding_box_mm`,
    `within_tolerance`, `tolerance_mm`.
    """
    shape = _shape_of(solid)

    try:
        is_valid = bool(shape.isValid())
        volume = float(shape.Volume())
    except Exception as exc:  # noqa: BLE001 - OCP 예외 타입이 공개 계약이 아니다.
        raise SolidInvalidError(f"솔리드를 측정하지 못했습니다: {exc}") from exc

    if not is_valid or volume <= 0.0:
        raise SolidInvalidError(
            f"솔리드가 유효하지 않습니다 (is_valid={is_valid}, volume_mm3={volume}). "
            "닫힌 형상이 아니거나 불리언 결과가 비었습니다."
        )

    try:
        box = shape.BoundingBox()
        measured = (box.xlen, box.ylen, box.zlen)
    except Exception as exc:  # noqa: BLE001 - OCP 예외 타입이 공개 계약이 아니다.
        raise SolidInvalidError(f"바운딩 박스를 측정하지 못했습니다: {exc}") from exc

    expected = spec.bounding_box_mm()
    has_cut = any(operation.type is BooleanOp.CUT for operation in spec.operations)
    within = _within_tolerance(measured, expected, upper_bound_only=has_cut)

    return {
        "is_valid": is_valid,
        "volume_mm3": volume,
        "bounding_box_mm": [float(value) for value in measured],
        "expected_bounding_box_mm": [float(value) for value in expected],
        "within_tolerance": within,
        "tolerance_mm": TOLERANCE_MM,
    }


def _within_tolerance(
    measured: tuple[float, float, float],
    expected: tuple[float, float, float],
    *,
    upper_bound_only: bool,
) -> bool:
    """치수 비교.

    `spec.bounding_box_mm()` 은 union 기준 상한이다. cut 이 있으면 실제 형상이 더
    작아질 수 있으므로 상한만 본다. cut 이 없으면 양방향으로 본다.
    """
    for actual, target in zip(measured, expected, strict=True):
        if actual > target + TOLERANCE_MM:
            return False
        if not upper_bound_only and actual < target - TOLERANCE_MM:
            return False
    return True


def _shape_of(solid: cq.Workplane) -> cq.Shape:
    try:
        return solid.val()
    except Exception as exc:  # noqa: BLE001 - OCP 예외 타입이 공개 계약이 아니다.
        raise SolidInvalidError(f"솔리드가 비어 있습니다: {exc}") from exc
