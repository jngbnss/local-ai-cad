"""Phase 1 CLI.

`diagnose` 는 환경만 보고하고, `infer` 는 실제 추론을 실행한다.
종료 코드는 오류 타입별로 다르다 (errors.py 의 `exit_code`).
Phase 1에는 웹 계층을 넣지 않는다. GPU 실패와 API 설정 실패를 섞지 않기 위함이다.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Sequence

from app.ai.diagnostics import collect_diagnostics
from app.ai.errors import ProviderError
from app.ai.providers import build_provider
from app.config import ConfigError, Settings

DEFAULT_PROMPT = "가로 120cm 책상을 설계하기 위한 핵심 치수를 알려줘."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local-ai-cad",
        description="로컬 GPU LLM 진단·추론 (Phase 1)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("diagnose", help="Python/PyTorch/CUDA/GPU 환경을 보고한다")

    infer = subparsers.add_parser("infer", help="로컬 모델로 추론한다")
    infer.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="입력 프롬프트 (기본값: Phase 1 스모크 프롬프트)",
    )
    infer.add_argument(
        "--mock",
        action="store_true",
        help="모델을 로드하지 않고 Mock provider 로 애플리케이션 경로만 점검한다",
    )
    infer.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="같은 프로세스에서 요청을 N회 반복한다. 모델 재로드 여부 확인용",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"[구성 오류] {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.command == "diagnose":
        return _run_diagnose()
    return _run_infer(settings, args)


def _run_diagnose() -> int:
    try:
        report = collect_diagnostics()
    except ProviderError as exc:
        print(f"[환경 오류] {exc}", file=sys.stderr)
        return exc.exit_code
    _emit(report)
    return 0 if report["cuda_available"] else 3


def _run_infer(settings: Settings, args: argparse.Namespace) -> int:
    if args.repeat < 1:
        print("[구성 오류] --repeat 은 1 이상이어야 합니다.", file=sys.stderr)
        return 2

    provider = build_provider(settings, mock=args.mock)
    for index in range(1, args.repeat + 1):
        try:
            result = provider.generate(args.prompt)
        except ProviderError as exc:
            print(f"[{type(exc).__name__}] {exc}", file=sys.stderr)
            return exc.exit_code
        except KeyboardInterrupt:
            print("[중단] 사용자 요청으로 생성을 취소했습니다.", file=sys.stderr)
            return 130

        payload = result.metrics.as_dict()
        payload["request_index"] = index
        payload["model_load_count"] = provider.load_count
        payload["text"] = result.text
        _emit(payload)

    return 0


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
