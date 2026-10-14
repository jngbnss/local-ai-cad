"""Phase 4 기하 계층 테스트.

핵심은 좌표 규약이다. `Part.position` 이 바닥면 중심이라는 약속이 깨지면 책상은
다리가 상판을 뚫거나 공중에 뜨고, 바운딩 박스가 즉시 어긋난다.
"""

import pytest

from app.cad.builder import build_solid
from app.cad.errors import GeometryError
from app.cad.exporter import export_artifacts
from app.cad.validate import TOLERANCE_MM, validate_solid
from app.design.schema import DesignSpec

DESK = {
    "schema_version": "1.0",
    "unit": "mm",
    "name": "desk",
    "parts": [
        {
            "id": "top",
            "primitive": "box",
            "dimensions": {"x": 1200, "y": 600, "z": 25},
            "position": {"x": 0, "y": 0, "z": 725},
        },
        {
            "id": "leg_fl",
            "primitive": "box",
            "dimensions": {"x": 50, "y": 50, "z": 725},
            "position": {"x": -550, "y": -250, "z": 0},
        },
        {
            "id": "leg_fr",
            "primitive": "box",
            "dimensions": {"x": 50, "y": 50, "z": 725},
            "position": {"x": 550, "y": -250, "z": 0},
        },
        {
            "id": "leg_bl",
            "primitive": "box",
            "dimensions": {"x": 50, "y": 50, "z": 725},
            "position": {"x": -550, "y": 250, "z": 0},
        },
        {
            "id": "leg_br",
            "primitive": "box",
            "dimensions": {"x": 50, "y": 50, "z": 725},
            "position": {"x": 550, "y": 250, "z": 0},
        },
    ],
    "operations": [
        {"type": "union", "targets": ["top", "leg_fl", "leg_fr", "leg_bl", "leg_br"]}
    ],
}

# 100mm 정육면체에 지름 40mm 구멍을 관통시킨다.
PLATE_AND_HOLE = {
    "schema_version": "1.0",
    "unit": "mm",
    "name": "plate-with-hole",
    "parts": [
        {
            "id": "plate",
            "primitive": "box",
            "dimensions": {"x": 100, "y": 100, "z": 100},
            "position": {"x": 0, "y": 0, "z": 0},
        },
        {
            "id": "pin",
            "primitive": "cylinder",
            "dimensions": {"radius": 20, "height": 200},
            "position": {"x": 0, "y": 0, "z": -50},
        },
    ],
    "operations": [],
}


def _with_operations(spec_dict: dict, operations: list[dict]) -> DesignSpec:
    return DesignSpec.model_validate({**spec_dict, "operations": operations})


def test_desk_bounding_box_matches_spec():
    spec = DesignSpec.model_validate(DESK)

    report = validate_solid(build_solid(spec), spec)

    assert report["bounding_box_mm"] == pytest.approx([1200.0, 600.0, 750.0], abs=TOLERANCE_MM)
    assert report["expected_bounding_box_mm"] == pytest.approx([1200.0, 600.0, 750.0])
    assert report["within_tolerance"] is True


def test_desk_is_a_closed_solid_with_expected_volume():
    spec = DesignSpec.model_validate(DESK)

    report = validate_solid(build_solid(spec), spec)

    # 상판 1200*600*25 + 다리 4개 50*50*725. 겹치면(다리가 상판을 뚫으면) 더 작아진다.
    assert report["is_valid"] is True
    assert report["volume_mm3"] == pytest.approx(18_000_000 + 4 * 1_812_500, rel=1e-6)


def test_cut_removes_material_that_union_keeps():
    union_spec = _with_operations(PLATE_AND_HOLE, [{"type": "union", "targets": ["plate", "pin"]}])
    cut_spec = _with_operations(PLATE_AND_HOLE, [{"type": "cut", "targets": ["plate", "pin"]}])

    union_volume = validate_solid(build_solid(union_spec), union_spec)["volume_mm3"]
    cut_report = validate_solid(build_solid(cut_spec), cut_spec)

    assert cut_report["volume_mm3"] < union_volume
    # 구멍 부피 pi*20^2*100 만큼 줄어든 판재.
    assert cut_report["volume_mm3"] == pytest.approx(1_000_000 - 125_663.7, rel=1e-4)
    # cut 은 바운딩 박스를 줄일 수 있으므로 상한 비교만 한다. 여기선 100^3 그대로다.
    assert cut_report["within_tolerance"] is True


def test_dimension_mismatch_is_reported_not_raised():
    built_spec = DesignSpec.model_validate(DESK)
    # 같은 솔리드를 "상판이 2000mm 짜리" 명세로 재면 폭이 모자란다.
    wider = DESK["parts"][0] | {"dimensions": {"x": 2000, "y": 600, "z": 25}}
    expected_spec = DesignSpec.model_validate({**DESK, "parts": [wider, *DESK["parts"][1:]]})

    report = validate_solid(build_solid(built_spec), expected_spec)

    assert report["within_tolerance"] is False
    assert report["bounding_box_mm"][0] == pytest.approx(1200.0, abs=TOLERANCE_MM)
    assert report["expected_bounding_box_mm"][0] == pytest.approx(2000.0)


def test_cut_that_annihilates_the_solid_raises_geometry_error():
    # OCP 는 이 경우 예외 대신 빈 Compound 를 돌려준다. 조용히 넘어가면 안 된다.
    spec = DesignSpec.model_validate(
        {
            "schema_version": "1.0",
            "unit": "mm",
            "name": "swallowed",
            "parts": [
                {
                    "id": "small",
                    "primitive": "box",
                    "dimensions": {"x": 10, "y": 10, "z": 10},
                    "position": {"x": 0, "y": 0, "z": 0},
                },
                {
                    "id": "big",
                    "primitive": "box",
                    "dimensions": {"x": 100, "y": 100, "z": 100},
                    "position": {"x": 0, "y": 0, "z": -10},
                },
            ],
            "operations": [{"type": "cut", "targets": ["small", "big"]}],
        }
    )

    with pytest.raises(GeometryError) as excinfo:
        build_solid(spec)

    assert "big" in str(excinfo.value)


def test_exports_stl_and_step_files(tmp_path):
    spec = DesignSpec.model_validate(DESK)

    artifacts = export_artifacts(build_solid(spec), tmp_path, "a1b2c3d4-v1")

    stl = tmp_path / "a1b2c3d4-v1.stl"
    step = tmp_path / "a1b2c3d4-v1.step"
    assert artifacts == {"stl": str(stl), "step": str(step)}
    assert stl.stat().st_size > 0
    assert step.stat().st_size > 0
    assert "ISO-10303" in step.read_text(encoding="utf-8", errors="replace")[:200]
