from __future__ import annotations

from io import BytesIO
from math import cos, pi, sin
import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw
from app.cad.builder import build_solid
from app.cad.validate import validate_solid
from app.design.schema import DesignSpec

from app.drawing.analyzer import AnalysisRegion, analyze_image, analyze_path, overlay_svg
from app.drawing.errors import ProfileInvalidError, UnsupportedImageError
from app.drawing.fixtures import generate_suite
from app.drawing.prototype import build_prototype_solid, confirmed_profile, export_step
from app.drawing.store import cleanup_analyses
from app.drawing.ocr import OcrUnavailableError, extract_dimensions


def test_ten_drawing_spike_cases_produce_valid_step(tmp_path: Path):
    suite = tmp_path / "suite"
    manifest_path = generate_suite(suite, count=10)
    cases = json.loads(manifest_path.read_text(encoding="utf-8"))

    for case in cases:
        detected = analyze_path(suite / case["image"])
        assert len(detected.holes) == case["expected_holes"], case["id"]
        assert "<svg" in overlay_svg(detected)

        profile = confirmed_profile(
            detected,
            reference_start_px=tuple(case["reference_start_px"]),
            reference_end_px=tuple(case["reference_end_px"]),
            reference_length_mm=case["reference_length_mm"],
            depth_mm=case["depth_mm"],
        )
        solid = build_prototype_solid(profile)
        shape = solid.val()
        assert shape.isValid(), case["id"]
        assert len(shape.Solids()) == 1, case["id"]
        export_step(solid, tmp_path / f"{case['id']}.step")


def test_unconfirmed_profile_is_rejected():
    with pytest.raises(ProfileInvalidError, match="확인하지 않은"):
        build_prototype_solid(
            {
                "schema_version": "1.0",
                "outer_mm": [[0, 0], [100, 0], [100, 50], [0, 50]],
                "holes_mm": [],
                "depth_mm": 5,
                "confirmed": False,
            }
        )


def test_self_intersecting_profile_is_rejected():
    with pytest.raises(ProfileInvalidError, match="self-intersection"):
        build_prototype_solid(
            {
                "schema_version": "1.0",
                "outer_mm": [[0, 0], [100, 50], [0, 50], [100, 0]],
                "holes_mm": [],
                "depth_mm": 5,
                "confirmed": True,
            }
        )


def test_design_spec_v2_builds_sketch_extrusion_with_circle_and_polygon_holes():
    spec = DesignSpec.model_validate(
        {
            "schema_version": "2.0",
            "unit": "mm",
            "name": "imported_plate",
            "parts": [
                {
                    "id": "body",
                    "primitive": "sketch_extrusion",
                    "profile": {
                        "outer": [[-50, -30], [50, -30], [50, 30], [-50, 30]],
                        "holes": [
                            {"kind": "circle", "center": [-25, 0], "radius": 5},
                            {
                                "kind": "polygon",
                                "points": [[15, -5], [25, -5], [25, 5], [15, 5]],
                            },
                        ],
                    },
                    "depth": 8,
                    "position": {"x": 0, "y": 0, "z": 0},
                }
            ],
            "operations": [],
            "source": {"kind": "drawing_import", "analysis_id": "drawing01"},
        }
    )

    report = validate_solid(build_solid(spec), spec)
    assert report["is_valid"] is True
    assert report["within_tolerance"] is True
    assert report["bounding_box_mm"] == pytest.approx([100.0, 60.0, 8.0], abs=0.01)


@pytest.mark.parametrize(
    "profile",
    [
        {"outer": [[0, 0], [100, 50], [0, 50], [100, 0]], "holes": []},
        {
            "outer": [[0, 0], [100, 0], [100, 50], [0, 50]],
            "holes": [{"kind": "circle", "center": [150, 25], "radius": 5}],
        },
        {
            "outer": [[0, 0], [100, 0], [100, 50], [0, 50]],
            "holes": [
                {"kind": "circle", "center": [45, 25], "radius": 10},
                {"kind": "circle", "center": [55, 25], "radius": 10},
            ],
        },
    ],
)
def test_design_spec_rejects_invalid_sketch_topology(profile):
    with pytest.raises(ValueError):
        DesignSpec.model_validate(
            {
                "schema_version": "2.0",
                "unit": "mm",
                "name": "invalid",
                "parts": [
                    {
                        "id": "body",
                        "primitive": "sketch_extrusion",
                        "profile": profile,
                        "depth": 5,
                        "position": {},
                    }
                ],
                "operations": [],
            }
        )


