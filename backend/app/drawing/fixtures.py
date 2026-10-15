"""Track D 합성 회귀 도면 생성기.

합성 입력은 구현 회귀용이다. 실제 사용자 도면 검증을 대체하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

WIDTH = 800
HEIGHT = 600


def generate_suite(root: Path, *, count: int = 10) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    cases = _cases(count)
    manifest: list[dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        image = _render(case)
        case_id = f"drawing-{index:02d}-{case['name']}"
        image_path = root / f"{case_id}.png"
        if not cv2.imwrite(str(image_path), image):
            raise RuntimeError(f"fixture 이미지를 쓰지 못했습니다: {image_path}")
        manifest.append(
            {
                "id": case_id,
                "image": image_path.name,
                "reference_start_px": [100.0, 550.0],
                "reference_end_px": [700.0, 550.0],
                "reference_length_mm": 120.0,
                "depth_mm": 10.0,
                "expected_holes": int(case.get("expected_holes", 0)),
                "synthetic": True,
            }
        )
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _cases(count: int) -> list[dict[str, object]]:
    base: list[dict[str, object]] = [
        {"name": "rectangle", "outer": [(100, 100), (700, 100), (700, 500), (100, 500)]},
        {"name": "l-shape", "outer": [(100, 100), (700, 100), (700, 250), (350, 250), (350, 500), (100, 500)]},
        {"name": "u-shape", "outer": [(100, 100), (700, 100), (700, 500), (520, 500), (520, 260), (280, 260), (280, 500), (100, 500)]},
        {"name": "one-hole", "outer": [(100, 100), (700, 100), (700, 500), (100, 500)], "circles": [(400, 300, 70)], "expected_holes": 1},
        {"name": "four-holes", "outer": [(100, 100), (700, 100), (700, 500), (100, 500)], "circles": [(220, 220, 35), (580, 220, 35), (220, 380, 35), (580, 380, 35)], "expected_holes": 4},
        {"name": "polygon-hole", "outer": [(100, 100), (700, 100), (700, 500), (100, 500)], "polygon_holes": [[(330, 230), (470, 230), (500, 330), (400, 390), (300, 330)]], "expected_holes": 1},
        {"name": "inverted", "outer": [(100, 100), (700, 100), (700, 500), (100, 500)], "circles": [(400, 300, 60)], "expected_holes": 1, "inverted": True},
        {"name": "thick-outline", "outer": [(100, 100), (700, 100), (700, 500), (100, 500)], "outline_only": True},
        {"name": "low-contrast", "outer": [(100, 100), (700, 100), (700, 500), (100, 500)], "circles": [(400, 300, 55)], "expected_holes": 1, "foreground": 100, "background": 210},
        {"name": "noise", "outer": [(100, 100), (700, 100), (700, 500), (100, 500)], "circles": [(400, 300, 50)], "expected_holes": 1, "noise": True},
    ]
    if count <= len(base):
        return base[:count]
    expanded: list[dict[str, object]] = []
    for index in range(count):
        template = dict(base[index % len(base)])
        template["name"] = f"{template['name']}-{index + 1:02d}"
        if "circles" in template:
            shift = (index // len(base)) * 3
            template["circles"] = [
                (int(x) + shift, int(y), int(radius)) for x, y, radius in template["circles"]
            ]
        expanded.append(template)
    return expanded


def _render(case: dict[str, object]) -> np.ndarray:
    background = int(case.get("background", 255))
    foreground = int(case.get("foreground", 0))
    if case.get("inverted"):
        background, foreground = 0, 255
    image = np.full((HEIGHT, WIDTH, 3), background, dtype=np.uint8)
    outer = np.asarray(case["outer"], dtype=np.int32)
    if case.get("outline_only"):
        cv2.polylines(image, [outer], True, (foreground,) * 3, thickness=18)
    else:
        cv2.fillPoly(image, [outer], (foreground,) * 3)
        for x, y, radius in case.get("circles", []):
            cv2.circle(image, (int(x), int(y)), int(radius), (background,) * 3, thickness=-1)
        for points in case.get("polygon_holes", []):
            cv2.fillPoly(image, [np.asarray(points, dtype=np.int32)], (background,) * 3)
    if case.get("noise"):
        rng = np.random.default_rng(20261015)
        ys = rng.integers(0, HEIGHT, 400)
        xs = rng.integers(0, WIDTH, 400)
        image[ys, xs] = 255 - image[ys, xs]
    return image
