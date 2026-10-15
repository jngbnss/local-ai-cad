"""Minimal local Hunyuan3D-2mv HTTP server used by the photo3d backend adapter."""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL = "tencent/Hunyuan3D-2mv"
SUBFOLDER = "hunyuan3d-dit-v2-mv-turbo"
VIEW_KEYS = ("front", "left", "back", "right")
MAX_REQUEST_BYTES = 50 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="Hunyuan3D-2 checkout containing hy3dgen")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    return parser.parse_args()


def load_pipeline(repo: str):
    sys.path.insert(0, str(Path(repo).resolve()))
    import torch
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU를 찾지 못했습니다.")
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        MODEL, subfolder=SUBFOLDER, variant="fp16"
    )
    pipeline.enable_flashvdm()
    return pipeline, torch.cuda.get_device_name(0)


def decode_views(payload: dict):
    from PIL import Image

    images = {}
    for key in VIEW_KEYS:
        encoded = (payload.get("views") or {}).get(key)
        if not encoded:
            continue
        image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))).convert("RGBA")
        if image.getchannel("A").getextrema()[0] == 255:
            raise ValueError(f"'{key}' 이미지에 투명 배경이 없습니다.")
        images[key] = image
    if "front" not in images:
        raise ValueError("front 이미지가 필요합니다.")
    return images


def main() -> None:
    args = parse_args()
    print(f"[hunyuan-local] {MODEL}/{SUBFOLDER} 로드 중", flush=True)
    pipeline, device = load_pipeline(args.repo)
    import torch

    gpu_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def json_response(self, status: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/health":
                self.json_response(200, {"ready": True, "model": f"{MODEL}/{SUBFOLDER}", "device": device})
            else:
                self.json_response(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/generate":
                self.json_response(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError("요청 본문은 50MB 이하여야 합니다.")
                images = decode_views(json.loads(self.rfile.read(length)))
            except Exception as error:
                self.json_response(400, {"error": str(error)})
                return
            try:
                with gpu_lock, torch.inference_mode():
                    started = time.perf_counter()
                    mesh = pipeline(
                        image=images,
                        num_inference_steps=int(5),
                        octree_resolution=int(256),
                        num_chunks=int(8000),
                        generator=torch.manual_seed(1234),
                        output_type="trimesh",
                    )[0]
                    torch.cuda.empty_cache()
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "shape.glb"
                    mesh.export(path)
                    data = path.read_bytes()
                print(f"[hunyuan-local] {list(images)} -> {len(mesh.faces):,} triangles, {time.perf_counter() - started:.1f}s", flush=True)
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                self.json_response(507, {"error": "GPU 메모리가 부족합니다. 다른 GPU 모델과 GPU 앱을 종료한 뒤 다시 시도하세요."})
                return
            except Exception as error:
                self.json_response(500, {"error": str(error)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "model/gltf-binary")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, _format: str, *_args) -> None:
            return

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[hunyuan-local] ready: {device} http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
