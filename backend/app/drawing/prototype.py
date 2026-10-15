"""D0용 픽셀 후보 보정과 스케치 돌출.

D0 계약은 폐기 가능하다. 이 모듈의 출력으로 실제 입력을 검증한 뒤 영구
DesignSpec 계약을 확정한다.
"""

from __future__ import annotations

from math import hypot
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters
from shapely.geometry import Point, Polygon

from app.drawing.analyzer import CircleCandidate, DetectedProfile, PolygonCandidate
from app.drawing.errors import ProfileInvalidError


def confirmed_profile(
    detected: DetectedProfile,
    *,
    reference_start_px: tuple[float, float],
    reference_end_px: tuple[float, float],
    reference_length_mm: float,
    depth_mm: float,
) -> dict[str, Any]:
    pixel_distance = hypot(
        reference_end_px[0] - reference_start_px[0],
        reference_end_px[1] - reference_start_px[1],
    )
    if pixel_distance < 20.0:
        raise ProfileInvalidError("기준 선분은 20px 이상이어야 합니다.")
    if not 0.1 <= reference_length_mm <= 10_000.0:
        raise ProfileInvalidError("기준 길이는 0.1~10,000mm 범위여야 합니다.")
    if not 0.1 <= depth_mm <= 10_000.0:
        raise ProfileInvalidError("돌출 깊이는 0.1~10,000mm 범위여야 합니다.")

    scale = reference_length_mm / pixel_distance
    xs = [point[0] for point in detected.outer.points_px]
    ys = [point[1] for point in detected.outer.points_px]
    origin = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    def point_mm(point: tuple[float, float]) -> list[float]:
        return [
            round((point[0] - origin[0]) * scale, 6),
            round((origin[1] - point[1]) * scale, 6),
        ]

    holes: list[dict[str, Any]] = []
    for hole in detected.holes:
        if isinstance(hole, CircleCandidate):
            holes.append(
                {
                    "kind": "circle",
                    "center": point_mm(hole.center_px),
                    "radius": round(hole.radius_px * scale, 6),
                }
            )
        else:
            holes.append(
                {"kind": "polygon", "points": [point_mm(point) for point in hole.points_px]}
            )

    result = {
        "schema_version": "1.0",
        "outer_mm": [point_mm(point) for point in detected.outer.points_px],
        "holes_mm": holes,
        "depth_mm": float(depth_mm),
        "confirmed": True,
        "calibration": {
            "reference_start_px": list(reference_start_px),
            "reference_end_px": list(reference_end_px),
            "reference_length_mm": float(reference_length_mm),
            "mm_per_px": scale,
        },
    }
    validate_confirmed_profile(result)
    return result


def validate_confirmed_profile(profile: dict[str, Any]) -> None:
    if profile.get("confirmed") is not True:
        raise ProfileInvalidError("사용자가 확인하지 않은 프로파일입니다.")
    outer = profile.get("outer_mm")
    if not isinstance(outer, list) or len(outer) < 3:
        raise ProfileInvalidError("outer는 점 3개 이상의 폐곡선이어야 합니다.")
    try:
        polygon = Polygon(outer)
    except Exception as exc:  # noqa: BLE001 - Shapely 타입은 공개 계약이 아니다.
        raise ProfileInvalidError(f"outer polygon을 읽지 못했습니다: {exc}") from exc
    if not polygon.is_valid or polygon.area <= 0.0:
        raise ProfileInvalidError("outer polygon이 self-intersection 없이 유효해야 합니다.")

    for index, hole in enumerate(profile.get("holes_mm", [])):
        geometry = _hole_geometry(hole, index)
        if not polygon.contains(geometry):
            raise ProfileInvalidError(f"holes_mm[{index}]가 outer 내부에 완전히 포함되지 않습니다.")
        for previous_index, previous in enumerate(profile.get("holes_mm", [])[:index]):
            if geometry.intersects(_hole_geometry(previous, previous_index)):
                raise ProfileInvalidError(
                    f"holes_mm[{index}]가 holes_mm[{previous_index}]와 겹칩니다."
                )
    depth = float(profile.get("depth_mm", 0.0))
    if not 0.1 <= depth <= 10_000.0:
        raise ProfileInvalidError("depth_mm은 0.1~10,000mm 범위여야 합니다.")


def build_prototype_solid(profile: dict[str, Any]) -> cq.Workplane:
    validate_confirmed_profile(profile)
    try:
        outer = [(float(x), float(y)) for x, y in profile["outer_mm"]]
        depth = float(profile["depth_mm"])
        solid = cq.Workplane("XY").polyline(outer).close().extrude(depth)
        for hole in profile.get("holes_mm", []):
            if hole["kind"] == "circle":
                center_x, center_y = hole["center"]
                cutter = (
                    cq.Workplane("XY")
                    .center(float(center_x), float(center_y))
                    .circle(float(hole["radius"]))
                    .extrude(depth)
                )
            else:
                points = [(float(x), float(y)) for x, y in hole["points"]]
                cutter = cq.Workplane("XY").polyline(points).close().extrude(depth)
            solid = solid.cut(cutter)
    except ProfileInvalidError:
        raise
    except Exception as exc:  # noqa: BLE001 - OCP 타입은 공개 계약이 아니다.
        raise ProfileInvalidError(f"프로파일을 돌출하지 못했습니다: {exc}") from exc

    shape = solid.val()
    if not shape.isValid() or shape.Volume() <= 0.0 or len(shape.Solids()) != 1:
        raise ProfileInvalidError("돌출 결과가 유효한 단일 solid가 아닙니다.")
    return solid


def export_step(solid: cq.Workplane, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(solid, str(path), exportType="STEP")
    if not path.is_file() or path.stat().st_size == 0:
        raise ProfileInvalidError(f"STEP 파일을 생성하지 못했습니다: {path}")


def _hole_geometry(hole: dict[str, Any], index: int):
    kind = hole.get("kind")
    if kind == "circle":
        center = hole.get("center")
        radius = float(hole.get("radius", 0.0))
        if not isinstance(center, list) or len(center) != 2 or radius < 0.1:
            raise ProfileInvalidError(f"holes_mm[{index}] circle 값이 유효하지 않습니다.")
        return Point(float(center[0]), float(center[1])).buffer(radius)
    if kind == "polygon":
        points = hole.get("points")
        if not isinstance(points, list) or len(points) < 3:
            raise ProfileInvalidError(f"holes_mm[{index}] polygon은 점 3개 이상이어야 합니다.")
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.area <= 0.0:
            raise ProfileInvalidError(f"holes_mm[{index}] polygon이 유효하지 않습니다.")
        return polygon
    raise ProfileInvalidError(f"holes_mm[{index}] kind는 circle 또는 polygon이어야 합니다.")
