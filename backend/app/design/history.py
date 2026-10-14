"""설계 이력 저장소 (Phase 6).

이 계층이 지키는 것은 하나다. **수정 지시가 언급하지 않은 필드는 바뀌면 안 된다.**
LLM 재생성은 매번 전체 DesignSpec 을 다시 뱉으므로, 언급 없는 치수가 조용히
달라져도 사용자는 알아차리지 못한다. 그래서 버전마다 이전 버전과의 필드 단위
diff 를 함께 적재한다. diff 는 "무엇이 바뀌었는가"의 증거이자, 되돌릴 근거다.

저장 단위는 DesignSpec JSON 뿐이다. STL/STEP 은 spec 에서 언제든 재생성되는
파생물이라 보관하지 않는다 (디스크를 아끼고, 파일과 spec 이 어긋날 여지를 없앤다).

SQLite 를 쓰는 이유는 프로세스 재시작을 견디기 위해서다. 메모리 dict 는
`uvicorn --reload` 한 번에 전부 날아간다. 커넥션은 FastAPI 스레드 풀에서
호출되므로 `check_same_thread=False` 로 열고, 쓰기는 Lock + BEGIN IMMEDIATE 로
직렬화한다. version 번호는 (design_id, version) 기본키가 최종 방어선이다.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.design.schema import DesignSpec

DESIGN_ID_LENGTH = 8

# (design_id, version) 충돌 시 재시도 횟수. 여러 프로세스가 같은 DB 파일을
# 열었을 때를 위한 보험이며, 한도를 넘으면 조용히 덮어쓰지 않고 실패로 올린다.
_MAX_INSERT_ATTEMPTS = 8

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS design_versions (
    design_id   TEXT    NOT NULL,
    version     INTEGER NOT NULL,
    spec_json   TEXT    NOT NULL,
    prompt      TEXT,
    instruction TEXT,
    diff_json   TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    PRIMARY KEY (design_id, version)
)
"""


class HistoryError(Exception):
    """이력 저장소 계층의 기반 예외."""

    exit_code = 7


class DesignNotFoundError(HistoryError):
    """해당 design_id 로 저장된 버전이 하나도 없다."""


class VersionNotFoundError(HistoryError):
    """design 은 있지만 요청한 version 이 없다. 설계 부재와 섞지 않는다."""


@dataclass(frozen=True, slots=True)
class FieldChange:
    """변경된 필드 하나. `path` 는 평탄한 경로 (예: `parts[1].dimensions.x`)."""

    path: str
    before: Any
    after: Any

    def to_json(self) -> dict[str, Any]:
        return {"path": self.path, "before": self.before, "after": self.after}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "FieldChange":
        return cls(path=payload["path"], before=payload["before"], after=payload["after"])


@dataclass(frozen=True, slots=True)
class DesignVersion:
    """한 버전의 전체 기록. v1 은 prompt 를, v2+ 는 instruction 을 갖는다."""

    design_id: str
    version: int
    spec: DesignSpec
    prompt: str | None
    instruction: str | None
    created_at: str
    diff: list[FieldChange]


