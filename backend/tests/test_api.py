import json
from io import BytesIO
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.design.schema import DesignSpec
from app.design.validator import SpecAttempt, SpecGenerationError
from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_AI_CAD_USE_MOCK", "1")
    monkeypatch.setenv("LOCAL_AI_CAD_DEVICE", "cpu")
    monkeypatch.setenv("LOCAL_AI_CAD_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("LOCAL_AI_CAD_DB_PATH", str(tmp_path / "designs.sqlite3"))
    with TestClient(create_app()) as value:
        for _ in range(50):
            if value.get("/api/v1/health").json()["model_loaded"]:
                break
            time.sleep(0.01)
        yield value


def test_health_and_ten_requests_reuse_one_provider_load(client):
    assert client.get("/api/v1/health").json()["model_loaded"] is True
    for index in range(10):
        response = client.post("/api/v1/generate", json={"prompt": f"요청 {index}"})
        assert response.status_code == 200
        assert response.json()["request_id"]
    assert client.app.state.app_state.provider.load_count == 1


def test_two_concurrent_http_requests_are_serialised(client, monkeypatch):
    provider = client.app.state.app_state.provider
    original = provider._generate
    active = 0
    maximum = 0
    guard = threading.Lock()

    def probe(messages):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.03)
            return original(messages)
        finally:
            with guard:
                active -= 1

    monkeypatch.setattr(provider, "_generate", probe)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post("/api/v1/generate", json={"prompt": "책상"}), range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert maximum == 1


def test_design_sse_reports_both_stages_and_complete_result(client):
    with client.stream("POST", "/api/v1/design/stream", json={"prompt": "책상"}) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    frames = [frame for frame in body.split("\n\n") if frame]
    assert [frame.splitlines()[0] for frame in frames] == [
        "event: progress",
        "event: progress",
        "event: complete",
    ]
    payloads = [json.loads(frame.split("data: ", 1)[1]) for frame in frames]
    assert [payloads[0]["stage"], payloads[1]["stage"]] == ["llm", "geometry"]
    assert payloads[2]["spec"]["name"] == "mock_desk"
    assert payloads[2]["artifacts"]["stl"].endswith(".stl")


def test_drawing_analyze_assets_and_generate(client, monkeypatch):
    from app.api.v1 import routes

    worker_threads = []
    original = routes.analyze_image

    def observed_analysis(data, region=None):
        worker_threads.append(threading.current_thread())
        return original(data, region=region)

    monkeypatch.setattr(routes, "analyze_image", observed_analysis)
    image = Path("datasets/drawings/regression/drawing-01-rectangle-01.png")
    with image.open("rb") as stream:
        response = client.post(
            "/api/v1/drawing/analyze",
            files={"image": ("drawing.png", stream, "image/png")},
        )

    assert response.status_code == 200
    analysis = response.json()
    assert worker_threads and worker_threads[0] is not threading.current_thread()
    assert client.get(analysis["image_url"]).headers["content-type"] == "image/png"
    assert (
        client.get(analysis["overlay_url"]).headers["content-type"]
        == "image/svg+xml"
    )

    outer = [
        [point[0] * 0.1, point[1] * 0.1]
        for point in analysis["profile"]["outer"]["points_px"]
    ]
    generated = client.post(
        "/api/v1/drawing/generate",
        json={
            "analysis_id": analysis["analysis_id"],
            "name": "imported-plate",
            "profile": {"outer": outer, "holes": []},
            "depth": 5,
        },
    )

    assert generated.status_code == 200
    payload = generated.json()
    assert payload["spec"]["source"] == {
        "kind": "drawing_import",
        "analysis_id": analysis["analysis_id"],
    }
    assert payload["spec"]["parts"][0]["primitive"] == "sketch_extrusion"
    assert payload["geometry"]["is_valid"] is True
    assert client.get(payload["artifacts"]["step"]).status_code == 200


def test_drawing_analyze_rejects_partial_region_and_bad_image(client):
    image = Path("datasets/drawings/regression/drawing-01-rectangle-01.png")
    response = client.post(
        "/api/v1/drawing/analyze",
        files={"image": ("drawing.png", image.read_bytes(), "image/png")},
        data={"x": 0},
    )
    assert response.status_code == 422
    assert response.json()["error_type"] == "invalid_analysis_region"

    response = client.post(
        "/api/v1/drawing/analyze",
        files={"image": ("drawing.gif", b"GIF89a", "image/gif")},
    )
    assert response.status_code == 415
    assert response.json()["error_type"] == "image_unsupported"


