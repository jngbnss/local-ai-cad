"""솔리드를 STL(미리보기)·STEP(제조용)으로 내보낸다.

두 포맷을 항상 같이 쓴다. STL 은 브라우저 뷰어가 바로 읽을 수 있는 삼각망이고,
STEP 은 치수와 B-rep 을 보존해 실제 가공/편집으로 넘어갈 수 있는 원본이다.

내보내기 실패를 가장 쉽게 놓치는 지점이 "예외 없이 0바이트 파일"이다.
그래서 쓴 뒤 크기를 반드시 확인하고, 비어 있으면 `ExportError` 로 끊는다.
"""

from __future__ import annotations

from pathlib import Path

import cadquery as cq
from cadquery import exporters

from app.cad.errors import ExportError

# 확장자 → CadQuery exportType.
_EXPORT_TYPES: dict[str, str] = {"stl": "STL", "step": "STEP"}


def export_artifacts(solid: cq.Workplane, output_dir: Path, artifact_id: str) -> dict[str, str]:
    """`{artifact_id}.stl` 과 `{artifact_id}.step` 을 쓰고 경로를 돌려준다.

    반환: `{"stl": "<경로>", "step": "<경로>"}`.
    """
    directory = Path(output_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"출력 디렉터리를 만들지 못했습니다: {directory} ({exc})") from exc

    artifacts: dict[str, str] = {}
    for suffix, export_type in _EXPORT_TYPES.items():
        path = directory / f"{artifact_id}.{suffix}"
        try:
            exporters.export(solid, str(path), exportType=export_type)
        except Exception as exc:  # noqa: BLE001 - OCP/CadQuery 예외 타입이 공개 계약이 아니다.
            raise ExportError(f"{export_type} 내보내기가 실패했습니다: {path} ({exc})") from exc

        if not path.exists():
            raise ExportError(f"{export_type} 내보내기 뒤 파일이 없습니다: {path}")
        if path.stat().st_size == 0:
            raise ExportError(
                f"{export_type} 파일이 0바이트입니다: {path}. "
                "빈 솔리드를 내보냈을 가능성이 큽니다."
            )
        artifacts[suffix] = str(path)

    return artifacts
