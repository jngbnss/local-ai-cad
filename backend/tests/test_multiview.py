from __future__ import annotations

import pytest

from app.cad.builder import build_solid
from app.cad.validate import validate_solid
from app.design.schema import DesignSpec


def _spec(front: list[list[float]]) -> DesignSpec:
    return DesignSpec.model_validate(
        {
            "schema_version": "2.0",
            "unit": "mm",
            "name": "three-view-part",
            "source": {
                "kind": "multiview_import",
                "analysis_id": "a" * 32,
            },
            "parts": [
                {
                    "id": "body",
                    "primitive": "orthographic_intersection",
                    "dimensions": {"x": 100, "y": 60, "z": 40},
                    "front": {"outer": front, "holes": []},
                    "top": {
                        "outer": [[-50, -30], [50, -30], [50, 30], [-50, 30]],
                        "holes": [],
                    },
                    "right": {
                        "outer": [[-30, 0], [30, 0], [30, 40], [-30, 40]],
                        "holes": [],
                    },
                    "position": {},
                }
            ],
            "operations": [],
        }
    )


def test_rectangular_three_view_intersection_builds_expected_solid():
    spec = _spec([[-50, 0], [50, 0], [50, 40], [-50, 40]])

    report = validate_solid(build_solid(spec), spec)

    assert report["is_valid"] is True
    assert report["within_tolerance"] is True
    assert report["bounding_box_mm"] == pytest.approx([100, 60, 40], abs=0.01)
    assert report["volume_mm3"] == pytest.approx(240_000, rel=1e-6)


def test_front_l_profile_remains_an_l_prism_instead_of_bounding_box():
    spec = _spec([[-50, 0], [50, 0], [50, 15], [0, 15], [0, 40], [-50, 40]])

    report = validate_solid(build_solid(spec), spec)

    assert report["is_valid"] is True
    assert report["bounding_box_mm"] == pytest.approx([100, 60, 40], abs=0.01)
    assert report["volume_mm3"] == pytest.approx(165_000, rel=1e-6)
