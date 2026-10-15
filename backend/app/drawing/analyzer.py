"""래스터 도면에서 외곽선과 관통 구멍 후보를 추출한다.

이 모듈은 픽셀 후보만 만든다. 실제 mm 보정과 CAD 생성은 사용자가 후보를 확인한
뒤 별도 단계에서 수행한다. 애매한 contour를 조용히 고치지 않고 warning으로 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import pi
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2
import numpy as np

from app.drawing.errors import ImageTooLargeError, ProfileDetectionError, UnsupportedImageError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
MIN_CONTOUR_AREA_PX = 64.0


@dataclass(frozen=True, slots=True)
class AnalysisRegion:
    x: int
    y: int
    width: int
    height: int

    def clamp(self, image_width: int, image_height: int) -> "AnalysisRegion":
        if self.width <= 0 or self.height <= 0:
            raise UnsupportedImageError("analysis region의 폭과 높이는 양수여야 합니다.")
        x1 = max(0, self.x)
        y1 = max(0, self.y)
        x2 = min(image_width, self.x + self.width)
        y2 = min(image_height, self.y + self.height)
        if x2 <= x1 or y2 <= y1:
            raise UnsupportedImageError("analysis region이 이미지 밖에 있습니다.")
        return AnalysisRegion(x1, y1, x2 - x1, y2 - y1)


@dataclass(frozen=True, slots=True)
class PolygonCandidate:
    points_px: tuple[tuple[float, float], ...]
    area_px2: float
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "polygon",
            "points_px": [list(point) for point in self.points_px],
            "area_px2": self.area_px2,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class CircleCandidate:
    center_px: tuple[float, float]
    radius_px: float
    area_px2: float
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "circle",
            "center_px": list(self.center_px),
            "radius_px": self.radius_px,
            "area_px2": self.area_px2,
            "confidence": self.confidence,
        }


HoleCandidate = PolygonCandidate | CircleCandidate


@dataclass(slots=True)
class DetectedProfile:
    width_px: int
    height_px: int
    outer: PolygonCandidate
    outer_candidates: list[PolygonCandidate]
    holes: list[HoleCandidate]
    warnings: list[str] = field(default_factory=list)
    analysis_seconds: float = 0.0
    normalized_png: bytes = b""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "prototype-1",
            "image": {"width_px": self.width_px, "height_px": self.height_px},
            "outer": self.outer.as_dict(),
            "outer_candidates": [candidate.as_dict() for candidate in self.outer_candidates],
            "holes": [hole.as_dict() for hole in self.holes],
            "warnings": list(self.warnings),
            "analysis_seconds": self.analysis_seconds,
        }


def analyze_path(path: Path, region: AnalysisRegion | None = None) -> DetectedProfile:
    data = path.read_bytes()
    return analyze_image(data, region=region)


def analyze_image(data: bytes, region: AnalysisRegion | None = None) -> DetectedProfile:
    started = perf_counter()
    if not data:
        raise UnsupportedImageError("이미지 파일이 비어 있습니다.")
    if len(data) > MAX_FILE_BYTES:
        raise ImageTooLargeError(f"이미지는 {MAX_FILE_BYTES}바이트 이하여야 합니다.")

    encoded = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise UnsupportedImageError("PNG, JPEG 또는 WebP 이미지를 디코딩하지 못했습니다.")
    height, width = image.shape[:2]
    if width * height > MAX_PIXELS:
        raise ImageTooLargeError(f"디코딩한 이미지 픽셀 수가 상한 {MAX_PIXELS}을 넘었습니다.")

    selected = (region or AnalysisRegion(0, 0, width, height)).clamp(width, height)
    cropped = image[
        selected.y : selected.y + selected.height,
        selected.x : selected.x + selected.width,
    ].copy()
    normalized, mask = _normalise(cropped)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None or not contours:
        raise ProfileDetectionError("닫힌 외곽선 후보를 찾지 못했습니다.")

    hierarchy_rows = hierarchy[0]
    roots: list[tuple[int, float]] = []
    for index, contour in enumerate(contours):
        area = abs(float(cv2.contourArea(contour)))
        if hierarchy_rows[index][3] == -1 and area >= MIN_CONTOUR_AREA_PX:
            roots.append((index, area))
    if not roots:
        raise ProfileDetectionError("최소 면적을 만족하는 외곽선 후보가 없습니다.")

    roots.sort(key=lambda item: item[1], reverse=True)
    outer_candidates = [_polygon(contours[index]) for index, _area in roots]
    outer_index, outer_area = roots[0]
    outer = outer_candidates[0]
    warnings: list[str] = []
    if len(outer_candidates) > 1:
        warnings.append("ambiguous_outer")

    holes: list[HoleCandidate] = []
    child_index = int(hierarchy_rows[outer_index][2])
    while child_index != -1:
        contour = contours[child_index]
        area = abs(float(cv2.contourArea(contour)))
        if area >= MIN_CONTOUR_AREA_PX:
            ratio = area / outer_area if outer_area else 0.0
            if ratio >= 0.65:
                warnings.append("double_contour_suspected")
            else:
                holes.append(_hole(contour))
        child_index = int(hierarchy_rows[child_index][0])

    ok, png = cv2.imencode(".png", normalized)
    if not ok:
        raise UnsupportedImageError("정규화 이미지를 PNG로 인코딩하지 못했습니다.")

    return DetectedProfile(
        width_px=normalized.shape[1],
        height_px=normalized.shape[0],
        outer=outer,
        outer_candidates=outer_candidates,
        holes=holes,
        warnings=warnings,
        analysis_seconds=round(perf_counter() - started, 6),
        normalized_png=png.tobytes(),
    )


def overlay_svg(profile: DetectedProfile) -> str:
    outer_points = " ".join(f"{x:.3f},{y:.3f}" for x, y in profile.outer.points_px)
    hole_nodes: list[str] = []
    for hole in profile.holes:
        if isinstance(hole, CircleCandidate):
            hole_nodes.append(
                f'<circle cx="{hole.center_px[0]:.3f}" cy="{hole.center_px[1]:.3f}" '
                f'r="{hole.radius_px:.3f}" class="hole" />'
            )
        else:
            points = " ".join(f"{x:.3f},{y:.3f}" for x, y in hole.points_px)
            hole_nodes.append(f'<polygon points="{points}" class="hole" />')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {profile.width_px} {profile.height_px}">'
        '<style>.outer{fill:none;stroke:#00a86b;stroke-width:3}.hole{fill:none;stroke:#d33;stroke-width:3}</style>'
        f'<polygon points="{outer_points}" class="outer" />'
        f'{"".join(hole_nodes)}</svg>'
    )


def _normalise(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _threshold, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    border = np.concatenate((binary[0, :], binary[-1, :], binary[:, 0], binary[:, -1]))
    if float(np.mean(border)) > 127.0:
        binary = cv2.bitwise_not(binary)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    normalized = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return normalized, mask


def _polygon(contour: np.ndarray) -> PolygonCandidate:
    perimeter = float(cv2.arcLength(contour, True))
    epsilon = max(1.0, perimeter * 0.005)
    approximated = cv2.approxPolyDP(contour, epsilon, True)
    points = tuple((float(point[0][0]), float(point[0][1])) for point in approximated)
    area = abs(float(cv2.contourArea(contour)))
    confidence = min(1.0, area / max(1.0, float(cv2.boundingRect(contour)[2] * cv2.boundingRect(contour)[3])))
    return PolygonCandidate(points, area, round(confidence, 4))


def _hole(contour: np.ndarray) -> HoleCandidate:
    area = abs(float(cv2.contourArea(contour)))
    perimeter = float(cv2.arcLength(contour, True))
    circularity = 0.0 if perimeter <= 0.0 else 4.0 * pi * area / (perimeter * perimeter)
    if circularity >= 0.82:
        (x, y), radius = cv2.minEnclosingCircle(contour)
        return CircleCandidate(
            center_px=(float(x), float(y)),
            radius_px=float(radius),
            area_px2=area,
            confidence=round(min(1.0, circularity), 4),
        )
    return _polygon(contour)