def test_drawing_generate_requires_live_analysis(client):
    response = client.post(
        "/api/v1/drawing/generate",
        json={
            "analysis_id": "0" * 32,
            "name": "missing",
            "profile": {
                "outer": [[0, 0], [10, 0], [10, 10], [0, 10]],
                "holes": [],
            },
            "depth": 5,
        },
    )

    assert response.status_code == 404
    assert response.json()["error_type"] == "analysis_not_found"


def test_drawing_generate_validation_error_is_structured(client):
    response = client.post(
        "/api/v1/drawing/generate",
        json={
            "analysis_id": "0" * 32,
            "name": "invalid-profile",
            "profile": {
                "outer": [[0, 0], [10, 10], [0, 10], [10, 0]],
                "holes": [],
            },
            "depth": 5,
        },
    )

    assert response.status_code == 422
    assert response.json()["error_type"] == "profile_invalid"
    assert response.json()["detail"]["errors"]


def test_drawing_generate_blocks_photo_like_analysis(client):
    image = Path("datasets/drawings/regression/drawing-01-rectangle-01.png")
    analyzed = client.post(
        "/api/v1/drawing/analyze",
        files={"image": ("drawing.png", image.read_bytes(), "image/png")},
    ).json()
    profile_path = (
        client.app.state.app_state.artifact_dir
        / "drawing-analyses"
        / analyzed["analysis_id"]
        / "profile.json"
    )
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["warnings"].append("detail_heavy_input")
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    response = client.post(
        "/api/v1/drawing/generate",
        json={
            "analysis_id": analyzed["analysis_id"],
            "name": "photo",
            "profile": {
                "outer": [
                    [point[0] * 0.1, point[1] * 0.1]
                    for point in analyzed["profile"]["outer"]["points_px"]
                ],
                "holes": [],
            },
            "depth": 5,
        },
    )

    assert response.status_code == 422
    assert response.json()["error_type"] == "photo_input_unsupported"


def test_revision_generation_error_is_structured(client, monkeypatch):
    from app.api.v1 import routes

    record = client.app.state.app_state.history.create(
        DesignSpec.model_validate(
            {
                "schema_version": "2.0",
                "unit": "mm",
                "name": "block",
                "parts": [
                    {
                        "id": "body",
                        "primitive": "box",
                        "dimensions": {"x": 100, "y": 80, "z": 40},
                        "position": {},
                    }
                ],
                "operations": [],
            }
        ),
        "block",
    )

    def fail_revision(*_args, **_kwargs):
        attempt = SpecAttempt(1, "출력에서 JSON 객체를 찾지 못했습니다.", "")
        raise SpecGenerationError("유효한 설계 명세를 만들지 못했습니다.", [attempt])

    monkeypatch.setattr(routes, "revise_spec", fail_revision)
    response = client.post(
        f"/api/v1/design/{record.design_id}/revise",
        json={"instruction": "상판을 넓혀줘"},
    )

    assert response.status_code == 422
    assert response.json()["error_type"] == "schema_invalid"
    assert response.json()["detail"]["attempts"][0]["failure"].startswith("출력에서")


def _rectangle_png(width: int, height: int) -> bytes:
    image = Image.new("RGB", (width + 80, height + 80), "white")
    ImageDraw.Draw(image).rectangle((40, 40, 40 + width, 40 + height), fill="black")
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_multiview_analyze_generate_and_download_step(client):
    analyzed_response = client.post(
        "/api/v1/multiview/analyze",
        files={
            "front": ("front.png", _rectangle_png(300, 200), "image/png"),
            "top": ("top.png", _rectangle_png(300, 160), "image/png"),
            "right": ("right.png", _rectangle_png(160, 200), "image/png"),
        },
        data={"projection": "third_angle"},
    )

    assert analyzed_response.status_code == 200
    analyzed = analyzed_response.json()
    assert set(analyzed["views"]) == {"front", "top", "right"}
    assert all(
        client.get(analyzed["image_urls"][view]).status_code == 200
        for view in ("front", "top", "right")
    )

    generated = client.post(
        "/api/v1/multiview/generate",
        json={
            "analysis_id": analyzed["analysis_id"],
            "name": "orthographic-block",
            "width": 120,
            "depth": 80,
            "height": 60,
        },
    )

    assert generated.status_code == 200
    payload = generated.json()
    assert payload["spec"]["source"]["kind"] == "multiview_import"
    assert payload["spec"]["parts"][0]["primitive"] == "orthographic_intersection"
    assert payload["geometry"]["bounding_box_mm"] == pytest.approx([120, 80, 60], abs=0.01)
    assert payload["geometry"]["is_valid"] is True
    assert client.get(payload["artifacts"]["step"]).status_code == 200
