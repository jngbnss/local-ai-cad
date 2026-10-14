"""고정 20문항 DesignSpec 유효율 평가."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.ai.providers import build_provider
from app.config import Settings
from app.design.validator import SpecGenerationError, generate_spec


@dataclass(slots=True)
class EvalRow:
    id: str
    ok: bool
    attempts: int
    seconds: float
    error: str = ""
    total_seconds: float = 0.0


def evaluate(dataset: Path, report: Path, *, mock: bool, max_attempts: int, limit: int | None = None) -> int:
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit is not None:
        cases = cases[:limit]
    provider = build_provider(Settings.from_env(), mock=mock)
    provider.warm_up()
    rows: list[EvalRow] = []
    try:
        for index, case in enumerate(cases, 1):
            print(f"[{index}/{len(cases)}] {case['id']}", flush=True)
            try:
                result = generate_spec(provider, case["prompt"], max_attempts=max_attempts)
                rows.append(EvalRow(case["id"], True, result.attempt_count, result.metrics.inference_seconds, total_seconds=result.metrics.inference_seconds))
            except SpecGenerationError as exc:
                seconds = 0.0
                print(f"  raw={exc.attempts[-1].raw_text[:300]!r}", flush=True)
                rows.append(EvalRow(case["id"], False, len(exc.attempts), seconds, str(exc), seconds))
    finally:
        provider.release()

    passed = sum(row.ok for row in rows)
    total = len(rows)
    first_pass = sum(row.ok and row.attempts == 1 for row in rows)
    lines = [
        "# DesignSpec 정확도 보고서",
        "",
        f"- 측정일: {datetime.now().isoformat(timespec='seconds')}",
        f"- provider: {'mock' if mock else 'huggingface'}",
        f"- model: `{Settings.from_env().model_id}`",
        f"- 문항: {total}",
        f"- 1차 성공률: **{first_pass}/{total} ({first_pass / total:.1%})**",
        f"- 재시도 포함 성공률: **{passed}/{total} ({passed / total:.1%})**",
        f"- 최대 시도 횟수: {max_attempts}",
        "",
        "| ID | 결과 | 시도 | 추론 초 | 오류 |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        error = row.error.replace("|", "\\|").replace("\n", " ")[:240]
        lines.append(f"| {row.id} | {'PASS' if row.ok else 'FAIL'} | {row.attempts} | {row.seconds:.3f} | {error} |")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"result={passed}/{total} report={report}", flush=True)
    return 0 if passed == total else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("datasets/eval_prompts.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("experiments/spec_accuracy_report.md"))
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    return evaluate(args.dataset, args.report, mock=args.mock, max_attempts=args.max_attempts, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
