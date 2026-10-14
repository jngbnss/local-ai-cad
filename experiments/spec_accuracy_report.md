# DesignSpec 정확도 보고서

- 측정일: 2026-10-14T21:44:49
- provider: huggingface
- model: `Qwen/Qwen2.5-1.5B-Instruct`
- 문항: 20
- 1차 성공률: **16/20 (80.0%)**
- 재시도 포함 성공률: **18/20 (90.0%)**
- 최대 시도 횟수: 3

## 판정

1차 80%, 교정 재시도 포함 90%다. 단순 형상은 안정적이지만 네 다리 책상 두 문항은
중복 부품 ID를 끝내 교정하지 못했다. 따라서 Phase 3의 측정·명시적 실패 기준은
충족했지만, 복합 가구 신뢰도를 높이기 위해 트랙 Q(LoRA 또는 더 강한 모델)를 권장한다.

| ID | 결과 | 시도 | 추론 초 | 오류 |
|---|---:|---:|---:|---|
| box-01 | PASS | 1 | 5.673 |  |
| box-02 | PASS | 1 | 18.056 |  |
| cylinder-01 | PASS | 1 | 4.331 |  |
| cylinder-02 | PASS | 1 | 4.456 |  |
| plate-01 | PASS | 1 | 3.501 |  |
| desk-01 | FAIL | 3 | 0.000 | 3회 시도했지만 유효한 DesignSpec 을 얻지 못했습니다. [1] 스키마 위반 (1건): <root> — Value error, 부품 id 가 중복입니다: 'legs'; [2] 스키마 위반 (1건): <root> — Value error, 부품 id 가 중복입니다: 'legs'; [3] 스키마 위반 (1건): <root> — Value error, 부품 id 가 중복입니다: 'legs' |
| desk-02 | FAIL | 3 | 0.000 | 3회 시도했지만 유효한 DesignSpec 을 얻지 못했습니다. [1] 스키마 위반 (1건): <root> — Value error, 부품 id 가 중복입니다: 'leg'; [2] 스키마 위반 (1건): <root> — Value error, 부품 id 가 중복입니다: 'leg'; [3] 스키마 위반 (1건): <root> — Value error, 부품 id 가 중복입니다: 'leg' |
| table-01 | PASS | 2 | 8.894 |  |
| bench-01 | PASS | 1 | 10.738 |  |
| shelf-01 | PASS | 1 | 4.227 |  |
| leg-01 | PASS | 1 | 4.292 |  |
| post-01 | PASS | 1 | 3.427 |  |
| block-01 | PASS | 1 | 3.251 |  |
| panel-01 | PASS | 1 | 3.240 |  |
| top-01 | PASS | 1 | 3.248 |  |
| stool-01 | PASS | 1 | 9.253 |  |
| cabinet-01 | PASS | 1 | 3.347 |  |
| base-01 | PASS | 3 | 3.014 |  |
| beam-01 | PASS | 1 | 3.426 |  |
| cube-01 | PASS | 1 | 3.387 |  |