def test_analysis_region_excludes_other_shapes():
    image = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((50, 100, 300, 500), fill="black")
    draw.rectangle((500, 100, 750, 500), fill="black")
    stream = BytesIO()
    image.save(stream, format="PNG")

    full = analyze_image(stream.getvalue())
    selected = analyze_image(
        stream.getvalue(), region=AnalysisRegion(x=0, y=0, width=400, height=600)
    )

    assert len(full.outer_candidates) == 2
    assert len(selected.outer_candidates) == 1


def test_exif_orientation_is_applied_before_analysis():
    image = Image.new("RGB", (80, 40), "white")
    ImageDraw.Draw(image).rectangle((10, 8, 70, 32), fill="black")
    exif = Image.Exif()
    exif[274] = 6
    stream = BytesIO()
    image.save(stream, format="JPEG", exif=exif)

    detected = analyze_image(stream.getvalue())

    assert (detected.width_px, detected.height_px) == (40, 80)


def test_decodable_but_unsupported_gif_is_rejected():
    stream = BytesIO()
    Image.new("RGB", (100, 100), "white").save(stream, format="GIF")

    with pytest.raises(UnsupportedImageError, match="PNG, JPEG 또는 WebP"):
        analyze_image(stream.getvalue())


def test_analysis_cleanup_only_removes_expired_valid_ids(tmp_path):
    expired = tmp_path / ("a" * 32)
    current = tmp_path / ("b" * 32)
    unrelated = tmp_path / "keep-me"
    for directory in (expired, current, unrelated):
        directory.mkdir()
    os.utime(expired, (100, 100))

    removed = cleanup_analyses(tmp_path, ttl_seconds=100, now=201)

    assert removed == 1
    assert not expired.exists()
    assert current.exists()
    assert unrelated.exists()


def test_cpu_ocr_returns_confirmable_dimension_candidate():
    image = np.full((160, 500, 3), 255, np.uint8)
    cv2.putText(
        image,
        "120 mm",
        (20, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        2,
        (0, 0, 0),
        4,
        cv2.LINE_AA,
    )

    candidates = extract_dimensions(image)

    assert candidates
    assert candidates[0].value_mm == 120.0
    assert candidates[0].confidence > 0.9
    assert len(candidates[0].box_px) == 4


def test_ocr_failure_preserves_manual_analysis(tmp_path, monkeypatch):
    from app.drawing import analyzer

    manifest_path = generate_suite(tmp_path, count=1)
    case = json.loads(manifest_path.read_text(encoding="utf-8"))[0]

    def fail_ocr(_image):
        raise OcrUnavailableError("OCR disabled")

    monkeypatch.setattr(analyzer, "extract_dimensions", fail_ocr)
    detected = analyze_path(tmp_path / case["image"])

    assert detected.outer.points_px
    assert detected.dimensions == []
    assert "ocr_unavailable" in detected.warnings


def test_small_text_like_features_are_not_promoted_to_holes():
    image = np.full((600, 800, 3), 255, np.uint8)
    cv2.rectangle(image, (80, 80), (720, 520), (0, 0, 0), -1)
    cv2.circle(image, (400, 300), 55, (255, 255, 255), -1)
    for index in range(8):
        x = 130 + index * 65
        cv2.rectangle(image, (x, 130), (x + 12, 146), (255, 255, 255), -1)
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    detected = analyze_image(encoded.tobytes())

    assert len(detected.holes) == 1
    assert "small_holes_ignored" in detected.warnings
    assert "detail_heavy_input" in detected.warnings


def test_complex_logo_like_hole_is_marked_as_detail_heavy():
    image = np.full((600, 800, 3), 255, np.uint8)
    cv2.rectangle(image, (80, 80), (720, 520), (0, 0, 0), -1)
    points = []
    for index in range(48):
        angle = 2 * pi * index / 48
        radius = 90 if index % 2 == 0 else 45
        points.append(
            [round(400 + radius * cos(angle)), round(300 + radius * sin(angle))]
        )
    cv2.fillPoly(image, [np.asarray(points, dtype=np.int32)], (255, 255, 255))
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    detected = analyze_image(encoded.tobytes())

    assert "detail_heavy_input" in detected.warnings
