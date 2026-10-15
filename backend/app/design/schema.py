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
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from shapely.geometry import Point, Polygon

SCHEMA_VERSION = "2.0"

# 물리적으로 의미 있는 범위. 책상·선반 같은 가구 규모를 가정한다.
MIN_DIMENSION_MM = 0.1
MAX_DIMENSION_MM = 10_000.0


class Primitive(StrEnum):
    BOX = "box"
    CYLINDER = "cylinder"
    SKETCH_EXTRUSION = "sketch_extrusion"


class BooleanOp(StrEnum):
    UNION = "union"
    CUT = "cut"


class Vec3(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class _Dimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*")
    @classmethod
    def _positive_and_bounded(cls, value: float) -> float:
        if value < MIN_DIMENSION_MM:
            raise ValueError(f"치수는 {MIN_DIMENSION_MM}mm 이상이어야 합니다: {value}")
        if value > MAX_DIMENSION_MM:
            raise ValueError(f"치수는 {MAX_DIMENSION_MM}mm 이하여야 합니다: {value}")
        return value


class BoxDimensions(_Dimensions):
    x: float
    y: float
    z: float


class CylinderDimensions(_Dimensions):
    radius: float
    height: float


class _PartBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    position: Vec3 = Field(default_factory=Vec3)

    def bounding_size(self) -> tuple[float, float, float]:
        raise NotImplementedError


class BoxPart(_PartBase):
    primitive: Literal[Primitive.BOX]
    dimensions: BoxDimensions

    def bounding_size(self) -> tuple[float, float, float]:
        return (self.dimensions.x, self.dimensions.y, self.dimensions.z)


class CylinderPart(_PartBase):
    primitive: Literal[Primitive.CYLINDER]
    dimensions: CylinderDimensions

    def bounding_size(self) -> tuple[float, float, float]:
        diameter = self.dimensions.radius * 2
        return (diameter, diameter, self.dimensions.height)


Point2 = tuple[float, float]


class CircleHole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["circle"]
    center: Point2
    radius: float = Field(ge=MIN_DIMENSION_MM, le=MAX_DIMENSION_MM)


class PolygonHole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["polygon"]
    points: list[Point2] = Field(min_length=3)


ProfileHole = Annotated[CircleHole | PolygonHole, Field(discriminator="kind")]


class SketchProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outer: list[Point2] = Field(min_length=3)
    holes: list[ProfileHole] = Field(default_factory=list)

    @model_validator(mode="after")
    def _valid_topology(self) -> "SketchProfile":
        outer = Polygon(self.outer)
        if not outer.is_valid or outer.area <= 0.0:
            raise ValueError("sketch outer는 self-intersection 없는 유효 폐곡선이어야 합니다.")
        geometries = []
        for index, hole in enumerate(self.holes):
            if isinstance(hole, CircleHole):
                geometry = Point(hole.center).buffer(hole.radius)
            else:
                geometry = Polygon(hole.points)
                if not geometry.is_valid or geometry.area <= 0.0:
                    raise ValueError(f"sketch holes[{index}] polygon이 유효하지 않습니다.")
            if not outer.contains(geometry):
                raise ValueError(f"sketch holes[{index}]가 outer 내부에 있지 않습니다.")
            if any(geometry.intersects(previous) for previous in geometries):
                raise ValueError(f"sketch holes[{index}]가 다른 hole과 겹칩니다.")
            geometries.append(geometry)
        return self


class SketchExtrusionPart(_PartBase):
    primitive: Literal[Primitive.SKETCH_EXTRUSION]
    profile: SketchProfile
    depth: float = Field(ge=MIN_DIMENSION_MM, le=MAX_DIMENSION_MM)

    def bounding_size(self) -> tuple[float, float, float]:
        xs = [point[0] for point in self.profile.outer]
        ys = [point[1] for point in self.profile.outer]
        return (max(xs) - min(xs), max(ys) - min(ys), self.depth)


Part = Annotated[BoxPart | CylinderPart | SketchExtrusionPart, Field(discriminator="primitive")]


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: BooleanOp
    targets: list[str] = Field(min_length=2)


class DesignSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "drawing_import"] = "text"
    analysis_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")

    @model_validator(mode="after")
    def _drawing_requires_analysis_id(self) -> "DesignSource":
        if self.kind == "drawing_import" and not self.analysis_id:
            raise ValueError("drawing_import source에는 analysis_id가 필요합니다.")
        if self.kind == "text" and self.analysis_id is not None:
            raise ValueError("text source에는 analysis_id를 쓸 수 없습니다.")
        return self


class DesignSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"] = SCHEMA_VERSION
    unit: Literal["mm"] = "mm"
    name: str = Field(min_length=1, max_length=128)
    parts: list[Part] = Field(min_length=1, max_length=64)
    operations: list[Operation] = Field(default_factory=list)
    source: DesignSource = Field(default_factory=DesignSource)

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
