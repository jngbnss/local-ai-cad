from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.cad.builder import build_solid
from app.cad.validate import validate_solid
from app.design.schema import DesignSpec

from app.drawing.analyzer import analyze_path, overlay_svg
from app.drawing.errors import ProfileInvalidError
from app.drawing.fixtures import generate_suite
from app.drawing.prototype import build_prototype_solid, confirmed_profile, export_step


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
