import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
