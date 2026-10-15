"""Local Hunyuan3D-2mv client and deterministic photo cut-out preparation."""

from __future__ import annotations

import hashlib
import base64
import json
import os
import time
import urllib.error
import urllib.request
import struct
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.drawing.analyzer import MAX_FILE_BYTES, MAX_PIXELS
from app.drawing.errors import ImageTooLargeError, UnsupportedImageError

LOCAL_AI_URL_ENV = "LOCAL_AI_CAD_HUNYUAN_URL"
DEFAULT_LOCAL_AI_URL = "http://127.0.0.1:8090"
MAX_MESH_BYTES = 100 * 1024 * 1024
VIEW_NAMES = ("front", "back", "left", "right")


def local_ai_url() -> str:
    return os.environ.get(LOCAL_AI_URL_ENV, DEFAULT_LOCAL_AI_URL).strip().rstrip("/")


def health(timeout: float = 0.8) -> dict[str, object]:
    try:
        with urllib.request.urlopen(f"{local_ai_url()}/health", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "ready": bool(payload.get("ready")),
            "model": str(payload.get("model", "tencent/Hunyuan3D-2mv")),
            "device": str(payload.get("device", "CUDA GPU")),
            "url": local_ai_url(),
        }
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return {"ready": False, "model": "tencent/Hunyuan3D-2mv", "device": None, "url": local_ai_url()}


def prepare_cutout(data: bytes, *, max_side: int = 512) -> bytes:
    """Return a bounded RGBA PNG; preserve real alpha or estimate a border background."""
    if not data:
        raise UnsupportedImageError("이미지 파일이 비어 있습니다.")
    if len(data) > MAX_FILE_BYTES:
        raise ImageTooLargeError(f"이미지는 {MAX_FILE_BYTES}바이트 이하여야 합니다.")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"}:
                raise UnsupportedImageError("PNG, JPEG 또는 WebP 이미지만 지원합니다.")
            oriented = ImageOps.exif_transpose(source)
            if oriented.width * oriented.height > MAX_PIXELS:
                raise ImageTooLargeError(f"디코딩한 이미지 픽셀 수가 상한 {MAX_PIXELS}을 넘었습니다.")
            rgba = np.asarray(oriented.convert("RGBA")).copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise UnsupportedImageError("PNG, JPEG 또는 WebP 이미지를 디코딩하지 못했습니다.") from exc

    alpha = rgba[:, :, 3]
    if int(alpha.min()) == 255:
        rgb = rgba[:, :, :3].astype(np.int16)
        border = np.concatenate((rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]), axis=0)
        background = np.median(border, axis=0)
        distance = np.sqrt(np.sum((rgb - background) ** 2, axis=2)).astype(np.uint8)
        threshold, mask = cv2.threshold(distance, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if threshold < 12:
            _, mask = cv2.threshold(distance, 12, 255, cv2.THRESH_BINARY)
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise UnsupportedImageError("배경과 물체를 분리하지 못했습니다. 단색 배경 사진을 사용해 주세요.")
        largest = max(contours, key=cv2.contourArea)
        alpha = np.zeros(mask.shape, dtype=np.uint8)
        cv2.drawContours(alpha, [largest], -1, 255, thickness=cv2.FILLED)
        coverage = float(np.count_nonzero(alpha)) / float(alpha.size)
        if coverage < 0.01 or coverage > 0.95:
            raise UnsupportedImageError("배경과 물체의 대비가 부족합니다. 투명 또는 단색 배경 사진을 사용해 주세요.")
        rgba[:, :, 3] = alpha

    ys, xs = np.nonzero(rgba[:, :, 3])
    if not len(xs):
        raise UnsupportedImageError("투명하지 않은 물체 영역이 없습니다.")
    x1, x2, y1, y2 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    pad = max(8, round(max(x2 - x1, y2 - y1) * 0.08))
    cropped = Image.fromarray(rgba[y1:y2, x1:x2], "RGBA")
    canvas = Image.new("RGBA", (cropped.width + 2 * pad, cropped.height + 2 * pad))
    canvas.alpha_composite(cropped, (pad, pad))
    canvas.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


def generate_mesh(views: dict[str, bytes], artifact_dir: Path, *, timeout: float = 600.0) -> dict[str, object]:
    prepared = {name: prepare_cutout(data) for name, data in views.items() if data}
    if "front" not in prepared:
        raise ValueError("정면 사진이 필요합니다.")
    digest = hashlib.sha256(b"hunyuan3d-2mv-turbo:steps=5:octree=256")
    for name in VIEW_NAMES:
        if name in prepared:
            digest.update(name.encode("ascii"))
            digest.update(prepared[name])
    artifact_id = f"photo3d-{digest.hexdigest()[:32]}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{artifact_id}.glb"
    if path.is_file():
        cached_size = path.stat().st_size
        with path.open("rb") as cached_file:
            cached_header = cached_file.read(12)
        if len(cached_header) == 12 and cached_size <= MAX_MESH_BYTES:
            _magic, version, declared_length = struct.unpack("<4sII", cached_header)
            if _magic == b"glTF" and version == 2 and declared_length == cached_size:
                return {
                    "artifact": f"/api/v1/artifacts/{path.name}",
                    "provider": "local",
                    "model": "tencent/Hunyuan3D-2mv",
                    "input_views": list(prepared),
                    "generation_seconds": 0.0,
                    "bytes": cached_size,
                    "cached": True,
                }
    payload = {
        "views": {name: base64.b64encode(data).decode("ascii") for name, data in prepared.items()},
        "seed": 1234,
        "steps": 5,
        "octree": 256,
        "chunks": 8000,
    }
    request = urllib.request.Request(
        f"{local_ai_url()}/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            mesh = response.read(MAX_MESH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise RuntimeError(f"로컬 Hunyuan 서버 오류({exc.code}): {detail}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise ConnectionError(f"로컬 Hunyuan 서버({local_ai_url()})에 연결할 수 없습니다.") from exc
    if len(mesh) > MAX_MESH_BYTES:
        raise RuntimeError("생성된 GLB가 100MB 상한을 넘었습니다.")
    if len(mesh) < 12 or mesh[:4] != b"glTF":
        raise RuntimeError("로컬 Hunyuan 서버가 유효한 GLB를 반환하지 않았습니다.")
    _magic, version, declared_length = struct.unpack("<4sII", mesh[:12])
    if version != 2 or declared_length != len(mesh):
        raise RuntimeError("로컬 Hunyuan 서버가 손상된 GLB를 반환했습니다.")
    path.write_bytes(mesh)
    return {
        "artifact": f"/api/v1/artifacts/{path.name}",
        "provider": "local",
        "model": "tencent/Hunyuan3D-2mv",
        "input_views": list(prepared),
        "generation_seconds": round(time.perf_counter() - started, 3),
        "bytes": len(mesh),
        "cached": False,
    }
