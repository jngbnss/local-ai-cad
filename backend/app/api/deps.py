"""프로세스 전역 자원.

서버 프로세스 하나가 모델 하나를 소유한다. uvicorn 멀티워커는 모델을
워커 수만큼 복제해 8GB VRAM에서 즉시 OOM 이므로 금지한다 (main.py 참조).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.ai.providers import ModelProvider, build_provider
from app.config import Settings
from app.design.history import HistoryStore

ARTIFACT_DIR_ENV = "LOCAL_AI_CAD_ARTIFACT_DIR"
DB_PATH_ENV = "LOCAL_AI_CAD_DB_PATH"
MOCK_ENV = "LOCAL_AI_CAD_USE_MOCK"


@dataclass(slots=True)
class AppState:
    settings: Settings
    provider: ModelProvider
    history: HistoryStore
    artifact_dir: Path
    use_mock: bool


def build_state(settings: Settings | None = None) -> AppState:
    settings = settings or Settings.from_env()
    use_mock = os.environ.get(MOCK_ENV, "").strip().lower() in {"1", "true", "yes"}

    artifact_dir = Path(os.environ.get(ARTIFACT_DIR_ENV, "artifacts")).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path(os.environ.get(DB_PATH_ENV, "designs.sqlite3")).resolve()

    return AppState(
        settings=settings,
        provider=build_provider(settings, mock=use_mock),
        history=HistoryStore(db_path),
        artifact_dir=artifact_dir,
        use_mock=use_mock,
    )
