from __future__ import annotations

import json
import struct
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.drawing.errors import UnsupportedImageError
from app.photo3d import service


def _photo(*, uniform: bool = False) -> bytes:
    pixels = np.full((120, 160, 3), 245, dtype=np.uint8)
    if not uniform:
        pixels[20:110, 45:120] = (35, 80, 150)
    output = BytesIO()
    Image.fromarray(pixels, "RGB").save(output, format="PNG")
    return output.getvalue()


def test_prepare_cutout_removes_plain_background() -> None:
    result = service.prepare_cutout(_photo())
    with Image.open(BytesIO(result)) as image:
        alpha = np.asarray(image.getchannel("A"))
        assert image.mode == "RGBA"
        assert int(alpha.min()) == 0
        assert int(alpha.max()) == 255
        assert 0.25 < np.count_nonzero(alpha) / alpha.size < 0.8


def test_prepare_cutout_rejects_unseparable_uniform_image() -> None:
    with pytest.raises(UnsupportedImageError, match="배경"):
        service.prepare_cutout(_photo(uniform=True))


def test_generate_mesh_sends_alpha_cutout_and_saves_valid_glb(monkeypatch, tmp_path: Path) -> None:
    glb = struct.pack("<4sII", b"glTF", 2, 12)
    calls = 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int) -> bytes:
            return glb

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == 600.0
        payload = json.loads(request.data)
        assert list(payload["views"]) == ["front"]
        return Response()

    monkeypatch.setattr(service.urllib.request, "urlopen", fake_urlopen)
    result = service.generate_mesh({"front": _photo()}, tmp_path)
    saved = tmp_path / Path(str(result["artifact"])).name
    assert saved.read_bytes() == glb
    assert result["provider"] == "local"
    assert result["input_views"] == ["front"]
    cached = service.generate_mesh({"front": _photo()}, tmp_path)
    assert cached["cached"] is True
    assert calls == 1
