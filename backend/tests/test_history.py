"""Phase 6 이력 저장소 검증.

핵심 방어선은 "수정 지시가 언급하지 않은 필드가 바뀌지 않았는가"다.
diff 가 그 질문에 답할 수 있는지를 가장 먼저 검증한다.
"""

import threading
import json
import sqlite3

import pytest

from app.design.history import (
    DesignNotFoundError,
    HistoryStore,
    VersionNotFoundError,
    diff_specs,
)
from app.design.schema import DesignSpec


def _desk(top_thickness: float = 25.0, extra_legs: int = 0) -> DesignSpec:
    """상판 + 다리 두 개짜리 최소 책상. 치수 하나만 바꿔가며 쓴다."""
    parts = [
        {
            "id": "top",
            "primitive": "box",
            "dimensions": {"x": 1200, "y": 600, "z": top_thickness},
            "position": {"x": 0, "y": 0, "z": 725},
        },
        {
            "id": "leg_fl",
            "primitive": "box",
            "dimensions": {"x": 50, "y": 50, "z": 725},
            "position": {"x": -550, "y": -250, "z": 0},
        },
    ]
    for index in range(extra_legs):
        parts.append(
            {
                "id": f"leg_extra_{index}",
                "primitive": "box",
                "dimensions": {"x": 50, "y": 50, "z": 725},
                "position": {"x": 550, "y": 250 - index * 100, "z": 0},
            }
        )
    return DesignSpec.model_validate(
        {
            "schema_version": "2.0",
            "unit": "mm",
            "name": "desk",
            "parts": parts,
            "operations": [{"type": "union", "targets": ["top", "leg_fl"]}],
        }
    )


@pytest.fixture()
def store(tmp_path):
    history = HistoryStore(tmp_path / "history.db")
    yield history
    history.close()


def test_history_survives_a_fresh_store_on_the_same_file(tmp_path):
    # uvicorn --reload 한 번에 이력이 날아가면 Phase 6 은 의미가 없다.
    db_path = tmp_path / "history.db"
    first = HistoryStore(db_path)
    created = first.create(_desk(), prompt="책상 만들어줘")
    first.add_revision(created.design_id, _desk(top_thickness=30), "상판을 30mm로")
    first.close()

    reopened = HistoryStore(db_path)
    try:
        versions = reopened.list_versions(created.design_id)
        assert [version.version for version in versions] == [1, 2]
        assert versions[0].prompt == "책상 만들어줘"
        assert versions[1].instruction == "상판을 30mm로"
        assert reopened.latest_version_number(created.design_id) == 2
    finally:
        reopened.close()


def test_old_version_restores_the_original_spec(store):
    original = _desk(top_thickness=25)
    created = store.create(original, prompt="책상")
    store.add_revision(created.design_id, _desk(top_thickness=30), "상판 30mm")

    restored = store.get(created.design_id, 1)

    assert restored.version == 1
    assert restored.spec == original
    assert restored.diff == []
    # 기본값(None)은 최신 버전을 뜻한다.
    assert store.get(created.design_id).version == 2


def test_revision_diff_names_only_the_changed_field(store):
    created = store.create(_desk(top_thickness=25), prompt="책상")

    revision = store.add_revision(
        created.design_id, _desk(top_thickness=30), "상판을 30mm로 바꿔줘"
    )

    assert [(change.path, change.before, change.after) for change in revision.diff] == [
        ("parts[0].dimensions.z", 25.0, 30.0)
    ]
    # 기록된 diff 도 같아야 한다. 되돌릴 근거가 되는 건 메모리가 아니라 DB다.
    assert store.get(created.design_id, 2).diff == revision.diff


def test_revision_that_silently_moves_another_part_is_visible_in_the_diff(store):
    created = store.create(_desk(top_thickness=25), prompt="책상")
    drifted = _desk(top_thickness=30)
    drifted.parts[1].position.x = -500  # 언급 없는 다리가 움직였다.

    revision = store.add_revision(created.design_id, drifted, "상판을 30mm로 바꿔줘")

    assert {change.path for change in revision.diff} == {
        "parts[0].dimensions.z",
        "parts[1].position.x",
    }


def test_added_part_appears_as_a_single_change_with_no_before(store):
    created = store.create(_desk(), prompt="책상")

    revision = store.add_revision(created.design_id, _desk(extra_legs=1), "다리 추가")

    assert len(revision.diff) == 1
    change = revision.diff[0]
    assert change.path == "parts[2]"
    assert change.before is None
    assert change.after["id"] == "leg_extra_0"


def test_removed_part_appears_with_no_after():
    change = diff_specs(_desk(extra_legs=1), _desk())[0]

    assert change.path == "parts[2]"
    assert change.after is None
    assert change.before["id"] == "leg_extra_0"


def test_missing_design_and_missing_version_are_different_failures(store):
    created = store.create(_desk(), prompt="책상")

    with pytest.raises(DesignNotFoundError):
        store.get("deadbeef")
    with pytest.raises(DesignNotFoundError):
        store.get("deadbeef", 1)
    with pytest.raises(DesignNotFoundError):
        store.list_versions("deadbeef")
    with pytest.raises(DesignNotFoundError):
        store.add_revision("deadbeef", _desk(), "뭐든")

    with pytest.raises(VersionNotFoundError):
        store.get(created.design_id, 2)


def test_concurrent_revisions_never_reuse_a_version_number(store):
    created = store.create(_desk(), prompt="책상")
    thread_count = 8
    start = threading.Barrier(thread_count)
    results: list[int] = []
    results_lock = threading.Lock()

    def revise(index: int) -> None:
        start.wait()
        version = store.add_revision(
            created.design_id, _desk(top_thickness=20 + index), f"수정 {index}"
        )
        with results_lock:
            results.append(version.version)

    threads = [threading.Thread(target=revise, args=(i,)) for i in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == list(range(2, 2 + thread_count))
    assert [v.version for v in store.list_versions(created.design_id)] == list(
        range(1, 2 + thread_count)
    )


def test_opening_store_migrates_v1_specs_once(tmp_path):
    db_path = tmp_path / "legacy.db"
    HistoryStore(db_path).close()
    legacy = {
        "schema_version": "1.0",
        "unit": "mm",
        "name": "legacy_box",
        "parts": [
            {
                "id": "body",
                "primitive": "box",
                "dimensions": {"x": 100, "y": 80, "z": 40, "radius": None, "height": None},
                "position": {"x": 0, "y": 0, "z": 0},
            }
        ],
        "operations": [],
    }
    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO design_versions"
        " (design_id, version, spec_json, prompt, instruction, diff_json, created_at)"
        " VALUES ('legacy01', 1, ?, 'legacy', NULL, '[]', '2026-10-15T00:00:00+00:00')",
        (json.dumps(legacy),),
    )
    connection.commit()
    connection.close()

    with HistoryStore(db_path) as store:
        restored = store.get("legacy01")
        assert restored.spec.schema_version == "2.0"
        assert restored.spec.parts[0].dimensions.model_dump() == {
            "x": 100.0,
            "y": 80.0,
            "z": 40.0,
        }

    connection = sqlite3.connect(db_path)
    saved = json.loads(connection.execute("SELECT spec_json FROM design_versions").fetchone()[0])
    connection.close()
    assert saved["schema_version"] == "2.0"
    assert saved["source"] == {"kind": "text", "analysis_id": None}
