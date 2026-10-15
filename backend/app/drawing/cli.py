"""Track D 도면 스파이크와 회귀 평가 CLI."""

from __future__ import annotations

import argparse
import json
import shutil
from math import ceil
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
    metrics = _metrics(rows)
    (args.output / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_report(args.output / "report.md", rows, metrics)
    passed = int(metrics["passed"])
    print(
        json.dumps(
            {"cases": len(rows), "passed": passed, "metrics": metrics, "report": str(summary_path)},
            ensure_ascii=False,
        )
    )
    return 0 if passed == len(rows) else 1


def _run_case(suite_root: Path, output_root: Path, case: dict[str, object]) -> dict[str, object]:
    case_id = str(case["id"])
    output = output_root / case_id
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    started = perf_counter()
    expected_holes = int(case.get("expected_holes", 0))
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
            "expected_holes": expected_holes,
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
            "expected_holes": expected_holes,
            "manual_edits": 0,
            "analysis_seconds": 0.0,
            "total_seconds": round(perf_counter() - started, 6),
            "warnings": [],
            "volume_mm3": 0.0,
            "bounding_box_mm": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _metrics(rows: list[dict[str, object]]) -> dict[str, float | int]:
    passed = sum(bool(row["ok"]) for row in rows)
    expected_holes = sum(int(row["expected_holes"]) for row in rows)
    true_holes = sum(
        min(int(row["holes"]), int(row["expected_holes"])) for row in rows
    )
    false_holes = sum(
        max(0, int(row["holes"]) - int(row["expected_holes"])) for row in rows
    )
    detected_holes = sum(int(row["holes"]) for row in rows)
    timings = sorted(float(row["analysis_seconds"]) for row in rows)
    p95_index = max(0, ceil(len(timings) * 0.95) - 1)
    return {
        "cases": len(rows),
        "passed": passed,
        "outer_success_rate": passed / len(rows) if rows else 0.0,
        "hole_recall": true_holes / expected_holes if expected_holes else 1.0,
        "hole_false_positive_rate": false_holes / detected_holes if detected_holes else 0.0,
        "analysis_p95_seconds": timings[p95_index] if timings else 0.0,
    }


def _write_report(
    path: Path, rows: list[dict[str, object]], metrics: dict[str, float | int]
) -> None:
    lines = [
        "# Track D 도면 평가",
        "",
        "> 합성 입력은 구현 회귀용이며 실제 사용자 도면 완료 조건을 대체하지 않는다.",
        "",
        "| 지표 | 값 |",
        "|---|---:|",
        f"| 케이스 통과 | {metrics['passed']}/{metrics['cases']} |",
        f"| outer 성공률 | {float(metrics['outer_success_rate']):.2%} |",
        f"| hole 재현율 | {float(metrics['hole_recall']):.2%} |",
        f"| hole 오검출률 | {float(metrics['hole_false_positive_rate']):.2%} |",
        f"| 분석 p95 | {float(metrics['analysis_p95_seconds']):.4f}s |",
        "",
        "| ID | 결과 | outer 후보 | holes | 분석 초 | 경고/오류 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        detail = row["error"] or ", ".join(row["warnings"])
        lines.append(
            f"| {row['id']} | {'PASS' if row['ok'] else 'FAIL'} | {row['outer_candidates']} | "
            f"{row['holes']}/{row['expected_holes']} | "
            f"{float(row['analysis_seconds']):.4f} | {detail} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
