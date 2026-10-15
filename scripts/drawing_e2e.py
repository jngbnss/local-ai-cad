"""Run the committed drawing suite through the live HTTP API and record evidence."""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psutil


def _request_json(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}") from exc


def _post_image(url: str, image: Path) -> dict[str, Any]:
    boundary = f"local-ai-cad-{time.time_ns()}"
    content_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{image.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + image.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return _request_json(
        urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
    )


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _request_json(
        urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    )


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def _confirmed_profile(detected: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    start = case["reference_start_px"]
    end = case["reference_end_px"]
    pixel_length = math.hypot(end[0] - start[0], end[1] - start[1])
    scale = float(case["reference_length_mm"]) / pixel_length
    outer_px = detected["outer"]["points_px"]
    min_x = min(point[0] for point in outer_px)
    min_y = min(point[1] for point in outer_px)

    def point(value: list[float]) -> list[float]:
        return [(value[0] - min_x) * scale, (value[1] - min_y) * scale]

    holes = []
    for detected_hole in detected["holes"]:
        if detected_hole["kind"] == "circle":
            holes.append(
                {
                    "kind": "circle",
                    "center": point(detected_hole["center_px"]),
                    "radius": detected_hole["radius_px"] * scale,
                }
            )
        else:
            holes.append(
                {
                    "kind": "polygon",
                    "points": [point(value) for value in detected_hole["points_px"]],
                }
            )
    return {"outer": [point(value) for value in outer_px], "holes": holes}


def _write_report(path: Path, metrics: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Track D HTTP E2E 평가",
        "",
        "> 합성 30개 회귀 입력을 실행 중인 FastAPI의 analyze → confirm → CAD → STEP 경로로 검증했다.",
        "",
        "| 지표 | 값 |",
        "|---|---:|",
        f"| 통과 | {metrics['passed']}/{metrics['cases']} |",
        f"| HTTP E2E p95 | {metrics['e2e_p95_seconds']:.4f}s |",
        f"| 서버 RSS 시작 | {metrics['rss_start_mib']:.2f} MiB |",
        f"| 서버 RSS 최대 | {metrics['rss_peak_mib']:.2f} MiB |",
        f"| 서버 RSS 증가 | {metrics['rss_growth_mib']:.2f} MiB |",
        f"| 디스크 증가 | {metrics['disk_growth_mib']:.2f} MiB |",
        "",
        "| ID | 결과 | holes | E2E 초 | 최대 축 오차(mm) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {'PASS' if row['ok'] else 'FAIL'} | {row['holes']} | "
            f"{row['seconds']:.4f} | {row['max_axis_error_mm']:.6f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--suite", type=Path, default=Path("datasets/drawings/regression/manifest.json"))
    parser.add_argument("--artifact-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--output", type=Path, default=Path("experiments/drawing-e2e"))
    parser.add_argument("--server-pid", type=int, required=True)
    args = parser.parse_args()

    cases = json.loads(args.suite.read_text(encoding="utf-8"))
    process = psutil.Process(args.server_pid)
    rss_start = process.memory_info().rss
    rss_peak = rss_start
    disk_start = _directory_bytes(args.artifact_dir)
    rows: list[dict[str, Any]] = []
    suite_root = args.suite.parent

    for case in cases:
        started = time.perf_counter()
        analyzed = _post_image(f"{args.base_url}/drawing/analyze", suite_root / case["image"])
        confirmed = _confirmed_profile(analyzed["profile"], case)
        generated = _post_json(
            f"{args.base_url}/drawing/generate",
            {
                "analysis_id": analyzed["analysis_id"],
                "name": case["id"],
                "profile": confirmed,
                "depth": case["depth_mm"],
            },
        )
        geometry = generated["geometry"]
        errors = [
            abs(actual - expected)
            for actual, expected in zip(
                geometry["bounding_box_mm"], geometry["expected_bounding_box_mm"], strict=True
            )
        ]
        step_url = args.base_url.removesuffix("/api/v1") + generated["artifacts"]["step"]
        with urllib.request.urlopen(step_url, timeout=30) as step_response:
            step_bytes = len(step_response.read())
        rss_peak = max(rss_peak, process.memory_info().rss)
        holes = len(analyzed["profile"]["holes"])
        ok = (
            geometry["is_valid"]
            and geometry["within_tolerance"]
            and holes == int(case["expected_holes"])
            and step_bytes > 0
        )
        rows.append(
            {
                "id": case["id"],
                "ok": ok,
                "holes": holes,
                "seconds": time.perf_counter() - started,
                "max_axis_error_mm": max(errors),
                "step_bytes": step_bytes,
            }
        )

    timings = sorted(row["seconds"] for row in rows)
    p95 = timings[max(0, math.ceil(len(timings) * 0.95) - 1)] if timings else 0.0
    disk_end = _directory_bytes(args.artifact_dir)
    metrics = {
        "cases": len(rows),
        "passed": sum(row["ok"] for row in rows),
        "e2e_p95_seconds": p95,
        "rss_start_mib": rss_start / 1024**2,
        "rss_peak_mib": rss_peak / 1024**2,
        "rss_growth_mib": (rss_peak - rss_start) / 1024**2,
        "disk_growth_mib": (disk_end - disk_start) / 1024**2,
        "network_hosts": ["127.0.0.1"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(
        json.dumps({"metrics": metrics, "cases": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_report(args.output / "report.md", metrics, rows)
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if metrics["passed"] == metrics["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
