# Track D HTTP E2E 평가

> 합성 30개 회귀 입력을 실행 중인 FastAPI의 analyze → confirm → CAD → STEP 경로로 검증했다.

| 지표 | 값 |
|---|---:|
| 통과 | 30/30 |
| HTTP E2E p95 | 0.1831s |
| 서버 RSS 시작 | 1287.21 MiB |
| 서버 RSS 최대 | 1292.94 MiB |
| 서버 RSS 증가 | 5.72 MiB |
| 디스크 증가 | 1.51 MiB |

| ID | 결과 | holes | E2E 초 | 최대 축 오차(mm) |
|---|---:|---:|---:|---:|
| drawing-01-rectangle-01 | PASS | 0 | 0.1730 | 0.000000 |
| drawing-02-l-shape-02 | PASS | 0 | 0.0950 | 0.000000 |
| drawing-03-u-shape-03 | PASS | 0 | 0.1327 | 0.000000 |
| drawing-04-one-hole-04 | PASS | 1 | 0.1689 | 0.000000 |
| drawing-05-four-holes-05 | PASS | 4 | 0.1701 | 0.000000 |
| drawing-06-polygon-hole-06 | PASS | 1 | 0.1676 | 0.000000 |
| drawing-07-inverted-07 | PASS | 1 | 0.1199 | 0.000000 |
| drawing-08-thick-outline-08 | PASS | 0 | 0.1149 | 0.000000 |
| drawing-09-low-contrast-09 | PASS | 1 | 0.1831 | 0.000000 |
| drawing-10-noise-10 | PASS | 1 | 0.1406 | 0.000000 |
| drawing-11-rectangle-11 | PASS | 0 | 0.1430 | 0.000000 |
| drawing-12-l-shape-12 | PASS | 0 | 0.1594 | 0.000000 |
| drawing-13-u-shape-13 | PASS | 0 | 0.1353 | 0.000000 |
| drawing-14-one-hole-14 | PASS | 1 | 0.1306 | 0.000000 |
| drawing-15-four-holes-15 | PASS | 4 | 0.1759 | 0.000000 |
| drawing-16-polygon-hole-16 | PASS | 1 | 0.1488 | 0.000000 |
| drawing-17-inverted-17 | PASS | 1 | 0.1186 | 0.000000 |
| drawing-18-thick-outline-18 | PASS | 0 | 0.1088 | 0.000000 |
| drawing-19-low-contrast-19 | PASS | 1 | 0.1404 | 0.000000 |
| drawing-20-noise-20 | PASS | 1 | 0.1268 | 0.000000 |
| drawing-21-rectangle-21 | PASS | 0 | 0.1226 | 0.000000 |
| drawing-22-l-shape-22 | PASS | 0 | 0.1299 | 0.000000 |
| drawing-23-u-shape-23 | PASS | 0 | 0.1486 | 0.000000 |
| drawing-24-one-hole-24 | PASS | 1 | 0.1507 | 0.000000 |
| drawing-25-four-holes-25 | PASS | 4 | 0.1947 | 0.000000 |
| drawing-26-polygon-hole-26 | PASS | 1 | 0.1499 | 0.000000 |
| drawing-27-inverted-27 | PASS | 1 | 0.1460 | 0.000000 |
| drawing-28-thick-outline-28 | PASS | 0 | 0.1069 | 0.000000 |
| drawing-29-low-contrast-29 | PASS | 1 | 0.1444 | 0.000000 |
| drawing-30-noise-30 | PASS | 1 | 0.1412 | 0.000000 |
