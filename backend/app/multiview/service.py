"""Storage and deterministic reconstruction for front/top/right drawings."""

from __future__ import annotations

import json
import math
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.design.schema import DesignSpec, SketchProfile
from app.drawing.analyzer import DetectedProfile, analyze_image
from app.drawing.errors import ProfileInvalidError
from app.drawing.store import ANALYSIS_ID, DEFAULT_TTL_SECONDS

ViewName = Literal["front", "top", "right"]
Projection = Literal["first_angle", "third_angle"]
VIEW_NAMES: tuple[ViewName, ...] = ("front", "top", "right")


@dataclass(frozen=True, slots=True)
class StoredMultiviewAnalysis:
    analysis_id: str
    directory: Path

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"

    def image_path(self, view: ViewName) -> Path:
        return self.directory / f"{view}.png"


def create_analysis(
    root: Path,
    *,
    images: dict[ViewName, bytes],
    projection: Projection,
) -> tuple[StoredMultiviewAnalysis, dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    cleanup_analyses(root)
    detected: dict[ViewName, DetectedProfile] = {
        view: analyze_image(images[view]) for view in VIEW_NAMES
    }
    analysis_id = uuid.uuid4().hex
    directory = root / analysis_id
    directory.mkdir()
    stored = StoredMultiviewAnalysis(analysis_id, directory)
    profiles = {view: detected[view].as_dict() for view in VIEW_NAMES}
    manifest = {
        "schema_version": "multiview-1",
        "projection": projection,
        "views": profiles,
    }
    stored.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for view in VIEW_NAMES:
        stored.image_path(view).write_bytes(detected[view].normalized_png)
    return stored, manifest


def get_analysis(root: Path, analysis_id: str) -> StoredMultiviewAnalysis | None:
    if not ANALYSIS_ID.fullmatch(analysis_id):
        return None
    stored = StoredMultiviewAnalysis(analysis_id, root / analysis_id)
    required = [stored.manifest_path, *(stored.image_path(view) for view in VIEW_NAMES)]
    if not stored.directory.is_dir() or not all(path.is_file() for path in required):
        return None
    return stored


def cleanup_analyses(
    root: Path,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> int:
    if not root.is_dir():
        return 0
    cutoff = (time.time() if now is None else now) - ttl_seconds
    removed = 0
    for candidate in root.iterdir():
        if (
            candidate.is_dir()
            and ANALYSIS_ID.fullmatch(candidate.name)
            and candidate.stat().st_mtime < cutoff
        ):
            shutil.rmtree(candidate)
            removed += 1
    return removed


def load_manifest(stored: StoredMultiviewAnalysis) -> dict[str, Any]:
    return json.loads(stored.manifest_path.read_text(encoding="utf-8"))


def build_spec(
    stored: StoredMultiviewAnalysis,
    *,
    name: str,
    width: float,
    depth: float,
    height: float,
) -> DesignSpec:
    manifest = load_manifest(stored)
    views = manifest["views"]
    for view in VIEW_NAMES:
        warnings = views[view].get("warnings", [])
        if "detail_heavy_input" in warnings:
            raise ProfileInvalidError(
                f"{view} 뷰에 문자·무늬 또는 복잡한 선이 너무 많습니다."
            )

    front = _scaled_profile(views["front"], width, height, vertical_base=True)
    top = _scaled_profile(views["top"], width, depth, vertical_base=False)
    right = _scaled_profile(views["right"], depth, height, vertical_base=True)
    return DesignSpec.model_validate(
        {
            "schema_version": "2.0",
            "unit": "mm",
            "name": name,
            "source": {
                "kind": "multiview_import",
                "analysis_id": stored.analysis_id,
            },
            "parts": [
                {
                    "id": "orthographic-body",
                    "primitive": "orthographic_intersection",
                    "dimensions": {"x": width, "y": depth, "z": height},
                    "front": front.model_dump(mode="json"),
                    "top": top.model_dump(mode="json"),
                    "right": right.model_dump(mode="json"),
                    "position": {},
                }
            ],
            "operations": [],
        }
    )


def _scaled_profile(
    raw: dict[str, Any],
    horizontal_mm: float,
    vertical_mm: float,
    *,
    vertical_base: bool,
) -> SketchProfile:
    outer_px = raw["outer"]["points_px"]
    xs = [float(point[0]) for point in outer_px]
    ys = [float(point[1]) for point in outer_px]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max_x - min_x
    span_y = max_y - min_y
    if span_x <= 0 or span_y <= 0:
        raise ProfileInvalidError("3면도 외곽선의 폭과 높이는 양수여야 합니다.")

    def convert(point: list[float] | tuple[float, float]) -> tuple[float, float]:
        horizontal = (float(point[0]) - min_x) / span_x * horizontal_mm - horizontal_mm / 2
        vertical = (max_y - float(point[1])) / span_y * vertical_mm
        if not vertical_base:
            vertical -= vertical_mm / 2
        return (round(horizontal, 6), round(vertical, 6))

    holes: list[dict[str, Any]] = []
    for hole in raw.get("holes", []):
        if hole["kind"] == "polygon":
            holes.append(
                {"kind": "polygon", "points": [convert(point) for point in hole["points_px"]]}
            )
            continue
        center_x, center_y = hole["center_px"]
        radius = float(hole["radius_px"])
        points = [
            convert(
                (
                    center_x + radius * math.cos(2 * math.pi * index / 32),
                    center_y + radius * math.sin(2 * math.pi * index / 32),
                )
            )
            for index in range(32)
        ]
        holes.append({"kind": "polygon", "points": points})

    return SketchProfile.model_validate(
        {"outer": [convert(point) for point in outer_px], "holes": holes}
    )
