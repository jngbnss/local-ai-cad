# Local AI CAD — 다음 작업

현재 상태: **Phase 1~6 및 Track D 구현 완료**. Track D의 합성 회귀·브라우저 경로는 통과했고 실제 사용자 도면 10개 검증만 입력 대기다. Phase 7 패키징과 복합 가구 정확도 개선 트랙 Q가 뒤따른다.

## 0. Track D — 2D 도면 이미지에서 3D CAD 생성

상세 계약과 완료 기준은 [`docs/track-d-2d-drawing-import-design.md`](docs/track-d-2d-drawing-import-design.md)를 따른다.

- [ ] D0 실제 사용자 도면 10개 검증 — 입력 부재. 합성 10개 독립 CLI 검증은 완료.
- [x] D1: `ConfirmedProfile`, `DesignSpec 2.0`, migration, `sketch_extrusion` 계약을 구현했다.
- [x] D2: 이미지 검증·분석 영역·외곽선·구멍 검출과 합성 30개 회귀셋을 구현했다.
- [x] D3: 동기 analyze/generate API와 24시간 임시 analysis 정리를 구현했다.
- [x] D4: SVG 보정·프로파일 수정·undo/redo·3D 생성 UI를 구현했다.
- [x] D5: 실제 브라우저 E2E와 합성 30개 치수·유효 솔리드 완료 기준을 검증했다.
- [x] D6: p95 1.3911초 측정에 따라 job·SSE·draft 영속성을 추가하지 않기로 판정했다.
- [x] D7: CPU OCR 치수 후보와 사용자 선택·수정·거부 흐름을 구현했다.

일반 제품 사진 복원은 Track D 범위가 아니다. 정면 도면 입력이 안정화된 뒤 별도 Track V로 진행한다.

## 0.1 Track V — 3면도·사진 기반 CAD 리버스 엔지니어링

상세 아키텍처와 오픈소스 판정은 [`docs/track-v-cad-reverse-engineering-design.md`](docs/track-v-cad-reverse-engineering-design.md)를 따른다.

- [ ] V0: 실제 3면도+STEP 10세트와 합성 30세트 평가 계약을 만든다. 기본 직육면체·L형 회귀는 완료.
- [x] V1a: 정면·평면·우측면 고정 슬롯, 제1각/제3각, 공통 X/Y/Z 치수 UI/API를 구현했다.
- [ ] V1b: 뷰별 회전·crop·기준점 축척과 대응 치수 불일치 표시를 구현한다.
- [x] V2a: 세 실루엣 직교 돌출·교집합과 STEP/STL 생성을 구현했다.
- [ ] V2b: 생성 솔리드의 3면 재투영 IoU와 위치별 잔차 표시를 구현한다.
- [ ] V3: 숨은선·중심선·치수 기반 구멍·포켓·단계 피처 후보를 구현한다.
- [ ] V4: MIT Drawing2CAD를 별도 환경에서 평가하고 결정론적 결과보다 나을 때만 선택 기능으로 연결한다.
- [ ] V5: 제품 사진은 20~60장/영상 촬영과 COLMAP 점군 경로로 분리한다.

사진 세 장 또는 생성형 메시만으로 제작 치수와 편집 가능한 CAD를 보장하지 않는다. Hunyuan3D-2는 비상업 라이선스이므로 현재 로컬 연구 모드에서만 사용하며 배포 가능한 제품 런타임에는 포함하지 않는다.

## 0.2 Track P — 로컬 GPU 사진 3D 메시

- [x] P0: 정면·후면·좌측·우측 사진을 로컬 Hunyuan3D-2mv로 처리하고 GLB로 표시·다운로드한다.
- [x] P1: RTX 4050 6GB 실제 CUDA 생성과 동일 입력 콘텐츠 캐시를 검증했다.
- [ ] P2: 실제 제품 사진 세트로 배경 분리·형상 품질·반복 성능을 평가한다.
- [ ] P3: 상용 배포 전 허용 라이선스 모델로 교체하거나 별도 라이선스 승인을 받는다.

## 1. Phase 7 시작 전 공간 확보

