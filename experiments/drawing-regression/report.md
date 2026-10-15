# Track D 도면 평가

> 합성 입력은 구현 회귀용이며 실제 사용자 도면 완료 조건을 대체하지 않는다.

| 지표 | 값 |
|---|---:|
| 케이스 통과 | 30/30 |
| outer 성공률 | 100.00% |
| hole 재현율 | 100.00% |
| hole 오검출률 | 0.00% |
| 분석 p95 | 0.0105s |

| ID | 결과 | outer 후보 | holes | 분석 초 | 경고/오류 |
|---|---:|---:|---:|---:|---|
| drawing-01-rectangle-01 | PASS | 1 | 0/0 | 0.0242 |  |
| drawing-02-l-shape-02 | PASS | 1 | 0/0 | 0.0075 |  |
| drawing-03-u-shape-03 | PASS | 1 | 0/0 | 0.0068 |  |
| drawing-04-one-hole-04 | PASS | 1 | 1/1 | 0.0090 |  |
| drawing-05-four-holes-05 | PASS | 1 | 4/4 | 0.0078 |  |
| drawing-06-polygon-hole-06 | PASS | 1 | 1/1 | 0.0092 |  |
| drawing-07-inverted-07 | PASS | 1 | 1/1 | 0.0094 |  |
| drawing-08-thick-outline-08 | PASS | 1 | 0/0 | 0.0082 | double_contour_suspected |
| drawing-09-low-contrast-09 | PASS | 1 | 1/1 | 0.0084 |  |
| drawing-10-noise-10 | PASS | 1 | 1/1 | 0.0080 |  |
| drawing-11-rectangle-11 | PASS | 1 | 0/0 | 0.0090 |  |
| drawing-12-l-shape-12 | PASS | 1 | 0/0 | 0.0080 |  |
| drawing-13-u-shape-13 | PASS | 1 | 0/0 | 0.0099 |  |
| drawing-14-one-hole-14 | PASS | 1 | 1/1 | 0.0101 |  |
| drawing-15-four-holes-15 | PASS | 1 | 4/4 | 0.0076 |  |
| drawing-16-polygon-hole-16 | PASS | 1 | 1/1 | 0.0077 |  |
| drawing-17-inverted-17 | PASS | 1 | 1/1 | 0.0105 |  |
| drawing-18-thick-outline-18 | PASS | 1 | 0/0 | 0.0098 | double_contour_suspected |
| drawing-19-low-contrast-19 | PASS | 1 | 1/1 | 0.0080 |  |
| drawing-20-noise-20 | PASS | 1 | 1/1 | 0.0083 |  |
| drawing-21-rectangle-21 | PASS | 1 | 0/0 | 0.0082 |  |
| drawing-22-l-shape-22 | PASS | 1 | 0/0 | 0.0087 |  |
| drawing-23-u-shape-23 | PASS | 1 | 0/0 | 0.0087 |  |
| drawing-24-one-hole-24 | PASS | 1 | 1/1 | 0.0085 |  |
| drawing-25-four-holes-25 | PASS | 1 | 4/4 | 0.0090 |  |
| drawing-26-polygon-hole-26 | PASS | 1 | 1/1 | 0.0091 |  |
| drawing-27-inverted-27 | PASS | 1 | 1/1 | 0.0088 |  |
| drawing-28-thick-outline-28 | PASS | 1 | 0/0 | 0.0085 | double_contour_suspected |
| drawing-29-low-contrast-29 | PASS | 1 | 1/1 | 0.0091 |  |
| drawing-30-noise-30 | PASS | 1 | 1/1 | 0.0086 |  |
