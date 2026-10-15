# Track D D0 평가

> 합성 입력은 구현 회귀용이며 실제 사용자 도면 완료 조건을 대체하지 않는다.

| ID | 결과 | outer 후보 | holes | 분석 초 | 경고/오류 |
|---|---:|---:|---:|---:|---|
| drawing-01-rectangle | PASS | 1 | 0 | 0.0130 |  |
| drawing-02-l-shape | PASS | 1 | 0 | 0.0074 |  |
| drawing-03-u-shape | PASS | 1 | 0 | 0.0069 |  |
| drawing-04-one-hole | PASS | 1 | 1 | 0.0055 |  |
| drawing-05-four-holes | PASS | 1 | 4 | 0.0058 |  |
| drawing-06-polygon-hole | PASS | 1 | 1 | 0.0058 |  |
| drawing-07-inverted | PASS | 1 | 1 | 0.0059 |  |
| drawing-08-thick-outline | PASS | 1 | 0 | 0.0057 | double_contour_suspected |
| drawing-09-low-contrast | PASS | 1 | 1 | 0.0056 |  |
| drawing-10-noise | PASS | 1 | 1 | 0.0057 |  |
