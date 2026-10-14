"""DesignSpec — LLM 출력과 CAD 입력 사이의 유일한 계약.

불변 규칙 (docs/roadmap.md §6):
- 단위는 항상 mm. 사용자 입력의 cm/inch 는 이 계층 진입 전에 정규화한다.
- `Part.id` 는 Phase 6 수정 지시가 부품을 지목하는 핸들이다. 재생성해도 유지한다.
- `schema_version` 은 이력 호환성의 근거다. 처음부터 넣는다.

LLM 이 만든 Python 코드를 실행하지 않는다. LLM 은 이 선언적 구조만 만들고,
CadQuery 호출은 우리 코드가 한다.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"

# 물리적으로 의미 있는 범위. 책상·선반 같은 가구 규모를 가정한다.
MIN_DIMENSION_MM = 0.1
MAX_DIMENSION_MM = 10_000.0


class Primitive(StrEnum):
    BOX = "box"
    CYLINDER = "cylinder"


class BooleanOp(StrEnum):
    UNION = "union"
    CUT = "cut"


class Vec3(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Dimensions(BaseModel):
    """박스는 x·y·z, 실린더는 radius·height 를 쓴다."""

    model_config = ConfigDict(extra="forbid")

    x: float | None = None
    y: float | None = None
    z: float | None = None
    radius: float | None = None
    height: float | None = None

    @field_validator("x", "y", "z", "radius", "height")
    @classmethod
    def _positive_and_bounded(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < MIN_DIMENSION_MM:
            raise ValueError(f"치수는 {MIN_DIMENSION_MM}mm 이상이어야 합니다: {value}")
        if value > MAX_DIMENSION_MM:
            raise ValueError(f"치수는 {MAX_DIMENSION_MM}mm 이하여야 합니다: {value}")
        return value


class Part(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    primitive: Primitive
    """부품 하나.

    `position` 은 **바닥면 중심** 좌표다. x·y 는 부품 중심, z 는 바닥 높이를 뜻한다.
    가구는 바닥에 놓이므로 이 규약이 "다리 높이 725mm 위에 상판" 같은 배치를
    음수 좌표 없이 표현한다. Phase 4 builder 와 `bounding_box_mm()` 이 같은 규약을 쓴다.
    """

    dimensions: Dimensions
    position: Vec3 = Field(default_factory=Vec3)

    @model_validator(mode="after")
    def _dimensions_match_primitive(self) -> "Part":
        dims = self.dimensions
        if self.primitive is Primitive.BOX:
            missing = [axis for axis in ("x", "y", "z") if getattr(dims, axis) is None]
            if missing:
                raise ValueError(f"box 부품 '{self.id}' 에 {missing} 치수가 없습니다.")
            if dims.radius is not None or dims.height is not None:
                raise ValueError(f"box 부품 '{self.id}' 에 radius/height 를 쓸 수 없습니다.")
        else:
            if dims.radius is None or dims.height is None:
                raise ValueError(
                    f"cylinder 부품 '{self.id}' 에는 radius 와 height 가 모두 필요합니다."
                )
            if any(getattr(dims, axis) is not None for axis in ("x", "y", "z")):
                raise ValueError(f"cylinder 부품 '{self.id}' 에 x/y/z 를 쓸 수 없습니다.")
        return self

    def bounding_size(self) -> tuple[float, float, float]:
        dims = self.dimensions
        if self.primitive is Primitive.BOX:
            return (float(dims.x), float(dims.y), float(dims.z))
        diameter = float(dims.radius) * 2
        return (diameter, diameter, float(dims.height))


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: BooleanOp
    targets: list[str] = Field(min_length=2)


class DesignSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    unit: Literal["mm"] = "mm"
    name: str = Field(min_length=1, max_length=128)
    parts: list[Part] = Field(min_length=1, max_length=64)
    operations: list[Operation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids_unique_and_operations_resolvable(self) -> "DesignSpec":
        seen: set[str] = set()
        for part in self.parts:
            if part.id in seen:
                raise ValueError(f"부품 id 가 중복입니다: '{part.id}'")
            seen.add(part.id)

        for index, operation in enumerate(self.operations):
            unknown = [target for target in operation.targets if target not in seen]
            if unknown:
                raise ValueError(
                    f"operations[{index}] 가 존재하지 않는 부품을 참조합니다: {unknown}"
                )
            if len(set(operation.targets)) != len(operation.targets):
                raise ValueError(f"operations[{index}] 의 targets 에 중복이 있습니다.")
        return self

    def bounding_box_mm(self) -> tuple[float, float, float]:
        """부품 배치를 포함한 전체 바운딩 박스 크기(mm).

        Phase 4의 치수 검증이 "명세대로 만들어졌는가"를 판정하는 기준이다.
        cut 연산은 크기를 줄일 수 있으므로 여기서는 union 기준 상한을 계산한다.
        """
        lows: list[tuple[float, float, float]] = []
        highs: list[tuple[float, float, float]] = []
        for part in self.parts:
            size_x, size_y, size_z = part.bounding_size()
            center = part.position
            lows.append((center.x - size_x / 2, center.y - size_y / 2, center.z))
            highs.append((center.x + size_x / 2, center.y + size_y / 2, center.z + size_z))

        min_x = min(point[0] for point in lows)
        min_y = min(point[1] for point in lows)
        min_z = min(point[2] for point in lows)
        max_x = max(point[0] for point in highs)
        max_y = max(point[1] for point in highs)
        max_z = max(point[2] for point in highs)
        return (max_x - min_x, max_y - min_y, max_z - min_z)
