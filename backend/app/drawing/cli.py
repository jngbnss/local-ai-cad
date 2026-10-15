"""Track D 도면 스파이크와 회귀 평가 CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from time import perf_counter
from typing import Sequence

from app.drawing.analyzer import analyze_path, overlay_svg
from app.drawing.fixtures import generate_suite
from app.drawing.prototype import build_prototype_solid, confirmed_profile, export_step


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drawing-spike")
    parser.add_argument("--suite", type=Path, default=Path("datasets/drawings/d0/manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("experiments/drawing-d0"))
    parser.add_argument("--generate-fixtures", action="store_true")
    parser.add_argument("--fixture-count", type=int, default=10)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.generate_fixtures:
        generate_suite(args.suite.parent, count=args.fixture_count)
    if not args.suite.is_file():
        print(f"평가 manifest가 없습니다: {args.suite}", file=sys.stderr)
        return 2

    cases = json.loads(args.suite.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for case in cases:
        rows.append(_run_case(args.suite.parent, args.output, case))

    summary_path = args.output / "summary.json"
    summary_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(args.output / "report.md", rows)
    passed = sum(bool(row["ok"]) for row in rows)
    print(json.dumps({"cases": len(rows), "passed": passed, "report": str(summary_path)}, ensure_ascii=False))
    return 0 if passed == len(rows) else 1


def _run_case(suite_root: Path, output_root: Path, case: dict[str, object]) -> dict[str, object]:
    case_id = str(case["id"])
    output = output_root / case_id
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    started = perf_counter()
    try:
        detected = analyze_path(suite_root / str(case["image"]))
        (output / "normalized.png").write_bytes(detected.normalized_png)
        (output / "overlay.svg").write_text(overlay_svg(detected), encoding="utf-8")
        profile = confirmed_profile(
            detected,
            reference_start_px=tuple(case["reference_start_px"]),
            reference_end_px=tuple(case["reference_end_px"]),
            reference_length_mm=float(case["reference_length_mm"]),
            depth_mm=float(case["depth_mm"]),
        )
        (output / "profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        solid = build_prototype_solid(profile)
        export_step(solid, output / "result.step")
        hole_count = len(detected.holes)
        expected_holes = int(case.get("expected_holes", 0))
        if hole_count != expected_holes:
            raise RuntimeError(f"hole 수 불일치: expected={expected_holes}, detected={hole_count}")
        shape = solid.val()
        box = shape.BoundingBox()
        return {
            "id": case_id,
            "ok": True,
            "synthetic": bool(case.get("synthetic", False)),
            "outer_candidates": len(detected.outer_candidates),
            "holes": hole_count,
            "manual_edits": 0,
            "analysis_seconds": detected.analysis_seconds,
            "total_seconds": round(perf_counter() - started, 6),
            "warnings": detected.warnings,
            "volume_mm3": float(shape.Volume()),
            "bounding_box_mm": [float(box.xlen), float(box.ylen), float(box.zlen)],
            "error": None,
        }
    except Exception as exc:  # CLI 평가에서 케이스별 실패를 끝까지 수집한다.
        return {
            "id": case_id,
            "ok": False,
            "synthetic": bool(case.get("synthetic", False)),
            "outer_candidates": 0,
            "holes": 0,
            "manual_edits": 0,
            "analysis_seconds": 0.0,
            "total_seconds": round(perf_counter() - started, 6),
            "warnings": [],
            "volume_mm3": 0.0,
            "bounding_box_mm": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _write_report(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "# Track D D0 평가",
        "",
        "> 합성 입력은 구현 회귀용이며 실제 사용자 도면 완료 조건을 대체하지 않는다.",
        "",
        "| ID | 결과 | outer 후보 | holes | 분석 초 | 경고/오류 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        detail = row["error"] or ", ".join(row["warnings"])
        lines.append(
            f"| {row['id']} | {'PASS' if row['ok'] else 'FAIL'} | {row['outer_candidates']} | "
            f"{row['holes']} | {float(row['analysis_seconds']):.4f} | {detail} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