class _Missing:
    """`None` 값과 "키 자체가 없음"을 구분하기 위한 센티널."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - 디버깅 편의
        return "<missing>"


_MISSING = _Missing()


def diff_specs(before: DesignSpec, after: DesignSpec) -> list[FieldChange]:
    """두 명세 사이에서 **실제로 바뀐 필드만** 평탄한 경로로 뽑는다.

    - 리스트는 인덱스로 경로를 만든다: `parts[0].dimensions.z`.
    - 한쪽에만 존재하면 반대쪽을 `None` 으로 기록하고 더 내려가지 않는다.
      (부품 추가는 `parts[2]` 하나로, 필드 수십 개로 흩어지지 않는다.)
    - 딕셔너리 키를 정렬해 순회하므로 결과 순서는 결정적이다.
    """
    changes: list[FieldChange] = []
    _collect(
        "",
        before.model_dump(mode="json"),
        after.model_dump(mode="json"),
        changes,
    )
    return changes


def _collect(path: str, before: Any, after: Any, out: list[FieldChange]) -> None:
    if before is _MISSING or after is _MISSING:
        out.append(
            FieldChange(
                path=path,
                before=None if before is _MISSING else before,
                after=None if after is _MISSING else after,
            )
        )
        return

    if before == after:
        return

    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            _collect(
                f"{path}.{key}" if path else str(key),
                before.get(key, _MISSING),
                after.get(key, _MISSING),
                out,
            )
        return

    if isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            _collect(
                f"{path}[{index}]",
                before[index] if index < len(before) else _MISSING,
                after[index] if index < len(after) else _MISSING,
                out,
            )
        return

    out.append(FieldChange(path=path, before=before, after=after))


class HistoryStore:
    """DesignSpec 버전 이력의 영속 저장소. 스키마는 생성 시 멱등하게 만든다."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        parent = self._db_path.parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        # isolation_level=None: 트랜잭션 경계를 우리가 직접 잡는다 (BEGIN IMMEDIATE).
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_CREATE_TABLE_SQL)

    # -- 쓰기 ---------------------------------------------------------------

    def create(self, spec: DesignSpec, prompt: str) -> DesignVersion:
        """새 설계를 v1 로 적재하고 design_id 를 발급한다. diff 는 비어 있다."""
        spec_json = spec.model_dump_json()
        created_at = _now_iso()

        last_error: sqlite3.IntegrityError | None = None
        for _ in range(_MAX_INSERT_ATTEMPTS):
            design_id = uuid4().hex[:DESIGN_ID_LENGTH]
            try:
                with self._lock:
                    self._conn.execute("BEGIN IMMEDIATE")
                    try:
                        self._conn.execute(
                            "INSERT INTO design_versions"
                            " (design_id, version, spec_json, prompt, instruction,"
                            "  diff_json, created_at)"
                            " VALUES (?, 1, ?, ?, NULL, '[]', ?)",
                            (design_id, spec_json, prompt, created_at),
                        )
                    except BaseException:
                        self._conn.execute("ROLLBACK")
                        raise
                    self._conn.execute("COMMIT")
            except sqlite3.IntegrityError as error:  # design_id 충돌 — 다시 뽑는다.
                last_error = error
                continue
            return DesignVersion(
                design_id=design_id,
                version=1,
                spec=spec,
                prompt=prompt,
                instruction=None,
                created_at=created_at,
                diff=[],
            )

        raise HistoryError(
            f"design_id 를 {_MAX_INSERT_ATTEMPTS}번 시도했지만 모두 충돌했습니다."
        ) from last_error

    def add_revision(
        self, design_id: str, spec: DesignSpec, instruction: str
    ) -> DesignVersion:
        """직전 버전과의 diff 를 계산해 다음 버전으로 적재한다.

        version 채번과 삽입을 한 트랜잭션 안에서 처리하므로 동시 호출에도
        번호가 겹치지 않는다. 겹쳤다면 기본키가 막고, 우리는 다시 읽어 재시도한다.
        """
        spec_json = spec.model_dump_json()
        created_at = _now_iso()

        last_error: sqlite3.IntegrityError | None = None
        for _ in range(_MAX_INSERT_ATTEMPTS):
            try:
                with self._lock:
                    self._conn.execute("BEGIN IMMEDIATE")
                    try:
                        row = self._conn.execute(
                            "SELECT version, spec_json FROM design_versions"
                            " WHERE design_id = ? ORDER BY version DESC LIMIT 1",
                            (design_id,),
                        ).fetchone()
                        if row is None:
                            raise DesignNotFoundError(
                                f"설계 '{design_id}' 를 찾을 수 없습니다."
                            )

                        previous = DesignSpec.model_validate_json(row["spec_json"])
                        version = int(row["version"]) + 1
                        diff = diff_specs(previous, spec)
                        diff_json = json.dumps(
                            [change.to_json() for change in diff], ensure_ascii=False
                        )
                        self._conn.execute(
                            "INSERT INTO design_versions"
                            " (design_id, version, spec_json, prompt, instruction,"
                            "  diff_json, created_at)"
                            " VALUES (?, ?, ?, NULL, ?, ?, ?)",
                            (
                                design_id,
                                version,
                                spec_json,
                                instruction,
                                diff_json,
                                created_at,
                            ),
                        )
                    except BaseException:
                        self._conn.execute("ROLLBACK")
                        raise
                    self._conn.execute("COMMIT")
            except sqlite3.IntegrityError as error:  # version 경쟁 — 다시 읽는다.
                last_error = error
                continue
            return DesignVersion(
                design_id=design_id,
                version=version,
                spec=spec,
                prompt=None,
                instruction=instruction,
                created_at=created_at,
                diff=diff,
            )

        raise HistoryError(
            f"설계 '{design_id}' 의 버전 채번이 {_MAX_INSERT_ATTEMPTS}번 모두"
            " 경쟁에서 밀렸습니다."
        ) from last_error

    # -- 읽기 ---------------------------------------------------------------

    def get(self, design_id: str, version: int | None = None) -> DesignVersion:
        """버전 하나를 복원한다. `version=None` 이면 최신 버전."""
        if version is None:
            row = self._fetch_one(
                "SELECT * FROM design_versions WHERE design_id = ?"
                " ORDER BY version DESC LIMIT 1",
                (design_id,),
            )
            if row is None:
                raise DesignNotFoundError(f"설계 '{design_id}' 를 찾을 수 없습니다.")
            return _row_to_version(row)

        row = self._fetch_one(
            "SELECT * FROM design_versions WHERE design_id = ? AND version = ?",
            (design_id, version),
        )
        if row is not None:
            return _row_to_version(row)

        # 설계 자체가 없는 것과, 설계는 있는데 그 버전이 없는 것은 다른 사건이다.
        if (
            self._fetch_one(
                "SELECT 1 FROM design_versions WHERE design_id = ? LIMIT 1",
                (design_id,),
            )
            is None
        ):
            raise DesignNotFoundError(f"설계 '{design_id}' 를 찾을 수 없습니다.")
        raise VersionNotFoundError(
            f"설계 '{design_id}' 에 버전 {version} 이(가) 없습니다."
        )

    def list_versions(self, design_id: str) -> list[DesignVersion]:
        """버전 오름차순 전체 이력. 설계가 없으면 빈 리스트 대신 예외를 올린다."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM design_versions WHERE design_id = ?"
                " ORDER BY version ASC",
                (design_id,),
            ).fetchall()
        if not rows:
            raise DesignNotFoundError(f"설계 '{design_id}' 를 찾을 수 없습니다.")
        return [_row_to_version(row) for row in rows]

    def latest_version_number(self, design_id: str) -> int:
        row = self._fetch_one(
            "SELECT MAX(version) AS latest FROM design_versions WHERE design_id = ?",
            (design_id,),
        )
        if row is None or row["latest"] is None:
            raise DesignNotFoundError(f"설계 '{design_id}' 를 찾을 수 없습니다.")
        return int(row["latest"])

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "HistoryStore":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # -- 내부 ---------------------------------------------------------------

    def _fetch_one(
        self, sql: str, params: tuple[object, ...]
    ) -> sqlite3.Row | None:
        # 읽기도 Lock 아래에서 돈다. 커넥션 하나를 여러 스레드가 공유하므로,
        # 쓰기 트랜잭션 도중의 조회가 미확정 상태를 보는 일을 막는다.
        with self._lock:
            return self._conn.execute(sql, params).fetchone()


def _row_to_version(row: sqlite3.Row) -> DesignVersion:
    return DesignVersion(
        design_id=row["design_id"],
        version=int(row["version"]),
        spec=DesignSpec.model_validate_json(row["spec_json"]),
        prompt=row["prompt"],
        instruction=row["instruction"],
        created_at=row["created_at"],
        diff=[FieldChange.from_json(item) for item in json.loads(row["diff_json"])],
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
