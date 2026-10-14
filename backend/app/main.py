"""FastAPI 애플리케이션 (Phase 2).

수명주기 규칙:
- 서버 기동 시 모델을 **1회** 로드하고, 종료 시 VRAM 을 해제한다.
- 워커는 반드시 1개다. uvicorn `--workers N` 은 프로세스마다 모델을 복제해
  8GB VRAM 에서 즉시 OOM 이다. `run()` 이 이를 강제한다.
- 모델 로드는 수십 초가 걸린다. 그동안 `/health` 가 막히면 안 되므로
  로딩을 백그라운드 스레드에서 돌리고 상태를 `model_loaded` 로 보고한다.
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import build_state
from app.api.errors import register_error_handlers
from app.api.v1.routes import router as v1_router
from app.config import Settings

logger = logging.getLogger(__name__)


def _warm_up(app: FastAPI) -> None:
    """모델을 미리 로드한다. 실패해도 서버는 떠 있어야 원인을 조회할 수 있다."""
    state = app.state.app_state
    try:
        state.provider.warm_up()
        logger.info("모델 예열 완료: load_count=%d", state.provider.load_count)
    except Exception as exc:  # noqa: BLE001 - 예열 실패는 health 로 드러낸다
        logger.warning("모델 예열 실패: %s", exc)
        app.state.warmup_error = str(exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app.state.app_state = build_state(settings)
    app.state.warmup_error = None

    thread = threading.Thread(target=_warm_up, args=(app,), name="model-warmup", daemon=True)
    thread.start()

    yield

    app.state.app_state.provider.release()
    logger.info("모델 해제 완료")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Local AI CAD",
        version="0.2.0",
        description="로컬 GPU LLM 으로 CAD 설계를 생성한다 (Phase 2~6)",
        lifespan=lifespan,
    )
    app.include_router(v1_router)
    register_error_handlers(app)
    return app


app = create_app()


def run() -> None:
    """개발 서버. 워커 1개를 강제한다."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        workers=1,
        reload=False,
    )


if __name__ == "__main__":
    run()