- [ ] C: 여유 공간을 현재 24.1GB에서 **최소 35GB, 권장 40GB 이상**으로 확보한다.
- [ ] Docker Desktop의 이미지·빌드 캐시·WSL 가상 디스크 위치를 확인한다.
- [ ] 모델 가중치는 Docker 이미지에 넣지 않고 기존 Hugging Face 캐시를 볼륨으로 연결한다.

예상 추가 사용량은 15~25GB다. 빌드 도중 레이어가 중복되므로 24.1GB 상태에서 바로 시작하지 않는다.

## 2. Phase 7 — Docker/WSL2 GPU 패키징

- [ ] WSL2 배포판과 Docker Desktop의 WSL 통합 상태를 확인한다.
- [ ] 컨테이너에서 NVIDIA GPU가 노출되는지 확인한다.
  - `nvidia-smi`
  - `python -c "import torch; print(torch.cuda.is_available())"`
- [ ] `docker/Dockerfile.backend`를 작성한다.
  - Python 3.11
  - CUDA 호환 PyTorch
  - FastAPI, CadQuery/OCP
  - 모델 캐시는 이미지에서 제외
- [ ] `docker/Dockerfile.frontend`를 작성한다.
  - Vite 프로덕션 빌드
  - 정적 파일 서빙 및 `/api` 프록시
- [ ] `docker-compose.yml`을 작성한다.
  - 백엔드 워커 1개 고정
  - GPU 예약
  - 모델 캐시·설계 DB·CAD 아티팩트 볼륨 분리
  - healthcheck 추가
- [ ] `.dockerignore`를 작성해 `.venv`, `node_modules`, 모델 캐시, 아티팩트를 제외한다.
- [ ] `docker compose up --build` 한 번으로 전체 서비스가 실행되는지 확인한다.
- [ ] 컨테이너에서 실제 GPU 프롬프트 → DesignSpec → STL/STEP 생성 E2E를 실행한다.
- [ ] Windows 호스트 대비 모델 적재 시간·추론 시간·VRAM 사용량을 측정한다.
- [ ] 최종 이미지 크기와 디스크 사용량을 기록한다.
- [ ] `docs/phase-7-design.md`와 완료 보고서를 작성한다.

### Phase 7 완료 조건

- [ ] 컨테이너 안에서 `torch.cuda.is_available() == True`다.
- [ ] `docker compose up`만으로 프론트엔드와 백엔드가 실행된다.
- [ ] 실제 GPU CAD 생성과 STL/STEP 다운로드가 성공한다.
- [ ] 모델 캐시가 이미지에 포함되지 않는다.
- [ ] 호스트/컨테이너 성능 비교와 이미지 크기가 문서에 남는다.

## 3. 트랙 Q — 복합 가구 정확도 개선

현재 실제 모델 평가 결과는 1차 16/20(80%), 교정 재시도 포함 18/20(90%)다. 네 다리 책상 두 문항에서 중복 부품 ID를 교정하지 못했다.

- [ ] 실패한 `desk-01`, `desk-02`를 회귀 평가셋으로 고정한다.
- [ ] JSON 문법 제약 디코딩 라이브러리의 Windows/CUDA 호환성을 조사한다.
- [ ] 프롬프트 개선, 문법 제약, LoRA, 더 큰 양자화 모델을 동일 조건으로 비교한다.
- [ ] 각 후보의 유효율·추론 시간·최대 VRAM·디스크 사용량을 기록한다.
- [ ] 20문항 재시도 포함 성공률 목표를 **100%**로 둔다.
- [ ] 결과가 개선된 경우 `experiments/spec_accuracy_report.md`를 갱신한다.

## 4. 후속 품질 개선

- [x] Three.js Viewer를 동적 import로 분리해 앱 핵심 번들을 약 790KB에서 244KB로 줄였다.
- [ ] API와 프론트엔드에 취소 기능을 추가해 긴 GPU 요청을 중단할 수 있게 한다.
- [ ] 생성 아티팩트와 오래된 설계 이력의 정리 정책을 추가한다.
- [ ] 실제 GPU 서버 10회 연속 설계 생성 장시간 테스트를 자동화한다.

## 참고 자료

- Phase 2~6 완료 근거: `docs/phase-2-6-report.md`
- 실제 모델 정확도: `experiments/spec_accuracy_report.md`
- 전체 로드맵: `docs/roadmap.md`
- 2D 도면 입력 설계: `docs/track-d-2d-drawing-import-design.md`
