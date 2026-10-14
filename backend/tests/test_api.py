import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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
